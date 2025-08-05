#!/usr/bin/env python3
"""
Project model for the Telegram-Jira bot.

Contains the Project dataclass and related functionality for managing
Jira projects within the bot ecosystem.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
import re
from urllib.parse import urlparse

from .enums import UserRole


@dataclass
class Project:
    """Jira project data model with comprehensive validation."""
    
    key: str
    name: str
    description: str
    url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    is_active: bool = True
    lead: Optional[str] = None
    project_type: str = "software"
    avatar_url: Optional[str] = None
    issue_count: int = 0
    
    # Bot-specific fields
    telegram_admins: List[str] = field(default_factory=list)
    default_priority: str = "Medium"
    default_issue_type: str = "Task"
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate project data after initialization."""
        self._validate_required_fields()
        self._validate_key_format()
        self._validate_url_format()
        self._validate_timestamps()
        self._validate_counts()
        self._validate_enums()
        
        # Auto-update timestamp
        if self.updated_at is None:
            self.updated_at = self.created_at

    def _validate_required_fields(self) -> None:
        """Validate required string fields."""
        required_fields = {
            'key': self.key,
            'name': self.name,
            'description': self.description,
            'url': self.url,
            'project_type': self.project_type
        }
        
        for field_name, field_value in required_fields.items():
            if not isinstance(field_value, str):
                raise TypeError(f"{field_name} must be a string")
            if not field_value.strip():
                raise ValueError(f"{field_name} cannot be empty")

    def _validate_key_format(self) -> None:
        """Validate project key format (uppercase letters, numbers, underscores only)."""
        if not isinstance(self.key, str):
            raise TypeError("Project key must be a string")
        
        # Check length
        if len(self.key) < 2 or len(self.key) > 20:
            raise ValueError("Project key must be between 2 and 20 characters")
        
        # Check format - only uppercase letters, numbers, and underscores
        if not re.match(r'^[A-Z][A-Z0-9_]*$', self.key):
            raise ValueError(
                "Project key must start with uppercase letter and contain only "
                "uppercase letters, numbers, and underscores"
            )

    def _validate_url_format(self) -> None:
        """Validate URL format."""
        if not isinstance(self.url, str):
            raise TypeError("URL must be a string")
        
        try:
            parsed = urlparse(self.url)
            if not all([parsed.scheme, parsed.netloc]):
                raise ValueError("URL must be a valid HTTP/HTTPS URL")
            if parsed.scheme not in ['http', 'https']:
                raise ValueError("URL must use HTTP or HTTPS protocol")
        except Exception as e:
            raise ValueError(f"Invalid URL format: {e}")

    def _validate_timestamps(self) -> None:
        """Validate timestamp fields."""
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime object")
        
        if self.updated_at is not None:
            if not isinstance(self.updated_at, datetime):
                raise TypeError("updated_at must be a datetime object or None")
            if self.updated_at < self.created_at:
                raise ValueError("updated_at cannot be before created_at")

    def _validate_counts(self) -> None:
        """Validate count fields."""
        if not isinstance(self.issue_count, int) or self.issue_count < 0:
            raise ValueError("issue_count must be a non-negative integer")

    def _validate_enums(self) -> None:
        """Validate enum-like fields."""
        valid_project_types = [
            "software", "service_desk", "business", "product_discovery"
        ]
        if self.project_type not in valid_project_types:
            raise ValueError(f"project_type must be one of: {valid_project_types}")
        
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active must be a boolean")

    def to_dict(self) -> Dict[str, Any]:
        """Convert project to dictionary for serialization.
        
        Returns:
            Dictionary representation of the project
        """
        return {
            'key': self.key,
            'name': self.name,
            'description': self.description,
            'url': self.url,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active,
            'lead': self.lead,
            'project_type': self.project_type,
            'avatar_url': self.avatar_url,
            'issue_count': self.issue_count,
            'telegram_admins': self.telegram_admins.copy(),
            'default_priority': self.default_priority,
            'default_issue_type': self.default_issue_type,
            'custom_fields': self.custom_fields.copy()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create project from dictionary.
        
        Args:
            data: Dictionary containing project data
            
        Returns:
            Project instance
            
        Raises:
            ValueError: If required fields are missing
            TypeError: If field types are incorrect
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        
        # Parse timestamps
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        elif created_at is None:
            created_at = datetime.now(timezone.utc)
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        return cls(
            key=data['key'],
            name=data['name'],
            description=data.get('description', ''),
            url=data['url'],
            created_at=created_at,
            updated_at=updated_at,
            is_active=data.get('is_active', True),
            lead=data.get('lead'),
            project_type=data.get('project_type', 'software'),
            avatar_url=data.get('avatar_url'),
            issue_count=data.get('issue_count', 0),
            telegram_admins=data.get('telegram_admins', []),
            default_priority=data.get('default_priority', 'Medium'),
            default_issue_type=data.get('default_issue_type', 'Task'),
            custom_fields=data.get('custom_fields', {})
        )

    @classmethod
    def from_jira_response(cls, jira_data: Dict[str, Any]) -> 'Project':
        """Create project from Jira API response.
        
        Args:
            jira_data: Raw Jira API response data
            
        Returns:
            Project instance
            
        Raises:
            ValueError: If required Jira fields are missing
            KeyError: If expected Jira structure is invalid
        """
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")
        
        try:
            return cls(
                key=jira_data['key'],
                name=jira_data['name'],
                description=jira_data.get('description', ''),
                url=jira_data['self'],
                lead=jira_data.get('lead', {}).get('displayName'),
                project_type=jira_data.get('projectTypeKey', 'software'),
                avatar_url=jira_data.get('avatarUrls', {}).get('48x48'),
                is_active=jira_data.get('archived', False) == False
            )
        except KeyError as e:
            raise ValueError(f"Missing required Jira field: {e}")

    def update_from_jira(self, jira_data: Dict[str, Any]) -> None:
        """Update project data from Jira response.
        
        Args:
            jira_data: Jira API response data
        """
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")
        
        # Update fields that can change in Jira
        self.name = jira_data.get('name', self.name)
        self.description = jira_data.get('description', self.description)
        self.lead = jira_data.get('lead', {}).get('displayName', self.lead)
        self.avatar_url = jira_data.get('avatarUrls', {}).get('48x48', self.avatar_url)
        self.is_active = jira_data.get('archived', False) == False
        self.updated_at = datetime.now(timezone.utc)

    def add_telegram_admin(self, user_id: str) -> bool:
        """Add a Telegram admin to the project.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if added, False if already exists
        """
        if not isinstance(user_id, str):
            raise TypeError("user_id must be a string")
        
        if user_id not in self.telegram_admins:
            self.telegram_admins.append(user_id)
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def remove_telegram_admin(self, user_id: str) -> bool:
        """Remove a Telegram admin from the project.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if removed, False if not found
        """
        if not isinstance(user_id, str):
            raise TypeError("user_id must be a string")
        
        if user_id in self.telegram_admins:
            self.telegram_admins.remove(user_id)
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def is_telegram_admin(self, user_id: str) -> bool:
        """Check if user is a Telegram admin for this project.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user is admin
        """
        if not isinstance(user_id, str):
            raise TypeError("user_id must be a string")
        
        return user_id in self.telegram_admins

    def set_custom_field(self, key: str, value: Any) -> None:
        """Set a custom field value.
        
        Args:
            key: Field key
            value: Field value
        """
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        
        self.custom_fields[key] = value
        self.updated_at = datetime.now(timezone.utc)

    def get_custom_field(self, key: str, default: Any = None) -> Any:
        """Get a custom field value.
        
        Args:
            key: Field key
            default: Default value if key not found
            
        Returns:
            Field value or default
        """
        return self.custom_fields.get(key, default)

    def increment_issue_count(self, count: int = 1) -> None:
        """Increment the issue count.
        
        Args:
            count: Number to increment by (default: 1)
        """
        if not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative integer")
        
        self.issue_count += count
        self.updated_at = datetime.now(timezone.utc)

    def decrement_issue_count(self, count: int = 1) -> None:
        """Decrement the issue count.
        
        Args:
            count: Number to decrement by (default: 1)
        """
        if not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative integer")
        
        self.issue_count = max(0, self.issue_count - count)
        self.updated_at = datetime.now(timezone.utc)

    def get_display_name(self) -> str:
        """Get formatted display name for the project.
        
        Returns:
            Formatted project name with key
        """
        return f"{self.key}: {self.name}"

    def get_short_description(self, max_length: int = 100) -> str:
        """Get truncated description for display.
        
        Args:
            max_length: Maximum length of description
            
        Returns:
            Truncated description
        """
        if len(self.description) <= max_length:
            return self.description
        return self.description[:max_length - 3] + "..."

    def __str__(self) -> str:
        """String representation of the project."""
        return f"Project({self.key}: {self.name})"

    def __repr__(self) -> str:
        """Detailed string representation of the project."""
        return (
            f"Project(key='{self.key}', name='{self.name}', "
            f"active={self.is_active}, issues={self.issue_count})"
        )

    def __eq__(self, other: object) -> bool:
        """Check equality based on project key."""
        if not isinstance(other, Project):
            return NotImplemented
        return self.key == other.key

    def __hash__(self) -> int:
        """Hash based on project key."""
        return hash(self.key)


@dataclass
class ProjectSummary:
    """Lightweight project summary for listing and selection."""
    
    key: str
    name: str
    issue_count: int
    is_active: bool = True
    
    def __post_init__(self) -> None:
        """Validate summary data."""
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("key must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.issue_count, int) or self.issue_count < 0:
            raise ValueError("issue_count must be a non-negative integer")
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active must be a boolean")

    @classmethod
    def from_project(cls, project: Project) -> 'ProjectSummary':
        """Create summary from full project.
        
        Args:
            project: Full project object
            
        Returns:
            Project summary
        """
        return cls(
            key=project.key,
            name=project.name,
            issue_count=project.issue_count,
            is_active=project.is_active
        )

    def get_display_text(self) -> str:
        """Get formatted display text for the summary.
        
        Returns:
            Formatted summary text
        """
        status = "✅" if self.is_active else "❌"
        return f"{status} {self.key}: {self.name} ({self.issue_count} issues)"

    def __str__(self) -> str:
        """String representation of the summary."""
        return f"{self.key}: {self.name}"