#!/usr/bin/env python3
"""
Refactored Wizard handlers for the Telegram-Jira bot.

Handles interactive wizard functionality for guided setup and operations.
Provides step-by-step guidance for project setup, issue creation, and configuration.
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from enum import Enum
from dataclasses import dataclass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .base_handler import BaseHandler
from models.project import Project
from models.user import User
from models.enums import IssuePriority, IssueType, UserRole, ErrorType
from services.database import DatabaseError
from services.jira_service import JiraAPIError
from utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES
from utils.validators import InputValidator, ValidationResult
from utils.formatters import MessageFormatter, truncate_text
from utils.keyboards import (
    cb, parse_cb, build_project_list_keyboard, build_issue_type_keyboard,
    build_issue_priority_keyboard, build_confirm_keyboard, build_back_cancel_keyboard
)
from utils.messages import (
    setup_welcome_message, confirm_project_message, quick_issue_summary_message,
    no_projects_message, issue_created_success_message
)


# Conversation states for ConversationHandler
class ConversationState(Enum):
    """States for conversation handler."""
    # Setup wizard states
    SETUP_WELCOME = 0
    SETUP_SELECT_PROJECT = 1
    SETUP_CONFIRM_PROJECT = 2
    SETUP_COMPLETE = 3
    
    # Issue creation wizard states
    ISSUE_SELECT_PROJECT = 10
    ISSUE_SELECT_TYPE = 11
    ISSUE_SELECT_PRIORITY = 12
    ISSUE_ENTER_SUMMARY = 13
    ISSUE_ENTER_DESCRIPTION = 14
    ISSUE_CONFIRM_CREATE = 15
    ISSUE_COMPLETE = 16


@dataclass
class IssueWizardData:
    """Strongly-typed wizard context for issue creation."""
    project_key: Optional[str] = None
    issue_type: Optional[str] = None  # enum name
    priority: Optional[str] = None    # enum name
    summary: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'project_key': self.project_key,
            'issue_type': self.issue_type,
            'priority': self.priority,
            'summary': self.summary,
            'description': self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IssueWizardData':
        """Create from dictionary."""
        return cls(
            project_key=data.get('project_key'),
            issue_type=data.get('issue_type'),
            priority=data.get('priority'),
            summary=data.get('summary'),
            description=data.get('description', ''),
        )


def wizard_try(context_label: str):
    """Decorator for wizard error handling."""
    def decorator(func):
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                return await func(self, update, context)
            except DatabaseError as e:
                await self.handle_error(update, e, f"{context_label} - Database error")
                return ConversationHandler.END
            except JiraAPIError as e:
                await self.handle_error(update, e, f"{context_label} - Jira API error")
                return ConversationHandler.END
            except ValueError as e:
                await self.handle_error(update, e, f"{context_label} - Validation error")
                return ConversationHandler.END
            except Exception as e:
                await self.handle_error(update, e, f"{context_label} - Unexpected error")
                return ConversationHandler.END
        return wrapper
    return decorator


def get_issue_ctx(context: ContextTypes.DEFAULT_TYPE) -> IssueWizardData:
    """Get issue wizard context data."""
    if context.user_data is None:
        context.user_data = {}
    
    data = context.user_data.get('issue_wizard', {})
    return IssueWizardData.from_dict(data)


def set_issue_ctx(context: ContextTypes.DEFAULT_TYPE, data: IssueWizardData) -> None:
    """Set issue wizard context data."""
    if context.user_data is None:
        context.user_data = {}
    
    context.user_data['issue_wizard'] = data.to_dict()


def require(ctx: IssueWizardData, *fields) -> None:
    """Guard helper to ensure required fields are present."""
    missing = [f for f in fields if getattr(ctx, f) in (None, "")]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


async def reply_or_edit(update: Update, text: str, reply_markup=None, parse_mode="HTML") -> None:
    """Reply or edit message based on update type."""
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    else:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )


async def answer_cb(query) -> None:
    """Answer callback query to remove loading state."""
    if query:
        await query.answer()


class WizardHandlers(BaseHandler):
    """Handles interactive wizard functionality."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = MessageFormatter(
            compact_mode=self.config.compact_mode,
            use_emoji=True
        )
        self.validator = InputValidator()

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "WizardHandlers"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to wizard operations."""
        error_message = f"❌ <b>Wizard Error</b>\n\n"
        
        if isinstance(error, DatabaseError):
            error_message += "Database operation failed. Please try again later."
        elif isinstance(error, JiraAPIError):
            error_message += "Jira API error. Please check your permissions and try again."
        elif isinstance(error, ValueError):
            error_message += f"Invalid input: {str(error)}"
        else:
            error_message += "An unexpected error occurred. Please try again."
        
        # Add helpful navigation
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Return to Start", callback_data="wizard_restart")],
            [InlineKeyboardButton("❌ Cancel", callback_data="wizard_cancel")]
        ])
        
        await reply_or_edit(update, error_message, reply_markup=keyboard)
        
        # Log the error
        self.logger.error(f"Wizard error in {context}: {error}")

    # =============================================================================
    # COMMAND HANDLERS
    # =============================================================================

    @wizard_try("Wizard Command")
    async def wizard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /wizard command - show main wizard menu."""
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        # Clean up any existing wizard data
        await self.cleanup_wizard_data(context)

        # Get user's default project
        default_project = None
        if user.default_project_key:
            try:
                default_project = await self.db.get_project_by_key(user.default_project_key)
            except Exception:
                pass  # Default project might not exist anymore

        # Show wizard welcome
        welcome_text = setup_welcome_message(user, default_project)
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Quick Issue", callback_data="wizard_quick_issue"),
                InlineKeyboardButton("🔧 Setup", callback_data="wizard_setup")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="wizard_cancel")]
        ])

        await reply_or_edit(update, welcome_text, reply_markup=keyboard)
        return ConversationState.SETUP_WELCOME.value

    @wizard_try("Quick Issue Command")
    async def quick_issue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /quick command - start quick issue creation."""
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        # Initialize wizard context
        wizard_data = IssueWizardData()
        set_issue_ctx(context, wizard_data)

        # If user has a default project, use it
        if user.default_project_key:
            try:
                default_project = await self.db.get_project_by_key(user.default_project_key)
                if default_project:
                    wizard_data.project_key = default_project.key
                    set_issue_ctx(context, wizard_data)
                    return await self._show_issue_type_selection(update, context)
            except Exception:
                pass  # Fall through to project selection

        return await self._show_project_selection(update, context, "issue")

    # =============================================================================
    # CALLBACK HANDLERS
    # =============================================================================

    @wizard_try("Wizard Callback")
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle all wizard callback queries."""
        query = update.callback_query
        await answer_cb(query)
        
        if not query or not query.data:
            return ConversationHandler.END

        scope, action, payload = parse_cb(query.data)

        # Route callbacks
        if scope == "wizard":
            return await self._handle_wizard_callback(update, context, action, payload)
        elif scope == "setup":
            return await self._handle_setup_callback(update, context, action, payload)
        elif scope == "issue":
            return await self._handle_issue_callback(update, context, action, payload)
        elif scope == "nav":
            return await self._handle_navigation_callback(update, context, action, payload)
        else:
            return ConversationHandler.END

    async def _handle_wizard_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                    action: str, payload: str) -> int:
        """Handle wizard-scope callbacks."""
        if action == "quick_issue":
            return await self.quick_issue_command(update, context)
        elif action == "setup":
            return await self._start_setup_wizard(update, context)
        elif action == "restart":
            return await self.wizard_command(update, context)
        elif action == "cancel":
            return await self._cancel_wizard(update, context)
        
        return ConversationHandler.END

    async def _handle_setup_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                   action: str, payload: str) -> int:
        """Handle setup-scope callbacks."""
        if action == "select_project":
            return await self._confirm_project_selection(update, context, payload)
        elif action == "confirm_project":
            return await self._complete_setup(update, context, payload)
        elif action == "cancel":
            return await self._cancel_wizard(update, context)
        
        return ConversationState.SETUP_SELECT_PROJECT.value

    async def _handle_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                   action: str, payload: str) -> int:
        """Handle issue-scope callbacks."""
        wizard_data = get_issue_ctx(context)
        
        if action == "select_project":
            wizard_data.project_key = payload
            set_issue_ctx(context, wizard_data)
            return await self._show_issue_type_selection(update, context)
        elif action == "set_type":
            wizard_data.issue_type = payload
            set_issue_ctx(context, wizard_data)
            return await self._show_issue_priority_selection(update, context)
        elif action == "set_priority":
            wizard_data.priority = payload
            set_issue_ctx(context, wizard_data)
            return await self._request_summary(update, context)
        elif action == "confirm_create":
            return await self._create_issue(update, context)
        elif action == "back_to_project":
            return await self._show_project_selection(update, context, "issue")
        elif action == "back_to_type":
            return await self._show_issue_type_selection(update, context)
        elif action == "back_to_priority":
            return await self._show_issue_priority_selection(update, context)
        elif action == "back_to_summary":
            return await self._request_summary(update, context)
        elif action == "back_to_description":
            return await self._request_description(update, context)
        elif action == "cancel":
            return await self._cancel_wizard(update, context)
        
        return ConversationState.ISSUE_SELECT_PROJECT.value

    async def _handle_navigation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                        action: str, payload: str) -> int:
        """Handle navigation callbacks."""
        if action == "back":
            # Handle back navigation based on payload
            if payload == "setup_welcome":
                return await self.wizard_command(update, context)
            elif payload == "issue_project":
                return await self._show_project_selection(update, context, "issue")
            # Add more back navigation cases as needed
        
        return ConversationHandler.END

    # =============================================================================
    # MESSAGE HANDLERS
    # =============================================================================

    @wizard_try("Summary Input")
    async def handle_summary_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle summary text input."""
        if not update.message or not update.message.text:
            await reply_or_edit(update, "❌ Please provide a valid summary text.")
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        wizard_data = get_issue_ctx(context)
        summary = update.message.text.strip()

        # Validate summary
        validation_result = self.validator.validate_summary(summary)
        if not validation_result.is_valid:
            error_text = f"❌ <b>Invalid Summary</b>\n\n{validation_result.error_message}"
            keyboard = build_back_cancel_keyboard(
                cb("issue", "back_to_priority"),
                cb("issue", "cancel")
            )
            await reply_or_edit(update, error_text, reply_markup=keyboard)
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        wizard_data.summary = summary
        set_issue_ctx(context, wizard_data)

        return await self._request_description(update, context)

    @wizard_try("Description Input")
    async def handle_description_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle description text input."""
        wizard_data = get_issue_ctx(context)
        
        description = ""
        if update.message and update.message.text:
            description = update.message.text.strip()

            # Validate description if provided
            if description:
                validation_result = self.validator.validate_description(description)
                if not validation_result.is_valid:
                    error_text = f"❌ <b>Invalid Description</b>\n\n{validation_result.error_message}"
                    keyboard = build_back_cancel_keyboard(
                        cb("issue", "back_to_summary"),
                        cb("issue", "cancel")
                    )
                    await reply_or_edit(update, error_text, reply_markup=keyboard)
                    return ConversationState.ISSUE_ENTER_DESCRIPTION.value

        wizard_data.description = description
        set_issue_ctx(context, wizard_data)

        return await self._show_confirmation(update, context)

    # =============================================================================
    # SETUP WIZARD FLOW
    # =============================================================================

    @wizard_try("Setup Wizard Start")
    async def _start_setup_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the setup wizard."""
        return await self._show_project_selection(update, context, "setup")

    @wizard_try("Project Selection")
    async def _show_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                    wizard_type: str) -> int:
        """Show project selection screen."""
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        # Get user's accessible projects - FIXED: Use correct method name
        projects = await self.db.list_user_projects(user.user_id)

        if not projects:
            # FIXED: Proper no projects handling
            message = no_projects_message()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Setup", callback_data="nav:back:setup_welcome")],
                [InlineKeyboardButton("❌ Cancel", callback_data="wizard:cancel")]
            ])
            await reply_or_edit(update, message, reply_markup=keyboard)
            return ConversationState.SETUP_WELCOME.value

        # Show project list
        message = f"📁 <b>Select Project</b>\n\nChoose a project for your {wizard_type}:"
        
        cancel_cb = "wizard:cancel" if wizard_type == "setup" else "issue:cancel"
        back_to = "setup" if wizard_type == "setup" else "wizard"
        
        keyboard = build_project_list_keyboard(projects, back_to, cancel_cb)
        
        await reply_or_edit(update, message, reply_markup=keyboard)
        
        return (ConversationState.SETUP_SELECT_PROJECT.value if wizard_type == "setup" 
                else ConversationState.ISSUE_SELECT_PROJECT.value)

    @wizard_try("Project Confirmation")
    async def _confirm_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                       project_key: str) -> int:
        """Confirm project selection."""
        try:
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await reply_or_edit(update, f"❌ Project '{project_key}' not found.")
                return ConversationState.SETUP_SELECT_PROJECT.value

            message = confirm_project_message(project)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm", callback_data=cb("setup", "confirm_project", project_key))],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="nav:back:setup_project"),
                    InlineKeyboardButton("❌ Cancel", callback_data="setup:cancel")
                ]
            ])

            await reply_or_edit(update, message, reply_markup=keyboard)
            return ConversationState.SETUP_CONFIRM_PROJECT.value

        except Exception as e:
            self.logger.error(f"Error confirming project selection: {e}")
            await reply_or_edit(update, "❌ Error retrieving project information.")
            return ConversationState.SETUP_SELECT_PROJECT.value

    @wizard_try("Setup Complete")
    async def _complete_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                            project_key: str) -> int:
        """Complete the setup wizard."""
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        try:
            # Set as default project
            await self.db.set_user_default_project(user.user_id, project_key)
            
            # Log the action
            await self.db.log_user_action(user.user_id, "wizard.setup.complete", {
                "project_key": project_key,
            })

            project = await self.db.get_project_by_key(project_key)
            project_name = project.name if project else project_key

            success_text = f"""
✅ <b>Setup Complete!</b>

<b>{project_name}</b> is now your default project.

🚀 <b>Ready to go! Try these:</b>
• Use <code>/quick</code> for fast issue creation
• Type: <code>HIGH BUG Something is broken</code>
• Use <code>/help</code> to see all commands

<b>Need help?</b> Use <code>/help</code> anytime!
            """.strip()

            await reply_or_edit(update, success_text)
            await self.cleanup_wizard_data(context)
            
            return ConversationHandler.END

        except Exception as e:
            self.logger.error(f"Error completing setup: {e}")
            await reply_or_edit(update, "❌ Failed to complete setup.")
            return ConversationHandler.END

    # =============================================================================
    # ISSUE CREATION WIZARD FLOW
    # =============================================================================

    @wizard_try("Issue Type Selection")
    async def _show_issue_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show issue type selection."""
        wizard_data = get_issue_ctx(context)
        require(wizard_data, 'project_key')

        # Get project details for context
        try:
            project = await self.db.get_project_by_key(wizard_data.project_key)
            project_name = project.name if project else wizard_data.project_key
        except Exception:
            project_name = wizard_data.project_key

        message = f"🎯 <b>Issue Type</b>\n\nProject: <b>{project_name}</b>\n\nSelect the type of issue:"

        # Available issue types
        issue_types = [IssueType.TASK, IssueType.BUG, IssueType.STORY, IssueType.EPIC]
        keyboard = build_issue_type_keyboard(
            issue_types,
            cb("issue", "back_to_project"),
            cb("issue", "cancel")
        )

        await reply_or_edit(update, message, reply_markup=keyboard)
        return ConversationState.ISSUE_SELECT_TYPE.value

    @wizard_try("Priority Selection")
    async def _show_issue_priority_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show issue priority selection."""
        wizard_data = get_issue_ctx(context)
        require(wizard_data, 'project_key', 'issue_type')

        # Get display info
        try:
            project = await self.db.get_project_by_key(wizard_data.project_key)
            project_name = project.name if project else wizard_data.project_key
        except Exception:
            project_name = wizard_data.project_key

        issue_type_display = IssueType[wizard_data.issue_type].value

        message = (f"⚡ <b>Priority</b>\n\n"
                  f"Project: <b>{project_name}</b>\n"
                  f"Type: <b>{issue_type_display}</b>\n\n"
                  f"Select the priority level:")

        # Available priorities
        priorities = [IssuePriority.HIGHEST, IssuePriority.HIGH, IssuePriority.MEDIUM, 
                     IssuePriority.LOW, IssuePriority.LOWEST]
        keyboard = build_issue_priority_keyboard(
            priorities,
            cb("issue", "back_to_type"),
            cb("issue", "cancel")
        )

        await reply_or_edit(update, message, reply_markup=keyboard)
        return ConversationState.ISSUE_SELECT_PRIORITY.value

    @wizard_try("Summary Request")
    async def _request_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Request issue summary."""
        wizard_data = get_issue_ctx(context)
        require(wizard_data, 'project_key', 'issue_type', 'priority')

        # Get display info
        try:
            project = await self.db.get_project_by_key(wizard_data.project_key)
            project_name = project.name if project else wizard_data.project_key
        except Exception:
            project_name = wizard_data.project_key

        issue_type_display = IssueType[wizard_data.issue_type].value
        priority_display = IssuePriority[wizard_data.priority].value

        message = (f"📝 <b>Issue Summary</b>\n\n"
                  f"Project: <b>{project_name}</b>\n"
                  f"Type: <b>{issue_type_display}</b>\n"
                  f"Priority: <b>{priority_display}</b>\n\n"
                  f"Please enter a brief summary for your issue:\n\n"
                  f"<i>Example: \"Login button not working on mobile\"</i>")

        keyboard = build_back_cancel_keyboard(
            cb("issue", "back_to_priority"),
            cb("issue", "cancel")
        )

        await reply_or_edit(update, message, reply_markup=keyboard)
        return ConversationState.ISSUE_ENTER_SUMMARY.value

    @wizard_try("Description Request")
    async def _request_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Request issue description."""
        wizard_data = get_issue_ctx(context)
        require(wizard_data, 'project_key', 'issue_type', 'priority', 'summary')

        message = (f"📄 <b>Issue Description</b>\n\n"
                  f"Summary: <i>{truncate_text(wizard_data.summary, 50)}</i>\n\n"
                  f"Please provide a detailed description for your issue.\n\n"
                  f"You can also send <b>/skip</b> to create the issue without a description.")

        keyboard = build_back_cancel_keyboard(
            cb("issue", "back_to_summary"),
            cb("issue", "cancel")
        )

        await reply_or_edit(update, message, reply_markup=keyboard)
        return ConversationState.ISSUE_ENTER_DESCRIPTION.value

    @wizard_try("Issue Confirmation")
    async def _show_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show issue creation confirmation."""
        wizard_data = get_issue_ctx(context)
        require(wizard_data, 'project_key', 'issue_type', 'priority', 'summary')

        # Get project details
        try:
            project = await self.db.get_project_by_key(wizard_data.project_key)
            project_name = project.name if project else wizard_data.project_key
        except Exception:
            project_name = wizard_data.project_key

        issue_type_display = IssueType[wizard_data.issue_type].value
        priority_display = IssuePriority[wizard_data.priority].value

        message = quick_issue_summary_message(
            project_name, issue_type_display, priority_display, 
            wizard_data.summary, wizard_data.description
        )

        keyboard = build_confirm_keyboard(
            cb("issue", "confirm_create"),
            cb("issue", "back_to_description"),
            cb("issue", "cancel")
        )

        await reply_or_edit(update, message, reply_markup=keyboard)
        return ConversationState.ISSUE_CONFIRM_CREATE.value

    @wizard_try("Issue Creation")
    async def _create_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Create the issue in Jira."""
        wizard_data = get_issue_ctx(context)
        require(wizard_data, 'project_key', 'issue_type', 'priority', 'summary')

        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        try:
            # FIXED: Pass enum instances, not strings
            issue_type = IssueType[wizard_data.issue_type]
            priority = IssuePriority[wizard_data.priority]

            # Create the issue
            created_issue = await self.jira.create_issue(
                project_key=wizard_data.project_key,
                summary=wizard_data.summary,
                description=wizard_data.description or 'Created via Telegram bot',
                issue_type=issue_type,
                priority=priority,
            )

            # Log the action
            await self.db.log_user_action(user.user_id, "wizard.issue.created", {
                "issue_key": created_issue.key,
                "project_key": wizard_data.project_key,
                "issue_type": wizard_data.issue_type,
                "priority": wizard_data.priority,
            })

            success_message = issue_created_success_message(created_issue)
            await reply_or_edit(update, success_message)

            await self.cleanup_wizard_data(context)
            return ConversationHandler.END

        except JiraAPIError as e:
            error_message = f"❌ <b>Failed to create issue</b>\n\n{str(e)}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data=cb("issue", "confirm_create"))],
                [InlineKeyboardButton("❌ Cancel", callback_data=cb("issue", "cancel"))]
            ])
            await reply_or_edit(update, error_message, reply_markup=keyboard)
            return ConversationState.ISSUE_CONFIRM_CREATE.value

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    @wizard_try("Skip Handler")
    async def handle_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /skip command in description state."""
        wizard_data = get_issue_ctx(context)
        wizard_data.description = ""
        set_issue_ctx(context, wizard_data)
        
        return await self._show_confirmation(update, context)

    @wizard_try("Cancel Wizard")
    async def _cancel_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the wizard and clean up."""
        await reply_or_edit(update, "❌ <b>Wizard Cancelled</b>\n\nYou can start again anytime with <code>/wizard</code>.")
        await self.cleanup_wizard_data(context)
        return ConversationHandler.END

    async def cleanup_wizard_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clean up wizard data from context."""
        if context.user_data:
            context.user_data.pop('issue_wizard', None)
            context.user_data.pop('setup_wizard', None)

    # =============================================================================
    # CONVERSATION HANDLER SETUP
    # =============================================================================

    def get_conversation_handler(self) -> ConversationHandler:
        """Get the configured ConversationHandler for wizard flows."""
        return ConversationHandler(
            entry_points=[
                CommandHandler(['wizard', 'w'], self.wizard_command),
                CommandHandler(['quick', 'q'], self.quick_issue_command),
            ],
            states={
                ConversationState.SETUP_WELCOME.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.SETUP_SELECT_PROJECT.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.SETUP_CONFIRM_PROJECT.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.ISSUE_SELECT_PROJECT.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.ISSUE_SELECT_TYPE.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.ISSUE_SELECT_PRIORITY.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.ISSUE_ENTER_SUMMARY.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_summary_input),
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.ISSUE_ENTER_DESCRIPTION.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_description_input),
                    CommandHandler('skip', self.handle_skip),
                    CallbackQueryHandler(self.handle_callback),
                ],
                ConversationState.ISSUE_CONFIRM_CREATE.value: [
                    CallbackQueryHandler(self.handle_callback),
                ],
            },
            fallbacks=[
                CommandHandler('cancel', self._cancel_wizard),
                CallbackQueryHandler(self.handle_callback, pattern=r'^(wizard|setup|issue|nav):.*'),
            ],
            name="wizard_conversation",
            persistent=True,
        )