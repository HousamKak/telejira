# =============================================================================
# telegram_jira_bot/handlers/__init__.py
# =============================================================================
#!/usr/bin/env python3
"""
Handlers package for the Telegram-Jira bot.

Contains all command handlers and callback handlers for bot functionality.
"""

try:
    from .base_handler import BaseHandler
    from .admin_handlers import AdminHandlers
    from .project_handlers import ProjectHandlers  
    from .issue_handlers import IssueHandlers
    from .wizard_handlers import WizardHandlers
    
    __all__ = [
        "BaseHandler",
        "AdminHandlers",
        "ProjectHandlers",
        "IssueHandlers", 
        "WizardHandlers"
    ]
    
except ImportError as e:
    import warnings
    warnings.warn(f"Handler imports failed: {e}", ImportWarning)
    __all__ = []