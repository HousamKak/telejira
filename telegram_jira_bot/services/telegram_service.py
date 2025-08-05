#!/usr/bin/env python3
"""
Telegram service for the Telegram-Jira bot.

Handles Telegram-specific operations and message formatting.
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..models.project import Project
from ..models.issue import JiraIssue
from ..models.user import User, UserPreferences
from ..models.enums import IssuePriority, IssueType, IssueStatus, CommandShortcut
from ..utils.formatters import MessageFormatter
from ..utils.constants import EMOJI, MAX_MESSAGE_LENGTH, MAX_CALLBACK_DATA_LENGTH


class TelegramService:
    """Service for Telegram bot operations and message handling."""

    def __init__(self, use_inline_keyboards: bool = True, compact_mode: bool = False):
        """Initialize Telegram service.
        
        Args:
            use_inline_keyboards: Whether to use inline keyboards
            compact_mode: Whether to use compact message formatting
        """
        self.use_inline_keyboards = use_inline_keyboards
        self.compact_mode = compact_mode
        self.formatter = MessageFormatter(compact_mode)
        self.logger = logging.getLogger(__name__)

    # Message sending utilities
    async def send_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
        parse_mode: ParseMode = ParseMode.MARKDOWN,
        disable_web_page_preview: bool = True,
        reply_to_message: bool = False
    ) -> Optional[int]:
        """Send a message with proper error handling.
        
        Args:
            update: Telegram update object
            text: Message text
            reply_markup: Keyboard markup
            parse_mode: Message parse mode
            disable_web_page_preview: Whether to disable web page preview
            reply_to_message: Whether to reply to the original message
            
        Returns:
            Message ID if sent successfully, None otherwise
        """
        if not update.effective_chat:
            self.logger.error("No effective chat in update")
            return None

        # Truncate message if too long
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 3] + "..."
            self.logger.warning(f"Message truncated to {MAX_MESSAGE_LENGTH} characters")

        try:
            message = await update.effective_chat.send_message(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                reply_to_message_id=update.effective_message.message_id if reply_to_message and update.effective_message else None
            )
            return message.message_id
        except TelegramError as e:
            self.logger.error(f"Failed to send message: {e}")
            # Try sending without markdown if parse error
            if "parse" in str(e).lower():
                try:
                    message = await update.effective_chat.send_message(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=disable_web_page_preview
                    )
                    return message.message_id
                except TelegramError as e2:
                    self.logger.error(f"Failed to send message without parse mode: {e2}")
            return None

    async def edit_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: ParseMode = ParseMode.MARKDOWN
    ) -> bool:
        """Edit a message with proper error handling.
        
        Args:
            update: Telegram update object
            text: New message text
            reply_markup: New keyboard markup
            parse_mode: Message parse mode
            
        Returns:
            True if edited successfully, False otherwise
        """
        if not update.callback_query:
            return False

        # Truncate message if too long
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH - 3] + "..."

        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            return True
        except TelegramError as e:
            self.logger.error(f"Failed to edit message: {e}")
            # Try without markdown if parse error
            if "parse" in str(e).lower():
                try:
                    await update.callback_query.edit_message_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        disable_web_page_preview=True
                    )
                    return True
                except TelegramError as e2:
                    self.logger.error(f"Failed to edit message without parse mode: {e2}")
            return False

    async def send_error_message(
        self,
        update: Update,
        error_text: str,
        include_help: bool = True
    ) -> Optional[int]:
        """Send an error message with consistent formatting.
        
        Args:
            update: Telegram update object
            error_text: Error message text
            include_help: Whether to include help text
            
        Returns:
            Message ID if sent successfully, None otherwise
        """
        message = f"{EMOJI['ERROR']} **Error**\n\n{error_text}"
        
        if include_help:
            message += f"\n\nType /help for assistance or contact an administrator."
        
        return await self.send_message(update, message)

    async def send_success_message(
        self,
        update: Update,
        success_text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send a success message with consistent formatting.
        
        Args:
            update: Telegram update object
            success_text: Success message text
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID if sent successfully, None otherwise
        """
        message = f"{EMOJI['SUCCESS']} {success_text}"
        return await self.send_message(update, message, reply_markup)

    async def send_info_message(
        self,
        update: Update,
        info_text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send an info message with consistent formatting.
        
        Args:
            update: Telegram update object
            info_text: Info message text
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID if sent successfully, None otherwise
        """
        message = f"{EMOJI['INFO']} {info_text}"
        return await self.send_message(update, message, reply_markup)

    async def send_warning_message(
        self,
        update: Update,
        warning_text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send a warning message with consistent formatting.
        
        Args:
            update: Telegram update object
            warning_text: Warning message text
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID if sent successfully, None otherwise
        """
        message = f"{EMOJI['WARNING']} {warning_text}"
        return await self.send_message(update, message, reply_markup)

    # Keyboard creation utilities
    def create_project_selection_keyboard(
        self,
        projects: List[Project],
        callback_prefix: str = "select_project",
        max_per_row: int = 1,
        show_cancel: bool = True
    ) -> InlineKeyboardMarkup:
        """Create an inline keyboard for project selection.
        
        Args:
            projects: List of projects to display
            callback_prefix: Prefix for callback data
            max_per_row: Maximum buttons per row
            show_cancel: Whether to show cancel button
            
        Returns:
            InlineKeyboardMarkup object
        """
        keyboard = []
        row = []
        
        for project in projects:
            button_text = f"{EMOJI['PROJECT']} {project.key} - {project.name}"
            if len(button_text) > 40:  # Telegram button text limit
                button_text = f"{EMOJI['PROJECT']} {project.key} - {project.name[:30]}..."
            
            callback_data = f"{callback_prefix}_{project.key}"
            if len(callback_data) > MAX_CALLBACK_DATA_LENGTH:
                callback_data = callback_data[:MAX_CALLBACK_DATA_LENGTH]
            
            button = InlineKeyboardButton(button_text, callback_data=callback_data)
            row.append(button)
            
            if len(row) >= max_per_row:
                keyboard.append(row)
                row = []
        
        if row:  # Add remaining buttons
            keyboard.append(row)
        
        if show_cancel:
            keyboard.append([InlineKeyboardButton(f"{EMOJI['CANCEL']} Cancel", callback_data="cancel")])
        
        return InlineKeyboardMarkup(keyboard)

    def create_priority_selection_keyboard(
        self,
        callback_prefix: str = "select_priority",
        selected_priority: Optional[IssuePriority] = None
    ) -> InlineKeyboardMarkup:
        """Create an inline keyboard for priority selection.
        
        Args:
            callback_prefix: Prefix for callback data
            selected_priority: Currently selected priority (will be marked)
            
        Returns:
            InlineKeyboardMarkup object
        """
        keyboard = []
        
        for priority in IssuePriority:
            emoji = priority.get_emoji()
            text = f"{emoji} {priority.value}"
            
            if priority == selected_priority:
                text = f"{EMOJI['SELECTED']} {text}"
            
            callback_data = f"{callback_prefix}_{priority.value}"
            button = InlineKeyboardButton(text, callback_data=callback_data)
            keyboard.append([button])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['CANCEL']} Cancel", callback_data="cancel")])
        return InlineKeyboardMarkup(keyboard)

    def create_issue_type_selection_keyboard(
        self,
        callback_prefix: str = "select_type",
        selected_type: Optional[IssueType] = None
    ) -> InlineKeyboardMarkup:
        """Create an inline keyboard for issue type selection.
        
        Args:
            callback_prefix: Prefix for callback data
            selected_type: Currently selected type (will be marked)
            
        Returns:
            InlineKeyboardMarkup object
        """
        keyboard = []
        
        for issue_type in IssueType:
            emoji = issue_type.get_emoji()
            text = f"{emoji} {issue_type.value}"
            
            if issue_type == selected_type:
                text = f"{EMOJI['SELECTED']} {text}"
            
            callback_data = f"{callback_prefix}_{issue_type.value}"
            button = InlineKeyboardButton(text, callback_data=callback_data)
            keyboard.append([button])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJI['CANCEL']} Cancel", callback_data="cancel")])
        return InlineKeyboardMarkup(keyboard)

    def create_pagination_keyboard(
        self,
        current_page: int,
        total_pages: int,
        callback_prefix: str = "page",
        show_numbers: bool = True
    ) -> InlineKeyboardMarkup:
        """Create pagination keyboard.
        
        Args:
            current_page: Current page number (0-based)
            total_pages: Total number of pages
            callback_prefix: Prefix for callback data
            show_numbers: Whether to show page numbers
            
        Returns:
            InlineKeyboardMarkup object
        """
        keyboard = []
        row = []
        
        # Previous page button
        if current_page > 0:
            row.append(InlineKeyboardButton(
                f"{EMOJI['PREVIOUS']} Previous",
                callback_data=f"{callback_prefix}_{current_page - 1}"
            ))
        
        # Page number display
        if show_numbers and total_pages > 1:
            row.append(InlineKeyboardButton(
                f"{current_page + 1}/{total_pages}",
                callback_data="noop"
            ))
        
        # Next page button
        if current_page < total_pages - 1:
            row.append(InlineKeyboardButton(
                f"Next {EMOJI['NEXT']}",
                callback_data=f"{callback_prefix}_{current_page + 1}"
            ))
        
        if row:
            keyboard.append(row)
        
        return InlineKeyboardMarkup(keyboard)

    def create_issue_actions_keyboard(
        self,
        issue: JiraIssue,
        show_comments: bool = True,
        show_edit: bool = True,
        show_assign: bool = True
    ) -> InlineKeyboardMarkup:
        """Create action keyboard for an issue.
        
        Args:
            issue: Issue to create actions for
            show_comments: Whether to show comments button
            show_edit: Whether to show edit button
            show_assign: Whether to show assign button
            
        Returns:
            InlineKeyboardMarkup object
        """
        keyboard = []
        
        # First row - View in Jira
        keyboard.append([
            InlineKeyboardButton(f"{EMOJI['LINK']} View in Jira", url=issue.url)
        ])
        
        # Second row - Actions
        row = []
        if show_comments:
            row.append(InlineKeyboardButton(
                f"{EMOJI['COMMENT']} Comments",
                callback_data=f"comments_{issue.key}"
            ))
        
        if show_edit:
            row.append(InlineKeyboardButton(
                f"{EMOJI['EDIT']} Edit",
                callback_data=f"edit_{issue.key}"
            ))
        
        if row:
            keyboard.append(row)
        
        # Third row - Additional actions
        row = []
        if show_assign:
            row.append(InlineKeyboardButton(
                f"{EMOJI['USER']} Assign",
                callback_data=f"assign_{issue.key}"
            ))
        
        row.append(InlineKeyboardButton(
            f"{EMOJI['REFRESH']} Refresh",
            callback_data=f"refresh_{issue.key}"
        ))
        
        if row:
            keyboard.append(row)
        
        return InlineKeyboardMarkup(keyboard)

    def create_command_shortcuts_keyboard(self) -> ReplyKeyboardMarkup:
        """Create reply keyboard with command shortcuts.
        
        Returns:
            ReplyKeyboardMarkup object
        """
        keyboard = [
            [
                KeyboardButton(f"/{CommandShortcut.PROJECTS.value}"),
                KeyboardButton(f"/{CommandShortcut.CREATE_ISSUE.value}"),
                KeyboardButton(f"/{CommandShortcut.MY_ISSUES.value}")
            ],
            [
                KeyboardButton(f"/{CommandShortcut.STATUS.value}"),
                KeyboardButton(f"/{CommandShortcut.WIZARD.value}"),
                KeyboardButton("/help")
            ]
        ]
        
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
            input_field_placeholder="Choose a command or type a message to create an issue..."
        )

    # Message formatting utilities
    def format_project_list(
        self,
        projects: List[Project],
        user_default: Optional[str] = None,
        show_details: bool = True
    ) -> str:
        """Format a list of projects for display.
        
        Args:
            projects: List of projects to format
            user_default: User's default project key
            show_details: Whether to show project details
            
        Returns:
            Formatted project list text
        """
        if not projects:
            return f"{EMOJI['INFO']} No projects available."
        
        text = f"{EMOJI['PROJECT']} **Available Projects ({len(projects)})**\n\n"
        
        for project in projects:
            default_marker = f" {EMOJI['DEFAULT']}" if project.key == user_default else ""
            status_emoji = EMOJI['ACTIVE'] if project.is_active else EMOJI['INACTIVE']
            
            text += f"{status_emoji} **{project.key}**{default_marker}\n"
            text += f"└ {project.name}\n"
            
            if show_details:
                if project.description:
                    desc = project.description[:100] + "..." if len(project.description) > 100 else project.description
                    text += f"└ _{desc}_\n"
                
                if project.lead:
                    text += f"└ {EMOJI['USER']} Lead: {project.lead}\n"
                
                if project.issue_count > 0:
                    text += f"└ {EMOJI['ISSUE']} Issues: {project.issue_count}\n"
            
            text += "\n"
        
        if user_default:
            text += f"\n{EMOJI['DEFAULT']} Your default: **{user_default}**"
        else:
            text += f"\n{EMOJI['INFO']} No default project set. Use /setdefault to choose one."
        
        return text

    def format_issue_list(
        self,
        issues: List[JiraIssue],
        title: str = "Issues",
        show_project: bool = True,
        show_status: bool = True,
        compact: bool = False
    ) -> str:
        """Format a list of issues for display.
        
        Args:
            issues: List of issues to format
            title: Title for the list
            show_project: Whether to show project information
            show_status: Whether to show issue status
            compact: Whether to use compact formatting
            
        Returns:
            Formatted issue list text
        """
        if not issues:
            return f"{EMOJI['INFO']} No issues found."
        
        text = f"{EMOJI['ISSUE']} **{title} ({len(issues)})**\n\n"
        
        for issue in issues:
            if compact:
                text += self._format_issue_compact(issue, show_project, show_status)
            else:
                text += self._format_issue_detailed(issue, show_project, show_status)
            text += "\n"
        
        return text

    def _format_issue_compact(
        self,
        issue: JiraIssue,
        show_project: bool = True,
        show_status: bool = True
    ) -> str:
        """Format an issue in compact mode."""
        priority_emoji = issue.priority.get_emoji()
        type_emoji = issue.issue_type.get_emoji()
        
        text = f"{priority_emoji}{type_emoji} **{issue.key}**: {issue.summary[:50]}"
        if len(issue.summary) > 50:
            text += "..."
        text += "\n"
        
        details = []
        if show_project:
            details.append(f"Project: {issue.project_key}")
        if show_status and issue.status:
            details.append(f"Status: {issue.status.value}")
        if issue.assignee:
            details.append(f"Assignee: {issue.assignee}")
        
        if details:
            text += f"└ {' • '.join(details)}\n"
        
        return text

    def _format_issue_detailed(
        self,
        issue: JiraIssue,
        show_project: bool = True,
        show_status: bool = True
    ) -> str:
        """Format an issue in detailed mode."""
        priority_emoji = issue.priority.get_emoji()
        type_emoji = issue.issue_type.get_emoji()
        status_emoji = issue.status.get_emoji() if issue.status else ""
        
        text = f"{priority_emoji} {type_emoji} **{issue.key}**: {issue.summary}\n"
        
        if show_project:
            text += f"└ {EMOJI['PROJECT']} Project: {issue.project_key}\n"
        
        if show_status and issue.status:
            text += f"└ {status_emoji} Status: {issue.status.value}\n"
        
        if issue.assignee:
            text += f"└ {EMOJI['USER']} Assignee: {issue.assignee}\n"
        
        if issue.priority != IssuePriority.MEDIUM:  # Only show if not default
            text += f"└ {priority_emoji} Priority: {issue.priority.value}\n"
        
        if issue.labels:
            labels_text = ", ".join(issue.labels[:3])
            if len(issue.labels) > 3:
                labels_text += f" (+{len(issue.labels) - 3} more)"
            text += f"└ {EMOJI['LABEL']} Labels: {labels_text}\n"
        
        if issue.due_date:
            due_text = issue.due_date.strftime('%Y-%m-%d')
            if issue.is_overdue():
                due_text = f"{EMOJI['OVERDUE']} {due_text} (overdue)"
            text += f"└ {EMOJI['CALENDAR']} Due: {due_text}\n"
        
        # Age of issue
        age_days = issue.get_age_days()
        if age_days > 0:
            text += f"└ {EMOJI['CLOCK']} Age: {age_days} days\n"
        
        return text

    def format_user_stats(
        self,
        user: User,
        preferences: Optional[UserPreferences] = None,
        recent_issues_count: int = 0
    ) -> str:
        """Format user statistics for display.
        
        Args:
            user: User object
            preferences: User preferences
            recent_issues_count: Number of recent issues
            
        Returns:
            Formatted user stats text
        """
        text = f"{EMOJI['USER']} **User Profile**\n\n"
        text += f"**Name:** {user.get_display_name()}\n"
        text += f"**ID:** `{user.user_id}`\n"
        text += f"**Role:** {user.role.value.title()}\n"
        
        # Activity stats
        text += f"\n{EMOJI['STATS']} **Activity**\n"
        text += f"└ Issues Created: {user.issues_created}\n"
        text += f"└ Recent Issues: {recent_issues_count}\n"
        
        # Account info
        days_since_joined = (datetime.now(timezone.utc) - user.created_at).days
        days_since_activity = (datetime.now(timezone.utc) - user.last_activity).days
        
        text += f"\n{EMOJI['INFO']} **Account**\n"
        text += f"└ Member Since: {days_since_joined} days ago\n"
        text += f"└ Last Active: {days_since_activity} days ago\n"
        
        if user.timezone:
            text += f"└ Timezone: {user.timezone}\n"
        
        # Preferences
        if preferences:
            text += f"\n{EMOJI['SETTINGS']} **Preferences**\n"
            text += f"└ Default Project: {preferences.default_project_key or 'None'}\n"
            text += f"└ Default Priority: {preferences.default_priority.get_emoji()} {preferences.default_priority.value}\n"
            text += f"└ Default Type: {preferences.default_issue_type.get_emoji()} {preferences.default_issue_type.value}\n"
            text += f"└ Quick Create: {'✅' if preferences.quick_create_mode else '❌'}\n"
        
        return text

    def format_help_text(
        self,
        user_role: str = "user",
        show_shortcuts: bool = True,
        show_examples: bool = True
    ) -> str:
        """Format help text based on user role.
        
        Args:
            user_role: User's role (user, admin, super_admin)
            show_shortcuts: Whether to show command shortcuts
            show_examples: Whether to show examples
            
        Returns:
            Formatted help text
        """
        text = f"{EMOJI['HELP']} **Telegram-Jira Bot Help**\n\n"
        
        # Basic commands
        text += f"{EMOJI['COMMAND']} **Basic Commands**\n"
        text += "• `/start` - Welcome message and setup\n"
        text += "• `/help` - Show this help message\n"
        text += "• `/status` - Bot status and your statistics\n"
        text += "• `/projects` - List available projects\n"
        text += "• `/setdefault <KEY>` - Set your default project\n"
        text += "• `/create` - Interactive issue creation\n"
        text += "• `/myissues` - Your recent issues\n"
        
        # Issue management
        text += f"\n{EMOJI['ISSUE']} **Issue Management**\n"
        text += "• `/listissues` - List all issues with filters\n"
        text += "• `/searchissues <query>` - Search issues by text\n"
        text += "• Send any message - Create issue in default project\n"
        
        # Quick formatting
        if show_examples:
            text += f"\n{EMOJI['MAGIC']} **Quick Create Examples**\n"
            text += "• `Login button not working` - Creates Medium Task\n"
            text += "• `HIGH BUG App crashes on startup` - Creates High Bug\n"
            text += "• `STORY User wants export feature` - Creates Medium Story\n"
        
        # Admin commands
        if user_role in ["admin", "super_admin"]:
            text += f"\n{EMOJI['ADMIN']} **Admin Commands**\n"
            text += "• `/addproject <KEY> <Name> [Description]` - Add new project\n"
            text += "• `/editproject <KEY>` - Edit project details\n"
            text += "• `/deleteproject <KEY>` - Delete project\n"
            text += "• `/users` - List all users and statistics\n"
            text += "• `/syncjira` - Sync data with Jira\n"
        
        # Shortcuts
        if show_shortcuts:
            text += f"\n{EMOJI['SHORTCUT']} **Command Shortcuts**\n"
            text += f"• `/p` → `/projects`\n"
            text += f"• `/c` → `/create`\n"
            text += f"• `/mi` → `/myissues`\n"
            text += f"• `/s` → `/status`\n"
            text += f"• `/w` → `/wizard`\n"
            
            if user_role in ["admin", "super_admin"]:
                text += f"• `/ap` → `/addproject`\n"
                text += f"• `/u` → `/users`\n"
        
        # Tips
        text += f"\n{EMOJI['TIP']} **Tips**\n"
        text += "• Use `/wizard` for step-by-step guidance\n"
        text += "• Set a default project for quick issue creation\n"
        text += "• Use priority and type prefixes for quick formatting\n"
        text += "• All created issues are linked to your Telegram account\n"
        
        return text

    def format_wizard_welcome(self) -> str:
        """Format the wizard welcome message.
        
        Returns:
            Formatted wizard welcome text
        """
        text = f"{EMOJI['WIZARD']} **Setup Wizard**\n\n"
        text += "Welcome to the interactive setup wizard! "
        text += "I'll guide you through configuring the bot step by step.\n\n"
        text += "What would you like to do?\n\n"
        text += f"{EMOJI['PROJECT']} Set up projects\n"
        text += f"{EMOJI['ISSUE']} Create an issue\n"
        text += f"{EMOJI['SETTINGS']} Configure preferences\n"
        text += f"{EMOJI['HELP']} Get help and tips\n"
        
        return text

    # Utility methods
    def extract_command_args(self, message_text: str, command: str) -> List[str]:
        """Extract arguments from a command message.
        
        Args:
            message_text: Full message text
            command: Command name (without /)
            
        Returns:
            List of command arguments
        """
        if not message_text.startswith(f"/{command}"):
            return []
        
        # Remove command and split by spaces
        args_text = message_text[len(f"/{command}"):].strip()
        if not args_text:
            return []
        
        # Simple argument parsing (could be enhanced for quoted args)
        return args_text.split()

    def is_command_shortcut(self, text: str) -> Optional[str]:
        """Check if text is a command shortcut and return the full command.
        
        Args:
            text: Message text to check
            
        Returns:
            Full command name if shortcut found, None otherwise
        """
        if not text.startswith("/"):
            return None
        
        shortcut = text[1:]  # Remove /
        
        for command_shortcut in CommandShortcut:
            if command_shortcut.value == shortcut:
                return command_shortcut.get_full_command()
        
        return None

    def truncate_text(self, text: str, max_length: int = 100, suffix: str = "...") -> str:
        """Truncate text to specified length.
        
        Args:
            text: Text to truncate
            max_length: Maximum length
            suffix: Suffix to add if truncated
            
        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        
        return text[:max_length - len(suffix)] + suffix

    def escape_markdown(self, text: str) -> str:
        """Escape special markdown characters.
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text
        """
        # Characters that need escaping in Telegram markdown
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        
        return text

    def create_confirmation_keyboard(
        self,
        confirm_callback: str,
        cancel_callback: str = "cancel",
        confirm_text: str = "✅ Confirm",
        cancel_text: str = "❌ Cancel"
    ) -> InlineKeyboardMarkup:
        """Create a confirmation keyboard.
        
        Args:
            confirm_callback: Callback data for confirm button
            cancel_callback: Callback data for cancel button
            confirm_text: Text for confirm button
            cancel_text: Text for cancel button
            
        Returns:
            InlineKeyboardMarkup object
        """
        keyboard = [[
            InlineKeyboardButton(confirm_text, callback_data=confirm_callback),
            InlineKeyboardButton(cancel_text, callback_data=cancel_callback)
        ]]
        
        return InlineKeyboardMarkup(keyboard)

    def get_user_mention(self, user: User) -> str:
        """Get a user mention string.
        
        Args:
            user: User to mention
            
        Returns:
            Formatted user mention
        """
        if user.username:
            return f"@{user.username}"
        else:
            return f"[{user.get_display_name()}](tg://user?id={user.user_id})"

    def format_callback_data(self, action: str, *args) -> str:
        """Format callback data with length limits.
        
        Args:
            action: Action name
            *args: Additional arguments
            
        Returns:
            Formatted callback data
        """
        callback_data = "_".join([action] + [str(arg) for arg in args])
        
        if len(callback_data) > MAX_CALLBACK_DATA_LENGTH:
            # Truncate while keeping the action
            available_length = MAX_CALLBACK_DATA_LENGTH - len(action) - 1
            args_text = "_".join([str(arg) for arg in args])
            if len(args_text) > available_length:
                args_text = args_text[:available_length]
            callback_data = f"{action}_{args_text}"
        
        return callback_data