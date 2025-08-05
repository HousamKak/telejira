#!/usr/bin/env python3
"""
Base handler for the Telegram-Jira bot.

Contains the base handler class with common functionality for all handlers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from ..config.settings import BotConfig
from ..services.database import DatabaseManager, DatabaseError
from ..services.jira_service import JiraService, JiraAPIError
from ..services.telegram_service import TelegramService
from ..models.user import User, UserPreferences, UserSession
from ..models.enums import UserRole, WizardState, ErrorType
from ..utils.constants import EMOJI, ERROR_MESSAGES, SUCCESS_MESSAGES
from ..utils.validators import InputValidator, ValidationResult


class BaseHandler(ABC):
    """Base class for all bot handlers."""

    def __init__(
        self,
        config: BotConfig,
        db: DatabaseManager,
        jira_service: JiraService,
        telegram_service: TelegramService
    ):
        """Initialize the base handler.
        
        Args:
            config: Bot configuration
            db: Database manager
            jira_service: Jira service
            telegram_service: Telegram service
        """
        self.config = config
        self.db = db
        self.jira = jira_service
        self.telegram = telegram_service
        self.logger = logging.getLogger(self.__class__.__name__)

    # User management methods
    async def get_or_create_user(self, update: Update) -> Optional[User]:
        """Get or create user from update.
        
        Args:
            update: Telegram update
            
        Returns:
            User object or None if no effective user
        """
        if not update.effective_user:
            return None

        try:
            telegram_user_id = str(update.effective_user.id)  # Convert to string
            user = await self.db.get_user(telegram_user_id)
            if user:
                # Update activity
                await self.db.update_user_activity(telegram_user_id)
                return user
            else:
                # Create new user
                new_user = User.from_telegram_user(update.effective_user)
                
                # Set role based on config
                if self.config.is_user_super_admin(update.effective_user.id):
                    new_user.role = UserRole.SUPER_ADMIN
                elif self.config.is_user_admin(update.effective_user.id):
                    new_user.role = UserRole.ADMIN
                
                await self.db.save_user(new_user)
                self.logger.info(f"Created new user: {telegram_user_id}")
                return new_user

        except DatabaseError as e:
            self.logger.error(f"Failed to get/create user: {e}")
            await self.send_error_message(update, "Database error occurred")
            return None

    async def get_user_preferences(self, user_id: str) -> Optional[UserPreferences]:
        """Get user preferences.
        
        Args:
            user_id: User ID (Telegram user ID as string)
            
        Returns:
            UserPreferences or None if not found
        """
        try:
            return await self.db.get_user_preferences(user_id)
        except DatabaseError as e:
            self.logger.error(f"Failed to get user preferences: {e}")
            return None

    async def get_user_session(self, user_id: str) -> Optional[UserSession]:
        """Get user session.
        
        Args:
            user_id: User ID (Telegram user ID as string)
            
        Returns:
            UserSession or None if not found
        """
        try:
            session = await self.db.get_user_session(user_id)
            if session and session.is_expired():
                # Clean up expired session
                session.clear_wizard()
                await self.db.save_user_session(session)
                return session
            return session
        except DatabaseError as e:
            self.logger.error(f"Failed to get user session: {e}")
            return None

    async def save_user_session(self, session: UserSession) -> bool:
            """Save user session.
            
            Args:
                session: User session to save
                
            Returns:
                True if saved successfully
            """
            try:
                await self.db.save_user_session(session)
                return True
            except DatabaseError as e:
                self.logger.error(f"Failed to save user session: {e}")
                return False

    # Permission checking methods
    def check_user_access(self, user_id: int) -> bool:
        """Check if user has access to the bot.
        
        Args:
            user_id: User ID to check
            
        Returns:
            True if user has access
        """
        return self.config.is_user_allowed(user_id)

    def check_user_role(self, user: User, required_role: UserRole) -> bool:
        """Check if user has required role.
        
        Args:
            user: User to check
            required_role: Required role
            
        Returns:
            True if user has required role or higher
        """
        return user.has_permission(required_role)

    def is_admin(self, user: User) -> bool:
        """Check if user is an admin.
        
        Args:
            user: User to check
            
        Returns:
            True if user is admin or super admin
        """
        return user.is_admin()

    def is_super_admin(self, user: User) -> bool:
        """Check if user is a super admin.
        
        Args:
            user: User to check
            
        Returns:
            True if user is super admin
        """
        return user.is_super_admin()

    # Message sending utilities
    async def send_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message: bool = False
    ) -> Optional[int]:
        """Send a message with error handling.
        
        Args:
            update: Telegram update
            text: Message text
            reply_markup: Optional keyboard markup
            reply_to_message: Whether to reply to the original message
            
        Returns:
            Message ID if sent successfully
        """
        return await self.telegram.send_message(
            update, text, reply_markup, reply_to_message=reply_to_message
        )

    async def edit_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> bool:
        """Edit a message with error handling.
        
        Args:
            update: Telegram update
            text: New message text
            reply_markup: New keyboard markup
            
        Returns:
            True if edited successfully
        """
        return await self.telegram.edit_message(update, text, reply_markup)

    async def send_error_message(
        self,
        update: Update,
        error_text: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        include_help: bool = True
    ) -> Optional[int]:
        """Send an error message.
        
        Args:
            update: Telegram update
            error_text: Error message text
            error_type: Type of error
            include_help: Whether to include help text
            
        Returns:
            Message ID if sent successfully
        """
        emoji = error_type.get_emoji()
        message = f"{emoji} **Error**\n\n{error_text}"
        
        if include_help:
            message += f"\n\n{EMOJI['TIP']} Type /help for assistance."
        
        return await self.send_message(update, message)

    async def send_success_message(
        self,
        update: Update,
        success_text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send a success message.
        
        Args:
            update: Telegram update
            success_text: Success message text
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID if sent successfully
        """
        return await self.telegram.send_success_message(update, success_text, reply_markup)

    async def send_info_message(
        self,
        update: Update,
        info_text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send an info message.
        
        Args:
            update: Telegram update
            info_text: Info message text
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID if sent successfully
        """
        return await self.telegram.send_info_message(update, info_text, reply_markup)

    async def send_warning_message(
        self,
        update: Update,
        warning_text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Optional[int]:
        """Send a warning message.
        
        Args:
            update: Telegram update
            warning_text: Warning message text
            reply_markup: Optional keyboard markup
            
        Returns:
            Message ID if sent successfully
        """
        return await self.telegram.send_warning_message(update, warning_text, reply_markup)

    # Validation utilities
    def validate_project_key(self, key: str) -> ValidationResult:
        """Validate project key.
        
        Args:
            key: Project key to validate
            
        Returns:
            ValidationResult
        """
        return InputValidator.validate_project_key(key)

    def validate_project_name(self, name: str) -> ValidationResult:
        """Validate project name.
        
        Args:
            name: Project name to validate
            
        Returns:
            ValidationResult
        """
        return InputValidator.validate_project_name(name)

    def validate_issue_summary(self, summary: str) -> ValidationResult:
        """Validate issue summary.
        
        Args:
            summary: Issue summary to validate
            
        Returns:
            ValidationResult
        """
        return InputValidator.validate_issue_summary(summary, self.config.max_summary_length)

    def validate_issue_description(self, description: str) -> ValidationResult:
        """Validate issue description.
        
        Args:
            description: Issue description to validate
            
        Returns:
            ValidationResult
        """
        return InputValidator.validate_issue_description(description, self.config.max_description_length)

    # Command argument parsing
    def parse_command_args(self, update: Update, expected_args: int) -> Optional[List[str]]:
        """Parse command arguments from message.
        
        Args:
            update: Telegram update
            expected_args: Expected number of arguments
            
        Returns:
            List of arguments or None if invalid
        """
        if not update.message or not update.message.text:
            return None

        # Split message and remove command
        parts = update.message.text.split()
        if len(parts) < 1:
            return None

        args = parts[1:]  # Remove command itself
        
        if len(args) < expected_args:
            return None

        return args

    def extract_callback_data(self, update: Update) -> Optional[str]:
        """Extract callback data from update.
        
        Args:
            update: Telegram update
            
        Returns:
            Callback data or None
        """
        if update.callback_query and update.callback_query.data:
            return update.callback_query.data
        return None

    def parse_callback_data(self, callback_data: str) -> List[str]:
        """Parse callback data into components.
        
        Args:
            callback_data: Callback data string
            
        Returns:
            List of callback data components
        """
        return callback_data.split('_') if callback_data else []

    # Error handling utilities
    async def handle_database_error(self, update: Update, error: DatabaseError, context: str = "") -> None:
        """Handle database errors consistently.
        
        Args:
            update: Telegram update
            error: Database error
            context: Additional context for logging
        """
        self.logger.error(f"Database error{' in ' + context if context else ''}: {error}")
        await self.send_error_message(
            update,
            "Database error occurred. Please try again later.",
            ErrorType.DATABASE_ERROR
        )

    async def handle_jira_error(self, update: Update, error: JiraAPIError, context: str = "") -> None:
        """Handle Jira API errors consistently.
        
        Args:
            update: Telegram update
            error: Jira API error
            context: Additional context for logging
        """
        self.logger.error(f"Jira API error{' in ' + context if context else ''}: {error}")
        
        if error.status_code == 401:
            error_message = "Jira authentication failed. Please check bot configuration."
        elif error.status_code == 403:
            error_message = "Permission denied. Check your Jira permissions."
        elif error.status_code == 404:
            error_message = "Resource not found in Jira."
        else:
            error_message = f"Jira API error: {str(error)}"
        
        await self.send_error_message(update, error_message, ErrorType.JIRA_API_ERROR)

    async def handle_validation_error(self, update: Update, validation_result: ValidationResult, context: str = "") -> None:
        """Handle validation errors consistently.
        
        Args:
            update: Telegram update
            validation_result: Validation result with errors
            context: Additional context
        """
        if validation_result.has_errors():
            error_message = "\n".join([f"• {error}" for error in validation_result.errors])
            self.logger.warning(f"Validation error{' in ' + context if context else ''}: {error_message}")
            await self.send_error_message(update, error_message, ErrorType.VALIDATION_ERROR)

    # Permission enforcement
    async def enforce_user_access(self, update: Update) -> Optional[User]:
        """Enforce user access and return user if allowed.
        
        Args:
            update: Telegram update
            
        Returns:
            User object if access is allowed, None otherwise
        """
        if not update.effective_user:
            await self.send_error_message(update, "Unable to identify user")
            return None

        if not self.check_user_access(update.effective_user.id):
            await self.send_error_message(
                update,
                "You don't have access to this bot. Contact an administrator.",
                ErrorType.PERMISSION_ERROR
            )
            return None

        return await self.get_or_create_user(update)

    async def enforce_role(self, update: Update, required_role: UserRole) -> Optional[User]:
        """Enforce role requirement and return user if authorized.
        
        Args:
            update: Telegram update
            required_role: Required user role
            
        Returns:
            User object if authorized, None otherwise
        """
        user = await self.enforce_user_access(update)
        if not user:
            return None

        if not self.check_user_role(user, required_role):
            role_name = required_role.value.replace('_', ' ').title()
            await self.send_error_message(
                update,
                f"You need {role_name} permissions to use this command.",
                ErrorType.PERMISSION_ERROR
            )
            return None

        return user

    async def enforce_admin(self, update: Update) -> Optional[User]:
        """Enforce admin requirement.
        
        Args:
            update: Telegram update
            
        Returns:
            User object if admin, None otherwise
        """
        return await self.enforce_role(update, UserRole.ADMIN)

    async def enforce_super_admin(self, update: Update) -> Optional[User]:
        """Enforce super admin requirement.
        
        Args:
            update: Telegram update
            
        Returns:
            User object if super admin, None otherwise
        """
        return await self.enforce_role(update, UserRole.SUPER_ADMIN)

    # Utility methods
    def get_user_display_name(self, user: User) -> str:
        """Get display name for user.
        
        Args:
            user: User object
            
        Returns:
            Display name
        """
        return user.get_display_name()

    def format_error_list(self, errors: List[str]) -> str:
        """Format list of errors for display.
        
        Args:
            errors: List of error messages
            
        Returns:
            Formatted error text
        """
        if len(errors) == 1:
            return errors[0]
        else:
            return "Multiple errors occurred:\n" + "\n".join([f"• {error}" for error in errors])

    def truncate_text(self, text: str, max_length: int = 100) -> str:
        """Truncate text to specified length.
        
        Args:
            text: Text to truncate
            max_length: Maximum length
            
        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    # Abstract methods that must be implemented by subclasses
    @abstractmethod
    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to this handler.
        
        Args:
            update: Telegram update
            error: Exception that occurred
            context: Additional context
        """
        pass

    @abstractmethod
    def get_handler_name(self) -> str:
        """Get the name of this handler for logging purposes.
        
        Returns:
            Handler name
        """
        pass

    # Logging utilities
    def log_user_action(self, user: User, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log user action for audit purposes.
        
        Args:
            user: User who performed the action
            action: Action performed
            details: Additional details
        """
        log_data = {
            'user_id': user.user_id,
            'username': user.username,
            'action': action,
            'handler': self.get_handler_name()
        }
        
        if details:
            log_data.update(details)
        
        self.logger.info(f"User action: {action}", extra=log_data)

    def log_handler_start(self, update: Update, handler_method: str) -> None:
        """Log handler method start.
        
        Args:
            update: Telegram update
            handler_method: Method name
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"
        self.logger.debug(
            f"Handler {self.get_handler_name()}.{handler_method} started",
            extra={'user_id': user_id, 'method': handler_method}
        )

    def log_handler_end(self, update: Update, handler_method: str, success: bool = True) -> None:
        """Log handler method end.
        
        Args:
            update: Telegram update
            handler_method: Method name
            success: Whether handler completed successfully
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"
        status = "completed" if success else "failed"
        self.logger.debug(
            f"Handler {self.get_handler_name()}.{handler_method} {status}",
            extra={'user_id': user_id, 'method': handler_method, 'success': success}
        )