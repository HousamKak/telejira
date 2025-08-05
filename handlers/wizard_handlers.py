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
from models.project import Project, ProjectSummary
from models.issue import JiraIssue
from models.user import User, UserPreferences
from models.enums import IssuePriority, IssueType, IssueStatus, UserRole, ErrorType
from services.database import DatabaseError
from services.jira_service import JiraAPIError
from utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES
from utils.validators import InputValidator, ValidationResult
from utils.formatters import MessageFormatter


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
            compact_mode=self.config.compact_mode,
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
        """Handle /wizard command - start setup wizard."""
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
        """Handle /quick command - quick issue creation wizard."""
        self.log_handler_start(update, "quick_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return ConversationHandler.END

        try:
            await self._show_quick_issue_wizard(update, context, user)
            self.log_handler_end(update, "quick_command")
            return ConversationState.ISSUE_SELECT_PROJECT.value

        except Exception as e:
            await self.handle_error(update, e, "quick_command")
            self.log_handler_end(update, "quick_command", success=False)
            return ConversationHandler.END

    async def cancel_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle wizard cancellation."""
        self.log_handler_start(update, "cancel_wizard")
        
        try:
            # Clean up wizard data
            await self.cleanup_wizard_data(context)
            
            message = f"""
{EMOJI.get('CANCEL', '❌')} **Wizard Cancelled**

No changes were made. You can start again anytime:
• `/wizard` - Setup wizard
• `/quick` - Quick issue creation
• `/help` - Show help
            """
            
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(message)
            else:
                await self.send_message(update, message)
            
            self.log_handler_end(update, "cancel_wizard")
            return ConversationHandler.END

        except Exception as e:
            await self.handle_error(update, e, "cancel_wizard")
            self.log_handler_end(update, "cancel_wizard", success=False)
            return ConversationHandler.END

    # =============================================================================
    # SETUP WIZARD HANDLERS
    # =============================================================================

    async def _show_setup_wizard_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
        """Show setup wizard welcome screen."""
        # Get user's current status
        default_project = await self.db.get_user_default_project(user.user_id)
        projects_count = len(await self.db.get_user_projects(user.user_id))

        message = f"""
{EMOJI.get('WIZARD', '🧙‍♂️')} **Welcome to Setup Wizard**

Hi **{user.username}**! Let me help you get started.

**Current Status:**
• Role: {user.role.value.replace('_', ' ').title()}
• Default Project: {default_project.key if default_project else 'None'}
• Available Projects: {projects_count}

**What would you like to do?**
        """

        keyboard_buttons = [
            [InlineKeyboardButton("⭐ Set Default Project", callback_data="setup_default_project")],
            [InlineKeyboardButton("⚙️ Configure Preferences", callback_data="setup_preferences")],
            [InlineKeyboardButton("📖 Learn Quick Commands", callback_data="setup_tutorial")]
        ]

        if self.is_admin(user):
            keyboard_buttons.append([
                InlineKeyboardButton("🔧 Admin Setup", callback_data="setup_admin")
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("✅ I'm All Set", callback_data="setup_complete"),
            InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.send_message(update, message, reply_markup=keyboard)

    async def handle_setup_welcome_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle setup welcome callbacks."""
        query = update.callback_query
        await query.answer()

        if query.data == "setup_default_project":
            return await self._show_project_selection(update, context)
        elif query.data == "setup_preferences":
            return await self._show_preferences_setup(update, context)
        elif query.data == "setup_tutorial":
            return await self._show_tutorial(update, context)
        elif query.data == "setup_admin":
            return await self._show_admin_setup(update, context)
        elif query.data == "setup_complete":
            return await self._complete_setup(update, context)
        elif query.data == "setup_cancel":
            return await self.cancel_wizard(update, context)

        return ConversationHandler.END

    async def _show_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show project selection for default project."""
        user = await self.get_or_create_user(update)
        if not user:
            return ConversationHandler.END

        projects = await self.db.get_user_projects(user.user_id)
        
        if not projects:
            message = f"""
{EMOJI.get('ERROR', '❌')} **No Projects Available**

You don't have access to any projects yet. Contact your admin to add projects.

**Available Actions:**
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Setup", callback_data="back_to_setup")],
                [InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")]
            ])
            
            await query.edit_message_text(message, reply_markup=keyboard)
            return ConversationState.SETUP_WELCOME.value

        message = f"""
{EMOJI.get('PROJECT', '📁')} **Choose Default Project**

Select a project for quick issue creation:
        """

        keyboard_buttons = []
        for project in projects:
            status_emoji = "✅" if project.is_active else "❌"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{status_emoji} {project.key}: {project.name}",
                    callback_data=f"select_project_{project.key}"
                )
            ])

        keyboard_buttons.extend([
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_setup")],
            [InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")]
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await update.callback_query.edit_message_text(message, reply_markup=keyboard)
        return ConversationState.SETUP_SELECT_PROJECT.value

    async def handle_project_selection_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle project selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "back_to_setup":
            user = await self.get_or_create_user(update)
            await self._show_setup_wizard_welcome(update, context, user)
            return ConversationState.SETUP_WELCOME.value
        elif query.data == "setup_cancel":
            return await self.cancel_wizard(update, context)
        elif query.data.startswith("select_project_"):
            project_key = query.data.replace("select_project_", "")
            return await self._confirm_project_selection(update, context, project_key)

        return ConversationHandler.END

    async def _confirm_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, project_key: str) -> int:
        """Confirm project selection."""
        project = await self.db.get_project_by_key(project_key)
        if not project:
            await update.callback_query.edit_message_text("❌ Project not found.")
            return ConversationHandler.END

        # Store selected project in context
        context.user_data['selected_project'] = project_key

        message = f"""
{EMOJI.get('CONFIRM', '✅')} **Confirm Default Project**

**Selected Project:**
• **{project.key}**: {project.name}
• Status: {'✅ Active' if project.is_active else '❌ Inactive'}

With this as your default project, you can create issues quickly by typing:
`HIGH BUG Login button not working`

**Confirm this selection?**
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_project")],
            [InlineKeyboardButton("🔙 Choose Different", callback_data="back_to_project_selection")],
            [InlineKeyboardButton("❌ Cancel", callback_data="setup_cancel")]
        ])

        await update.callback_query.edit_message_text(message, reply_markup=keyboard)
        return ConversationState.SETUP_CONFIRM_PROJECT.value

    async def handle_project_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle project confirmation callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "confirm_project":
            return await self._apply_project_selection(update, context)
        elif query.data == "back_to_project_selection":
            return await self._show_project_selection(update, context)
        elif query.data == "setup_cancel":
            return await self.cancel_wizard(update, context)

        return ConversationHandler.END

    async def _apply_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Apply the selected project as default."""
        user = await self.get_or_create_user(update)
        if not user:
            return ConversationHandler.END

        project_key = context.user_data.get('selected_project')
        if not project_key:
            await update.callback_query.edit_message_text("❌ No project selected.")
            return ConversationHandler.END

        try:
            # Set default project
            await self.db.set_user_default_project(user.user_id, project_key)
            
            project = await self.db.get_project_by_key(project_key)
            
            success_message = self.formatter.format_success_message(
                "Default project set successfully!",
                f"**{project.name}** is now your default project.\n\n"
                f"**Quick Issue Creation:**\n"
                f"Just type: `HIGH BUG Your issue description`\n\n"
                f"**Continue setup or finish?**"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Configure Preferences", callback_data="setup_preferences")],
                [InlineKeyboardButton("✅ Finish Setup", callback_data="setup_complete")]
            ])

            await update.callback_query.edit_message_text(success_message, reply_markup=keyboard)
            return ConversationState.SETUP_WELCOME.value

        except Exception as e:
            await update.callback_query.edit_message_text(f"❌ Failed to set default project: {str(e)}")
            return ConversationHandler.END

    # =============================================================================
    # QUICK ISSUE WIZARD HANDLERS
    # =============================================================================

    async def _show_quick_issue_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
        """Show quick issue creation wizard."""
        projects = await self.db.get_user_projects(user.user_id)
        
        if not projects:
            message = f"""
{EMOJI.get('ERROR', '❌')} **No Projects Available**

You need access to projects before creating issues.
Contact your admin to add projects.
            """
            await self.send_message(update, message)
            return

        # Check if user has a default project
        default_project = await self.db.get_user_default_project(user.user_id)
        
        if default_project:
            # Skip project selection, go to issue type
            context.user_data['issue_wizard'] = {'project_key': default_project.key}
            await self._show_issue_type_selection(update, context)
        else:
            # Show project selection
            await self._show_issue_project_selection(update, context, projects)

    async def _show_issue_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, projects: List[Project]) -> None:
        """Show project selection for issue creation."""
        message = f"""
{EMOJI.get('CREATE', '📝')} **Quick Issue Creation**

**Step 1:** Choose a project for your issue:
        """

        keyboard_buttons = []
        for project in projects:
            status_emoji = "✅" if project.is_active else "❌"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{status_emoji} {project.key}: {project.name}",
                    callback_data=f"issue_project_{project.key}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.send_message(update, message, reply_markup=keyboard)

    async def handle_issue_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle issue project selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_cancel":
            return await self.cancel_wizard(update, context)
        elif query.data.startswith("issue_project_"):
            project_key = query.data.replace("issue_project_", "")
            context.user_data['issue_wizard'] = {'project_key': project_key}
            await self._show_issue_type_selection(update, context)
            return ConversationState.ISSUE_SELECT_TYPE.value

        return ConversationHandler.END

    async def _show_issue_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue type selection."""
        message = f"""
{EMOJI.get('CREATE', '📝')} **Quick Issue Creation**

**Step 2:** Choose issue type:
        """

        keyboard_buttons = []
        for issue_type in IssueType:
            emoji = issue_type.get_emoji()
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {issue_type.value}",
                    callback_data=f"issue_type_{issue_type.name}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("🔙 Back", callback_data="back_to_project"),
            InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=keyboard)
        else:
            await self.send_message(update, message, reply_markup=keyboard)

    async def handle_issue_type_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle issue type selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_cancel":
            return await self.cancel_wizard(update, context)
        elif query.data == "back_to_project":
            user = await self.get_or_create_user(update)
            projects = await self.db.get_user_projects(user.user_id)
            await self._show_issue_project_selection(update, context, projects)
            return ConversationState.ISSUE_SELECT_PROJECT.value
        elif query.data.startswith("issue_type_"):
            issue_type_name = query.data.replace("issue_type_", "")
            context.user_data['issue_wizard']['issue_type'] = issue_type_name
            await self._show_issue_priority_selection(update, context)
            return ConversationState.ISSUE_SELECT_PRIORITY.value

        return ConversationHandler.END

    async def _show_issue_priority_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue priority selection."""
        message = f"""
{EMOJI.get('CREATE', '📝')} **Quick Issue Creation**

**Step 3:** Choose priority:
        """

        keyboard_buttons = []
        for priority in IssuePriority:
            emoji = priority.get_emoji()
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {priority.value}",
                    callback_data=f"issue_priority_{priority.name}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("🔙 Back", callback_data="back_to_type"),
            InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await update.callback_query.edit_message_text(message, reply_markup=keyboard)

    async def handle_issue_priority_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle issue priority selection callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "issue_cancel":
            return await self.cancel_wizard(update, context)
        elif query.data == "back_to_type":
            await self._show_issue_type_selection(update, context)
            return ConversationState.ISSUE_SELECT_TYPE.value
        elif query.data.startswith("issue_priority_"):
            priority_name = query.data.replace("issue_priority_", "")
            context.user_data['issue_wizard']['priority'] = priority_name
            await self._show_issue_summary_input(update, context)
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        return ConversationHandler.END

    async def _show_issue_summary_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue summary input prompt."""
        message = f"""
{EMOJI.get('CREATE', '📝')} **Quick Issue Creation**

**Step 4:** Enter a brief summary of your issue:

**Examples:**
• "Login button not working on mobile"
• "Add user profile settings page"
• "Fix database connection timeout"

Type your issue summary below:
        """

        # Remove inline keyboard and show instruction
        await update.callback_query.edit_message_text(message)

    async def handle_issue_summary_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle issue summary input."""
        if not update.message or not update.message.text:
            await self.send_message(update, "❌ Please enter a valid summary.")
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        summary = update.message.text.strip()
        
        if len(summary) < 10:
            await self.send_message(update, "❌ Summary must be at least 10 characters long.")
            return ConversationState.ISSUE_ENTER_SUMMARY.value

        context.user_data['issue_wizard']['summary'] = summary
        await self._show_issue_description_input(update, context)
        return ConversationState.ISSUE_ENTER_DESCRIPTION.value

    async def _show_issue_description_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue description input prompt."""
        message = f"""
{EMOJI.get('CREATE', '📝')} **Quick Issue Creation**

**Step 5:** Add a detailed description (optional):

Provide more context about the issue, steps to reproduce, expected behavior, etc.

**Type your description below, or send "skip" to continue without a description:**
        """

        await self.send_message(update, message)

    async def handle_issue_description_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle issue description input."""
        if not update.message or not update.message.text:
            await self.send_message(update, "❌ Please enter a description or 'skip'.")
            return ConversationState.ISSUE_ENTER_DESCRIPTION.value

        description = update.message.text.strip()
        
        if description.lower() == 'skip':
            context.user_data['issue_wizard']['description'] = ""
        else:
            context.user_data['issue_wizard']['description'] = description

        await self._show_issue_confirmation(update, context)
        return ConversationState.ISSUE_CONFIRM_CREATE.value

    async def _show_issue_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show issue creation confirmation."""
        wizard_data = context.user_data.get('issue_wizard', {})
        
        project_key = wizard_data.get('project_key')
        issue_type = IssueType[wizard_data.get('issue_type')]
        priority = IssuePriority[wizard_data.get('priority')]
        summary = wizard_data.get('summary')
        description = wizard_data.get('description', '')

        project = await self.db.get_project_by_key(project_key)

        message = f"""
{EMOJI.get('CONFIRM', '✅')} **Confirm Issue Creation**

**Project:** {project.key}: {project.name}
**Type:** {issue_type.get_emoji()} {issue_type.value}
**Priority:** {priority.get_emoji()} {priority.value}
**Summary:** {summary}
**Description:** {description[:100] + '...' if len(description) > 100 else description or 'None'}

**Create this issue?**
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Create Issue", callback_data="confirm_create_issue")],
            [InlineKeyboardButton("✏️ Edit Details", callback_data="edit_issue_details")],
            [InlineKeyboardButton("❌ Cancel", callback_data="issue_cancel")]
        ])

        await self.send_message(update, message, reply_markup=keyboard)

    async def handle_issue_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle issue confirmation callback."""
        query = update.callback_query
        await query.answer()

        if query.data == "confirm_create_issue":
            return await self._create_issue_from_wizard(update, context)
        elif query.data == "edit_issue_details":
            await self._show_issue_type_selection(update, context)
            return ConversationState.ISSUE_SELECT_TYPE.value
        elif query.data == "issue_cancel":
            return await self.cancel_wizard(update, context)

        return ConversationHandler.END

    async def _create_issue_from_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Create issue from wizard data."""
        wizard_data = context.user_data.get('issue_wizard', {})
        
        try:
            # Create issue in Jira
            created_issue = await self.jira.create_issue(
                project_key=wizard_data['project_key'],
                summary=wizard_data['summary'],
                description=wizard_data.get('description', 'Created via Telegram bot'),
                issue_type=IssueType[wizard_data['issue_type']].value,
                priority=IssuePriority[wizard_data['priority']].value
            )

            success_message = self.formatter.format_success_message(
                "Issue created successfully!",
                f"**{created_issue.key}**: {created_issue.summary}\n"
                f"🔗 View in Jira: {created_issue.url}\n\n"
                f"You can now:\n"
                f"• View with `/view {created_issue.key}`\n"
                f"• Add comments with `/comment {created_issue.key} <text>`\n"
                f"• Create another issue with `/quick`"
            )

            await update.callback_query.edit_message_text(success_message)
            
            # Clean up wizard data
            await self.cleanup_wizard_data(context)
            
            return ConversationHandler.END

        except JiraAPIError as e:
            await update.callback_query.edit_message_text(f"❌ Failed to create issue: {str(e)}")
            return ConversationHandler.END

    # =============================================================================
    # ADDITIONAL SETUP FUNCTIONS
    # =============================================================================

    async def _show_preferences_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show preferences setup."""
        message = f"""
{EMOJI.get('SETTINGS', '⚙️')} **Configure Preferences**

**Current Settings:**
• Compact Mode: {'✅ Enabled' if self.config.compact_mode else '❌ Disabled'}
• Notifications: ✅ Enabled
• Quick Create: {'✅ Enabled' if self.config.enable_quick_create else '❌ Disabled'}

**Note:** Some settings are managed by your administrator.

**What would you like to do?**
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 View All Settings", callback_data="view_settings")],
            [InlineKeyboardButton("🔙 Back to Setup", callback_data="back_to_setup")],
            [InlineKeyboardButton("✅ Finish Setup", callback_data="setup_complete")]
        ])

        await update.callback_query.edit_message_text(message, reply_markup=keyboard)
        return ConversationState.SETUP_WELCOME.value

    async def _show_tutorial(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show tutorial for quick commands."""
        message = f"""
{EMOJI.get('TUTORIAL', '📖')} **Quick Commands Tutorial**

**🚀 Quick Issue Creation:**
Just type: `[PRIORITY] [TYPE] Description`

**Examples:**
• `HIGH BUG Login button broken`
• `MEDIUM TASK Update user documentation`
• `LOW IMPROVEMENT Add dark mode theme`

**📋 Essential Commands:**
• `/projects` - View available projects
• `/myissues` - Your recent issues
• `/create` - Full issue creation wizard
• `/help` - Complete command list

**⚡ Shortcuts:**
• `/c` = `/create`
• `/mi` = `/myissues`
• `/p` = `/projects`

**Ready to start?**
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Try Quick Create", callback_data="try_quick_create")],
            [InlineKeyboardButton("🔙 Back to Setup", callback_data="back_to_setup")],
            [InlineKeyboardButton("✅ Finish Setup", callback_data="setup_complete")]
        ])

        await update.callback_query.edit_message_text(message, reply_markup=keyboard)
        return ConversationState.SETUP_WELCOME.value

    async def _show_admin_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show admin setup options."""
        message = f"""
{EMOJI.get('ADMIN', '⚙️')} **Admin Setup**

**Quick Admin Tasks:**
• Add projects from Jira
• Configure user permissions
• Review system status

**What would you like to do?**
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Projects", callback_data="admin_add_projects")],
            [InlineKeyboardButton("👥 Manage Users", callback_data="admin_manage_users")],
            [InlineKeyboardButton("📊 View Statistics", callback_data="admin_view_stats")],
            [InlineKeyboardButton("🔙 Back to Setup", callback_data="back_to_setup")],
            [InlineKeyboardButton("✅ Finish Setup", callback_data="setup_complete")]
        ])

        await update.callback_query.edit_message_text(message, reply_markup=keyboard)
        return ConversationState.SETUP_WELCOME.value

    async def _complete_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Complete setup wizard."""
        user = await self.get_or_create_user(update)
        default_project = await self.db.get_user_default_project(user.user_id)
        
        message = f"""
{EMOJI.get('SUCCESS', '🎉')} **Setup Complete!**

Welcome to the Telegram-Jira Bot, **{user.username}**!

**Your Configuration:**
• Default Project: {default_project.key if default_project else 'Not set'}
• Role: {user.role.value.replace('_', ' ').title()}

**🚀 Ready to go! Try these:**
• Type: `HIGH BUG Something is broken`
• Use `/help` to see all commands
• Use `/projects` to manage projects

**Need help?** Use `/help` anytime!
        """

        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await self.send_message(update, message)

        # Clean up wizard data
        await self.cleanup_wizard_data(context)
        
        return ConversationHandler.END

    # =============================================================================
    # CONVERSATION HANDLER SETUP
    # =============================================================================

    def get_conversation_handler(self) -> ConversationHandler:
        """Get the configured ConversationHandler for wizard flows."""
        entry_points = [
            CommandHandler("wizard", self.wizard_command),
            CommandHandler("quick", self.quick_command),
        ]
        
        # Add shortcuts if enabled
        if self.config.enable_shortcuts:
            entry_points.extend([
                CommandHandler("w", self.wizard_command),  # Shortcut for wizard
                CommandHandler("q", self.quick_command),   # Shortcut for quick
            ])
        
        return ConversationHandler(
            entry_points=entry_points,
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
            per_chat=True,
            per_message=False  # Set to False to avoid deprecation warnings
        )

    async def cleanup_wizard_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clean up wizard data from context."""
        keys_to_remove = ['wizard_data', 'issue_wizard', 'project_wizard', 'selected_project']
        
        for key in keys_to_remove:
            if key in context.user_data:
                del context.user_data[key]