#!/usr/bin/env python3
"""
Services package for the Telegram-Jira bot.

Contains service classes for database operations, Jira API integration,
and Telegram bot functionality.
"""

import warnings

__all__ = []

try:
    from .database import (DatabaseManager, DatabaseError)
    __all__.extend(["DatabaseManager", "DatabaseError"])
except ImportError as e:
    warnings.warn(f"Database service import failed: {e}", ImportWarning)

try:
    from .jira_service import (JiraService, JiraAPIError)
    __all__.extend(["JiraService", "JiraAPIError"])
except ImportError as e:
    warnings.warn(f"Jira service import failed: {e}", ImportWarning)

try:
    from .telegram_service import TelegramService
    __all__.append("TelegramService")
except ImportError as e:
    warnings.warn(f"Telegram service import failed: {e}", ImportWarning)

# Package metadata
__version__ = "2.1.0"
__description__ = "Service layer for Telegram-Jira bot"