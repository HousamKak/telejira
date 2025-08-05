#!/usr/bin/env python3
"""
Enumerations for the Telegram-Jira bot.

Contains all enum classes used throughout the application for type safety
and consistent value handling.
"""

from enum import Enum
from typing import List, Type, TypeVar, cast

# Type variable for enum type hints
T = TypeVar('T', bound='BaseEnum')


class BaseEnum(Enum):
    """Base enum class with common functionality."""
    
    @classmethod
    def from_string(cls: Type[T], value: str) -> T:
        """Create enum from string with case-insensitive matching.
        
        Args:
            value: String value to match
            
        Returns:
            Corresponding enum instance
            
        Raises:
            TypeError: If value is not a string
            ValueError: If value doesn't match any enum member
        """
        if not isinstance(value, str):
            raise TypeError("value must be a string")
        
        value_normalized = value.strip().lower()
        if not value_normalized:
            raise ValueError(f"Invalid {cls.__name__}: empty string")
        
        for member in cls:
            if member.value.lower() == value_normalized:
                return member
        
        # Try alternative matches
        for member in cls:
            if member.name.lower() == value_normalized:
                return member
        
        valid_values = [member.value for member in cls]
        raise ValueError(f"Invalid {cls.__name__}: {value}. Valid options: {valid_values}")
    
    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all enum values as a list.
        
        Returns:
            List of all enum values
        """
        return [member.value for member in cls]


class IssuePriority(BaseEnum):
    """Jira issue priority levels."""
    CRITICAL = "Critical"
    HIGH = "High" 
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"

    def get_emoji(self) -> str:
        """Get emoji representation for the priority.
        
        Returns:
            Priority emoji
        """
        emoji_map = {
            self.CRITICAL: "🚨",
            self.HIGH: "🔴", 
            self.MEDIUM: "🟡",
            self.LOW: "🟢",
            self.LOWEST: "⚪"
        }
        return emoji_map.get(self, "❓")
    
    def get_numeric_value(self) -> int:
        """Get numeric value for sorting/comparison.
        
        Returns:
            Numeric priority value (higher = more important)
        """
        value_map = {
            self.CRITICAL: 5,
            self.HIGH: 4,
            self.MEDIUM: 3, 
            self.LOW: 2,
            self.LOWEST: 1
        }
        return value_map.get(self, 0)


class IssueType(BaseEnum):
    """Jira issue types."""
    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"
    EPIC = "Epic"
    IMPROVEMENT = "Improvement"
    SUBTASK = "Sub-task"

    def get_emoji(self) -> str:
        """Get emoji representation for the issue type.
        
        Returns:
            Issue type emoji
        """
        emoji_map = {
            self.TASK: "📋",
            self.BUG: "🐛",
            self.STORY: "📖", 
            self.EPIC: "🚀",
            self.IMPROVEMENT: "⚡",
            self.SUBTASK: "📝"
        }
        return emoji_map.get(self, "📄")


class IssueStatus(BaseEnum):
    """Jira issue status levels."""
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    CLOSED = "Closed"
    REOPENED = "Reopened"
    RESOLVED = "Resolved"
    
    # Additional common statuses
    OPEN = "Open"
    IN_REVIEW = "In Review"
    TESTING = "Testing"
    BLOCKED = "Blocked"

    def get_emoji(self) -> str:
        """Get emoji representation for the status.
        
        Returns:
            Status emoji
        """
        emoji_map = {
            self.TODO: "📝",
            self.OPEN: "📂",
            self.IN_PROGRESS: "⏳",
            self.IN_REVIEW: "👀",
            self.TESTING: "🧪",
            self.BLOCKED: "🚫",
            self.DONE: "✅",
            self.CLOSED: "🔒",
            self.REOPENED: "🔄", 
            self.RESOLVED: "✅"
        }
        return emoji_map.get(self, "❓")
    
    def is_final_status(self) -> bool:
        """Check if this is a final/completed status.
        
        Returns:
            True if status indicates completion
        """
        final_statuses = {self.DONE, self.CLOSED, self.RESOLVED}
        return self in final_statuses


class UserRole(BaseEnum):
    """User roles in the bot with permission hierarchy."""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

    def has_permission(self, required_role: 'UserRole') -> bool:
        """Check if this role has the required permission level.
        
        Args:
            required_role: Minimum role required
            
        Returns:
            True if this role has sufficient permissions
        """
        role_hierarchy = {
            self.USER: 1,
            self.ADMIN: 2,
            self.SUPER_ADMIN: 3
        }
        current_level = role_hierarchy.get(self, 0)
        required_level = role_hierarchy.get(required_role, 0)
        return current_level >= required_level
    
    def get_display_name(self) -> str:
        """Get formatted display name for the role.
        
        Returns:
            Human-readable role name
        """
        display_map = {
            self.USER: "User",
            self.ADMIN: "Administrator", 
            self.SUPER_ADMIN: "Super Administrator"
        }
        return display_map.get(self, "Unknown")
    
    def get_emoji(self) -> str:
        """Get emoji representation for the role.
        
        Returns:
            Role emoji
        """
        emoji_map = {
            self.USER: "👤",
            self.ADMIN: "🛡️",
            self.SUPER_ADMIN: "👑"
        }
        return emoji_map.get(self, "❓")


class CommandShortcut(BaseEnum):
    """Command shortcuts for faster access."""
    # Project shortcuts
    PROJECTS = "p"
    ADD_PROJECT = "ap"
    EDIT_PROJECT = "ep"
    DELETE_PROJECT = "dp"
    SET_DEFAULT = "sd"
    
    # Issue shortcuts
    CREATE_ISSUE = "c"
    LIST_ISSUES = "li"
    MY_ISSUES = "mi"
    SEARCH_ISSUES = "si"
    
    # Admin shortcuts
    STATUS = "s"
    USERS = "u"
    SYNC_JIRA = "sync"
    
    # Wizard shortcuts
    WIZARD = "w"
    QUICK = "q"

    def get_full_command(self) -> str:
        """Get the full command name for this shortcut.
        
        Returns:
            Full command string
        """
        command_map = {
            self.PROJECTS: "projects",
            self.ADD_PROJECT: "addproject",
            self.EDIT_PROJECT: "editproject", 
            self.DELETE_PROJECT: "deleteproject",
            self.SET_DEFAULT: "setdefault",
            self.CREATE_ISSUE: "create",
            self.LIST_ISSUES: "listissues",
            self.MY_ISSUES: "myissues",
            self.SEARCH_ISSUES: "searchissues",
            self.STATUS: "status",
            self.USERS: "users",
            self.SYNC_JIRA: "syncjira",
            self.WIZARD: "wizard",
            self.QUICK: "quick"
        }
        return command_map.get(self, self.value)


class WizardState(BaseEnum):
    """States for interactive wizards."""
    IDLE = "idle"
    
    # Project wizard states
    PROJECT_SELECTING_ACTION = "project_action"
    PROJECT_ENTERING_KEY = "project_key"
    PROJECT_ENTERING_NAME = "project_name"
    PROJECT_ENTERING_DESCRIPTION = "project_description"
    PROJECT_CONFIRMING = "project_confirm"
    
    # Issue wizard states
    ISSUE_SELECTING_PROJECT = "issue_project"
    ISSUE_SELECTING_TYPE = "issue_type"
    ISSUE_SELECTING_PRIORITY = "issue_priority"
    ISSUE_ENTERING_SUMMARY = "issue_summary"
    ISSUE_ENTERING_DESCRIPTION = "issue_description"
    ISSUE_CONFIRMING = "issue_confirm"
    
    # Edit wizard states
    EDIT_SELECTING_FIELD = "edit_field"
    EDIT_ENTERING_VALUE = "edit_value"
    EDIT_CONFIRMING = "edit_confirm"
    
    def is_active(self) -> bool:
        """Check if wizard is actively running.
        
        Returns:
            True if wizard is in an active state
        """
        return self != self.IDLE


class ErrorType(BaseEnum):
    """Types of errors that can occur in the bot."""
    VALIDATION_ERROR = "validation"
    DATABASE_ERROR = "database"
    JIRA_API_ERROR = "jira_api"
    TELEGRAM_ERROR = "telegram"
    PERMISSION_ERROR = "permission"
    NOT_FOUND_ERROR = "not_found"
    CONFIGURATION_ERROR = "configuration"
    NETWORK_ERROR = "network"
    TIMEOUT_ERROR = "timeout"
    UNKNOWN_ERROR = "unknown"

    def get_emoji(self) -> str:
        """Get emoji representation for the error type.
        
        Returns:
            Error type emoji
        """
        emoji_map = {
            self.VALIDATION_ERROR: "⚠️",
            self.DATABASE_ERROR: "💾",
            self.JIRA_API_ERROR: "🔗",
            self.TELEGRAM_ERROR: "📱",
            self.PERMISSION_ERROR: "🔐",
            self.NOT_FOUND_ERROR: "🔍",
            self.CONFIGURATION_ERROR: "⚙️",
            self.NETWORK_ERROR: "🌐",
            self.TIMEOUT_ERROR: "⏰",
            self.UNKNOWN_ERROR: "❓"
        }
        return emoji_map.get(self, "❗")
    
    def is_user_error(self) -> bool:
        """Check if this is a user-caused error.
        
        Returns:
            True if error was caused by user input/action
        """
        user_errors = {
            self.VALIDATION_ERROR,
            self.PERMISSION_ERROR, 
            self.NOT_FOUND_ERROR
        }
        return self in user_errors