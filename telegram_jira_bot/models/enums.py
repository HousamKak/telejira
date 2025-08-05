#!/usr/bin/env python3
"""
Enumerations for the Telegram-Jira bot.

Contains all enum definitions used throughout the application.
"""

from enum import Enum
from typing import List, Union


class IssuePriority(Enum):
    """Jira issue priority levels."""
    LOWEST = "Lowest"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    HIGHEST = "Highest"

    @classmethod
    def from_string(cls, value: str) -> 'IssuePriority':
        """Create IssuePriority from string with case-insensitive matching.
        
        Args:
            value: Priority string to parse
            
        Returns:
            IssuePriority instance
            
        Raises:
            TypeError: If value is not a string
            ValueError: If value doesn't match any priority
        """
        if not isinstance(value, str):
            raise TypeError("value must be a string")
        
        value_upper = value.upper()
        for priority in cls:
            if priority.value.upper() == value_upper:
                return priority
        
        raise ValueError(f"Invalid priority: {value}. Valid options: {[p.value for p in cls]}")

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all priority values as a list."""
        return [priority.value for priority in cls]

    def get_emoji(self) -> str:
        """Get emoji representation for the priority."""
        emoji_map = {
            self.LOWEST: "🔵",
            self.LOW: "🟢", 
            self.MEDIUM: "🟡",
            self.HIGH: "🟠",
            self.HIGHEST: "🔴"
        }
        return emoji_map.get(self, "⚪")


class IssueType(Enum):
    """Jira issue types."""
    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"
    EPIC = "Epic"
    IMPROVEMENT = "Improvement"
    SUBTASK = "Sub-task"

    @classmethod
    def from_string(cls, value: str) -> 'IssueType':
        """Create IssueType from string with case-insensitive matching.
        
        Args:
            value: Issue type string to parse
            
        Returns:
            IssueType instance
            
        Raises:
            TypeError: If value is not a string
            ValueError: If value doesn't match any issue type
        """
        if not isinstance(value, str):
            raise TypeError("value must be a string")
        
        value_upper = value.upper().replace("-", "")
        for issue_type in cls:
            type_upper = issue_type.value.upper().replace("-", "")
            if type_upper == value_upper:
                return issue_type
        
        raise ValueError(f"Invalid issue type: {value}. Valid options: {[t.value for t in cls]}")

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all issue type values as a list."""
        return [issue_type.value for issue_type in cls]

    def get_emoji(self) -> str:
        """Get emoji representation for the issue type."""
        emoji_map = {
            self.TASK: "📋",
            self.BUG: "🐛",
            self.STORY: "📖",
            self.EPIC: "🚀",
            self.IMPROVEMENT: "⚡",
            self.SUBTASK: "📝"
        }
        return emoji_map.get(self, "📄")


class IssueStatus(Enum):
    """Jira issue status levels."""
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    CLOSED = "Closed"
    REOPENED = "Reopened"
    RESOLVED = "Resolved"

    @classmethod
    def from_string(cls, value: str) -> 'IssueStatus':
        """Create IssueStatus from string with case-insensitive matching."""
        if not isinstance(value, str):
            raise TypeError("value must be a string")
        
        value_normalized = value.upper().replace(" ", "_")
        for status in cls:
            status_normalized = status.value.upper().replace(" ", "_")
            if status_normalized == value_normalized:
                return status
        
        raise ValueError(f"Invalid status: {value}. Valid options: {[s.value for s in cls]}")

    def get_emoji(self) -> str:
        """Get emoji representation for the status."""
        emoji_map = {
            self.TO_DO: "📝",
            self.IN_PROGRESS: "⏳",
            self.DONE: "✅",
            self.CLOSED: "🔒",
            self.REOPENED: "🔄",
            self.RESOLVED: "✅"
        }
        return emoji_map.get(self, "❓")


class UserRole(Enum):
    """User roles in the bot."""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

    def has_permission(self, required_role: 'UserRole') -> bool:
        """Check if this role has the required permission."""
        role_hierarchy = {
            self.USER: 1,
            self.ADMIN: 2,
            self.SUPER_ADMIN: 3
        }
        return role_hierarchy.get(self, 0) >= role_hierarchy.get(required_role, 0)


class CommandShortcut(Enum):
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
        """Get the full command name for this shortcut."""
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


class WizardState(Enum):
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


class ErrorType(Enum):
    """Types of errors that can occur."""
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
        """Get emoji representation for the error type."""
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