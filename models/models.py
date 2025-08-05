"""
Domain models and enums for the Telegram Jira Bot.

This module contains all the core domain models and enums used throughout the application.
All models include proper type hints, validation, and serialization methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User role enumeration defining access levels."""
    
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

    def __str__(self) -> str:
        return self.value

    @property
    def display_name(self) -> str:
        """Get human-readable display name for the role."""
        return self.value.replace("_", " ").title()


class IssueType(Enum):
    """Jira issue type enumeration."""
    
    TASK = "Task"
    BUG = "Bug"
    STORY = "Story"
    EPIC = "Epic"
    SUBTASK = "Sub-task"

    def __str__(self) -> str:
        return self.value


class IssuePriority(Enum):
    """Jira issue priority enumeration."""
    
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"

    def __str__(self) -> str:
        return self.value


class IssueStatus(Enum):
    """Jira issue status enumeration."""
    
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    BLOCKED = "Blocked"
    REVIEW = "In Review"

    def __str__(self) -> str:
        return self.value


class ErrorType(Enum):
    """Error type enumeration for standardized error handling."""
    
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND_ERROR = "not_found_error"
    JIRA_API_ERROR = "jira_api_error"
    DATABASE_ERROR = "database_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN_ERROR = "unknown_error"

    def __str__(self) -> str:
        return self.value


class WizardState(Enum):
    """Wizard conversation states for Telegram bot."""
    
    # Setup wizard states
    SETUP_WELCOME = "setup_welcome"
    SETUP_PROJECT_SELECTION = "setup_project_selection"
    SETUP_PROJECT_CONFIRMATION = "setup_project_confirmation"
    
    # Issue creation wizard states
    ISSUE_PROJECT_SELECTION = "issue_project_selection"
    ISSUE_TYPE_SELECTION = "issue_type_selection"
    ISSUE_PRIORITY_SELECTION = "issue_priority_selection"
    ISSUE_SUMMARY_INPUT = "issue_summary_input"
    ISSUE_DESCRIPTION_INPUT = "issue_description_input"
    ISSUE_CONFIRMATION = "issue_confirmation"

    def __str__(self) -> str:
        return self.value


@dataclass
class User:
    """User domain model representing a Telegram user."""
    
    row_id: Optional[int]
    user_id: str  # Telegram ID as string
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    role: UserRole
    is_active: bool = True
    preferred_language: str = "en"
    timezone: Optional[str] = None
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate user data after initialization."""
        if not isinstance(self.user_id, str):
            raise TypeError(f"user_id must be str, got {type(self.user_id)}")
        if not isinstance(self.role, UserRole):
            raise TypeError(f"role must be UserRole, got {type(self.role)}")
        if self.username is not None and not isinstance(self.username, str):
            raise TypeError(f"username must be str or None, got {type(self.username)}")

    @property
    def display_name(self) -> str:
        """Get user's display name for UI purposes."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.user_id}"

    @property
    def mention(self) -> str:
        """Get user mention string for Telegram."""
        if self.username:
            return f"@{self.username}"
        else:
            return self.display_name

    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    def is_super_admin(self) -> bool:
        """Check if user has super admin privileges."""
        return self.role == UserRole.SUPER_ADMIN

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary representation."""
        return {
            'row_id': self.row_id,
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'role': self.role.value,
            'is_active': self.is_active,
            'preferred_language': self.preferred_language,
            'timezone': self.timezone,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
        }


@dataclass
class Project:
    """Project domain model representing a Jira project."""
    
    key: str
    name: str
    description: str = ""
    url: str = ""
    is_active: bool = True
    project_type: str = "software"
    lead: Optional[str] = None
    avatar_url: Optional[str] = None
    default_priority: IssuePriority = IssuePriority.MEDIUM
    default_issue_type: IssueType = IssueType.TASK
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate project data after initialization."""
        if not isinstance(self.key, str) or not self.key:
            raise TypeError("project key must be non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise TypeError("project name must be non-empty string")
        if not isinstance(self.default_priority, IssuePriority):
            raise TypeError(f"default_priority must be IssuePriority, got {type(self.default_priority)}")
        if not isinstance(self.default_issue_type, IssueType):
            raise TypeError(f"default_issue_type must be IssueType, got {type(self.default_issue_type)}")

    @classmethod
    def from_jira_response(cls, data: Dict[str, Any]) -> Project:
        """Create Project instance from Jira API response."""
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data)}")

        try:
            return cls(
                key=data['key'],
                name=data['name'],
                description=data.get('description', ''),
                url=data.get('self', ''),
                project_type=data.get('projectTypeKey', 'software'),
                lead=data.get('lead', {}).get('displayName'),
                avatar_url=data.get('avatarUrls', {}).get('48x48'),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in Jira response: {e}")

    def get_formatted_summary(self) -> str:
        """Get formatted project summary for display."""
        summary = f"🏗 **{self.name}** (`{self.key}`)"
        if self.description:
            # Truncate long descriptions
            desc = self.description[:100] + "..." if len(self.description) > 100 else self.description
            summary += f"\n_{desc}_"
        if self.lead:
            summary += f"\n👤 Lead: {self.lead}"
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert project to dictionary representation."""
        return {
            'key': self.key,
            'name': self.name,
            'description': self.description,
            'url': self.url,
            'is_active': self.is_active,
            'project_type': self.project_type,
            'lead': self.lead,
            'avatar_url': self.avatar_url,
            'default_priority': self.default_priority.value,
            'default_issue_type': self.default_issue_type.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class JiraIssue:
    """Jira issue domain model."""
    
    key: str
    summary: str
    description: str
    issue_type: IssueType
    status: str
    priority: IssuePriority
    assignee: Optional[str] = None
    assignee_display_name: Optional[str] = None
    reporter: Optional[str] = None
    reporter_display_name: Optional[str] = None
    project_key: str = ""
    project_name: str = ""
    labels: List[str] = None
    components: List[str] = None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    url: str = ""

    def __post_init__(self) -> None:
        """Initialize default values and validate data."""
        if self.labels is None:
            self.labels = []
        if self.components is None:
            self.components = []
            
        # Validation
        if not isinstance(self.key, str) or not self.key:
            raise TypeError("issue key must be non-empty string")
        if not isinstance(self.summary, str) or not self.summary:
            raise TypeError("issue summary must be non-empty string")
        if not isinstance(self.issue_type, IssueType):
            raise TypeError(f"issue_type must be IssueType, got {type(self.issue_type)}")
        if not isinstance(self.priority, IssuePriority):
            raise TypeError(f"priority must be IssuePriority, got {type(self.priority)}")

    @classmethod
    def from_jira_response(cls, data: Dict[str, Any]) -> JiraIssue:
        """Create JiraIssue instance from Jira API response."""
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data)}")

        try:
            fields = data.get('fields', {})
            
            # Parse dates
            created = None
            updated = None
            if fields.get('created'):
                try:
                    created = datetime.fromisoformat(fields['created'].replace('Z', '+00:00'))
                except ValueError:
                    logger.warning(f"Could not parse created date: {fields['created']}")
            if fields.get('updated'):
                try:
                    updated = datetime.fromisoformat(fields['updated'].replace('Z', '+00:00'))
                except ValueError:
                    logger.warning(f"Could not parse updated date: {fields['updated']}")

            # Parse issue type
            issue_type_name = fields.get('issuetype', {}).get('name', 'Task')
            try:
                issue_type = IssueType(issue_type_name)
            except ValueError:
                issue_type = IssueType.TASK

            # Parse priority
            priority_name = fields.get('priority', {}).get('name', 'Medium')
            try:
                priority = IssuePriority(priority_name)
            except ValueError:
                priority = IssuePriority.MEDIUM

            return cls(
                key=data['key'],
                summary=fields.get('summary', ''),
                description=fields.get('description', ''),
                issue_type=issue_type,
                status=fields.get('status', {}).get('name', 'Unknown'),
                priority=priority,
                assignee=fields.get('assignee', {}).get('accountId') if fields.get('assignee') else None,
                assignee_display_name=fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None,
                reporter=fields.get('reporter', {}).get('accountId') if fields.get('reporter') else None,
                reporter_display_name=fields.get('reporter', {}).get('displayName') if fields.get('reporter') else None,
                project_key=fields.get('project', {}).get('key', ''),
                project_name=fields.get('project', {}).get('name', ''),
                labels=fields.get('labels', []),
                components=[c.get('name', '') for c in fields.get('components', [])],
                created=created,
                updated=updated,
                url=data.get('self', ''),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in Jira response: {e}")

    def get_formatted_summary(self) -> str:
        """Get formatted issue summary for display."""
        status_emoji = {
            'To Do': '📋',
            'In Progress': '🔄',
            'Done': '✅',
            'Blocked': '🚫',
            'In Review': '👀',
        }.get(self.status, '📌')

        priority_emoji = {
            IssuePriority.HIGHEST: '🔴',
            IssuePriority.HIGH: '🟠', 
            IssuePriority.MEDIUM: '🟡',
            IssuePriority.LOW: '🔵',
            IssuePriority.LOWEST: '⚪',
        }.get(self.priority, '🟡')

        summary = f"{status_emoji} **{self.key}** - {self.summary}"
        summary += f"\n{priority_emoji} {self.priority.value} | {self.issue_type.value}"
        
        if self.assignee_display_name:
            summary += f" | 👤 {self.assignee_display_name}"
        
        if self.labels:
            summary += f" | 🏷 {', '.join(self.labels[:3])}"
            
        return summary

    def get_detailed_view(self) -> str:
        """Get detailed issue view for display."""
        lines = [
            f"📋 **{self.key}: {self.summary}**",
            f"🏗 Project: {self.project_name} ({self.project_key})",
            f"📊 Status: {self.status}",
            f"🎯 Type: {self.issue_type.value}",
            f"⚡ Priority: {self.priority.value}",
        ]
        
        if self.assignee_display_name:
            lines.append(f"👤 Assignee: {self.assignee_display_name}")
        
        if self.reporter_display_name:
            lines.append(f"📝 Reporter: {self.reporter_display_name}")
            
        if self.labels:
            lines.append(f"🏷 Labels: {', '.join(self.labels)}")
            
        if self.components:
            lines.append(f"🔧 Components: {', '.join(self.components)}")
            
        if self.created:
            lines.append(f"📅 Created: {self.created.strftime('%Y-%m-%d %H:%M')}")
            
        if self.updated:
            lines.append(f"🔄 Updated: {self.updated.strftime('%Y-%m-%d %H:%M')}")
            
        if self.description:
            desc = self.description[:200] + "..." if len(self.description) > 200 else self.description
            lines.append(f"\n📄 **Description:**\n_{desc}_")
            
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to dictionary representation."""
        return {
            'key': self.key,
            'summary': self.summary,
            'description': self.description,
            'issue_type': self.issue_type.value,
            'status': self.status,
            'priority': self.priority.value,
            'assignee': self.assignee,
            'assignee_display_name': self.assignee_display_name,
            'reporter': self.reporter,
            'reporter_display_name': self.reporter_display_name,
            'project_key': self.project_key,
            'project_name': self.project_name,
            'labels': self.labels,
            'components': self.components,
            'created': self.created.isoformat() if self.created else None,
            'updated': self.updated.isoformat() if self.updated else None,
            'url': self.url,
        }


@dataclass
class IssueComment:
    """Jira issue comment domain model."""
    
    id: str
    body: str
    author_account_id: str
    author_display_name: str
    created: Optional[datetime] = None
    updated: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate comment data after initialization."""
        if not isinstance(self.id, str) or not self.id:
            raise TypeError("comment id must be non-empty string")
        if not isinstance(self.body, str) or not self.body:
            raise TypeError("comment body must be non-empty string")
        if not isinstance(self.author_account_id, str) or not self.author_account_id:
            raise TypeError("author_account_id must be non-empty string")

    @classmethod
    def from_jira_response(cls, data: Dict[str, Any]) -> IssueComment:
        """Create IssueComment instance from Jira API response."""
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data)}")

        try:
            # Parse dates
            created = None
            updated = None
            if data.get('created'):
                try:
                    created = datetime.fromisoformat(data['created'].replace('Z', '+00:00'))
                except ValueError:
                    logger.warning(f"Could not parse created date: {data['created']}")
            if data.get('updated'):
                try:
                    updated = datetime.fromisoformat(data['updated'].replace('Z', '+00:00'))
                except ValueError:
                    logger.warning(f"Could not parse updated date: {data['updated']}")

            return cls(
                id=data['id'],
                body=data['body'],
                author_account_id=data['author']['accountId'],
                author_display_name=data['author']['displayName'],
                created=created,
                updated=updated,
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in Jira comment response: {e}")

    def get_formatted_comment(self) -> str:
        """Get formatted comment for display."""
        timestamp = ""
        if self.created:
            timestamp = f" ({self.created.strftime('%Y-%m-%d %H:%M')})"
        
        # Truncate long comments
        body = self.body[:300] + "..." if len(self.body) > 300 else self.body
        
        return f"💬 **{self.author_display_name}**{timestamp}\n_{body}_"

    def to_dict(self) -> Dict[str, Any]:
        """Convert comment to dictionary representation."""
        return {
            'id': self.id,
            'body': self.body,
            'author_account_id': self.author_account_id,
            'author_display_name': self.author_display_name,
            'created': self.created.isoformat() if self.created else None,
            'updated': self.updated.isoformat() if self.updated else None,
        }


@dataclass
class IssueSearchResult:
    """Result container for issue search operations."""
    
    issues: List[JiraIssue]
    total_count: int
    search_query: str
    start_at: int = 0
    max_results: int = 20

    def __post_init__(self) -> None:
        """Validate search result data."""
        if not isinstance(self.issues, list):
            raise TypeError(f"issues must be list, got {type(self.issues)}")
        if not isinstance(self.total_count, int) or self.total_count < 0:
            raise TypeError("total_count must be non-negative integer")
        if not isinstance(self.search_query, str):
            raise TypeError(f"search_query must be str, got {type(self.search_query)}")

    @property
    def has_more(self) -> bool:
        """Check if there are more results available."""
        return self.start_at + len(self.issues) < self.total_count

    @property
    def current_page(self) -> int:
        """Get current page number (1-based)."""
        return (self.start_at // self.max_results) + 1

    @property
    def total_pages(self) -> int:
        """Get total number of pages."""
        if self.max_results <= 0:
            return 1
        return max(1, (self.total_count + self.max_results - 1) // self.max_results)

    def get_formatted_summary(self) -> str:
        """Get formatted search result summary."""
        if not self.issues:
            return f"🔍 No issues found for query: `{self.search_query}`"
        
        summary = f"🔍 Found {self.total_count} issue(s) for: `{self.search_query}`"
        if self.total_pages > 1:
            summary += f" (Page {self.current_page}/{self.total_pages})"
        
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert search result to dictionary representation."""
        return {
            'issues': [issue.to_dict() for issue in self.issues],
            'total_count': self.total_count,
            'search_query': self.search_query,
            'start_at': self.start_at,
            'max_results': self.max_results,
        }


@dataclass  
class SentMessages:
    """Container for sent Telegram message information."""
    
    message_ids: List[int]
    first_message_id: Optional[int] = None

    def __post_init__(self) -> None:
        """Set first_message_id if not provided."""
        if self.first_message_id is None and self.message_ids:
            self.first_message_id = self.message_ids[0]

    @property
    def count(self) -> int:
        """Get number of sent messages."""
        return len(self.message_ids)

    @property
    def last_message_id(self) -> Optional[int]:
        """Get ID of the last sent message."""
        return self.message_ids[-1] if self.message_ids else None