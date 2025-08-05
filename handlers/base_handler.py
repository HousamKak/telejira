"""
Base Handler for Telegram Bot command handlers.

This module provides the base class with shared functionality for all bot handlers,
including user authentication, error handling, and common operations.
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config.settings import BotConfig
from services.database import DatabaseError, DatabaseService
from services.jira_service import JiraAPIError, JiraService
from models import ErrorType, SentMessages, User, UserRole
from services.telegram_service import TelegramAPIError, TelegramService

logger = logging.getLogger(__name__)


class BaseHandler:
    """
    Base class for all Telegram bot handlers.
    
    Provides shared functionality including user authentication, error handling,
    message sending, and logging. All handler classes should inherit from this base.
    """

    def __init__(
        self,
        config: BotConfig,
        database_service: DatabaseService,
        jira_service: JiraService,
        telegram_service: TelegramService,
    ) -> None:
        """
        Initialize base handler with required services.
        
        Args:
            database_service: Database service instance
            jira_service: Jira service instance
            telegram_service: Telegram service instance
            
        Raises:
            TypeError: If services have incorrect types
        """
        if not isinstance(database_service, DatabaseService):
            raise TypeError(f"database_service must be DatabaseService, got {type(database_service)}")
        if not isinstance(jira_service, JiraService):
            raise TypeError(f"jira_service must be JiraService, got {type(jira_service)}")
        if not isinstance(telegram_service, TelegramService):
            raise TypeError(f"telegram_service must be TelegramService, got {type(telegram_service)}")

        self.config = config 
        self.db = database_service
        self.jira = jira_service
        self.telegram = telegram_service

    def get_handler_name(self) -> str:
        """
        Get the name of this handler for logging purposes.
        
        Returns:
            Handler class name
        """
        return self.__class__.__name__

    # ---- Message Operations ----

    async def send_message(
        self,
        update: Update,
        text: str,
        *,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message: bool = False,
    ) -> Optional[SentMessages]:
        """
        Send a message to the user.
        
        Args:
            update: Telegram update object
            text: Message text to send
            reply_markup: Optional inline keyboard
            reply_to_message: Whether to reply to the original message
            
        Returns:
            SentMessages if successful, None if failed
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(text, str) or not text:
            raise TypeError("text must be non-empty string")
        if reply_markup is not None and not isinstance(reply_markup, InlineKeyboardMarkup):
            raise TypeError("reply_markup must be InlineKeyboardMarkup or None")
        if not isinstance(reply_to_message, bool):
            raise TypeError("reply_to_message must be boolean")

        try:
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id is None:
                logger.error("No effective chat found in update")
                return None

            reply_to_message_id = None
            if reply_to_message and update.effective_message:
                reply_to_message_id = update.effective_message.message_id

            sent_messages = await self.telegram.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
            )
            
            return sent_messages

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None

    async def edit_message(
        self,
        update: Update,
        text: str,
        *,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> bool:
        """
        Edit an existing message.
        
        Args:
            update: Telegram update object
            text: New message text
            reply_markup: Optional inline keyboard
            
        Returns:
            True if successful, False otherwise
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(text, str) or not text:
            raise TypeError("text must be non-empty string")
        if reply_markup is not None and not isinstance(reply_markup, InlineKeyboardMarkup):
            raise TypeError("reply_markup must be InlineKeyboardMarkup or None")

        try:
            if not update.callback_query or not update.callback_query.message:
                logger.error("No callback query message found for editing")
                return False

            chat_id = update.callback_query.message.chat.id
            message_id = update.callback_query.message.message_id

            await self.telegram.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            
            return True

        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
            return False

    # ---- User Authentication & Authorization ----

    async def get_or_create_user(self, update: Update) -> Optional[User]:
        """
        Get existing user or create new user if preauthorized.
        
        This method handles the complete user authentication flow:
        1. Extract user info from Telegram update
        2. Check if user exists in database
        3. If exists, update last activity and return user
        4. If not exists, check preauthorization
        5. Create new user if preauthorized, otherwise deny access
        
        Args:
            update: Telegram update object
            
        Returns:
            User instance if authenticated, None if access denied
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")

        try:
            telegram_user = update.effective_user
            if not telegram_user:
                logger.warning("No effective user found in update")
                await self.send_error_message(update, "Unable to identify user", ErrorType.AUTHENTICATION_ERROR)
                return None

            user_id = str(telegram_user.id)
            username = telegram_user.username

            # Try to get existing user
            existing_user = await self.db.get_user_by_telegram_id(user_id)
            
            if existing_user:
                # User exists, update last activity
                await self.db.update_user_last_activity(user_id)
                
                if not existing_user.is_active:
                    await self.send_error_message(
                        update, 
                        "Your account has been deactivated. Please contact an administrator.",
                        ErrorType.AUTHORIZATION_ERROR
                    )
                    return None
                
                return existing_user

            # User doesn't exist, check preauthorization
            if not username:
                await self.send_error_message(
                    update,
                    "You must have a username to use this bot. Please set a username in your Telegram settings.",
                    ErrorType.AUTHORIZATION_ERROR
                )
                return None

            preauth_role = await self.db.get_preauthorized_user_role(username)
            if not preauth_role:
                await self.send_error_message(
                    update,
                    f"Access denied. Your username @{username} is not authorized to use this bot. "
                    "Please contact an administrator to request access.",
                    ErrorType.AUTHORIZATION_ERROR
                )
                return None

            # Create new user
            row_id = await self.db.create_user(
                user_id=user_id,
                username=username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                role=preauth_role,
            )

            # Get the created user
            new_user = await self.db.get_user_by_row_id(row_id)
            if new_user:
                await self.db.log_user_action(user_id, "user_created", {
                    "username": username,
                    "role": preauth_role.value,
                })
                
                logger.info(f"Created new user: {username} ({user_id}) with role {preauth_role.value}")
                
                # Send welcome message
                welcome_text = (
                    f"🎉 Welcome to the Jira Bot, {new_user.display_name}!\n\n"
                    f"Your account has been created with role: **{preauth_role.display_name}**\n\n"
                    "Use /help to see available commands or /setup to configure your preferences."
                )
                await self.send_message(update, welcome_text)

            return new_user

        except DatabaseError as e:
            logger.error(f"Database error in get_or_create_user: {e}")
            await self.handle_database_error(update, e, "user authentication")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_or_create_user: {e}")
            await self.send_error_message(update, "An unexpected error occurred during authentication", ErrorType.UNKNOWN_ERROR)
            return None

    async def enforce_user_access(self, update: Update) -> Optional[User]:
        """
        Enforce that user has basic access to the bot.
        
        Args:
            update: Telegram update object
            
        Returns:
            User instance if access granted, None if denied
        """
        user = await self.get_or_create_user(update)
        if not user:
            return None

        # Log user activity
        try:
            telegram_user = update.effective_user
            action = "unknown_action"
            
            if update.message and update.message.text:
                if update.message.text.startswith('/'):
                    action = f"command_{update.message.text.split()[0][1:]}"
                else:
                    action = "message_sent"
            elif update.callback_query:
                action = f"callback_{update.callback_query.data}" if update.callback_query.data else "callback_query"
            
            await self.db.log_user_action(user.user_id, action)
            
        except Exception as e:
            logger.warning(f"Failed to log user activity: {e}")

        return user

    async def enforce_role(self, update: Update, required_role: UserRole) -> Optional[User]:
        """
        Enforce that user has specific role or higher.
        
        Args:
            update: Telegram update object
            required_role: Minimum required role
            
        Returns:
            User instance if role check passes, None if denied
        """
        if not isinstance(required_role, UserRole):
            raise TypeError(f"required_role must be UserRole, got {type(required_role)}")

        user = await self.enforce_user_access(update)
        if not user:
            return None

        # Define role hierarchy
        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.USER: 1,
            UserRole.ADMIN: 2,
            UserRole.SUPER_ADMIN: 3,
        }

        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        if user_level < required_level:
            await self.send_error_message(
                update,
                f"Access denied. This command requires {required_role.display_name} role or higher. "
                f"Your current role: {user.role.display_name}",
                ErrorType.AUTHORIZATION_ERROR
            )
            
            await self.db.log_user_action(user.user_id, "access_denied", {
                "required_role": required_role.value,
                "user_role": user.role.value,
            })
            
            return None

        return user

    def is_admin(self, user: User) -> bool:
        """
        Check if user has admin privileges.
        
        Args:
            user: User instance to check
            
        Returns:
            True if user is admin or super admin
        """
        if not isinstance(user, User):
            raise TypeError(f"user must be User, got {type(user)}")
        
        return user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    def is_super_admin(self, user: User) -> bool:
        """
        Check if user has super admin privileges.
        
        Args:
            user: User instance to check
            
        Returns:
            True if user is super admin
        """
        if not isinstance(user, User):
            raise TypeError(f"user must be User, got {type(user)}")
            
        return user.role == UserRole.SUPER_ADMIN

    # ---- Error Handling ----

    async def handle_database_error(self, update: Update, error: Exception, context: str) -> None:
        """
        Handle database errors with appropriate user messaging.
        
        Args:
            update: Telegram update object
            error: Database error that occurred
            context: Context description for logging
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(error, Exception):
            raise TypeError(f"error must be Exception, got {type(error)}")
        if not isinstance(context, str):
            raise TypeError(f"context must be string, got {type(context)}")

        logger.error(f"Database error in {context}: {error}")
        
        await self.send_error_message(
            update,
            "A database error occurred. Please try again later or contact support if the problem persists.",
            ErrorType.DATABASE_ERROR
        )

    async def handle_jira_error(self, update: Update, error: Exception, context: str) -> None:
        """
        Handle Jira API errors with appropriate user messaging.
        
        Args:
            update: Telegram update object
            error: Jira error that occurred
            context: Context description for logging
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(error, Exception):
            raise TypeError(f"error must be Exception, got {type(error)}")
        if not isinstance(context, str):
            raise TypeError(f"context must be string, got {type(context)}")

        logger.error(f"Jira error in {context}: {error}")
        
        error_message = "A Jira API error occurred"
        
        if isinstance(error, JiraAPIError):
            if "authentication" in str(error).lower():
                error_message = "Jira authentication failed. Please contact an administrator to check the API credentials."
            elif "not found" in str(error).lower():
                error_message = "The requested Jira resource was not found. It may have been moved or deleted."
            elif "permission" in str(error).lower():
                error_message = "Permission denied. You may not have access to this Jira resource."
            else:
                error_message = f"Jira API error: {str(error)}"
        
        await self.send_error_message(update, error_message, ErrorType.JIRA_API_ERROR)

    async def send_error_message(self, update: Update, text: str, error_type: ErrorType = ErrorType.UNKNOWN_ERROR) -> None:
        """
        Send a formatted error message to the user.
        
        Args:
            update: Telegram update object
            text: Error message text
            error_type: Type of error for categorization
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(text, str) or not text:
            raise TypeError("text must be non-empty string")
        if not isinstance(error_type, ErrorType):
            raise TypeError(f"error_type must be ErrorType, got {type(error_type)}")

        # Format error message with appropriate emoji
        error_emojis = {
            ErrorType.AUTHENTICATION_ERROR: "🔐",
            ErrorType.AUTHORIZATION_ERROR: "⛔",
            ErrorType.VALIDATION_ERROR: "⚠️",
            ErrorType.NOT_FOUND_ERROR: "🔍",
            ErrorType.JIRA_API_ERROR: "🔧",
            ErrorType.DATABASE_ERROR: "💾",
            ErrorType.NETWORK_ERROR: "🌐",
            ErrorType.UNKNOWN_ERROR: "❌",
        }
        
        emoji = error_emojis.get(error_type, "❌")
        formatted_text = f"{emoji} **Error:** {text}"
        
        await self.send_message(update, formatted_text)

    # ---- Logging Helpers ----

    def log_handler_start(self, update: Update, name: str) -> None:
        """
        Log the start of a handler operation.
        
        Args:
            update: Telegram update object
            name: Handler operation name
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(name, str):
            raise TypeError(f"name must be string, got {type(name)}")

        user_info = "unknown"
        if update.effective_user:
            user_info = f"{update.effective_user.username or update.effective_user.id}"
        
        chat_info = "unknown"
        if update.effective_chat:
            chat_info = str(update.effective_chat.id)
            
        logger.info(f"Handler {self.get_handler_name()}.{name} started for user {user_info} in chat {chat_info}")

    def log_handler_end(self, update: Update, name: str, *, success: bool = True) -> None:
        """
        Log the end of a handler operation.
        
        Args:
            update: Telegram update object
            name: Handler operation name
            success: Whether the operation was successful
        """
        if not isinstance(update, Update):
            raise TypeError(f"update must be Update, got {type(update)}")
        if not isinstance(name, str):
            raise TypeError(f"name must be string, got {type(name)}")
        if not isinstance(success, bool):
            raise TypeError(f"success must be boolean, got {type(success)}")

        user_info = "unknown"
        if update.effective_user:
            user_info = f"{update.effective_user.username or update.effective_user.id}"
        
        status = "completed" if success else "failed"
        logger.info(f"Handler {self.get_handler_name()}.{name} {status} for user {user_info}")

    # ---- Utility Methods ----

    def _extract_command_args(self, update: Update) -> list[str]:
        """
        Extract command arguments from message text.
        
        Args:
            update: Telegram update object
            
        Returns:
            List of command arguments
        """
        if not update.message or not update.message.text:
            return []
        
        parts = update.message.text.strip().split()
        return parts[1:] if len(parts) > 1 else []

    def _get_callback_data(self, update: Update) -> Optional[str]:
        """
        Extract callback data from callback query.
        
        Args:
            update: Telegram update object
            
        Returns:
            Callback data string or None
        """
        if update.callback_query and update.callback_query.data:
            return update.callback_query.data
        return None

    async def _answer_callback_query(self, update: Update, text: Optional[str] = None) -> None:
        """
        Answer callback query to remove loading state.
        
        Args:
            update: Telegram update object
            text: Optional text to show in popup
        """
        if update.callback_query:
            try:
                await update.callback_query.answer(text=text)
            except Exception as e:
                logger.warning(f"Failed to answer callback query: {e}")