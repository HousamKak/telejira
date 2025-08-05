#!/usr/bin/env python3
"""
Project model for the Telegram-Jira bot.

Contains the Project dataclass and related functionality.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from .enums import IssueType, IssuePriority


@dataclass
class Project:
    """Jira project data model."""
    key: str
    name: str
    description: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    jira_project_id: Optional[str] = None
    project_type: Optional[str] = None
    lead: Optional[str] = None
    url: Optional[str] = None
    avatar_url: Optional[str] = None
    category: Optional[str] = None
    issue_count: int = 0
    
    def __post_init__(self) -> None:
        """Validate project data after initialization."""
        self._validate_key()
        self._validate_name()
        self._validate_description()
        self._validate_boolean_fields()
        self._validate_datetime_fields()

    def _validate_key(self) -> None:
        """Validate project key."""
        if not isinstance(self.key, str):
            raise TypeError("key must be a string")
        if not self.key.strip():
            raise ValueError("key must be a non-empty string")
        if len(self.key) > 10:
            raise ValueError("key must be 10 characters or less")
        if not self.key.isupper():
            raise ValueError("key must be uppercase")
        # Check for valid Jira key format
        import re
        if not re.match(r'^[A-Z][A-Z0-9_]*$', self.key):
            raise ValueError("key must start with a letter and contain only uppercase letters, numbers, and underscores")

    def _validate_name(self) -> None:
        """Validate project name."""
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if len(self.name) > 255:
            raise ValueError("name must be 255 characters or less")

    def _validate_description(self) -> None:
        """Validate project description."""
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if len(self.description) > 1000:
            raise ValueError("description must be 1000 characters or less")

    def _validate_boolean_fields(self) -> None:
        """Validate boolean fields."""
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active must be a boolean")

    def _validate_datetime_fields(self) -> None:
        """Validate datetime fields."""
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be a datetime")

    def to_dict(self) -> Dict[str, Any]:
        """Convert project to dictionary for serialization."""
        return {
            'key': self.key,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'jira_project_id': self.jira_project_id,
            'project_type': self.project_type,
            'lead': self.lead,
            'url': self.url,
            'avatar_url': self.avatar_url,
            'category': self.category,
            'issue_count': self.issue_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create Project from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        
        # Parse datetime fields
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)
            
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now(timezone.utc)

        return cls(
            key=data['key'],
            name=data['name'],
            description=data.get('description', ''),
            is_active=data.get('is_active', True),
            created_at=created_at,
            updated_at=updated_at,
            jira_project_id=data.get('jira_project_id'),
            project_type=data.get('project_type'),
            lead=data.get('lead'),
            url=data.get('url'),
            avatar_url=data.get('avatar_url'),
            category=data.get('category'),
            issue_count=data.get('issue_count', 0)
        )

    @classmethod
    def from_jira_data(cls, jira_data: Dict[str, Any]) -> 'Project':
        """Create Project from Jira API response data."""
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")

        key = jira_data.get('key', '')
        name = jira_data.get('name', '')
        description = jira_data.get('description', '')
        
        # Extract additional Jira-specific fields
        jira_project_id = jira_data.get('id')
        project_type = jira_data.get('projectTypeKey')
        lead_info = jira_data.get('lead', {})
        lead = lead_info.get('displayName') if isinstance(lead_info, dict) else None
        
        # Build project URL
        self_url = jira_data.get('self', '')
        if self_url:
            # Extract base URL and create browse URL
            import re
            match = re.match(r'^(https?://[^/]+)', self_url)
            if match:
                base_url = match.group(1)
                url = f"{base_url}/browse/{key}"
            else:
                url = None
        else:
            url = None
            
        avatar_urls = jira_data.get('avatarUrls', {})
        avatar_url = avatar_urls.get('48x48') or avatar_urls.get('32x32') or avatar_urls.get('24x24')
        
        category_info = jira_data.get('projectCategory', {})
        category = category_info.get('name') if isinstance(category_info, dict) else None

        return cls(
            key=key,
            name=name,
            description=description,
            jira_project_id=jira_project_id,
            project_type=project_type,
            lead=lead,
            url=url,
            avatar_url=avatar_url,
            category=category
        )

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update project fields from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        updatable_fields = {
            'name', 'description', 'is_active', 'jira_project_id', 
            'project_type', 'lead', 'url', 'avatar_url', 'category'
        }
        
        for field, value in data.items():
            if field in updatable_fields and hasattr(self, field):
                setattr(self, field, value)
        
        self.updated_at = datetime.now(timezone.utc)
        
        # Re-validate after update
        self.__post_init__()

    def get_display_name(self) -> str:
        """Get formatted display name for UI."""
        if self.category:
            return f"{self.name} ({self.category})"
        return self.name

    def get_summary_text(self) -> str:
        """Get formatted summary text for messages."""
        status = "🟢 Active" if self.is_active else "🔴 Inactive"
        lead_text = f" • Lead: {self.lead}" if self.lead else ""
        issue_text = f" • Issues: {self.issue_count}" if self.issue_count > 0 else ""
        
        summary = f"**{self.key}** - {self.name}\n"
        summary += f"{status}{lead_text}{issue_text}\n"
        
        if self.description:
            desc_preview = self.description[:100] + "..." if len(self.description) > 100 else self.description
            summary += f"_{desc_preview}_\n"
            
        return summary

    def can_be_deleted(self) -> bool:
        """Check if project can be safely deleted."""
        return self.issue_count == 0

    def get_deletion_warning(self) -> Optional[str]:
        """Get warning message if project cannot be deleted."""
        if not self.can_be_deleted():
            return f"⚠️ Project has {self.issue_count} issue(s). Delete issues first or use force delete."
        return None

    def __str__(self) -> str:
        """String representation of the project."""
        return f"Project({self.key}: {self.name})"

    def __repr__(self) -> str:
        """Developer representation of the project."""
        return (f"Project(key='{self.key}', name='{self.name}', "
                f"is_active={self.is_active}, issue_count={self.issue_count})")


@dataclass
class ProjectSearchResult:
    """Result of a project search operation."""
    projects: List[Project]
    total_count: int
    search_query: Optional[str] = None
    filters_applied: Dict[str, Any] = field(default_factory=dict)
    
    def has_results(self) -> bool:
        """Check if search returned any results."""
        return len(self.projects) > 0
    
    def get_summary(self) -> str:
        """Get search result summary."""
        if not self.has_results():
            return "No projects found"
        
        query_text = f" for '{self.search_query}'" if self.search_query else ""
        return f"Found {len(self.projects)} of {self.total_count} projects{query_text}"


@dataclass 
class ProjectStats:
    """Statistics for a project."""
    project_key: str
    total_issues: int
    issues_by_type: Dict[str, int] = field(default_factory=dict)
    issues_by_priority: Dict[str, int] = field(default_factory=dict)
    issues_by_status: Dict[str, int] = field(default_factory=dict)
    created_this_month: int = 0
    created_this_week: int = 0
    last_activity: Optional[datetime] = None
    
    def get_formatted_stats(self) -> str:
        """Get formatted statistics text."""
        stats = f"📊 **{self.project_key} Statistics**\n\n"
        stats += f"**Total Issues:** {self.total_issues}\n"
        
        if self.issues_by_type:
            stats += "\n**By Type:**\n"
            for issue_type, count in self.issues_by_type.items():
                try:
                    emoji = IssueType.from_string(issue_type).get_emoji()
                except (ValueError, AttributeError):
                    emoji = "📄"
                stats += f"  {emoji} {issue_type}: {count}\n"
        
        if self.issues_by_priority:
            stats += "\n**By Priority:**\n"
            for priority, count in self.issues_by_priority.items():
                try:
                    emoji = IssuePriority.from_string(priority).get_emoji()
                except (ValueError, AttributeError):
                    emoji = "⚪"
                stats += f"  {emoji} {priority}: {count}\n"
        
        stats += f"\n**Activity:**\n"
        stats += f"  📅 This month: {self.created_this_month}\n"
        stats += f"  📆 This week: {self.created_this_week}\n"
        
        if self.last_activity:
            activity_date = self.last_activity.strftime('%Y-%m-%d %H:%M')
            stats += f"  ⏰ Last activity: {activity_date}\n"
        
        return stats