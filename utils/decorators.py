#!/usr/bin/env python3
"""
Decorators for the Telegram-Jira bot.

Contains decorators for authentication, authorization, rate limiting, and other cross-cutting concerns.
Provides both class-based decorators and individual function decorators for backward compatibility.
"""

import asyncio
import functools
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, Any, Optional, List, Union

from telegram import Update
from telegram.ext import ContextTypes

from models.enums import UserRole, ErrorType
from models.user import User
from services.database import DatabaseManager, DatabaseError
from .constants import EMOJI, ERROR_MESSAGES


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class PermissionDenied(Exception):
    """Exception raised when user lacks required permissions."""
    pass


class BotDecorators:
    """Collection of decorators for bot handlers."""
    
    def __init__(self, db: DatabaseManager, config: Any):
        """Initialize decorators with database and config.
        
        Args:
            db: Database manager instance
            config: Bot configuration
        """
        self.db = db
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._rate_limit_cache: Dict[str, Dict[str, Any]] = {}
        self._permission_cache: Dict[int, Dict[str, Any]] = {}

    def require_user_access(self, func: Callable) -> Callable:
        """Decorator to require user access to the bot.
        
        Args:
            func: Handler function to decorate
            
        Returns:
            Decorated function
        """
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                self.logger.warning("Handler called without effective user")
                return
            
            user_id = update.effective_user.id
            
            # Check if user is allowed
            if not self.config.is_user_allowed(user_id):
                await self._send_access_denied_message(update)
                return
            
            # Update user activity and ensure user exists in database
            try:
                await self._ensure_user_exists(update.effective_user)
            except DatabaseError as e:
                self.logger.error(f"Failed to ensure user exists: {e}")
            
            return await func(update, context, *args, **kwargs)
        
        return wrapper

    def require_role(self, required_role: Union[UserRole, str]) -> Callable:
        """Decorator to require specific user role.
        
        Args:
            required_role: Required role (UserRole enum or string)
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                if not update.effective_user:
                    return
                
                user_id = update.effective_user.id
                
                # Convert string to UserRole if needed
                if isinstance(required_role, str):
                    try:
                        role_enum = UserRole(required_role.lower())
                    except ValueError:
                        self.logger.error(f"Invalid role string: {required_role}")
                        await self._send_error_message(update, "Invalid role configuration")
                        return
                else:
                    role_enum = required_role
                
                # Check user role
                user_role = await self._get_user_role(user_id)
                if not user_role.has_permission(role_enum):
                    await self._send_permission_denied_message(update, role_enum.value)
                    return
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator

    def require_admin(self, func: Callable) -> Callable:
        """Decorator to require admin role.
        
        Args:
            func: Handler function to decorate
            
        Returns:
            Decorated function
        """
        return self.require_role(UserRole.ADMIN)(func)

    def require_super_admin(self, func: Callable) -> Callable:
        """Decorator to require super admin role.
        
        Args:
            func: Handler function to decorate
            
        Returns:
            Decorated function
        """
        return self.require_role(UserRole.SUPER_ADMIN)(func)

    def rate_limit(
        self,
        max_calls: int = 10,
        window_seconds: int = 60,
        per_user: bool = True,
        per_chat: bool = False
    ) -> Callable:
        """Decorator to implement rate limiting.
        
        Args:
            max_calls: Maximum calls allowed
            window_seconds: Time window in seconds
            per_user: Apply rate limit per user
            per_chat: Apply rate limit per chat
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                # Determine rate limit key
                key_parts = []
                if per_user and update.effective_user:
                    key_parts.append(f"user_{update.effective_user.id}")
                if per_chat and update.effective_chat:
                    key_parts.append(f"chat_{update.effective_chat.id}")
                
                if not key_parts:
                    # No rate limiting if no key can be determined
                    return await func(update, context, *args, **kwargs)
                
                rate_limit_key = "_".join(key_parts + [func.__name__])
                
                # Check rate limit
                now = time.time()
                if rate_limit_key in self._rate_limit_cache:
                    cache_entry = self._rate_limit_cache[rate_limit_key]
                    
                    # Clean old entries
                    cache_entry['calls'] = [
                        call_time for call_time in cache_entry['calls']
                        if now - call_time < window_seconds
                    ]
                    
                    # Check if limit exceeded
                    if len(cache_entry['calls']) >= max_calls:
                        retry_after = window_seconds - (now - cache_entry['calls'][0])
                        await self._send_rate_limit_message(update, int(retry_after))
                        return
                else:
                    self._rate_limit_cache[rate_limit_key] = {'calls': []}
                
                # Record this call
                self._rate_limit_cache[rate_limit_key]['calls'].append(now)
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator

    def log_handler_calls(self, func: Callable) -> Callable:
        """Decorator to log handler calls and execution time.
        
        Args:
            func: Handler function to decorate
            
        Returns:
            Decorated function
        """
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            start_time = time.time()
            user_id = update.effective_user.id if update.effective_user else "unknown"
            
            self.logger.info(
                f"Handler {func.__name__} called by user {user_id}",
                extra={'user_id': user_id, 'function': func.__name__}
            )
            
            try:
                result = await func(update, context, *args, **kwargs)
                execution_time = time.time() - start_time
                
                self.logger.info(
                    f"Handler {func.__name__} completed in {execution_time:.2f}s",
                    extra={
                        'user_id': user_id,
                        'function': func.__name__,
                        'execution_time': execution_time
                    }
                )
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                self.logger.error(
                    f"Handler {func.__name__} failed after {execution_time:.2f}s: {e}",
                    extra={
                        'user_id': user_id,
                        'function': func.__name__,
                        'execution_time': execution_time,
                        'error': str(e)
                    }
                )
                raise
        
        return wrapper

    def validate_arguments(self, validators: Dict[str, Callable]) -> Callable:
        """Decorator to validate handler arguments.
        
        Args:
            validators: Dict mapping argument names to validator functions
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                # Get function signature to map arguments
                import inspect
                sig = inspect.signature(func)
                bound_args = sig.bind(update, context, *args, **kwargs)
                bound_args.apply_defaults()
                
                # Validate arguments
                for arg_name, validator in validators.items():
                    if arg_name in bound_args.arguments:
                        value = bound_args.arguments[arg_name]
                        try:
                            if not validator(value):
                                await self._send_validation_error_message(update, arg_name)
                                return
                        except Exception as e:
                            self.logger.error(f"Validation error for {arg_name}: {e}")
                            await self._send_validation_error_message(update, arg_name)
                            return
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator

    def require_private_chat(self, func: Callable) -> Callable:
        """Decorator to require handler to be called in private chat.
        
        Args:
            func: Handler function to decorate
            
        Returns:
            Decorated function
        """
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_chat or update.effective_chat.type != 'private':
                await self._send_private_chat_required_message(update)
                return
            
            return await func(update, context, *args, **kwargs)
        
        return wrapper

    def require_group_chat(self, func: Callable) -> Callable:
        """Decorator to require handler to be called in group chat.
        
        Args:
            func: Handler function to decorate
            
        Returns:
            Decorated function
        """
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
                await self._send_group_chat_required_message(update)
                return
            
            return await func(update, context, *args, **kwargs)
        
        return wrapper

    # Helper methods for sending messages
    async def _send_access_denied_message(self, update: Update) -> None:
        """Send access denied message."""
        message = f"{EMOJI.get('LOCK', '🔒')} Access denied. Contact your administrator."
        if update.callback_query:
            await update.callback_query.answer(message)
        elif update.message:
            await update.message.reply_text(message)

    async def _send_permission_denied_message(self, update: Update, required_role: str) -> None:
        """Send permission denied message."""
        message = f"{EMOJI.get('LOCK', '🔒')} This command requires {required_role} privileges."
        if update.callback_query:
            await update.callback_query.answer(message)
        elif update.message:
            await update.message.reply_text(message)

    async def _send_rate_limit_message(self, update: Update, retry_after: int) -> None:
        """Send rate limit exceeded message."""
        message = f"{EMOJI.get('WARNING', '⚠️')} Rate limit exceeded. Try again in {retry_after} seconds."
        if update.callback_query:
            await update.callback_query.answer(message)
        elif update.message:
            await update.message.reply_text(message)

    async def _send_error_message(self, update: Update, message: str) -> None:
        """Send generic error message."""
        full_message = f"{EMOJI.get('ERROR', '❌')} {message}"
        if update.callback_query:
            await update.callback_query.answer(full_message)
        elif update.message:
            await update.message.reply_text(full_message)

    async def _send_validation_error_message(self, update: Update, field_name: str) -> None:
        """Send validation error message."""
        message = f"{EMOJI.get('ERROR', '❌')} Invalid {field_name}. Please check your input."
        if update.callback_query:
            await update.callback_query.answer(message)
        elif update.message:
            await update.message.reply_text(message)

    async def _send_private_chat_required_message(self, update: Update) -> None:
        """Send private chat required message."""
        message = f"{EMOJI.get('INFO', 'ℹ️')} This command only works in private chat."
        if update.callback_query:
            await update.callback_query.answer(message)
        elif update.message:
            await update.message.reply_text(message)

    async def _send_group_chat_required_message(self, update: Update) -> None:
        """Send group chat required message."""
        message = f"{EMOJI.get('INFO', 'ℹ️')} This command only works in group chats."
        if update.callback_query:
            await update.callback_query.answer(message)
        elif update.message:
            await update.message.reply_text(message)

    async def _ensure_user_exists(self, telegram_user) -> None:
        """Ensure user exists in database."""
        # This would typically interact with the database
        # Implementation depends on your User model and database setup
        pass

    async def _get_user_role(self, user_id: int) -> UserRole:
        """Get user role from database."""
        # This would typically query the database for user role
        # Implementation depends on your User model and database setup
        # For now, return a default role
        return UserRole.USER


# =============================================================================
# INDIVIDUAL DECORATOR FUNCTIONS FOR BACKWARD COMPATIBILITY
# =============================================================================

# Global instance for individual decorator functions
_default_decorators_instance: Optional[BotDecorators] = None

def initialize_decorators(db: DatabaseManager, config: Any) -> None:
    """Initialize the global decorators instance.
    
    Args:
        db: Database manager instance
        config: Bot configuration
    """
    global _default_decorators_instance
    _default_decorators_instance = BotDecorators(db, config)

def get_decorators_instance() -> Optional[BotDecorators]:
    """Get the global decorators instance.
    
    Returns:
        BotDecorators instance or None if not initialized
    """
    return _default_decorators_instance


# Individual decorator functions that use the global instance
def with_user_access(func: Callable) -> Callable:
    """Decorator to require user access (individual function version).
    
    Args:
        func: Handler function to decorate
        
    Returns:
        Decorated function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if _default_decorators_instance is None:
            raise RuntimeError("Decorators not initialized. Call initialize_decorators() first.")
        return await _default_decorators_instance.require_user_access(func)(*args, **kwargs)
    return wrapper


def require_admin(func: Callable) -> Callable:
    """Decorator to require admin role (individual function version).
    
    Args:
        func: Handler function to decorate
        
    Returns:
        Decorated function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if _default_decorators_instance is None:
            raise RuntimeError("Decorators not initialized. Call initialize_decorators() first.")
        return await _default_decorators_instance.require_admin(func)(*args, **kwargs)
    return wrapper


def require_super_admin(func: Callable) -> Callable:
    """Decorator to require super admin role (individual function version).
    
    Args:
        func: Handler function to decorate
        
    Returns:
        Decorated function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if _default_decorators_instance is None:
            raise RuntimeError("Decorators not initialized. Call initialize_decorators() first.")
        return await _default_decorators_instance.require_super_admin(func)(*args, **kwargs)
    return wrapper


def rate_limit(max_calls: int = 10, window_seconds: int = 60, per_user: bool = True, per_chat: bool = False):
    """Decorator to implement rate limiting (individual function version).
    
    Args:
        max_calls: Maximum calls allowed
        window_seconds: Time window in seconds
        per_user: Apply rate limit per user
        per_chat: Apply rate limit per chat
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if _default_decorators_instance is None:
                raise RuntimeError("Decorators not initialized. Call initialize_decorators() first.")
            decorated = _default_decorators_instance.rate_limit(max_calls, window_seconds, per_user, per_chat)(func)
            return await decorated(*args, **kwargs)
        return wrapper
    return decorator


def log_handler_calls(func: Callable) -> Callable:
    """Decorator to log handler calls (individual function version).
    
    Args:
        func: Handler function to decorate
        
    Returns:
        Decorated function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if _default_decorators_instance is None:
            raise RuntimeError("Decorators not initialized. Call initialize_decorators() first.")
        return await _default_decorators_instance.log_handler_calls(func)(*args, **kwargs)
    return wrapper


# Alias for backward compatibility
AuthDecorator = BotDecorators