#!/usr/bin/env python3
"""
Models package for the Telegram-Jira bot.

This package contains all data models used throughout the application including
Project, JiraIssue, IssueComment, User, UserPreferences, UserSession, and enums.

Models provide comprehensive validation, serialization, and business logic
for all bot operations.
"""

import logging
from typing import TYPE_CHECKING

# Import all models for package exports
try:
    from .enums import (
        IssuePriority,
        IssueType, 
        IssueStatus,
        UserRole,
        CommandShortcut,
        WizardState,
        ErrorType
    )
    from .project import Project, ProjectSummary, ProjectStats
    from .issue import JiraIssue, IssueComment, IssueSearchResult
    from .user import User, UserPreferences, UserSession
    
except ImportError as e:
    logging.getLogger(__name__).warning(f"Failed to import some models: {e}")
    # For development/testing, continue without failing
    pass

# Package metadata
__version__ = "2.1.0"
__author__ = "AI Assistant"
__description__ = "Data models for Telegram-Jira Bot"

# Export all public models and enums
__all__ = [
    # Enums
    "IssuePriority",
    "IssueType",
    "IssueStatus", 
    "UserRole",
    "CommandShortcut",
    "WizardState",
    "ErrorType",
    
    # Project models
    "Project",
    "ProjectSummary", 
    "ProjectStats",
    
    # Issue models
    "JiraIssue",
    "IssueComment",
    "IssueSearchResult",
    
    # User models
    "User",
    "UserPreferences",
    "UserSession"
]

# Model validation configuration
MODEL_CONFIG = {
    "validate_on_init": True,
    "strict_type_checking": True,
    "require_all_fields": True,
    "auto_update_timestamps": True
}

if TYPE_CHECKING:
    # Type checking imports - only available during static analysis
    from datetime import datetime
    from typing import Dict, Any, Optional, List, Union