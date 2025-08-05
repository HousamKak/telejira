#!/usr/bin/env python3
"""
Models package for the Telegram-Jira Bot.

This package contains all data models, enums, and related utilities for the bot.
All models include proper type hints, validation, and serialization methods.

Modules:
    enums: Core enumerations (UserRole, IssueType, IssuePriority, etc.)
    user: User model and related classes
    project: Project model and related classes  
    issue: Issue model and related classes
    models: Additional domain models and utilities

Usage:
    from models import User, Project, JiraIssue, IssueType, IssuePriority
    from models.enums import UserRole, IssueStatus
"""

from __future__ import annotations

# Import core enums
from .enums import (
    UserRole,
    IssueType,
    IssuePriority,
    IssueStatus,
    ErrorType,
)

# Import user models
from .user import (
    User,
    UserPreferences,
    UserSession,
    UserStats,
)

# Import project models
from .project import (
    Project,
    ProjectSummary,
    ProjectStats,
    ProjectSettings,
)

# Import issue models
from .issue import (
    JiraIssue,
    IssueComment,
    IssueTransition,
    IssueSearchResult,
    IssueHistory,
    IssueWorklog,
)

# Import additional models if they exist in models.py
try:
    from .models import (
        WizardState,
    )
except ImportError:
    # If models.py doesn't exist or doesn't have these classes, create minimal versions
    from enum import Enum
    
    class WizardState(Enum):
        """Wizard conversation states for Telegram bot."""
        SETUP_WELCOME = "setup_welcome"
        SETUP_PROJECT_SELECTION = "setup_project_selection"
        SETUP_PROJECT_CONFIRMATION = "setup_project_confirmation"
        ISSUE_PROJECT_SELECTION = "issue_project_selection"
        ISSUE_TYPE_SELECTION = "issue_type_selection"
        ISSUE_PRIORITY_SELECTION = "issue_priority_selection"
        ISSUE_SUMMARY_INPUT = "issue_summary_input"
        ISSUE_DESCRIPTION_INPUT = "issue_description_input"
        ISSUE_CONFIRMATION = "issue_confirmation"


# Version info
__version__ = "2.1.0"
__author__ = "AI Assistant"
__description__ = "Data models for Telegram-Jira Bot"

# Export all public classes and enums
__all__ = [
    # Core enums
    "UserRole",
    "IssueType", 
    "IssuePriority",
    "IssueStatus",
    "ErrorType",
    "WizardState",
    
    # User models
    "User",
    "UserPreferences",
    "UserSession", 
    "UserStats",
    
    # Project models
    "Project",
    "ProjectSummary",
    "ProjectStats",
    "ProjectSettings",
    
    # Issue models
    "JiraIssue",
    "IssueComment",
    "IssueTransition",
    "IssueSearchResult", 
    "IssueHistory",
    "IssueWorklog",
]


def get_model_info() -> dict:
    """Get information about all available models.
    
    Returns:
        Dict containing model names, descriptions, and types
    """
    return {
        "enums": {
            "UserRole": "User role enumeration (guest, user, admin, super_admin)",
            "IssueType": "Jira issue type enumeration (Task, Bug, Story, Epic, Sub-task)",
            "IssuePriority": "Jira issue priority enumeration (Highest, High, Medium, Low, Lowest)",
            "IssueStatus": "Jira issue status enumeration (To Do, In Progress, Done, etc.)",
            "ErrorType": "Error type enumeration for standardized error handling",
            "WizardState": "Wizard conversation states for Telegram bot"
        },
        "user_models": {
            "User": "Main user model representing a Telegram user",
            "UserPreferences": "User preference settings and configuration",
            "UserSession": "User session tracking and management",
            "UserStats": "User activity statistics and metrics"
        },
        "project_models": {
            "Project": "Main project model representing a Jira project",
            "ProjectSummary": "Lightweight project summary for listings",
            "ProjectStats": "Project statistics and metrics",
            "ProjectSettings": "Project-specific settings and configuration"
        },
        "issue_models": {
            "JiraIssue": "Main issue model representing a Jira issue",
            "IssueComment": "Issue comment model",
            "IssueTransition": "Issue status transition model",
            "IssueSearchResult": "Search results container for issues",
            "IssueHistory": "Issue change history tracking",
            "IssueWorklog": "Issue work log entries"
        }
    }


def validate_enum_value(enum_class, value: str) -> bool:
    """Validate if a string value is valid for the given enum class.
    
    Args:
        enum_class: The enum class to validate against
        value: String value to validate
        
    Returns:
        True if value is valid for the enum, False otherwise
    """
    try:
        if hasattr(enum_class, 'from_string'):
            enum_class.from_string(value)
            return True
        else:
            # Try direct value comparison
            return any(item.value.lower() == value.lower() for item in enum_class)
    except (ValueError, AttributeError):
        return False


def get_enum_values(enum_class) -> list:
    """Get all valid values for an enum class.
    
    Args:
        enum_class: The enum class to get values from
        
    Returns:
        List of all enum values
    """
    try:
        return [item.value for item in enum_class]
    except AttributeError:
        return []


def get_enum_names(enum_class) -> list:
    """Get all enum names for an enum class.
    
    Args:
        enum_class: The enum class to get names from
        
    Returns:
        List of all enum names
    """
    try:
        return [item.name for item in enum_class]
    except AttributeError:
        return []


# Convenience functions for common operations
def create_user_from_telegram(telegram_user, role: UserRole = UserRole.USER) -> User:
    """Create a User instance from a Telegram user object.
    
    Args:
        telegram_user: Telegram User object
        role: User role to assign (default: USER)
        
    Returns:
        User instance
    """
    return User(
        user_id=str(telegram_user.id),
        username=telegram_user.username or f"user_{telegram_user.id}",
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
        is_active=True,
        role=role,
    )


def get_priority_emoji(priority: IssuePriority) -> str:
    """Get emoji representation for issue priority.
    
    Args:
        priority: Issue priority enum value
        
    Returns:
        Emoji string representing the priority
    """
    priority_emojis = {
        IssuePriority.HIGHEST: "🔴",
        IssuePriority.HIGH: "🟠",
        IssuePriority.MEDIUM: "🟡",
        IssuePriority.LOW: "🔵", 
        IssuePriority.LOWEST: "⚪"
    }
    return priority_emojis.get(priority, "🟡")


def get_issue_type_emoji(issue_type: IssueType) -> str:
    """Get emoji representation for issue type.
    
    Args:
        issue_type: Issue type enum value
        
    Returns:
        Emoji string representing the issue type
    """
    type_emojis = {
        IssueType.TASK: "📋",
        IssueType.BUG: "🐛",
        IssueType.STORY: "📖", 
        IssueType.EPIC: "🏛️",
        IssueType.SUBTASK: "📝"
    }
    return type_emojis.get(issue_type, "📌")


def get_status_emoji(status: str) -> str:
    """Get emoji representation for issue status.
    
    Args:
        status: Issue status string
        
    Returns:
        Emoji string representing the status
    """
    status_emojis = {
        'To Do': '📋',
        'In Progress': '🔄',
        'Done': '✅',
        'Blocked': '🚫',
        'In Review': '👀',
        'Testing': '🧪',
        'Closed': '🔒'
    }
    return status_emojis.get(status, '📌')


def get_role_emoji(role: UserRole) -> str:
    """Get emoji representation for user role.
    
    Args:
        role: User role enum value
        
    Returns:
        Emoji string representing the role
    """
    role_emojis = {
        UserRole.GUEST: "👤",
        UserRole.USER: "👥", 
        UserRole.ADMIN: "🛡️",
        UserRole.SUPER_ADMIN: "👑"
    }
    return role_emojis.get(role, "👤")


# Model validation utilities
def validate_project_key(key: str) -> bool:
    """Validate project key format.
    
    Args:
        key: Project key to validate
        
    Returns:
        True if key format is valid
    """
    import re
    if not key or not isinstance(key, str):
        return False
    
    # Project keys should be uppercase alphanumeric, typically 2-10 characters
    return bool(re.match(r'^[A-Z][A-Z0-9]{1,9}$', key))


def validate_issue_key(key: str) -> bool:
    """Validate issue key format.
    
    Args:
        key: Issue key to validate
        
    Returns:
        True if key format is valid
    """
    import re
    if not key or not isinstance(key, str):
        return False
    
    # Issue keys should be PROJECT-NUMBER format
    return bool(re.match(r'^[A-Z][A-Z0-9]{1,9}-\d+$', key))


def validate_telegram_user_id(user_id: str) -> bool:
    """Validate Telegram user ID format.
    
    Args:
        user_id: User ID to validate
        
    Returns:
        True if user ID format is valid
    """
    if not user_id or not isinstance(user_id, str):
        return False
    
    # Telegram user IDs are positive integers
    try:
        uid = int(user_id)
        return uid > 0
    except ValueError:
        return False


# Export validation functions too
__all__.extend([
    "get_model_info",
    "validate_enum_value", 
    "get_enum_values",
    "get_enum_names",
    "create_user_from_telegram",
    "get_priority_emoji",
    "get_issue_type_emoji", 
    "get_status_emoji",
    "get_role_emoji",
    "validate_project_key",
    "validate_issue_key",
    "validate_telegram_user_id"
])