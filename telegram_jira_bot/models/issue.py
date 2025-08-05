#!/usr/bin/env python3
"""
Additional models for the Issue module.

This extends the existing issue.py file with the missing IssueComment model
and additional functionality that's referenced throughout the codebase.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from .enums import IssuePriority, IssueType, IssueStatus
from .issue import JiraIssue


@dataclass
class IssueComment:
    """Jira issue comment data model."""
    
    id: str
    body: str
    author: str
    author_display_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    issue_key: Optional[str] = None
    
    # Additional metadata
    author_email: Optional[str] = None
    author_avatar_url: Optional[str] = None
    is_internal: bool = False
    visibility: Optional[Dict[str, str]] = None
    
    def __post_init__(self) -> None:
        """Validate comment data after initialization."""
        self._validate_required_fields()
        self._validate_timestamps()
        self._validate_optional_fields()

    def _validate_required_fields(self) -> None:
        """Validate required fields."""
        required_string_fields = {
            'id': self.id,
            'body': self.body,
            'author': self.author,
            'author_display_name': self.author_display_name
        }
        
        for field_name, field_value in required_string_fields.items():
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def _validate_timestamps(self) -> None:
        """Validate timestamp fields."""
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime object")
        
        if self.updated_at is not None:
            if not isinstance(self.updated_at, datetime):
                raise TypeError("updated_at must be a datetime object or None")
            if self.updated_at < self.created_at:
                raise ValueError("updated_at cannot be before created_at")

    def _validate_optional_fields(self) -> None:
        """Validate optional fields."""
        if self.author_email is not None and not isinstance(self.author_email, str):
            raise TypeError("author_email must be a string or None")
        
        if self.author_avatar_url is not None and not isinstance(self.author_avatar_url, str):
            raise TypeError("author_avatar_url must be a string or None")
        
        if not isinstance(self.is_internal, bool):
            raise TypeError("is_internal must be a boolean")
        
        if self.visibility is not None and not isinstance(self.visibility, dict):
            raise TypeError("visibility must be a dictionary or None")

    def to_dict(self) -> Dict[str, Any]:
        """Convert comment to dictionary for serialization.
        
        Returns:
            Dictionary representation of the comment
        """
        return {
            'id': self.id,
            'body': self.body,
            'author': self.author,
            'author_display_name': self.author_display_name,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'issue_key': self.issue_key,
            'author_email': self.author_email,
            'author_avatar_url': self.author_avatar_url,
            'is_internal': self.is_internal,
            'visibility': self.visibility.copy() if self.visibility else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IssueComment':
        """Create comment from dictionary.
        
        Args:
            data: Dictionary containing comment data
            
        Returns:
            IssueComment instance
            
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
        elif not isinstance(created_at, datetime):
            raise ValueError("created_at must be a datetime or ISO string")
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        elif updated_at is not None and not isinstance(updated_at, datetime):
            raise ValueError("updated_at must be a datetime, ISO string, or None")
        
        return cls(
            id=data['id'],
            body=data['body'],
            author=data['author'],
            author_display_name=data['author_display_name'],
            created_at=created_at,
            updated_at=updated_at,
            issue_key=data.get('issue_key'),
            author_email=data.get('author_email'),
            author_avatar_url=data.get('author_avatar_url'),
            is_internal=data.get('is_internal', False),
            visibility=data.get('visibility')
        )

    @classmethod
    def from_jira_response(cls, jira_data: Dict[str, Any]) -> 'IssueComment':
        """Create comment from Jira API response.
        
        Args:
            jira_data: Raw Jira API response data
            
        Returns:
            IssueComment instance
            
        Raises:
            ValueError: If required Jira fields are missing
            KeyError: If expected Jira structure is invalid
        """
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")
        
        try:
            # Parse timestamps
            created_str = jira_data['created']
            created_at = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            
            updated_at = None
            if 'updated' in jira_data and jira_data['updated']:
                updated_str = jira_data['updated']
                updated_at = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
            
            # Extract author information
            author_info = jira_data.get('author', {})
            author = author_info.get('name', author_info.get('accountId', ''))
            author_display_name = author_info.get('displayName', author)
            author_email = author_info.get('emailAddress')
            author_avatar_url = author_info.get('avatarUrls', {}).get('48x48')
            
            # Handle visibility
            visibility = jira_data.get('visibility')
            
            return cls(
                id=jira_data['id'],
                body=jira_data['body'],
                author=author,
                author_display_name=author_display_name,
                created_at=created_at,
                updated_at=updated_at,
                author_email=author_email,
                author_avatar_url=author_avatar_url,
                visibility=visibility
            )
        except KeyError as e:
            raise ValueError(f"Missing required Jira field: {e}")

    def get_short_body(self, max_length: int = 100) -> str:
        """Get truncated body text for display.
        
        Args:
            max_length: Maximum length of body text
            
        Returns:
            Truncated body text
        """
        if len(self.body) <= max_length:
            return self.body
        return self.body[:max_length - 3] + "..."

    def is_edited(self) -> bool:
        """Check if comment has been edited.
        
        Returns:
            True if comment has been edited
        """
        if self.updated_at is None:
            return False
        
        # Consider a comment edited if updated time is more than 1 minute after creation
        time_diff = self.updated_at - self.created_at
        return time_diff.total_seconds() > 60

    def get_age_string(self) -> str:
        """Get human-readable age of the comment.
        
        Returns:
            Age string (e.g., "2 hours ago")
        """
        now = datetime.now(timezone.utc)
        if self.created_at.tzinfo is not None:
            created_utc = self.created_at.astimezone(timezone.utc)
        else:
            created_utc = self.created_at.replace(tzinfo=timezone.utc)
        
        diff = now - created_utc
        
        if diff.days > 0:
            if diff.days == 1:
                return "1 day ago"
            elif diff.days < 7:
                return f"{diff.days} days ago"
            elif diff.days < 30:
                weeks = diff.days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            elif diff.days < 365:
                months = diff.days // 30
                return f"{months} month{'s' if months > 1 else ''} ago"
            else:
                years = diff.days // 365
                return f"{years} year{'s' if years > 1 else ''} ago"
        
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        
        minutes = diff.seconds // 60
        if minutes > 0:
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        
        return "just now"

    def __str__(self) -> str:
        """String representation of the comment."""
        return f"Comment by {self.author_display_name}: {self.get_short_body(50)}"

    def __repr__(self) -> str:
        """Detailed string representation of the comment."""
        return f"IssueComment(id='{self.id}', author='{self.author}', created='{self.created_at}')"


# Additional methods to extend the existing JiraIssue class:

class JiraIssueExtensions:
    """Extension methods for JiraIssue class."""
    
    @classmethod
    def from_jira_response(cls, jira_data: Dict[str, Any]) -> 'JiraIssue':
        """Create issue from Jira API response.
        
        Args:
            jira_data: Raw Jira API response data
            
        Returns:
            JiraIssue instance
            
        Raises:
            ValueError: If required Jira fields are missing
            KeyError: If expected Jira structure is invalid
        """
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")
        
        try:
            fields = jira_data['fields']
            
            # Parse timestamps
            created_str = fields['created']
            created_at = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            
            updated_at = None
            if 'updated' in fields and fields['updated']:
                updated_str = fields['updated']
                updated_at = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
            
            # Parse priority
            priority_data = fields.get('priority', {})
            priority_name = priority_data.get('name', 'Medium')
            priority = IssuePriority.from_string(priority_name)
            
            # Parse issue type
            issuetype_data = fields.get('issuetype', {})
            type_name = issuetype_data.get('name', 'Task')
            issue_type = IssueType.from_string(type_name)
            
            # Parse status
            status = None
            if 'status' in fields and fields['status']:
                status_name = fields['status'].get('name', '')
                if status_name:
                    try:
                        status = IssueStatus.from_string(status_name)
                    except ValueError:
                        # If status is not in our enum, leave as None
                        pass
            
            # Extract assignee and reporter
            assignee = None
            if fields.get('assignee'):
                assignee = fields['assignee'].get('displayName', fields['assignee'].get('name'))
            
            reporter = None
            if fields.get('reporter'):
                reporter = fields['reporter'].get('displayName', fields['reporter'].get('name'))
            
            # Extract labels, components, fix versions
            labels = [label for label in fields.get('labels', [])]
            
            components = []
            for component in fields.get('components', []):
                components.append(component.get('name', ''))
            
            fix_versions = []
            for version in fields.get('fixVersions', []):
                fix_versions.append(version.get('name', ''))
            
            # Parse optional fields
            story_points = fields.get('customfield_10016')  # Common story points field
            if story_points and isinstance(story_points, (int, float)):
                story_points = int(story_points)
            
            # Parse time tracking
            original_estimate = None
            remaining_estimate = None
            time_spent = None
            
            timetracking = fields.get('timetracking', {})
            if timetracking:
                if 'originalEstimateSeconds' in timetracking:
                    original_estimate = timetracking['originalEstimateSeconds'] // 60  # Convert to minutes
                if 'remainingEstimateSeconds' in timetracking:
                    remaining_estimate = timetracking['remainingEstimateSeconds'] // 60
                if 'timeSpentSeconds' in timetracking:
                    time_spent = timetracking['timeSpentSeconds'] // 60
            
            # Parse parent and epic links
            parent_key = None
            if fields.get('parent'):
                parent_key = fields['parent'].get('key')
            
            epic_link = fields.get('customfield_10014')  # Common epic link field
            
            # Parse resolution
            resolution = None
            resolution_date = None
            if fields.get('resolution'):
                resolution = fields['resolution'].get('name')
                if fields.get('resolutiondate'):
                    resolution_date = datetime.fromisoformat(
                        fields['resolutiondate'].replace('Z', '+00:00')
                    )
            
            # Parse due date
            due_date = None
            if fields.get('duedate'):
                due_date = datetime.fromisoformat(fields['duedate'] + 'T00:00:00+00:00')
            
            # Create URL
            base_url = jira_data.get('self', '').replace('/rest/api/3/issue/', '/browse/')
            if not base_url.startswith('http'):
                base_url = f"https://unknown-domain.atlassian.net/browse/{jira_data['key']}"
            
            # Extract project key from issue key
            project_key = jira_data['key'].split('-')[0]
            
            return cls(
                key=jira_data['key'],
                summary=fields.get('summary', ''),
                description=fields.get('description', ''),
                priority=priority,
                issue_type=issue_type,
                project_key=project_key,
                url=base_url,
                created_at=created_at,
                updated_at=updated_at,
                status=status,
                assignee=assignee,
                reporter=reporter,
                labels=labels,
                components=components,
                fix_versions=fix_versions,
                story_points=story_points,
                original_estimate=original_estimate,
                remaining_estimate=remaining_estimate,
                time_spent=time_spent,
                parent_key=parent_key,
                epic_link=epic_link,
                resolution=resolution,
                resolution_date=resolution_date,
                due_date=due_date
            )
            
        except KeyError as e:
            raise ValueError(f"Missing required Jira field: {e}")
        except Exception as e:
            raise ValueError(f"Error parsing Jira issue data: {e}")

    def get_display_summary(self, max_length: int = 60) -> str:
        """Get truncated summary for display.
        
        Args:
            max_length: Maximum length of summary
            
        Returns:
            Truncated summary
        """
        if len(self.summary) <= max_length:
            return self.summary
        return self.summary[:max_length - 3] + "..."

    def get_status_emoji(self) -> str:
        """Get emoji for current status.
        
        Returns:
            Status emoji
        """
        if self.status:
            return self.status.get_emoji()
        return "❓"

    def is_overdue(self) -> bool:
        """Check if issue is overdue.
        
        Returns:
            True if issue is overdue
        """
        if not self.due_date:
            return False
        
        now = datetime.now(timezone.utc)
        if self.due_date.tzinfo is not None:
            due_utc = self.due_date.astimezone(timezone.utc)
        else:
            due_utc = self.due_date.replace(tzinfo=timezone.utc)
        
        return now > due_utc and self.status not in [IssueStatus.DONE, IssueStatus.CLOSED, IssueStatus.RESOLVED]

    def get_age_days(self) -> int:
        """Get age of issue in days.
        
        Returns:
            Age in days
        """
        now = datetime.now(timezone.utc)
        if self.created_at.tzinfo is not None:
            created_utc = self.created_at.astimezone(timezone.utc)
        else:
            created_utc = self.created_at.replace(tzinfo=timezone.utc)
        
        diff = now - created_utc
        return diff.days

    def get_time_spent_hours(self) -> Optional[float]:
        """Get time spent in hours.
        
        Returns:
            Time spent in hours, or None if not set
        """
        if self.time_spent:
            return self.time_spent / 60.0
        return None

    def get_remaining_estimate_hours(self) -> Optional[float]:
        """Get remaining estimate in hours.
        
        Returns:
            Remaining estimate in hours, or None if not set
        """
        if self.remaining_estimate:
            return self.remaining_estimate / 60.0
        return None

    def get_original_estimate_hours(self) -> Optional[float]:
        """Get original estimate in hours.
        
        Returns:
            Original estimate in hours, or None if not set
        """
        if self.original_estimate:
            return self.original_estimate / 60.0
        return None

    def has_attachment(self) -> bool:
        """Check if issue has attachments (placeholder).
        
        Returns:
            False (not implemented in current model)
        """
        # This would require additional field in the model
        return False

    def is_subtask(self) -> bool:
        """Check if issue is a subtask.
        
        Returns:
            True if issue is a subtask
        """
        return self.issue_type == IssueType.SUBTASK or self.parent_key is not None

    def is_epic(self) -> bool:
        """Check if issue is an epic.
        
        Returns:
            True if issue is an epic
        """
        return self.issue_type == IssueType.EPIC