# # =============================================================================
# # telegram_jira_bot/__init__.py
# # =============================================================================
# #!/usr/bin/env python3
# """
# Telegram-Jira Bot Package

# A comprehensive Telegram bot for seamless Jira integration.
# Provides project management, issue tracking, and team collaboration features.
# """

# import sys
# from typing import Dict, Any

# # Version information
# __version__ = "2.1.0"
# __author__ = "AI Assistant"
# __email__ = "ai-assistant@example.com"
# __description__ = "A comprehensive Telegram bot for seamless Jira integration"
# __license__ = "MIT"

# # Minimum Python version check
# if sys.version_info < (3, 9):
#     raise RuntimeError(
#         f"This package requires Python 3.9 or higher. "
#         f"You are using Python {sys.version_info.major}.{sys.version_info.minor}."
#     )

# # Package metadata
# __package_info__: Dict[str, Any] = {
#     "name": "telegram-jira-bot",
#     "version": __version__,
#     "description": __description__,
#     "author": __author__,
#     "author_email": __email__,
#     "license": __license__,
#     "python_requires": ">=3.9",
#     "keywords": [
#         "telegram", "bot", "jira", "atlassian", "issue-tracking",
#         "project-management", "automation", "productivity"
#     ],
#     "classifiers": [
#         "Development Status :: 4 - Beta",
#         "Intended Audience :: Developers",
#         "Topic :: Communications :: Chat",
#         "Topic :: Office/Business :: Groupware",
#         "License :: OSI Approved :: MIT License",
#         "Programming Language :: Python :: 3",
#         "Programming Language :: Python :: 3.9",
#         "Programming Language :: Python :: 3.10",
#         "Programming Language :: Python :: 3.11",
#         "Programming Language :: Python :: 3.12",
#     ]
# }

# # Import main components for easy access
# try:
#     from .config.settings import BotConfig, load_config
#     from .models.enums import UserRole, IssuePriority, IssueType, IssueStatus
#     from .models.user import User
#     from .models.project import Project
#     from .models.issue import JiraIssue
#     from .services.database import DatabaseManager
#     from .services.jira_service import JiraService
#     from .services.telegram_service import TelegramService
    
#     __all__ = [
#         "__version__",
#         "__author__", 
#         "__description__",
#         "__license__",
#         "BotConfig",
#         "load_config",
#         "UserRole",
#         "IssuePriority", 
#         "IssueType",
#         "IssueStatus",
#         "User",
#         "Project",
#         "JiraIssue",
#         "DatabaseManager",
#         "JiraService",
#         "TelegramService"
#     ]
    
# except ImportError as e:
#     # Handle import errors gracefully during development
#     import warnings
#     warnings.warn(f"Some components could not be imported: {e}", ImportWarning)
#     __all__ = ["__version__", "__author__", "__description__", "__license__"]