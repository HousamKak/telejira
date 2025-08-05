# =============================================================================
# telegram_jira_bot/utils/__init__.py
# =============================================================================
#!/usr/bin/env python3
"""
Utilities package for the Telegram-Jira bot.

Contains utility functions, validators, formatters, decorators, and constants.
"""

try:
    from .constants import (
        EMOJI,
        ERROR_MESSAGES,
        SUCCESS_MESSAGES,
        INFO_MESSAGES,
        COMMAND_SHORTCUTS,
        BOT_INFO,
        MAX_MESSAGE_LENGTH,
        MAX_SUMMARY_LENGTH
    )
    from .validators import (
        InputValidator,
        ValidationResult,
        ValidationError
    )
    from .formatters import MessageFormatter
    from .decorators import (
        AuthDecorator,
        with_user_access,
        require_admin,
        require_super_admin,
        rate_limit,
        log_handler_calls
    )
    
    __all__ = [
        # Constants
        "EMOJI",
        "ERROR_MESSAGES", 
        "SUCCESS_MESSAGES",
        "INFO_MESSAGES",
        "COMMAND_SHORTCUTS",
        "BOT_INFO",
        "MAX_MESSAGE_LENGTH",
        "MAX_SUMMARY_LENGTH",
        
        # Validators
        "InputValidator",
        "ValidationResult",
        "ValidationError",
        
        # Formatters
        "MessageFormatter",
        
        # Decorators
        "AuthDecorator",
        "with_user_access",
        "require_admin", 
        "require_super_admin",
        "rate_limit",
        "log_handler_calls"
    ]
    
except ImportError as e:
    import warnings
    warnings.warn(f"Utilities imports failed: {e}", ImportWarning)
    __all__ = []


# Helper functions for common operations
def get_version() -> str:
    """Get the package version.
    
    Returns:
        Version string
    """
    from . import __version__
    return __version__

def get_package_info() -> Dict[str, Any]:
    """Get package information.
    
    Returns:
        Dictionary with package metadata
    """
    from . import __package_info__
    return __package_info__.copy()