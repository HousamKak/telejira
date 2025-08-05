#!/usr/bin/env python3
"""
Decorators for the Telegram-Jira bot.

Contains decorators for authentication, authorization, rate limiting, and other cross-cutting concerns.
"""

import asyncio
import functools
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, Any, Optional, List, Union

from telegram import Update
from telegram.ext import ContextTypes

from ..models.enums import UserRole, ErrorType
from ..models.user import User
from ..services.database import DatabaseManager, DatabaseError
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
            max_calls: Maximum number of calls allowed
            window_seconds: Time window in seconds
            per_user: Whether to apply limit per user
            per_chat: Whether to apply limit per chat
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                # Determine rate limit key
                key_parts = [func.__name__]
                
                if per_user and update.effective_user:
                    key_parts.append(f"user_{update.effective_user.id}")
                
                if per_chat and update.effective_chat:
                    key_parts.append(f"chat_{update.effective_chat.id}")
                
                if not per_user and not per_chat:
                    key_parts.append("global")
                
                rate_key = "_".join(key_parts)
                
                # Check rate limit
                now = time.time()
                if rate_key not in self._rate_limit_cache:
                    self._rate_limit_cache[rate_key] = {
                        'calls': [],
                        'window_start': now
                    }
                
                cache_entry = self._rate_limit_cache[rate_key]
                
                # Clean old calls outside the window
                cache_entry['calls'] = [
                    call_time for call_time in cache_entry['calls']
                    if now - call_time < window_seconds
                ]
                
                # Check if limit exceeded
                if len(cache_entry['calls']) >= max_calls:
                    oldest_call = min(cache_entry['calls'])
                    retry_after = int(window_seconds - (now - oldest_call))
                    
                    await self._send_rate_limit_message(update, retry_after)
                    return
                
                # Record this call
                cache_entry['calls'].append(now)
                
                return await func(update, context, *args, **kwargs)
            
            return wrapper
        return decorator

    def log_errors(self, send_error_message: bool = True) -> Callable:
        """Decorator to log errors and optionally send error messages.
        
        Args:
            send_error_message: Whether to send error message to user
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                try:
                    return await func(update, context, *args, **kwargs)
                except Exception as e:
                    # Log the error with context
                    user_id = update.effective_user.id if update.effective_user else "unknown"
                    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
                    
                    self.logger.error(
                        f"Error in handler {func.__name__}: {e}",
                        extra={
                            'user_id': user_id,
                            'chat_id': chat_id,
                            'function': func.__name__,
                            'error_type': type(e).__name__
                        },
                        exc_info=True
                    )
                    
                    # Send error message to user if requested
                    if send_error_message:
                        error_type = self._get_error_type(e)
                        await self._send_error_message(update, self._get_error_message(e), error_type)
                    
                    # Re-raise the exception if it's a known bot exception
                    if isinstance(e, (RateLimitExceeded, PermissionDenied)):
                        raise
            
            return wrapper
        return decorator

    def measure_performance(self, warn_threshold: float = 2.0) -> Callable:
        """Decorator to measure and log handler performance.
        
        Args:
            warn_threshold: Threshold in seconds to log warning
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                start_time = time.time()
                
                try:
                    result = await func(update, context, *args, **kwargs)
                    return result
                finally:
                    end_time = time.time()
                    execution_time = end_time - start_time
                    
                    user_id = update.effective_user.id if update.effective_user else "unknown"
                    
                    if execution_time > warn_threshold:
                        self.logger.warning(
                            f"Slow handler {func.__name__}: {execution_time:.2f}s",
                            extra={
                                'user_id': user_id,
                                'function': func.__name__,
                                'execution_time': execution_time
                            }
                        )
                    else:
                        self.logger.debug(
                            f"Handler {func.__name__} completed in {execution_time:.2f}s",
                            extra={
                                'user_id': user_id,
                                'function': func.__name__,
                                'execution_time': execution_time
                            }
                        )
            
            return wrapper
        return decorator

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

    def cache_result(self, cache_key_func: Callable, ttl_seconds: int = 300) -> Callable:
        """Decorator to cache handler results.
        
        Args:
            cache_key_func: Function to generate cache key from arguments
            ttl_seconds: Time to live for cached results
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            cache: Dict[str, Dict[str, Any]] = {}
            
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                # Generate cache key
                try:
                    cache_key = cache_key_func(update, context, *args, **kwargs)
                except Exception as e:
                    self.logger.warning(f"Cache key generation failed: {e}")
                    # Proceed without caching
                    return await func(update, context, *args, **kwargs)
                
                # Check cache
                now = time.time()
                if cache_key in cache:
                    cache_entry = cache[cache_key]
                    if now - cache_entry['timestamp'] < ttl_seconds:
                        self.logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                        return cache_entry['result']
                
                # Execute function and cache result
                result = await func(update, context, *args, **kwargs)
                cache[cache_key] = {
                    'result': result,
                    'timestamp': now
                }
                
                # Clean old cache entries (simple cleanup)
                expired_keys = [
                    key for key, entry in cache.items()
                    if now - entry['timestamp'] >= ttl_seconds
                ]
                for key in expired_keys:
                    del cache[key]
                
                return result
            
            return wrapper
        return decorator

    def retry_on_failure(
        self,
        max_retries: int = 3,
        delay_seconds: float = 1.0,
        backoff_factor: float = 2.0,
        exceptions: tuple = (Exception,)
    ) -> Callable:
        """Decorator to retry handler on failure.
        
        Args:
            max_retries: Maximum number of retry attempts
            delay_seconds: Initial delay between retries
            backoff_factor: Factor to multiply delay by for each retry
            exceptions: Tuple of exceptions to retry on
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
                last_exception = None
                delay = delay_seconds
                
                for attempt in range(max_retries + 1):
                    try:
                        return await func(update, context, *args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        
                        if attempt < max_retries:
                            self.logger.warning(
                                f"Handler {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                            )
                            await asyncio.sleep(delay)
                            delay *= backoff_factor
                        else:
                            self.logger.error(
                                f"Handler {func.__name__} failed after {max_retries + 1} attempts: {e}"
                            )
                
                # Re-raise the last exception
                if last_exception:
                    raise last_exception
            
            return wrapper
        return decorator

    # Helper methods
    async def _ensure_user_exists(self, telegram_user) -> User:
        """Ensure user exists in database and update activity."""
        try:
            user = await self.db.get_user(telegram_user.id)
            if user:
                await self.db.update_user_activity(telegram_user.id)
                return user
            else:
                # Create new user
                new_user = User.from_telegram_user(telegram_user)
                await self.db.save_user(new_user)
                return new_user
        except DatabaseError as e:
            self.logger.error(f"Failed to ensure user exists: {e}")
            raise

    async def _get_user_role(self, user_id: int) -> UserRole:
        """Get user role with caching."""
        # Check cache first
        if user_id in self._permission_cache:
            cache_entry = self._permission_cache[user_id]
            if time.time() - cache_entry['timestamp'] < 300:  # 5 minute cache
                return cache_entry['role']
        
        # Check config first (faster)
        if self.config.is_user_super_admin(user_id):
            role = UserRole.SUPER_ADMIN
        elif self.config.is_user_admin(user_id):
            role = UserRole.ADMIN
        else:
            # Check database
            try:
                user = await self.db.get_user(user_id)
                role = user.role if user else UserRole.USER
            except DatabaseError:
                role = UserRole.USER
        
        # Cache the result
        self._permission_cache[user_id] = {
            'role': role,
            'timestamp': time.time()
        }
        
        return role

    def _get_error_type(self, exception: Exception) -> ErrorType:
        """Determine error type from exception."""
        if isinstance(exception, DatabaseError):
            return ErrorType.DATABASE_ERROR
        elif isinstance(exception, PermissionDenied):
            return ErrorType.PERMISSION_ERROR
        elif isinstance(exception, RateLimitExceeded):
            return ErrorType.TIMEOUT_ERROR
        elif isinstance(exception, ValueError):
            return ErrorType.VALIDATION_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR

    def _get_error_message(self, exception: Exception) -> str:
        """Get user-friendly error message."""
        error_type = self._get_error_type(exception)
        return ERROR_MESSAGES.get(error_type.value.upper(), str(exception))

    async def _send_access_denied_message(self, update: Update) -> None:
        """Send access denied message."""
        message = f"{EMOJI['ERROR']} You don't have access to this bot. Please contact an administrator."
        await self._send_message(update, message)

    async def _send_permission_denied_message(self, update: Update, required_role: str) -> None:
        """Send permission denied message."""
        message = f"{EMOJI['ERROR']} You need {required_role} permissions to use this command."
        await self._send_message(update, message)

    async def _send_rate_limit_message(self, update: Update, retry_after: int) -> None:
        """Send rate limit exceeded message."""
        message = f"{EMOJI['WARNING']} Rate limit exceeded. Please try again in {retry_after} seconds."
        await self._send_message(update, message)

    async def _send_error_message(self, update: Update, error_message: str, error_type: ErrorType = ErrorType.UNKNOWN_ERROR) -> None:
        """Send generic error message."""
        emoji = error_type.get_emoji()
        message = f"{emoji} {error_message}"
        await self._send_message(update, message)

    async def _send_validation_error_message(self, update: Update, field_name: str) -> None:
        """Send validation error message."""
        message = f"{EMOJI['ERROR']} Invalid {field_name}. Please check your input and try again."
        await self._send_message(update, message)

    async def _send_private_chat_required_message(self, update: Update) -> None:
        """Send private chat required message."""
        message = f"{EMOJI['INFO']} This command can only be used in private chat."
        await self._send_message(update, message)

    async def _send_group_chat_required_message(self, update: Update) -> None:
        """Send group chat required message."""
        message = f"{EMOJI['INFO']} This command can only be used in group chats."  
        await self._send_message(update, message)

    async def _send_message(self, update: Update, message: str) -> None:
        """Send message to user with error handling."""
        try:
            if update.effective_chat:
                await update.effective_chat.send_message(message)
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")


# Convenience decorators that can be used without instantiating BotDecorators
def user_access_required(db: DatabaseManager, config: Any):
    """Factory function for user access decorator."""
    decorators = BotDecorators(db, config)
    return decorators.require_user_access

def admin_required(db: DatabaseManager, config: Any):
    """Factory function for admin decorator."""
    decorators = BotDecorators(db, config)
    return decorators.require_admin

def rate_limited(max_calls: int = 10, window_seconds: int = 60):
    """Factory function for rate limit decorator."""
    def decorator_factory(db: DatabaseManager, config: Any):
        decorators = BotDecorators(db, config)
        return decorators.rate_limit(max_calls, window_seconds)
    return decorator_factory

def error_handler(send_message: bool = True):
    """Factory function for error handler decorator."""
    def decorator_factory(db: DatabaseManager, config: Any):
        decorators = BotDecorators(db, config)
        return decorators.log_errors(send_message)
    return decorator_factory