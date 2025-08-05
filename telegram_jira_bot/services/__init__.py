# =============================================================================
# telegram_jira_bot/services/__init__.py
# =============================================================================
#!/usr/bin/env python3
"""
Services package for the Telegram-Jira bot.

Contains service classes for database operations, Jira API integration,
and Telegram bot functionality.
"""

try:
    from .database import DatabaseManager, DatabaseError
    from .jira_service import JiraService, JiraAPIError
    from .telegram_service import TelegramService
    
    __all__ = [
        "DatabaseManager",
        "DatabaseError",
        "JiraService", 
        "JiraAPIError",
        "TelegramService"
    ]
    
except ImportError as e:
    import warnings
    warnings.warn(f"Service imports failed: {e}", ImportWarning)
    __all__ = []
