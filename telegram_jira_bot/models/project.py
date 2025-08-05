#!/usr/bin/env python3
"""
Project model for the Telegram-Jira bot.

Contains Project, ProjectSummary, and ProjectStats models with comprehensive
validation and business logic for managing Jira projects within the bot ecosystem.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urlparse
from .enums import IssuePriority, IssueType, UserRole


def parse_iso_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string with tolerant handling.
    
    Args:
        date_str: ISO datetime string
        
    Returns:
        Parsed datetime object or None if parsing fails
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # Handle various ISO formats
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        elif date_str.endswith('+0000'):
            date_str = date_str[:-5] + '+00:00'
        elif date_str.endswith('-0000'):
            date_str = date_str[:-5] + '+00:00'
        
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError, TypeError):
        return None


@dataclass
class Project:
    """Jira project data model with comprehensive validation.
    
    FIXED: Added proper validation for default_priority and default_issue_type
    using enum validation instead of raw strings.
    """
    
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
    
    # Bot-specific fields with proper enum validation
    telegram_admins: List[str] = field(default_factory=list)
    default_priority: IssuePriority = IssuePriority.MEDIUM
    default_issue_type: IssueType = IssueType.TASK
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate project data after initialization."""
        self._validate_required_fields()
        self._validate_key_format()
        self._validate_url_format()
        self._validate_timestamps()
        self._validate_counts()
        self._validate_enums()
        self._validate_optional_fields()
        
        # Auto-update timestamp if not set
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
        """Validate URL format and distinguish between API and human URLs."""
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
        """Validate enum-like fields and convert strings to enums if needed."""
        # Validate project type
        valid_project_types = [
            "software", "service_desk", "business", "product_discovery"
        ]
        if self.project_type not in valid_project_types:
            raise ValueError(f"project_type must be one of: {valid_project_types}")
        
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active must be a boolean")
        
        # FIXED: Validate and convert default priority
        if isinstance(self.default_priority, str):
            try:
                self.default_priority = IssuePriority.from_string(self.default_priority)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid default_priority: {e}")
        elif not isinstance(self.default_priority, IssuePriority):
            raise TypeError("default_priority must be an IssuePriority instance or valid string")
        
        # FIXED: Validate and convert default issue type
        if isinstance(self.default_issue_type, str):
            try:
                self.default_issue_type = IssueType.from_string(self.default_issue_type)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid default_issue_type: {e}")
        elif not isinstance(self.default_issue_type, IssueType):
            raise TypeError("default_issue_type must be an IssueType instance or valid string")

    def _validate_optional_fields(self) -> None:
        """Validate optional fields."""
        # Validate optional strings
        optional_strings = [self.lead, self.avatar_url]
        for field in optional_strings:
            if field is not None and not isinstance(field, str):
                raise TypeError("optional string fields must be strings or None")
        
        # Validate telegram_admins list
        if not isinstance(self.telegram_admins, list):
            raise TypeError("telegram_admins must be a list")
        for admin in self.telegram_admins:
            if not isinstance(admin, str):
                raise TypeError("telegram_admins items must be strings")
        
        # Validate custom_fields dict
        if not isinstance(self.custom_fields, dict):
            raise TypeError("custom_fields must be a dictionary")

    @classmethod
    def from_jira_response(cls, jira_data: Dict[str, Any], base_url: str = "") -> 'Project':
        """Create Project from Jira REST API response.
        
        Args:
            jira_data: Raw response data from Jira API
            base_url: Base URL for building project links
            
        Returns:
            Project instance
            
        Raises:
            ValueError: If required fields are missing
            TypeError: If data types are incorrect
        """
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")
        
        # Extract required fields
        key = jira_data.get('key', '')
        if not key:
            raise ValueError("Project key is required")
        
        name = jira_data.get('name', '')
        if not name:
            raise ValueError("Project name is required")
        
        description = jira_data.get('description', '')
        
        # Build URLs - prefer human-readable browse URL over API URL
        api_url = jira_data.get('self', '')
        if base_url:
            # Build human-readable URL
            url = f"{base_url.rstrip('/')}/projects/{key}"
        else:
            # Fall back to API URL if no base URL provided
            url = api_url
        
        # Extract optional fields
        lead_data = jira_data.get('lead', {})
        lead = None
        if lead_data:
            lead = (lead_data.get('displayName') or 
                   lead_data.get('name') or 
                   lead_data.get('accountId', ''))
        
        project_type = jira_data.get('projectTypeKey', 'software')
        avatar_urls = jira_data.get('avatarUrls', {})
        avatar_url = avatar_urls.get('48x48') or avatar_urls.get('24x24')
        
        # Issue count (may not be available in all responses)
        issue_count = 0
        if 'issueCount' in jira_data:
            try:
                issue_count = int(jira_data['issueCount'])
            except (ValueError, TypeError):
                issue_count = 0
        
        return cls(
            key=key,
            name=name,
            description=description,
            url=url,
            lead=lead,
            project_type=project_type,
            avatar_url=avatar_url,
            issue_count=issue_count
        )

    def get_human_url(self, base_url: str) -> str:
        """Get human-readable project URL.
        
        Args:
            base_url: Jira base URL
            
        Returns:
            Human-readable project URL
        """
        return f"{base_url.rstrip('/')}/projects/{self.key}"

    def get_api_url(self, base_url: str) -> str:
        """Get API URL for the project.
        
        Args:
            base_url: Jira base URL
            
        Returns:
            API URL for the project
        """
        return f"{base_url.rstrip('/')}/rest/api/2/project/{self.key}"

    def add_telegram_admin(self, admin_username: str) -> None:
        """Add a Telegram admin to the project.
        
        Args:
            admin_username: Telegram username (without @)
            
        Raises:
            ValueError: If username is invalid
            TypeError: If username is not a string
        """
        if not isinstance(admin_username, str):
            raise TypeError("admin_username must be a string")
        
        username = admin_username.lstrip('@')  # Remove @ if present
        if not username:
            raise ValueError("admin_username cannot be empty")
        
        if username not in self.telegram_admins:
            self.telegram_admins.append(username)
            self.updated_at = datetime.now(timezone.utc)

    def remove_telegram_admin(self, admin_username: str) -> bool:
        """Remove a Telegram admin from the project.
        
        Args:
            admin_username: Telegram username (with or without @)
            
        Returns:
            True if admin was removed, False if not found
        """
        username = admin_username.lstrip('@')  # Remove @ if present
        if username in self.telegram_admins:
            self.telegram_admins.remove(username)
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def is_telegram_admin(self, username: str) -> bool:
        """Check if user is a Telegram admin for this project.
        
        Args:
            username: Telegram username (with or without @)
            
        Returns:
            True if user is an admin
        """
        username = username.lstrip('@')  # Remove @ if present
        return username in self.telegram_admins

    def update_issue_count(self, count: int) -> None:
        """Update the issue count for the project.
        
        Args:
            count: New issue count
            
        Raises:
            ValueError: If count is negative
            TypeError: If count is not an integer
        """
        if not isinstance(count, int):
            raise TypeError("count must be an integer")
        if count < 0:
            raise ValueError("count cannot be negative")
        
        self.issue_count = count
        self.updated_at = datetime.now(timezone.utc)

    def set_custom_field(self, key: str, value: Any) -> None:
        """Set a custom field value.
        
        Args:
            key: Field key
            value: Field value
        """
        if not isinstance(key, str):
            raise TypeError("key must be a string")
        
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

    def get_display_name(self) -> str:
        """Get formatted display name for the project.
        
        Returns:
            Formatted project name
        """
        status = "✅" if self.is_active else "❌"
        return f"{status} {self.key}: {self.name}"

    def get_summary_info(self) -> str:
        """Get formatted project summary.
        
        Returns:
            Multi-line summary of project information
        """
        summary = f"**{self.name}** ({self.key})\n"
        summary += f"📝 {self.description}\n"
        summary += f"📊 Issues: {self.issue_count}\n"
        summary += f"🎯 Type: {self.project_type.title()}\n"
        
        if self.lead:
            summary += f"👤 Lead: {self.lead}\n"
        
        status = "✅ Active" if self.is_active else "❌ Inactive"
        summary += f"📈 Status: {status}\n"
        
        if self.telegram_admins:
            admins_text = ", ".join([f"@{admin}" for admin in self.telegram_admins[:3]])
            if len(self.telegram_admins) > 3:
                admins_text += f" (+{len(self.telegram_admins) - 3} more)"
            summary += f"🛡️ Admins: {admins_text}\n"
        
        summary += f"🔗 [View in Jira]({self.url})"
        
        return summary

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
            'default_priority': self.default_priority.value,
            'default_issue_type': self.default_issue_type.value,
            'custom_fields': self.custom_fields.copy()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create project from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            Project instance
            
        Raises:
            TypeError: If data is not a dictionary
            ValueError: If required fields are missing
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse datetime fields
        created_at = parse_iso_datetime(data.get('created_at')) or datetime.now(timezone.utc)
        updated_at = parse_iso_datetime(data.get('updated_at'))

        # Parse enums (will be validated in __post_init__)
        default_priority = data.get('default_priority', 'Medium')
        default_issue_type = data.get('default_issue_type', 'Task')

        return cls(
            key=data['key'],
            name=data['name'],
            description=data['description'],
            url=data['url'],
            created_at=created_at,
            updated_at=updated_at,
            is_active=data.get('is_active', True),
            lead=data.get('lead'),
            project_type=data.get('project_type', 'software'),
            avatar_url=data.get('avatar_url'),
            issue_count=data.get('issue_count', 0),
            telegram_admins=data.get('telegram_admins', []),
            default_priority=default_priority,
            default_issue_type=default_issue_type,
            custom_fields=data.get('custom_fields', {})
        )

    def __str__(self) -> str:
        """String representation of the project."""
        return f"{self.key}: {self.name}"

    def __repr__(self) -> str:
        """Developer representation of the project."""
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            'key': self.key,
            'name': self.name,
            'issue_count': self.issue_count,
            'is_active': self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectSummary':
        """Create summary from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            ProjectSummary instance
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        
        return cls(
            key=data['key'],
            name=data['name'],
            issue_count=data.get('issue_count', 0),
            is_active=data.get('is_active', True)
        )

    def __str__(self) -> str:
        """String representation of the summary."""
        return f"{self.key}: {self.name}"

    def __repr__(self) -> str:
        """Developer representation of the summary."""
        return f"ProjectSummary(key='{self.key}', name='{self.name}', issues={self.issue_count})"


@dataclass
class ProjectStats:
    """Project statistics for reporting and analysis."""
    
    project_key: str
    total_issues: int
    open_issues: int
    closed_issues: int
    overdue_issues: int
    recent_activity: int  # Issues updated in last 7 days
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self) -> None:
        """Validate statistics data."""
        if not isinstance(self.project_key, str) or not self.project_key.strip():
            raise ValueError("project_key must be a non-empty string")
        
        numeric_fields = [
            self.total_issues, self.open_issues, self.closed_issues,
            self.overdue_issues, self.recent_activity
        ]
        for field in numeric_fields:
            if not isinstance(field, int) or field < 0:
                raise ValueError("count fields must be non-negative integers")
        
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime object")
        
        # Validate consistency
        if self.open_issues + self.closed_issues > self.total_issues:
            raise ValueError("open + closed issues cannot exceed total issues")

    def get_completion_rate(self) -> float:
        """Get completion rate as a percentage.
        
        Returns:
            Completion rate (0.0 to 100.0)
        """
        if self.total_issues == 0:
            return 0.0
        return (self.closed_issues / self.total_issues) * 100

    def get_overdue_rate(self) -> float:
        """Get overdue rate as a percentage.
        
        Returns:
            Overdue rate (0.0 to 100.0)
        """
        if self.open_issues == 0:
            return 0.0
        return (self.overdue_issues / self.open_issues) * 100

    def get_activity_indicator(self) -> str:
        """Get activity level indicator.
        
        Returns:
            Activity level emoji and text
        """
        if self.recent_activity == 0:
            return "🔴 No recent activity"
        elif self.recent_activity < 5:
            return "🟡 Low activity"
        elif self.recent_activity < 15:
            return "🟢 Moderate activity"
        else:
            return "🚀 High activity"

    def get_formatted_summary(self) -> str:
        """Get formatted statistics summary.
        
        Returns:
            Multi-line formatted summary
        """
        completion_rate = self.get_completion_rate()
        overdue_rate = self.get_overdue_rate()
        activity = self.get_activity_indicator()
        
        summary = f"**Project Statistics: {self.project_key}**\n\n"
        summary += f"📊 **Total Issues:** {self.total_issues}\n"
        summary += f"📂 **Open:** {self.open_issues}\n"
        summary += f"✅ **Closed:** {self.closed_issues} ({completion_rate:.1f}%)\n"
        
        if self.overdue_issues > 0:
            summary += f"🚨 **Overdue:** {self.overdue_issues} ({overdue_rate:.1f}%)\n"
        
        summary += f"📈 **Recent Activity:** {self.recent_activity} issues (7 days)\n"
        summary += f"🎯 **Activity Level:** {activity}\n"
        
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            'project_key': self.project_key,
            'total_issues': self.total_issues,
            'open_issues': self.open_issues,
            'closed_issues': self.closed_issues,
            'overdue_issues': self.overdue_issues,
            'recent_activity': self.recent_activity,
            'created_at': self.created_at.isoformat(),
            'completion_rate': self.get_completion_rate(),
            'overdue_rate': self.get_overdue_rate()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectStats':
        """Create stats from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            ProjectStats instance
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        
        created_at = parse_iso_datetime(data.get('created_at')) or datetime.now(timezone.utc)
        
        return cls(
            project_key=data['project_key'],
            total_issues=data['total_issues'],
            open_issues=data['open_issues'],
            closed_issues=data['closed_issues'],
            overdue_issues=data.get('overdue_issues', 0),
            recent_activity=data.get('recent_activity', 0),
            created_at=created_at
        )

    def __str__(self) -> str:
        """String representation of stats."""
        return f"ProjectStats({self.project_key}: {self.total_issues} issues)"

    def __repr__(self) -> str:
        """Developer representation of stats."""
        return (f"ProjectStats(project='{self.project_key}', "
                f"total={self.total_issues}, completion={self.get_completion_rate():.1f}%)")