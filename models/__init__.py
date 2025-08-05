"""
Models package for the Telegram-Jira Bot.

This package contains all data models, enums, and related utilities for the bot.
All models include proper type hints, validation, and serialization methods.

Usage:
    from models import User, Project, JiraIssue, IssueType, IssuePriority
    from models import UserRole, IssueStatus, WizardState
"""

from __future__ import annotations

# Import all models and enums from the consolidated models module
from .models import (
    # Core enums
    UserRole,
    IssueType,
    IssuePriority,
    IssueStatus,
    ErrorType,
    WizardState,
    
    # Data classes
    User,
    Project,
    JiraIssue,
    IssueComment,
    IssueSearchResult,
    SentMessages,
)

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
    
    # Data classes
    "User",
    "Project",
    "JiraIssue",
    "IssueComment",
    "IssueSearchResult",
    "SentMessages",
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
        "data_models": {
            "User": "Main user model representing a Telegram user",
            "Project": "Main project model representing a Jira project",
            "JiraIssue": "Main issue model representing a Jira issue",
            "IssueComment": "Issue comment model",
            "IssueSearchResult": "Search results container for issues",
            "SentMessages": "Container for sent Telegram message information"
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


# Add utility functions to exports
__all__.extend([
    "get_model_info",
    "validate_enum_value", 
    "get_enum_values",
    "get_enum_names",
    "get_priority_emoji",
    "get_issue_type_emoji", 
    "get_status_emoji",
    "get_role_emoji",
    "validate_project_key",
    "validate_issue_key",
    "validate_telegram_user_id"
])