#!/usr/bin/env python3
"""
Utilities package for the Telegram-Jira bot.

Contains utility functions, validators, formatters, decorators, and constants.
"""

from typing import Dict, Any, Optional
import warnings

# Core utilities that should always be available
__all__ = []

# Import constants - these are heavily used throughout the codebase
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
    __all__.extend([
        "EMOJI",
        "ERROR_MESSAGES", 
        "SUCCESS_MESSAGES",
        "INFO_MESSAGES",
        "COMMAND_SHORTCUTS",
        "BOT_INFO",
        "MAX_MESSAGE_LENGTH",
        "MAX_SUMMARY_LENGTH"
    ])
except ImportError as e:
    warnings.warn(f"Constants import failed: {e}", ImportWarning)

# Import validators - used for input validation
try:
    from .validators import (
        InputValidator,
        ValidationResult,
        ValidationError
    )
    __all__.extend([
        "InputValidator",
        "ValidationResult",
        "ValidationError"
    ])
except ImportError as e:
    warnings.warn(f"Validators import failed: {e}", ImportWarning)

# Import formatters - used for message formatting
try:
    from .formatters import MessageFormatter
    __all__.extend(["MessageFormatter"])
except ImportError as e:
    warnings.warn(f"Formatters import failed: {e}", ImportWarning)

# Import decorators - note: these are class-based, not individual functions
try:
    from .decorators import (
        BotDecorators,
        RateLimitExceeded,
        PermissionDenied
    )
    __all__.extend([
        "BotDecorators",
        "RateLimitExceeded", 
        "PermissionDenied"
    ])
except ImportError as e:
    warnings.warn(f"Decorators import failed: {e}", ImportWarning)

# Import keyboard utilities - used by wizard handlers
try:
    from .keyboards import (
        cb,
        parse_cb,
        build_project_list_keyboard,
        build_issue_type_keyboard,
        build_issue_priority_keyboard,
        build_confirm_keyboard,
        build_back_cancel_keyboard,
        build_pagination_keyboard,
        build_menu_keyboard
    )
    __all__.extend([
        "cb",
        "parse_cb",
        "build_project_list_keyboard",
        "build_issue_type_keyboard",
        "build_issue_priority_keyboard",
        "build_confirm_keyboard",
        "build_back_cancel_keyboard",
        "build_pagination_keyboard",
        "build_menu_keyboard"
    ])
except ImportError as e:
    warnings.warn(f"Keyboard utilities import failed: {e}", ImportWarning)

# Import message utilities - used by wizard handlers
try:
    from .messages import (
        html_escape,
        setup_welcome_message,
        confirm_project_message,
        quick_issue_summary_message,
        no_projects_message,
        issue_created_success_message,
        project_selection_message,
        issue_type_selection_message,
        issue_priority_selection_message,
        summary_input_message,
        description_input_message,
        validation_error_message,
        wizard_error_message,
        setup_complete_message,
        wizard_cancelled_message,
        loading_message,
        pagination_info,
        back_navigation_message,
        truncate_text
    )
    __all__.extend([
        "html_escape",
        "setup_welcome_message",
        "confirm_project_message",
        "quick_issue_summary_message",
        "no_projects_message",
        "issue_created_success_message",
        "project_selection_message",
        "issue_type_selection_message",
        "issue_priority_selection_message",
        "summary_input_message",
        "description_input_message",
        "validation_error_message",
        "wizard_error_message",
        "setup_complete_message",
        "wizard_cancelled_message",
        "loading_message",
        "pagination_info",
        "back_navigation_message",
        "truncate_text"
    ])
except ImportError as e:
    warnings.warn(f"Message utilities import failed: {e}", ImportWarning)

# Package metadata
__version__ = "2.1.0"
__author__ = "AI Assistant"
__description__ = "Utilities package for Telegram-Jira bot"

def get_version() -> str:
    """Get the package version.
    
    Returns:
        Version string
    """
    return __version__

def get_package_info() -> Dict[str, Any]:
    """Get package information.
    
    Returns:
        Dictionary with package metadata
    """
    return {
        "name": "telegram_jira_bot.utils",
        "version": __version__,
        "author": __author__,
        "description": __description__
    }

# Backward compatibility helpers
def create_bot_decorators(db_manager, config):
    """Helper function to create BotDecorators instance.
    
    This provides backward compatibility for code expecting individual
    decorator functions.
    
    Args:
        db_manager: Database manager instance
        config: Bot configuration
        
    Returns:
        BotDecorators instance
    """
    try:
        return BotDecorators(db_manager, config)
    except NameError:
        warnings.warn("BotDecorators not available", ImportWarning)
        return None