#!/usr/bin/env python3
"""
Telegram service for the Telegram-Jira bot.

Handles Telegram-specific operations, message formatting, and bot interactions.
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..models.project import Project
from ..models.issue import JiraIssue, IssueComment
from ..models.user import User, UserPreferences
from ..models.enums import IssuePriority, IssueType, IssueStatus, CommandShortcut, UserRole
from ..utils.formatters import MessageFormatter
from ..utils.constants import EMOJI, MAX_MESSAGE_LENGTH, MAX_CALLBACK_DATA_LENGTH


class TelegramServiceError(Exception):
    """Custom exception for Telegram service operations."""
    pass


class TelegramService:
    """Service for Telegram bot operations and message handling."""

    def __init__(
        self,
        token: Optional[str] = None,
        timeout: int = 30,
        use_inline_keyboards: bool = True,
        compact_mode: bool = False
    ):
        """Initialize Telegram service.
        
        Args:
            token: Telegram bot token (optional for some operations)
            timeout: Request timeout in seconds
            use_inline_keyboards: Whether to use inline keyboards
            compact_mode: Whether to use compact message formatting
            
        Raises:
            ValueError: If token is empty when provided
        """
        if token is not None and (not isinstance(token, str) or not token.strip()):
            raise ValueError("Token cannot be empty")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("Timeout must be positive")
        
        self.token = token
        self.timeout = timeout
        self.use_inline_keyboards = use_inline_keyboards
        self.compact_mode = compact_mode
        self.formatter = MessageFormatter(compact_mode)
        self.logger = logging.getLogger(__name__)

    # =============================================================================
    # MESSAGE SENDING UTILITIES - FIXED SIGNATURES
    # =============================================================================

    async def send_message(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        chat_id: Optional[int] = None,
        text: str = "",
        reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
        parse_mode: ParseMode = ParseMode.MARKDOWN_V2,
        disable_web_page_preview: bool = True,
        reply_to_message: bool = False,
        message_id: Optional[int] = None
    ) -> Optional[int]:
        """Send a message with proper error handling.
        
        Args:
            update: Telegram update (for extracting chat_id)
            context: Bot context
            chat_id: Direct chat ID (overrides update)
            text: Message text
            reply_markup: Keyboard markup
            parse_mode: Message parse mode
            disable_web_page_preview: Whether to disable web page preview
            reply_to_message: Whether to reply to the original message
            message_id: Specific message ID to reply to
            
        Returns:
            Message ID of sent message or None if failed
            
        Raises:
            TelegramServiceError: If sending fails
        """
        if not text.strip():
            raise ValueError("Message text cannot be empty")

        # Determine chat_id
        effective_chat_id = chat_id
        if not effective_chat_id and update:
            effective_chat_id = update.effective_chat.id if update.effective_chat else None
        
        if not effective_chat_id:
            raise ValueError("No chat_id provided and cannot extract from update")

        # Escape text for MarkdownV2 if needed
        if parse_mode == ParseMode.MARKDOWN_V2:
            text = self._escape_markdown_v2(text)

        # Split long messages
        if len(text) > MAX_MESSAGE_LENGTH:
            return await self._send_long_message(
                effective_chat_id, text, reply_markup, parse_mode, 
                disable_web_page_preview, reply_to_message, message_id, context
            )

        try:
            # Determine reply parameters
            reply_to_message_id = None
            if reply_to_message and update and update.message:
                reply_to_message_id = update.message.message_id
            elif message_id:
                reply_to_message_id = message_id

            # Send message via context if available
            if context:
                message = await context.bot.send_message(
                    chat_id=effective_chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_to_message_id=reply_to_message_id
                )
                return message.message_id
            else:
                # Fallback - would need bot instance
                self.logger.warning("No context provided, cannot send message")
                return None

        except TelegramError as e:
            self.logger.error(f"Failed to send message: {e}")
            
            # Try to send without markup if it was the problem
            if reply_markup and "can't parse" in str(e).lower():
                try:
                    if context:
                        message = await context.bot.send_message(
                            chat_id=effective_chat_id,
                            text="⚠️ Message formatting error. Please check your input.",
                            parse_mode=ParseMode.HTML
                        )
                        return message.message_id
                except TelegramError:
                    pass
            
            raise TelegramServiceError(f"Failed to send message: {e}")

    async def edit_message(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None,
        text: str = "",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: ParseMode = ParseMode.MARKDOWN_V2
    ) -> bool:
        """Edit an existing message.
        
        Args:
            update: Telegram update
            context: Bot context
            chat_id: Chat ID
            message_id: Message ID to edit
            text: New message text
            reply_markup: New reply markup
            parse_mode: Parse mode
            
        Returns:
            True if successful
            
        Raises:
            TelegramServiceError: If editing fails
        """
        if not text.strip():
            raise ValueError("Message text cannot be empty")

        # Determine parameters
        effective_chat_id = chat_id
        effective_message_id = message_id
        
        if not effective_chat_id and update:
            if update.callback_query:
                effective_chat_id = update.callback_query.message.chat.id
                effective_message_id = update.callback_query.message.message_id
            elif update.message:
                effective_chat_id = update.message.chat.id
                effective_message_id = update.message.message_id

        if not effective_chat_id or not effective_message_id:
            raise ValueError("Cannot determine chat_id or message_id")

        # Escape text for MarkdownV2 if needed
        if parse_mode == ParseMode.MARKDOWN_V2:
            text = self._escape_markdown_v2(text)

        try:
            if context:
                await context.bot.edit_message_text(
                    chat_id=effective_chat_id,
                    message_id=effective_message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                return True
            else:
                self.logger.warning("No context provided, cannot edit message")
                return False

        except TelegramError as e:
            self.logger.error(f"Failed to edit message: {e}")
            raise TelegramServiceError(f"Failed to edit message: {e}")

    async def delete_message(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None
    ) -> bool:
        """Delete a message.
        
        Args:
            update: Telegram update
            context: Bot context
            chat_id: Chat ID
            message_id: Message ID to delete
            
        Returns:
            True if successful
        """
        # Determine parameters
        effective_chat_id = chat_id
        effective_message_id = message_id
        
        if not effective_chat_id and update:
            if update.callback_query:
                effective_chat_id = update.callback_query.message.chat.id
                effective_message_id = update.callback_query.message.message_id
            elif update.message:
                effective_chat_id = update.message.chat.id
                effective_message_id = update.message.message_id

        if not effective_chat_id or not effective_message_id:
            self.logger.warning("Cannot determine chat_id or message_id for deletion")
            return False

        try:
            if context:
                await context.bot.delete_message(
                    chat_id=effective_chat_id,
                    message_id=effective_message_id
                )
                return True
            else:
                self.logger.warning("No context provided, cannot delete message")
                return False

        except TelegramError as e:
            self.logger.warning(f"Failed to delete message: {e}")
            return False

    async def _send_long_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]],
        parse_mode: ParseMode,
        disable_web_page_preview: bool,
        reply_to_message: bool,
        message_id: Optional[int],
        context: Optional[ContextTypes.DEFAULT_TYPE]
    ) -> Optional[int]:
        """Send a long message by splitting it into chunks."""
        if not context:
            return None

        chunks = self._split_message(text, MAX_MESSAGE_LENGTH - 100)  # Leave buffer
        last_message_id = None
        
        for i, chunk in enumerate(chunks):
            # Only add markup to the last chunk
            chunk_markup = reply_markup if i == len(chunks) - 1 else None
            
            try:
                message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=parse_mode,
                    reply_markup=chunk_markup,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_to_message_id=message_id if i == 0 else None
                )
                last_message_id = message.message_id
            except TelegramError as e:
                self.logger.error(f"Failed to send message chunk {i+1}/{len(chunks)}: {e}")
                break
        
        return last_message_id

    def _split_message(self, text: str, max_length: int) -> List[str]:
        """Split a long message into chunks."""
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        for line in text.split('\n'):
            if len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk += line + '\n'
            else:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                    current_chunk = line + '\n'
                else:
                    # Line is too long, split it
                    while len(line) > max_length:
                        chunks.append(line[:max_length])
                        line = line[max_length:]
                    current_chunk = line + '\n'
        
        if current_chunk:
            chunks.append(current_chunk.rstrip())
        
        return chunks

    def _escape_markdown_v2(self, text: str) -> str:
        """Escape special characters for MarkdownV2."""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    # =============================================================================
    # MODEL-BASED MESSAGE FORMATTING - NEW FUNCTIONALITY
    # =============================================================================

    def format_project_message(
        self,
        project: Project,
        include_details: bool = True,
        include_stats: bool = False
    ) -> str:
        """Format a project for display.
        
        Args:
            project: Project model instance
            include_details: Whether to include detailed information
            include_stats: Whether to include statistics
            
        Returns:
            Formatted message text
        """
        if self.compact_mode:
            return f"🏗️ **{project.key}**: {project.name}"
        
        emoji = EMOJI.get('PROJECT', '🏗️')
        status_emoji = '✅' if project.is_active else '❌'
        
        message = f"{emoji} **{project.key}: {project.name}**\n"
        message += f"Status: {status_emoji}\n"
        
        if include_details:
            if project.description:
                message += f"📝 {project.description}\n"
            if project.lead:
                message += f"👤 Lead: {project.lead}\n"
            if project.project_type:
                message += f"🔧 Type: {project.project_type.title()}\n"
            if project.category:
                message += f"📂 Category: {project.category}\n"
        
        if include_stats and project.issue_count > 0:
            message += f"📊 Issues: {project.issue_count}\n"
        
        if project.url:
            message += f"🔗 [View in Jira]({project.url})\n"
        
        return message.strip()

    def format_issue_message(
        self,
        issue: JiraIssue,
        include_description: bool = True,
        include_details: bool = True
    ) -> str:
        """Format an issue for display.
        
        Args:
            issue: JiraIssue model instance
            include_description: Whether to include description
            include_details: Whether to include detailed information
            
        Returns:
            Formatted message text
        """
        if self.compact_mode:
            return f"{issue.priority.get_emoji()} **{issue.key}**: {issue.summary}"
        
        # Emojis
        priority_emoji = issue.priority.get_emoji()
        type_emoji = issue.issue_type.get_emoji()
        status_emoji = issue.status.get_emoji()
        
        message = f"{type_emoji} **{issue.key}: {issue.summary}**\n\n"
        
        # Basic info
        message += f"📊 **Status**: {status_emoji} {issue.status.value}\n"
        message += f"🎯 **Priority**: {priority_emoji} {issue.priority.value}\n"
        message += f"🏷️ **Type**: {type_emoji} {issue.issue_type.value}\n"
        message += f"🏗️ **Project**: {issue.project_key}\n"
        
        if include_details:
            if issue.assignee:
                message += f"👤 **Assignee**: {issue.assignee}\n"
            if issue.reporter:
                message += f"📝 **Reporter**: {issue.reporter}\n"
            
            # Dates
            message += f"📅 **Created**: {self._format_datetime(issue.created_at)}\n"
            if issue.updated_at and issue.updated_at != issue.created_at:
                message += f"🔄 **Updated**: {self._format_datetime(issue.updated_at)}\n"
            if issue.due_date:
                message += f"⏰ **Due**: {self._format_datetime(issue.due_date)}\n"
            if issue.resolved_at:
                message += f"✅ **Resolved**: {self._format_datetime(issue.resolved_at)}\n"
            
            # Labels and components
            if hasattr(issue, 'labels') and issue.labels:
                message += f"🏷️ **Labels**: {', '.join(issue.labels)}\n"
            if hasattr(issue, 'components') and issue.components:
                message += f"🔧 **Components**: {', '.join(issue.components)}\n"
        
        # Description
        if include_description and issue.description:
            description = issue.description
            if len(description) > 300:
                description = description[:297] + "..."
            message += f"\n📋 **Description**:\n{description}\n"
        
        return message.strip()

    def format_comment_message(self, comment: IssueComment) -> str:
        """Format a comment for display.
        
        Args:
            comment: IssueComment model instance
            
        Returns:
            Formatted message text
        """
        message = f"💬 **Comment by {comment.author}**\n"
        message += f"📅 {self._format_datetime(comment.created_at)}\n\n"
        
        body = comment.body
        if len(body) > 500:
            body = body[:497] + "..."
        
        message += body
        return message

    def format_user_message(
        self,
        user: User,
        include_stats: bool = False,
        include_preferences: bool = False,
        preferences: Optional[UserPreferences] = None
    ) -> str:
        """Format user information for display.
        
        Args:
            user: User model instance
            include_stats: Whether to include statistics
            include_preferences: Whether to include preferences
            preferences: User preferences (if available)
            
        Returns:
            Formatted message text
        """
        role_emoji = {
            UserRole.USER: '👤',
            UserRole.ADMIN: '🛡️',
            UserRole.SUPER_ADMIN: '👑'
        }.get(user.role, '👤')
        
        status_emoji = '✅' if user.is_active else '❌'
        
        message = f"{role_emoji} **{user.get_display_name()}**\n"
        message += f"Status: {status_emoji}\n"
        message += f"Role: {user.role.value.replace('_', ' ').title()}\n"
        
        if user.username:
            message += f"Username: @{user.username}\n"
        
        if include_stats:
            message += f"📊 Issues Created: {user.issues_created}\n"
            message += f"📅 Joined: {self._format_datetime(user.created_at)}\n"
            message += f"🕐 Last Active: {self._format_datetime(user.last_activity)}\n"
        
        if include_preferences and preferences:
            message += "\n**Preferences**:\n"
            if preferences.default_project_key:
                message += f"🏗️ Default Project: {preferences.default_project_key}\n"
            message += f"🎯 Default Priority: {preferences.default_priority.value}\n"
            message += f"🏷️ Default Type: {preferences.default_issue_type.value}\n"
            message += f"📄 Max Issues/Page: {preferences.max_issues_per_page}\n"
        
        return message.strip()

    def format_issue_list(
        self,
        issues: List[JiraIssue],
        title: str = "Issues",
        show_project: bool = True,
        max_items: int = 10
    ) -> str:
        """Format a list of issues for display.
        
        Args:
            issues: List of JiraIssue model instances
            title: List title
            show_project: Whether to show project key
            max_items: Maximum items to show
            
        Returns:
            Formatted message text
        """
        if not issues:
            return f"📝 **{title}**\n\nNo issues found."
        
        message = f"📝 **{title}** ({len(issues)})\n\n"
        
        for i, issue in enumerate(issues[:max_items]):
            priority_emoji = issue.priority.get_emoji()
            status_emoji = issue.status.get_emoji()
            
            line = f"{i+1}. {priority_emoji}{status_emoji} **{issue.key}**"
            if show_project:
                line += f" ({issue.project_key})"
            line += f": {issue.summary}\n"
            
            # Truncate long summaries
            if len(line) > 150:
                line = line[:147] + "...\n"
            
            message += line
        
        if len(issues) > max_items:
            message += f"\n... and {len(issues) - max_items} more"
        
        return message

    def format_project_list(
        self,
        projects: List[Project],
        title: str = "Projects",
        active_only: bool = True,
        max_items: int = 15
    ) -> str:
        """Format a list of projects for display.
        
        Args:
            projects: List of Project model instances
            title: List title
            active_only: Whether to show only active projects
            max_items: Maximum items to show
            
        Returns:
            Formatted message text
        """
        if active_only:
            projects = [p for p in projects if p.is_active]
        
        if not projects:
            return f"🏗️ **{title}**\n\nNo projects found."
        
        message = f"🏗️ **{title}** ({len(projects)})\n\n"
        
        for i, project in enumerate(projects[:max_items]):
            status_emoji = '✅' if project.is_active else '❌'
            message += f"{i+1}. {status_emoji} **{project.key}**: {project.name}\n"
        
        if len(projects) > max_items:
            message += f"\n... and {len(projects) - max_items} more"
        
        return message

    def _format_datetime(self, dt: Optional[datetime]) -> str:
        """Format datetime for display.
        
        Args:
            dt: datetime object
            
        Returns:
            Formatted datetime string
        """
        if not dt:
            return "N/A"
        
        # Convert to user's timezone if needed (simplified for now)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        if diff.days == 0:
            if diff.seconds < 3600:  # Less than 1 hour
                minutes = diff.seconds // 60
                return f"{minutes}m ago"
            else:  # Less than 24 hours
                hours = diff.seconds // 3600
                return f"{hours}h ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            return dt.strftime("%Y-%m-%d")

    # =============================================================================
    # KEYBOARD GENERATION - MODEL-AWARE
    # =============================================================================

    def create_project_keyboard(
        self,
        projects: List[Project],
        action_prefix: str = "select_project",
        max_per_row: int = 2,
        max_projects: int = 20
    ) -> InlineKeyboardMarkup:
        """Create keyboard with project selection buttons.
        
        Args:
            projects: List of Project model instances
            action_prefix: Callback data prefix
            max_per_row: Maximum buttons per row
            max_projects: Maximum projects to show
            
        Returns:
            InlineKeyboardMarkup
        """
        if not self.use_inline_keyboards:
            return None
        
        keyboard = []
        current_row = []
        
        active_projects = [p for p in projects if p.is_active][:max_projects]
        
        for project in active_projects:
            button_text = f"{project.key}: {project.name}"
            if len(button_text) > 30:
                button_text = f"{project.key}: {project.name[:20]}..."
            
            callback_data = f"{action_prefix}:{project.key}"
            if len(callback_data) > MAX_CALLBACK_DATA_LENGTH:
                callback_data = callback_data[:MAX_CALLBACK_DATA_LENGTH]
            
            button = InlineKeyboardButton(button_text, callback_data=callback_data)
            current_row.append(button)
            
            if len(current_row) >= max_per_row:
                keyboard.append(current_row)
                current_row = []
        
        if current_row:
            keyboard.append(current_row)
        
        return InlineKeyboardMarkup(keyboard)

    def create_issue_actions_keyboard(
        self,
        issue: JiraIssue,
        user_role: UserRole = UserRole.USER
    ) -> InlineKeyboardMarkup:
        """Create keyboard with issue action buttons.
        
        Args:
            issue: JiraIssue model instance
            user_role: User role for permission-based actions
            
        Returns:
            InlineKeyboardMarkup
        """
        if not self.use_inline_keyboards:
            return None
        
        keyboard = []
        
        # Basic actions
        row1 = [
            InlineKeyboardButton("📝 View Details", callback_data=f"view_issue:{issue.key}"),
            InlineKeyboardButton("💬 Comments", callback_data=f"comments:{issue.key}")
        ]
        keyboard.append(row1)
        
        # Status transition actions (simplified)
        row2 = []
        if issue.status == IssueStatus.TODO:
            row2.append(InlineKeyboardButton("▶️ Start Work", callback_data=f"transition:{issue.key}:progress"))
        elif issue.status == IssueStatus.IN_PROGRESS:
            row2.append(InlineKeyboardButton("✅ Mark Done", callback_data=f"transition:{issue.key}:done"))
            row2.append(InlineKeyboardButton("🚫 Block", callback_data=f"transition:{issue.key}:blocked"))
        elif issue.status == IssueStatus.BLOCKED:
            row2.append(InlineKeyboardButton("▶️ Unblock", callback_data=f"transition:{issue.key}:progress"))
        
        if row2:
            keyboard.append(row2)
        
        # Admin actions
        if user_role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            row3 = [
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_issue:{issue.key}"),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_issue:{issue.key}")
            ]
            keyboard.append(row3)
        
        # Navigation
        row4 = [
            InlineKeyboardButton("🔙 Back", callback_data="back"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_issue:{issue.key}")
        ]
        keyboard.append(row4)
        
        return InlineKeyboardMarkup(keyboard)

    def create_priority_keyboard(self, action_prefix: str = "priority") -> InlineKeyboardMarkup:
        """Create keyboard with priority selection buttons.
        
        Args:
            action_prefix: Callback data prefix
            
        Returns:
            InlineKeyboardMarkup
        """
        if not self.use_inline_keyboards:
            return None
        
        keyboard = []
        
        for priority in IssuePriority:
            button_text = f"{priority.get_emoji()} {priority.value}"
            callback_data = f"{action_prefix}:{priority.value.lower()}"
            button = InlineKeyboardButton(button_text, callback_data=callback_data)
            keyboard.append([button])
        
        return InlineKeyboardMarkup(keyboard)

    def create_issue_type_keyboard(self, action_prefix: str = "type") -> InlineKeyboardMarkup:
        """Create keyboard with issue type selection buttons.
        
        Args:
            action_prefix: Callback data prefix
            
        Returns:
            InlineKeyboardMarkup
        """
        if not self.use_inline_keyboards:
            return None
        
        keyboard = []
        
        for issue_type in IssueType:
            button_text = f"{issue_type.get_emoji()} {issue_type.value}"
            callback_data = f"{action_prefix}:{issue_type.value.lower()}"
            button = InlineKeyboardButton(button_text, callback_data=callback_data)
            keyboard.append([button])
        
        return InlineKeyboardMarkup(keyboard)

    def create_confirmation_keyboard(
        self,
        confirm_action: str,
        confirm_text: str = "✅ Confirm",
        cancel_text: str = "❌ Cancel"
    ) -> InlineKeyboardMarkup:
        """Create a confirmation keyboard.
        
        Args:
            confirm_action: Callback data for confirm button
            confirm_text: Text for confirm button
            cancel_text: Text for cancel button
            
        Returns:
            InlineKeyboardMarkup
        """
        if not self.use_inline_keyboards:
            return None
        
        keyboard = [
            [
                InlineKeyboardButton(confirm_text, callback_data=confirm_action),
                InlineKeyboardButton(cancel_text, callback_data="cancel")
            ]
        ]
        
        return InlineKeyboardMarkup(keyboard)

    # =============================================================================
    # ERROR HANDLING AND NOTIFICATIONS
    # =============================================================================

    async def send_error_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        error_message: str,
        show_help: bool = False
    ) -> Optional[int]:
        """Send an error message to the user.
        
        Args:
            update: Telegram update
            context: Bot context
            error_message: Error message to display
            show_help: Whether to show help information
            
        Returns:
            Message ID of sent message
        """
        message = f"❌ **Error**\n\n{error_message}"
        
        if show_help:
            message += "\n\nUse /help for available commands."
        
        return await self.send_message(
            update=update,
            context=context,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2
        )

    async def send_success_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        success_message: str
    ) -> Optional[int]:
        """Send a success message to the user.
        
        Args:
            update: Telegram update
            context: Bot context
            success_message: Success message to display
            
        Returns:
            Message ID of sent message
        """
        message = f"✅ **Success**\n\n{success_message}"
        
        return await self.send_message(
            update=update,
            context=context,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2
        )

    async def send_info_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        info_message: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send an info message to the user.
        
        Args:
            update: Telegram update
            context: Bot context
            info_message: Info message to display
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID of sent message
        """
        message = f"ℹ️ **Info**\n\n{info_message}"
        
        return await self.send_message(
            update=update,
            context=context,
            text=message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    async def send_error_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        error_message: str,
        show_help: bool = False
    ) -> Optional[int]:
        """Send an error message to the user.
        
        Args:
            update: Telegram update
            context: Bot context
            error_message: Error message to display
            show_help: Whether to show help information
            
        Returns:
            Message ID of sent message
        """
        message = f"❌ **Error**\n\n{error_message}"
        
        if show_help:
            message += "\n\nUse /help for available commands."
        
        return await self.send_message(
            update=update,
            context=context,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2
        )