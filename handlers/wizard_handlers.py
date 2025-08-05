#!/usr/bin/env python3
"""
Wizard handlers for the Telegram-Jira bot.

Handles interactive wizard functionality for guided setup and operations.
Provides step-by-step guidance for project setup, issue creation, and configuration.
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .base_handler import BaseHandler
from ..models.project import Project, ProjectSummary
from ..models.issue import JiraIssue
from ..models.user import User, UserPreferences, UserSession
from ..models.enums import IssuePriority, IssueType, IssueStatus, WizardState, UserRole, ErrorType
from ..services.database import DatabaseError
from ..services.jira_service import JiraAPIError
from ..utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES
from ..utils.validators import InputValidator, ValidationResult
from ..utils.formatters import MessageFormatter


# Conversation states for ConversationHandler
class ConversationState(Enum):
    """States for conversation handler."""
    # Setup wizard states
    SETUP_WELCOME = 0
    SETUP_SELECT_PROJECT = 1
    SETUP_CONFIRM_PROJECT = 2
    SETUP_PREFERENCES = 3
    SETUP_COMPLETE = 4
    
    # Issue creation wizard states
    ISSUE_SELECT_PROJECT = 10
    ISSUE_SELECT_TYPE = 11
    ISSUE_SELECT_PRIORITY = 12
    ISSUE_ENTER_SUMMARY = 13
    ISSUE_ENTER_DESCRIPTION = 14
    ISSUE_CONFIRM_CREATE = 15
    ISSUE_COMPLETE = 16
    
    # Project wizard states  
    PROJECT_SELECT_ACTION = 20
    PROJECT_ENTER_KEY = 21
    PROJECT_ENTER_NAME = 22
    PROJECT_ENTER_DESCRIPTION = 23
    PROJECT_CONFIRM_CREATE = 24
    PROJECT_COMPLETE = 25
    
    # Edit wizard states
    EDIT_SELECT_ISSUE = 30
    EDIT_SELECT_FIELD = 31
    EDIT_ENTER_VALUE = 32
    EDIT_CONFIRM_CHANGE = 33
    EDIT_COMPLETE = 34


class WizardHandlers(BaseHandler):
    """Handles interactive wizard functionality."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = MessageFormatter(
            compact_mode=self.config.compact_messages,
            use_emoji=True
        )
        self.validator = InputValidator()

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "WizardHandlers"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to wizard operations."""
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        elif isinstance(error, ValueError):
            await self.send_error_message(
                update, 
                f"Invalid input: {str(error)}", 
                ErrorType.VALIDATION_ERROR
            )
        else:
            await self.send_error_message(
                update,
                f"Wizard error: {str(error)}",
                ErrorType.UNKNOWN_ERROR
            )

    # =============================================================================
    # COMMAND HANDLERS
    # =============================================================================

    async def wizard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /wizard command - start setup wizard.
        
        Returns:
            Conversation state
        """
        self.log_handler_start(update, "wizard_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        try:
            await self._show_setup_wizard_welcome(update, context, user)
            self.log_handler_end(update, "wizard_command")
            return ConversationState.SETUP_WELCOME.value

        except Exception as e:
            await self.handle_error(update, e, "wizard_command")
            self.log_handler_end(update, "wizard_command", success=False)
            return ConversationHandler.END

    async def quick_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /quick command - quick issue creation wizard.
        
        Returns:
            Conversation state
        """
        self.log_handler_start(update, "quick_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        try:
            await self._start_quick_issue_wizard(update, context, user)
            self.log_handler_end(update, "quick_command")
            return ConversationState.ISSUE_SELECT_PROJECT.value

        except Exception as e:
            await self.handle_error(update, e, "quick_command")
            self.log_handler_end(update, "quick_command", success=False)
            return ConversationHandler.END

    async def cancel_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle wizard cancellation.
        
        Returns:
            ConversationHandler.END
        """
        await self.send_message(
            update,
            f"{EMOJI.get('CANCEL', '❌')} Wizard cancelled.",
            reply_markup=None
        )
        
        # Clear any stored wizard data
        if 'wizard_data' in context.user_data:
            del context.user_data['wizard_data']
        
        return ConversationHandler.END

    # =============================================================================
    # SETUP WIZARD HANDLERS
    # =============================================================================

    async def _show_setup_wizard_welcome(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        user: User
    ) -> None:
        """Show setup wizard welcome screen."""
        welcome_message = f"""
{EMOJI.get('WIZARD', '🧙‍♂️')} **Welcome to the Setup Wizard!**

I'll help you get started with the Telegram-Jira Bot. This wizard will guide you through:

{EMOJI.get('ONE', '1️⃣')} Selecting your default project
{EMOJI.get('TWO', '2️⃣')} Setting up your preferences  
{EMOJI.get('THREE', '3️⃣')} Learning basic commands

Let's begin! What would you like to do?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quick Setup", callback_data="setup_quick")],
            [InlineKeyboardButton("⚙️ Full Setup", callback_data="setup_full")],
            [InlineKeyboardButton("📋 Just Show Projects", callback_data="setup_projects_only")],
            [InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")]
        ])

        await self.send_message(update, welcome_message, reply_markup=keyboard)

    async def handle_setup_welcome_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle setup welcome callback queries."""
        query = update.callback_query
        await query.answer()

        if query.data == "setup_quick":
            return await self._start_quick_setup(update, context)
        elif query.data == "setup_full":
            return await self._start_full_setup(update, context)
        elif query.data == "setup_projects_only":
            return await self._show_projects_only(update, context)
        elif query.data == "setup_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END
        
        return ConversationState.SETUP_WELCOME.value

    async def _start_quick_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start quick setup process."""
        try:
            projects = await self.db.get_all_active_projects()
            
            if not projects:
                message = f"""
{EMOJI.get('WARNING', '⚠️')} **No Projects Available**

There are no projects set up yet. Please contact an administrator to add projects before continuing with setup.

You can still use the bot, but you'll need to specify project keys manually when creating issues.
                """
                await self.edit_message(update, message)
                return ConversationHandler.END

            # Store projects in context for later use
            context.user_data['wizard_data'] = {
                'projects': projects,
                'setup_type': 'quick'
            }

            return await self._show_project_selection(update, context, projects)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "quick_setup")
            return ConversationHandler.END

    async def _start_full_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start full setup process."""
        # Similar to quick setup but with more steps
        context.user_data['wizard_data'] = {'setup_type': 'full'}
        return await self._start_quick_setup(update, context)

    async def _show_projects_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show projects list only."""
        try:
            projects = await self.db.get_all_active_projects()
            
            if not projects:
                message = INFO_MESSAGES['NO_PROJECTS']
            else:
                message = self.formatter.format_project_list(projects, "Available Projects")
            
            await self.edit_message(update, message)
            return ConversationHandler.END

        except DatabaseError as e:
            await self.handle_database_error(update, e, "show_projects")
            return ConversationHandler.END

    async def _show_project_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        projects: List[Project]
    ) -> int:
        """Show project selection screen."""
        message = f"""
{EMOJI.get('PROJECTS', '📋')} **Select Your Default Project**

Choose a project that you'll work with most often. This will be used as the default when creating issues.

Available Projects:
        """

        # Create inline keyboard with projects
        keyboard_buttons = []
        for i, project in enumerate(projects[:10]):  # Limit to 10 projects
            button_text = f"{project.key}: {project.name[:30]}"
            if len(project.name) > 30:
                button_text += "..."
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    button_text, 
                    callback_data=f"setup_project_{project.key}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.edit_message(update, message, reply_markup=keyboard)
        
        return ConversationState.SETUP_SELECT_PROJECT.value

    async def handle_project_selection_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle project selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "setup_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END

        if query.data.startswith("setup_project_"):
            project_key = query.data.replace("setup_project_", "")
            
            # Find the selected project
            wizard_data = context.user_data.get('wizard_data', {})
            projects = wizard_data.get('projects', [])
            selected_project = next((p for p in projects if p.key == project_key), None)
            
            if not selected_project:
                await self.send_error_message(update, "Project not found")
                return ConversationHandler.END
            
            # Store selected project
            wizard_data['selected_project'] = selected_project
            
            return await self._confirm_project_selection(update, context, selected_project)
        
        return ConversationState.SETUP_SELECT_PROJECT.value

    async def _confirm_project_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        project: Project
    ) -> int:
        """Confirm project selection."""
        message = f"""
{EMOJI.get('CHECK', '✅')} **Confirm Project Selection**

You've selected: **{project.key}: {project.name}**

{project.description[:200]}{'...' if len(project.description) > 200 else ''}

This project will be set as your default. You can change this later using the /setdefault command.

Is this correct?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Set as Default", callback_data="setup_confirm_yes")],
            [InlineKeyboardButton("🔙 Choose Different", callback_data="setup_confirm_back")],
            [InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")]
        ])

        await self.edit_message(update, message, reply_markup=keyboard)
        return ConversationState.SETUP_CONFIRM_PROJECT.value

    async def handle_project_confirmation_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle project confirmation callback."""
        query = update.callback_query
        await query.answer()

        wizard_data = context.user_data.get('wizard_data', {})

        if query.data == "setup_confirm_yes":
            # Set the default project
            selected_project = wizard_data.get('selected_project')
            if selected_project:
                try:
                    user = await self.get_or_create_user(update)
                    if user:
                        await self.db.set_user_default_project(user.user_id, selected_project.key)
                        
                        # Check if this is quick or full setup
                        if wizard_data.get('setup_type') == 'quick':
                            return await self._complete_quick_setup(update, context, selected_project)
                        else:
                            return await self._continue_full_setup(update, context)
                    
                except DatabaseError as e:
                    await self.handle_database_error(update, e, "confirm_project")
                    return ConversationHandler.END
            
        elif query.data == "setup_confirm_back":
            # Go back to project selection
            projects = wizard_data.get('projects', [])
            return await self._show_project_selection(update, context, projects)
            
        elif query.data == "setup_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END

        return ConversationHandler.END

    async def _complete_quick_setup(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        project: Project
    ) -> int:
        """Complete quick setup."""
        message = f"""
{EMOJI.get('SUCCESS', '✅')} **Setup Complete!**

Great! Your default project is now set to **{project.key}: {project.name}**.

**Quick Commands to Get Started:**

{EMOJI.get('CREATE', '📝')} **/create** - Create a new issue
{EMOJI.get('MYISSUES', '📋')} **/myissues** - View your issues
{EMOJI.get('PROJECTS', '📋')} **/projects** - List all projects
{EMOJI.get('HELP', '❓')} **/help** - Show all commands

**Quick Issue Creation:**
You can also create issues by simply sending a message like:
`HIGH BUG Login button not working`

Try creating your first issue now!
        """

        # Clear wizard data
        if 'wizard_data' in context.user_data:
            del context.user_data['wizard_data']

        await self.edit_message(update, message)
        return ConversationHandler.END

    async def _continue_full_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Continue with full setup (preferences, etc.)."""
        # This would continue with preference setup, notifications, etc.
        # For now, we'll complete the setup
        return await self._complete_quick_setup(update, context, 
                                               context.user_data['wizard_data']['selected_project'])

    # =============================================================================
    # ISSUE CREATION WIZARD HANDLERS
    # =============================================================================

    async def _start_quick_issue_wizard(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        user: User
    ) -> None:
        """Start quick issue creation wizard."""
        try:
            projects = await self.db.get_all_active_projects()
            
            if not projects:
                await self.send_message(update, INFO_MESSAGES['NO_PROJECTS'])
                return

            # Check if user has a default project
            default_project_key = await self.db.get_user_default_project(user.user_id)
            
            if default_project_key:
                # Skip project selection, go directly to issue type
                default_project = next((p for p in projects if p.key == default_project_key), None)
                if default_project:
                    context.user_data['issue_wizard'] = {'project': default_project}
                    await self._show_issue_type_selection(update, context)
                    return

            # Show project selection
            context.user_data['issue_wizard'] = {'projects': projects}
            await self._show_issue_project_selection(update, context, projects)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "quick_issue_wizard")

    async def _show_issue_project_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        projects: List[Project]
    ) -> None:
        """Show project selection for issue creation."""
        message = f"""
{EMOJI.get('CREATE', '📝')} **Create New Issue**

First, select the project for your issue:
        """

        keyboard_buttons = []
        for project in projects[:10]:
            button_text = f"{project.key}: {project.name[:25]}"
            if len(project.name) > 25:
                button_text += "..."
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"issue_project_{project.key}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.send_message(update, message, reply_markup=keyboard)

    async def handle_issue_project_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle issue project selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END

        if query.data.startswith("issue_project_"):
            project_key = query.data.replace("issue_project_", "")
            
            # Find the project
            wizard_data = context.user_data.get('issue_wizard', {})
            projects = wizard_data.get('projects', [])
            selected_project = next((p for p in projects if p.key == project_key), None)
            
            if selected_project:
                wizard_data['project'] = selected_project
                await self._show_issue_type_selection(update, context)
                return ConversationState.ISSUE_SELECT_TYPE.value

        return ConversationState.ISSUE_SELECT_PROJECT.value

    async def _show_issue_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue type selection."""
        message = f"""
{EMOJI.get('TYPE', '📄')} **Select Issue Type**

What type of issue are you creating?
        """

        keyboard_buttons = []
        for issue_type in IssueType:
            emoji = issue_type.get_emoji()
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {issue_type.value}",
                    callback_data=f"issue_type_{issue_type.value}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.edit_message(update, message, reply_markup=keyboard)

    async def handle_issue_type_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle issue type selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END

        if query.data.startswith("issue_type_"):
            type_value = query.data.replace("issue_type_", "")
            
            try:
                issue_type = IssueType.from_string(type_value)
                wizard_data = context.user_data.get('issue_wizard', {})
                wizard_data['issue_type'] = issue_type
                
                await self._show_issue_priority_selection(update, context)
                return ConversationState.ISSUE_SELECT_PRIORITY.value
                
            except ValueError:
                await self.send_error_message(update, "Invalid issue type selected")

        return ConversationState.ISSUE_SELECT_TYPE.value

    async def _show_issue_priority_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue priority selection."""
        message = f"""
{EMOJI.get('PRIORITY', '🎯')} **Select Priority**

How urgent is this issue?
        """

        keyboard_buttons = []
        for priority in IssuePriority:
            emoji = priority.get_emoji()
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {priority.value}",
                    callback_data=f"issue_priority_{priority.value}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.edit_message(update, message, reply_markup=keyboard)

    async def handle_issue_priority_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle issue priority selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END

        if query.data.startswith("issue_priority_"):
            priority_value = query.data.replace("issue_priority_", "")
            
            try:
                priority = IssuePriority.from_string(priority_value)
                wizard_data = context.user_data.get('issue_wizard', {})
                wizard_data['priority'] = priority
                
                await self._request_issue_summary(update, context)
                return ConversationState.ISSUE_ENTER_SUMMARY.value
                
            except ValueError:
                await self.send_error_message(update, "Invalid priority selected")

        return ConversationState.ISSUE_SELECT_PRIORITY.value

    async def _request_issue_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Request issue summary from user."""
        message = f"""
{EMOJI.get('EDIT', '✏️')} **Enter Issue Summary**

Please provide a brief, descriptive summary of the issue:

Examples:
• "Login button not responding on mobile"
• "User registration emails not being sent"
• "Dashboard loading slowly"

Type your summary below:
        """

        await self.edit_message(update, message)

    async def handle_issue_summary_input(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle issue summary input."""
        if not update.message or not update.message.text:
            await self.send_error_message(update, "Please provide a text summary")
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        summary = update.message.text.strip()
        
        # Validate summary
        validation_result = self.validator.validate_issue_summary(summary)
        if not validation_result.is_valid:
            await self.handle_validation_error(update, validation_result, "summary validation")
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        # Store summary
        wizard_data = context.user_data.get('issue_wizard', {})
        wizard_data['summary'] = summary

        await self._request_issue_description(update, context)
        return ConversationState.ISSUE_ENTER_DESCRIPTION.value

    async def _request_issue_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Request issue description from user."""
        message = f"""
{EMOJI.get('DESCRIPTION', '📝')} **Enter Issue Description**

Provide a detailed description of the issue. Include:
• Steps to reproduce
• Expected behavior
• Actual behavior
• Any relevant context

You can also send "skip" to create the issue without a detailed description.

Type your description below:
        """

        await self.send_message(update, message)

    async def handle_issue_description_input(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle issue description input."""
        if not update.message or not update.message.text:
            await self.send_error_message(update, "Please provide a description or type 'skip'")
            return ConversationState.ISSUE_ENTER_DESCRIPTION.value

        description = update.message.text.strip()
        
        # Allow skipping description
        if description.lower() == "skip":
            description = ""

        # Store description
        wizard_data = context.user_data.get('issue_wizard', {})
        wizard_data['description'] = description

        await self._show_issue_confirmation(update, context)
        return ConversationState.ISSUE_CONFIRM_CREATE.value

    async def _show_issue_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue creation confirmation."""
        wizard_data = context.user_data.get('issue_wizard', {})
        
        project = wizard_data.get('project')
        issue_type = wizard_data.get('issue_type')
        priority = wizard_data.get('priority')
        summary = wizard_data.get('summary')
        description = wizard_data.get('description', '')

        message = f"""
{EMOJI.get('CONFIRM', '✅')} **Confirm Issue Creation**

**Project:** {project.key}: {project.name}
**Type:** {issue_type.get_emoji()} {issue_type.value}
**Priority:** {priority.get_emoji()} {priority.value}
**Summary:** {summary}

**Description:**
{description[:300]}{'...' if len(description) > 300 else ''}

Ready to create this issue?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Create Issue", callback_data="issue_create_confirm")],
            [InlineKeyboardButton("✏️ Edit Summary", callback_data="issue_edit_summary")],
            [InlineKeyboardButton("📝 Edit Description", callback_data="issue_edit_description")],
            [InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")]
        ])

        await self.send_message(update, message, reply_markup=keyboard)

    async def handle_issue_confirmation_callback(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle issue confirmation callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_create_confirm":
            return await self._create_issue_from_wizard(update, context)
        elif query.data == "issue_edit_summary":
            await self._request_issue_summary(update, context)
            return ConversationState.ISSUE_ENTER_SUMMARY.value
        elif query.data == "issue_edit_description":
            await self._request_issue_description(update, context)
            return ConversationState.ISSUE_ENTER_DESCRIPTION.value
        elif query.data == "issue_cancel":
            await self.cancel_wizard(update, context)
            return ConversationHandler.END

        return ConversationState.ISSUE_CONFIRM_CREATE.value

    async def _create_issue_from_wizard(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Create the issue from wizard data."""
        wizard_data = context.user_data.get('issue_wizard', {})
        
        try:
            # Create issue via Jira service
            issue = await self.jira.create_issue(
                project_key=wizard_data['project'].key,
                summary=wizard_data['summary'],
                description=wizard_data['description'],
                priority=wizard_data['priority'],
                issue_type=wizard_data['issue_type']
            )

            # Store in database
            user = await self.get_or_create_user(update)
            if user and update.message:
                await self.db.create_issue(
                    telegram_user_id=user.user_id,
                    telegram_message_id=update.message.message_id,
                    jira_key=issue.key,
                    project_key=wizard_data['project'].key,
                    summary=issue.summary,
                    description=issue.description,
                    priority=issue.priority.value,
                    issue_type=issue.issue_type.value,
                    url=issue.url
                )

            # Send success message
            success_message = self.formatter.format_success_message(
                "Issue created successfully!",
                f"**{issue.key}**: {issue.summary}\n\n🔗 [View in Jira]({issue.url})"
            )

            await self.edit_message(update, success_message)

            # Clear wizard data
            if 'issue_wizard' in context.user_data:
                del context.user_data['issue_wizard']

            return ConversationHandler.END

        except JiraAPIError as e:
            await self.handle_jira_error(update, e, "create_issue_wizard")
            return ConversationHandler.END
        except DatabaseError as e:
            await self.handle_database_error(update, e, "create_issue_wizard")
            return ConversationHandler.END
        except Exception as e:
            await self.handle_error(update, e, "create_issue_wizard")
            return ConversationHandler.END

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def get_conversation_handler(self) -> ConversationHandler:
        """Get the conversation handler for wizards.
        
        Returns:
            ConversationHandler configured for wizard flows
        """
        return ConversationHandler(
            entry_points=[
                CommandHandler("wizard", self.wizard_command),
                CommandHandler("quick", self.quick_command),
            ],
            states={
                ConversationState.SETUP_WELCOME.value: [
                    CallbackQueryHandler(self.handle_setup_welcome_callback)
                ],
                ConversationState.SETUP_SELECT_PROJECT.value: [
                    CallbackQueryHandler(self.handle_project_selection_callback)
                ],
                ConversationState.SETUP_CONFIRM_PROJECT.value: [
                    CallbackQueryHandler(self.handle_project_confirmation_callback)
                ],
                ConversationState.ISSUE_SELECT_PROJECT.value: [
                    CallbackQueryHandler(self.handle_issue_project_callback)
                ],
                ConversationState.ISSUE_SELECT_TYPE.value: [
                    CallbackQueryHandler(self.handle_issue_type_callback)
                ],
                ConversationState.ISSUE_SELECT_PRIORITY.value: [
                    CallbackQueryHandler(self.handle_issue_priority_callback)
                ],
                ConversationState.ISSUE_ENTER_SUMMARY.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_issue_summary_input)
                ],
                ConversationState.ISSUE_ENTER_DESCRIPTION.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_issue_description_input)
                ],
                ConversationState.ISSUE_CONFIRM_CREATE.value: [
                    CallbackQueryHandler(self.handle_issue_confirmation_callback)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_wizard),
                CallbackQueryHandler(self.cancel_wizard, pattern="^(setup_cancel|issue_cancel)$")
            ],
            per_user=True,
            per_chat=True
        )

    async def cleanup_wizard_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clean up wizard data from context."""
        keys_to_remove = ['wizard_data', 'issue_wizard', 'project_wizard']
        
        for key in keys_to_remove:
            if key in context.user_data:
                del context.user_data[key]