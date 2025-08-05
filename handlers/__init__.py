#!/usr/bin/env python3
"""
Handlers package for the Telegram-Jira bot.

Contains all command handlers and callback handlers for bot functionality.
"""

import warnings

__all__ = []

try:
    from .base_handler import BaseHandler
    __all__.append("BaseHandler")
except ImportError as e:
    warnings.warn(f"Base handler import failed: {e}", ImportWarning)

try:
    from .admin_handlers import AdminHandlers
    __all__.append("AdminHandlers")
except ImportError as e:
    warnings.warn(f"Admin handlers import failed: {e}", ImportWarning)

try:
    from .project_handlers import ProjectHandlers
    __all__.append("ProjectHandlers")
except ImportError as e:
    warnings.warn(f"Project handlers import failed: {e}", ImportWarning)

try:
    from .issue_handlers import IssueHandlers
    __all__.append("IssueHandlers")
except ImportError as e:
    warnings.warn(f"Issue handlers import failed: {e}", ImportWarning)

try:
    from .wizard_handlers import WizardHandlers
    __all__.append("WizardHandlers")
except ImportError as e:
    warnings.warn(f"Wizard handlers import failed: {e}", ImportWarning)

# Package metadata
__version__ = "2.1.0"
__description__ = "Command and callback handlers for Telegram-Jira bot"