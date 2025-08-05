#!/usr/bin/env python3
"""
Issue model for the Telegram-Jira bot.

Contains JiraIssue, IssueComment, and related functionality for managing
Jira issues within the bot ecosystem. All methods previously in JiraIssueExtensions
have been merged into the JiraIssue class.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Union
from .enums import IssuePriority, IssueType, IssueStatus


def parse_jira_iso(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Jira ISO datetime string with tolerant handling.
    
    Centralized date parsing function that handles various Jira date formats:
    - ISO format with Z suffix: 2023-12-01T10:30:00.000Z
    - ISO format with timezone: 2023-12-01T10:30:00.000+0000
    - ISO format with colon timezone: 2023-12-01T10:30:00.000+00:00
    
    Args:
        date_str: Date string from Jira API
        
    Returns:
        Parsed datetime object or None if parsing fails
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # Handle Z suffix (UTC timezone)
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        # Handle +0000 format without colon
        elif date_str.endswith('+0000'):
            date_str = date_str[:-5] + '+00:00'
        elif date_str.endswith('-0000'):
            date_str = date_str[:-5] + '+00:00'
        # Handle timezone offset formats like +0100, -0500
        elif re.search(r'[+-]\d{4}$', date_str):
            # Insert colon in timezone offset
            date_str = date_str[:-2] + ':' + date_str[-2:]
        
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError, TypeError):
        return None


@dataclass
class JiraIssue:
    """Jira issue data model with comprehensive validation and business logic.
    
    This class contains all functionality for Jira issues including validation,
    serialization, formatting, and utility methods previously in JiraIssueExtensions.
    """
    key: str
    summary: str
    description: str
    priority: IssuePriority
    issue_type: IssueType
    project_key: str
    url: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    status: Optional[IssueStatus] = None
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    fix_versions: List[str] = field(default_factory=list)
    story_points: Optional[int] = None
    original_estimate: Optional[int] = None  # in minutes
    remaining_estimate: Optional[int] = None  # in minutes
    time_spent: Optional[int] = None  # in minutes
    parent_key: Optional[str] = None  # for subtasks
    epic_link: Optional[str] = None
    resolution: Optional[str] = None
    resolution_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    telegram_user_id: Optional[int] = None
    telegram_message_id: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate issue data after initialization."""
        self._validate_required_fields()
        self._validate_enums()
        self._validate_datetime_fields()
        self._validate_optional_fields()

    def _validate_required_fields(self) -> None:
        """Validate required string fields."""
        required_string_fields = {
            'key': self.key,
            'summary': self.summary,
            'project_key': self.project_key,
            'url': self.url
        }
        
        for field_name, field_value in required_string_fields.items():
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")
        
        # Validate key format (PROJECT-123)
        if not re.match(r'^[A-Z][A-Z0-9_]*-\d+$', self.key):
            raise ValueError("key must be in format PROJECT-123")

    def _validate_enums(self) -> None:
        """Validate enum fields."""
        if not isinstance(self.priority, IssuePriority):
            raise TypeError("priority must be an IssuePriority instance")
        if not isinstance(self.issue_type, IssueType):
            raise TypeError("issue_type must be an IssueType instance")
        if self.status is not None and not isinstance(self.status, IssueStatus):
            raise TypeError("status must be an IssueStatus instance or None")

    def _validate_datetime_fields(self) -> None:
        """Validate datetime fields."""
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime object")
        
        optional_datetime_fields = [
            self.updated_at, self.resolution_date, self.due_date
        ]
        for field in optional_datetime_fields:
            if field is not None and not isinstance(field, datetime):
                raise TypeError("datetime fields must be datetime objects or None")

    def _validate_optional_fields(self) -> None:
        """Validate optional fields."""
        # Validate lists
        list_fields = [self.labels, self.components, self.fix_versions]
        for field in list_fields:
            if not isinstance(field, list):
                raise TypeError("list fields must be lists")
            for item in field:
                if not isinstance(item, str):
                    raise TypeError("list items must be strings")
        
        # Validate numeric fields
        numeric_fields = [
            self.story_points, self.original_estimate,
            self.remaining_estimate, self.time_spent,
            self.telegram_user_id, self.telegram_message_id
        ]
        for field in numeric_fields:
            if field is not None and not isinstance(field, int):
                raise TypeError("numeric fields must be integers or None")
            if field is not None and field < 0:
                raise ValueError("numeric fields must be non-negative")

    @classmethod
    def from_jira_response(cls, jira_data: Dict[str, Any], base_url: str = "") -> 'JiraIssue':
        """Create JiraIssue from Jira REST API response.
        
        Args:
            jira_data: Raw response data from Jira API
            base_url: Base URL for building issue links
            
        Returns:
            JiraIssue instance
            
        Raises:
            ValueError: If required fields are missing
            TypeError: If data types are incorrect
        """
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")
        
        # Extract basic fields
        key = jira_data.get('key', '')
        if not key:
            raise ValueError("Issue key is required")
        
        fields = jira_data.get('fields', {})
        
        # Extract summary and description
        summary = fields.get('summary', '')
        if not summary:
            raise ValueError("Issue summary is required")
        
        description_data = fields.get('description', {})
        description = cls._extract_description_text(description_data)
        
        # Extract project key
        project_data = fields.get('project', {})
        project_key = project_data.get('key', '')
        if not project_key:
            raise ValueError("Project key is required")
        
        # Parse enums with validation
        try:
            priority_data = fields.get('priority', {})
            priority_name = priority_data.get('name', 'Medium')
            priority = IssuePriority.from_string(priority_name)
        except (ValueError, TypeError):
            priority = IssuePriority.MEDIUM
        
        try:
            issue_type_data = fields.get('issuetype', {})
            issue_type_name = issue_type_data.get('name', 'Task')
            issue_type = IssueType.from_string(issue_type_name)
        except (ValueError, TypeError):
            issue_type = IssueType.TASK
        
        status = None
        if fields.get('status'):
            try:
                status_name = fields['status'].get('name', '')
                if status_name:
                    status = IssueStatus.from_string(status_name)
            except (ValueError, TypeError):
                pass
        
        # Parse dates using centralized function
        created_at = parse_jira_iso(fields.get('created', '')) or datetime.now(timezone.utc)
        updated_at = parse_jira_iso(fields.get('updated', ''))
        resolution_date = parse_jira_iso(fields.get('resolutiondate', ''))
        due_date = parse_jira_iso(fields.get('duedate', ''))
        
        # Extract user information (prefer accountId over deprecated name)
        assignee_data = fields.get('assignee', {})
        assignee = None
        if assignee_data:
            assignee = (assignee_data.get('accountId') or 
                       assignee_data.get('name') or 
                       assignee_data.get('displayName', ''))
        
        reporter_data = fields.get('reporter', {})
        reporter = None
        if reporter_data:
            reporter = (reporter_data.get('accountId') or
                       reporter_data.get('name') or
                       reporter_data.get('displayName', ''))
        
        # Extract arrays with validation
        labels = fields.get('labels', [])
        if not isinstance(labels, list):
            labels = []
        
        components_data = fields.get('components', [])
        components = []
        if isinstance(components_data, list):
            components = [comp.get('name', '') for comp in components_data 
                         if isinstance(comp, dict) and comp.get('name')]
        
        fix_versions_data = fields.get('fixVersions', [])
        fix_versions = []
        if isinstance(fix_versions_data, list):
            fix_versions = [ver.get('name', '') for ver in fix_versions_data
                           if isinstance(ver, dict) and ver.get('name')]
        
        # Extract numeric fields with validation
        story_points = fields.get('customfield_10016')  # Common field ID
        if story_points is not None:
            try:
                story_points = int(float(story_points))
                if story_points < 0:
                    story_points = None
            except (ValueError, TypeError):
                story_points = None
        
        # Time tracking
        timetracking = fields.get('timetracking', {})
        original_estimate = cls._parse_time_duration(timetracking.get('originalEstimate'))
        remaining_estimate = cls._parse_time_duration(timetracking.get('remainingEstimate'))
        time_spent = cls._parse_time_duration(timetracking.get('timeSpent'))
        
        # Parent and epic links
        parent_data = fields.get('parent', {})
        parent_key = parent_data.get('key') if parent_data else None
        
        epic_link = fields.get('customfield_10014')  # Common epic link field
        
        # Resolution
        resolution_data = fields.get('resolution', {})
        resolution = resolution_data.get('name') if resolution_data else None
        
        # Build URL - prefer browse URL over API URL
        url = f"{base_url.rstrip('/')}/browse/{key}" if base_url else f"/browse/{key}"
        
        return cls(
            key=key,
            summary=summary,
            description=description,
            priority=priority,
            issue_type=issue_type,
            project_key=project_key,
            url=url,
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

    @classmethod
    def _extract_description_text(cls, description_data: Any) -> str:
        """Extract plain text from Jira description (handles ADF format).
        
        Args:
            description_data: Description data from Jira (string or ADF format)
            
        Returns:
            Plain text description
        """
        if not description_data:
            return ""
        
        if isinstance(description_data, str):
            return description_data
        
        if isinstance(description_data, dict):
            # Handle Atlassian Document Format (ADF)
            content = description_data.get('content', [])
            if isinstance(content, list):
                return cls._extract_text_from_adf(content)
        
        return str(description_data) if description_data else ""

    @staticmethod
    def _extract_text_from_adf(content: List[Dict[str, Any]]) -> str:
        """Extract plain text from Atlassian Document Format.
        
        Args:
            content: ADF content array
            
        Returns:
            Extracted plain text
        """
        text_parts = []
        
        for item in content:
            if not isinstance(item, dict):
                continue
                
            item_type = item.get('type', '')
            
            if item_type == 'paragraph':
                paragraph_content = item.get('content', [])
                paragraph_text = []
                for text_item in paragraph_content:
                    if isinstance(text_item, dict) and text_item.get('type') == 'text':
                        paragraph_text.append(text_item.get('text', ''))
                if paragraph_text:
                    text_parts.append(' '.join(paragraph_text))
            elif item_type == 'text':
                text_parts.append(item.get('text', ''))
        
        return '\n'.join(text_parts).strip()

    @staticmethod
    def _parse_time_duration(duration_str: Optional[str]) -> Optional[int]:
        """Parse Jira time duration to minutes.
        
        Common formats: "2h 30m", "1d 4h", "45m", "3h", "1w 2d"
        
        Args:
            duration_str: Duration string from Jira
            
        Returns:
            Duration in minutes or None if parsing fails
        """
        if not duration_str or not isinstance(duration_str, str):
            return None
        
        try:
            total_minutes = 0
            
            # Convert weeks to minutes (1w = 5 working days = 2400 minutes)
            weeks_match = re.search(r'(\d+)w', duration_str)
            if weeks_match:
                total_minutes += int(weeks_match.group(1)) * 5 * 8 * 60
            
            # Convert days to minutes (1d = 8 hours = 480 minutes)
            days_match = re.search(r'(\d+)d', duration_str)
            if days_match:
                total_minutes += int(days_match.group(1)) * 8 * 60
            
            # Convert hours to minutes
            hours_match = re.search(r'(\d+)h', duration_str)
            if hours_match:
                total_minutes += int(hours_match.group(1)) * 60
            
            # Add minutes
            minutes_match = re.search(r'(\d+)m', duration_str)
            if minutes_match:
                total_minutes += int(minutes_match.group(1))
            
            return total_minutes if total_minutes > 0 else None
        except (ValueError, AttributeError, TypeError):
            return None

    # Display and formatting methods (previously in JiraIssueExtensions)
    
    def get_display_summary(self, max_length: int = 50) -> str:
        """Get formatted display summary with emojis.
        
        Args:
            max_length: Maximum length for summary text
            
        Returns:
            Formatted summary with priority and type emojis
        """
        priority_emoji = self.priority.get_emoji()
        type_emoji = self.issue_type.get_emoji()
        
        summary_text = self.summary
        if len(summary_text) > max_length:
            summary_text = summary_text[:max_length-3] + "..."
        
        return f"{priority_emoji} {type_emoji} `{self.key}`: {summary_text}"

    def get_status_emoji(self) -> str:
        """Get emoji for current status.
        
        Returns:
            Status emoji or empty string if no status
        """
        return self.status.get_emoji() if self.status else ""

    def is_overdue(self) -> bool:
        """Check if issue is overdue based on due date and status.
        
        Returns:
            True if issue is overdue and not completed
        """
        if not self.due_date:
            return False
        
        now = datetime.now(timezone.utc)
        is_past_due = now > self.due_date
        
        # Not overdue if already completed
        if self.status in {IssueStatus.DONE, IssueStatus.CLOSED, IssueStatus.RESOLVED}:
            return False
        
        return is_past_due

    def get_age_days(self) -> int:
        """Get age of issue in days since creation.
        
        Returns:
            Number of days since issue was created
        """
        now = datetime.now(timezone.utc)
        age_delta = now - self.created_at
        return max(0, age_delta.days)

    def get_age_hours(self) -> int:
        """Get age of issue in hours since creation.
        
        Returns:
            Number of hours since issue was created
        """
        now = datetime.now(timezone.utc)
        age_delta = now - self.created_at
        return max(0, int(age_delta.total_seconds() / 3600))

    def get_updated_hours(self) -> int:
        """Get hours since last update.
        
        Returns:
            Number of hours since last update, or age if never updated
        """
        if not self.updated_at:
            return self.get_age_hours()
        
        now = datetime.now(timezone.utc)
        update_delta = now - self.updated_at
        return max(0, int(update_delta.total_seconds() / 3600))

    def has_attachment(self) -> bool:
        """Check if issue has attachments (placeholder).
        
        Returns:
            False (attachment data not available in current model)
        """
        # This would require additional API call or field in model
        return False

    def is_subtask(self) -> bool:
        """Check if this is a subtask.
        
        Returns:
            True if issue is a subtask
        """
        return (self.issue_type == IssueType.SUBTASK or 
                self.parent_key is not None)

    def is_epic(self) -> bool:
        """Check if this is an epic.
        
        Returns:
            True if issue is an epic
        """
        return self.issue_type == IssueType.EPIC

    def get_time_estimates_summary(self) -> Optional[str]:
        """Get formatted time estimates summary.
        
        Returns:
            Formatted time tracking info or None if no time data
        """
        if not any([self.original_estimate, self.remaining_estimate, self.time_spent]):
            return None
        
        def format_minutes(minutes: Optional[int]) -> str:
            if not minutes:
                return "0m"
            hours, mins = divmod(minutes, 60)
            if hours:
                return f"{hours}h {mins}m" if mins else f"{hours}h"
            return f"{mins}m"
        
        parts = []
        if self.original_estimate:
            parts.append(f"Est: {format_minutes(self.original_estimate)}")
        if self.time_spent:
            parts.append(f"Spent: {format_minutes(self.time_spent)}")
        if self.remaining_estimate:
            parts.append(f"Remaining: {format_minutes(self.remaining_estimate)}")
        
        return " • ".join(parts) if parts else None

    def get_formatted_summary(self, include_url: bool = True, max_description_length: int = 100) -> str:
        """Get comprehensive formatted summary for display.
        
        Args:
            include_url: Whether to include Jira URL
            max_description_length: Maximum description length
            
        Returns:
            Formatted issue summary
        """
        priority_emoji = self.priority.get_emoji()
        type_emoji = self.issue_type.get_emoji()
        status_emoji = self.get_status_emoji()
        
        summary = f"{priority_emoji} {type_emoji} **{self.key}**: {self.summary}\n"
        
        if self.status:
            summary += f"{status_emoji} Status: {self.status.value}\n"
        
        if self.assignee:
            summary += f"👤 Assignee: {self.assignee}\n"
        
        if self.description and len(self.description.strip()) > 0:
            desc = self.description[:max_description_length]
            if len(self.description) > max_description_length:
                desc += "..."
            summary += f"📝 {desc}\n"
        
        if self.labels:
            labels_text = ", ".join(self.labels[:5])  # Show max 5 labels
            if len(self.labels) > 5:
                labels_text += f" (+{len(self.labels) - 5} more)"
            summary += f"🏷️ Labels: {labels_text}\n"
        
        if self.due_date:
            due_text = self.due_date.strftime('%Y-%m-%d')
            if self.is_overdue():
                due_text = f"🚨 {due_text} (overdue)"
            summary += f"📅 Due: {due_text}\n"
        
        time_summary = self.get_time_estimates_summary()
        if time_summary:
            summary += f"⏱️ Time: {time_summary}\n"
        
        if include_url:
            summary += f"\n🔗 [View in Jira]({self.url})"
        
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to dictionary for serialization.
        
        Returns:
            Dictionary representation of the issue
        """
        return {
            'key': self.key,
            'summary': self.summary,
            'description': self.description,
            'priority': self.priority.value,
            'issue_type': self.issue_type.value,
            'project_key': self.project_key,
            'url': self.url,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'status': self.status.value if self.status else None,
            'assignee': self.assignee,
            'reporter': self.reporter,
            'labels': self.labels.copy(),
            'components': self.components.copy(),
            'fix_versions': self.fix_versions.copy(),
            'story_points': self.story_points,
            'original_estimate': self.original_estimate,
            'remaining_estimate': self.remaining_estimate,
            'time_spent': self.time_spent,
            'parent_key': self.parent_key,
            'epic_link': self.epic_link,
            'resolution': self.resolution,
            'resolution_date': self.resolution_date.isoformat() if self.resolution_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'telegram_user_id': self.telegram_user_id,
            'telegram_message_id': self.telegram_message_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JiraIssue':
        """Create JiraIssue from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            JiraIssue instance
            
        Raises:
            TypeError: If data is not a dictionary
            ValueError: If required fields are missing or invalid
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse required fields
        key = data.get('key', '')
        summary = data.get('summary', '')
        description = data.get('description', '')
        project_key = data.get('project_key', '')
        url = data.get('url', '')
        
        if not all([key, summary, project_key, url]):
            raise ValueError("Missing required fields: key, summary, project_key, url")

        # Parse enums
        try:
            priority = IssuePriority.from_string(data.get('priority', 'Medium'))
        except (ValueError, TypeError):
            priority = IssuePriority.MEDIUM

        try:
            issue_type = IssueType.from_string(data.get('issue_type', 'Task'))
        except (ValueError, TypeError):
            issue_type = IssueType.TASK

        status = None
        if data.get('status'):
            try:
                status = IssueStatus.from_string(data['status'])
            except (ValueError, TypeError):
                pass

        # Parse dates
        created_at = parse_jira_iso(data.get('created_at')) or datetime.now(timezone.utc)
        updated_at = parse_jira_iso(data.get('updated_at'))
        resolution_date = parse_jira_iso(data.get('resolution_date'))
        due_date = parse_jira_iso(data.get('due_date'))

        return cls(
            key=key,
            summary=summary,
            description=description,
            priority=priority,
            issue_type=issue_type,
            project_key=project_key,
            url=url,
            created_at=created_at,
            updated_at=updated_at,
            status=status,
            assignee=data.get('assignee'),
            reporter=data.get('reporter'),
            labels=data.get('labels', []),
            components=data.get('components', []),
            fix_versions=data.get('fix_versions', []),
            story_points=data.get('story_points'),
            original_estimate=data.get('original_estimate'),
            remaining_estimate=data.get('remaining_estimate'),
            time_spent=data.get('time_spent'),
            parent_key=data.get('parent_key'),
            epic_link=data.get('epic_link'),
            resolution=data.get('resolution'),
            resolution_date=resolution_date,
            due_date=due_date,
            telegram_user_id=data.get('telegram_user_id'),
            telegram_message_id=data.get('telegram_message_id')
        )

    def __str__(self) -> str:
        """String representation of the issue."""
        return f"{self.key}: {self.summary}"

    def __repr__(self) -> str:
        """Developer representation of the issue."""
        return (f"JiraIssue(key='{self.key}', project='{self.project_key}', "
                f"type={self.issue_type.value}, priority={self.priority.value})")


@dataclass
class IssueComment:
    """Represents a comment on a Jira issue."""
    id: str
    author: str
    body: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    visibility: Optional[str] = None  # For restricted comments
    issue_key: Optional[str] = None  # Reference to parent issue
    
    def __post_init__(self) -> None:
        """Validate comment data after initialization."""
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("id must be a non-empty string")
        if not isinstance(self.author, str) or not self.author.strip():
            raise ValueError("author must be a non-empty string")
        if not isinstance(self.body, str):
            raise TypeError("body must be a string")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime object")
        if self.updated_at is not None and not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be a datetime object or None")

    @classmethod
    def from_jira_response(cls, comment_data: Dict[str, Any], issue_key: Optional[str] = None) -> 'IssueComment':
        """Create IssueComment from Jira REST API response.
        
        Args:
            comment_data: Raw comment data from Jira API
            issue_key: Key of the parent issue
            
        Returns:
            IssueComment instance
            
        Raises:
            ValueError: If required fields are missing
            TypeError: If data types are incorrect
        """
        if not isinstance(comment_data, dict):
            raise TypeError("comment_data must be a dictionary")
        
        comment_id = comment_data.get('id', '')
        if not comment_id:
            raise ValueError("Comment ID is required")
        
        # Extract author information (prefer accountId over name)
        author_info = comment_data.get('author', {})
        author = ""
        if author_info:
            author = (author_info.get('accountId') or 
                     author_info.get('name') or 
                     author_info.get('displayName', ''))
        
        if not author:
            author = "Unknown User"
        
        # Extract body (may be ADF format)
        body_data = comment_data.get('body', '')
        if isinstance(body_data, dict):
            # Handle ADF format
            body = JiraIssue._extract_text_from_adf(body_data.get('content', []))
        else:
            body = str(body_data) if body_data else ""
        
        # Parse dates
        created_at = parse_jira_iso(comment_data.get('created', '')) or datetime.now(timezone.utc)
        updated_at = parse_jira_iso(comment_data.get('updated', ''))
        
        # Extract visibility
        visibility_data = comment_data.get('visibility', {})
        visibility = None
        if visibility_data:
            visibility_type = visibility_data.get('type', '')
            visibility_value = visibility_data.get('value', '')
            if visibility_type and visibility_value:
                visibility = f"{visibility_type}:{visibility_value}"
        
        return cls(
            id=comment_id,
            author=author,
            body=body,
            created_at=created_at,
            updated_at=updated_at,
            visibility=visibility,
            issue_key=issue_key
        )

    def get_formatted_comment(self, max_length: int = 200) -> str:
        """Get formatted comment for display.
        
        Args:
            max_length: Maximum length for comment body
            
        Returns:
            Formatted comment with author and timestamp
        """
        body_preview = self.body[:max_length]
        if len(self.body) > max_length:
            body_preview += "..."
        
        created_date = self.created_at.strftime('%Y-%m-%d %H:%M')
        
        comment = f"💬 **{self.author}** ({created_date})\n"
        comment += f"{body_preview}"
        
        if self.visibility:
            comment += f"\n🔒 Visible to: {self.visibility}"
        
        return comment

    def get_age_hours(self) -> int:
        """Get age of comment in hours.
        
        Returns:
            Number of hours since comment was created
        """
        now = datetime.now(timezone.utc)
        age_delta = now - self.created_at
        return max(0, int(age_delta.total_seconds() / 3600))

    def to_dict(self) -> Dict[str, Any]:
        """Convert comment to dictionary for serialization.
        
        Returns:
            Dictionary representation of the comment
        """
        return {
            'id': self.id,
            'author': self.author,
            'body': self.body,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'visibility': self.visibility,
            'issue_key': self.issue_key
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IssueComment':
        """Create IssueComment from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            IssueComment instance
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        created_at = parse_jira_iso(data.get('created_at')) or datetime.now(timezone.utc)
        updated_at = parse_jira_iso(data.get('updated_at'))

        return cls(
            id=data['id'],
            author=data['author'],
            body=data['body'],
            created_at=created_at,
            updated_at=updated_at,
            visibility=data.get('visibility'),
            issue_key=data.get('issue_key')
        )

    def __str__(self) -> str:
        """String representation of the comment."""
        return f"Comment by {self.author}: {self.body[:50]}..."

    def __repr__(self) -> str:
        """Developer representation of the comment."""
        return f"IssueComment(id='{self.id}', author='{self.author}', issue='{self.issue_key}')"


@dataclass
class IssueSearchResult:
    """Result of an issue search operation."""
    issues: List[JiraIssue]
    total_count: int
    search_query: Optional[str] = None
    filters_applied: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate search result data."""
        if not isinstance(self.issues, list):
            raise TypeError("issues must be a list")
        if not isinstance(self.total_count, int) or self.total_count < 0:
            raise ValueError("total_count must be a non-negative integer")
        if self.search_query is not None and not isinstance(self.search_query, str):
            raise TypeError("search_query must be a string or None")
        if not isinstance(self.filters_applied, dict):
            raise TypeError("filters_applied must be a dictionary")
        
        # Validate all issues are JiraIssue instances
        for issue in self.issues:
            if not isinstance(issue, JiraIssue):
                raise TypeError("All items in issues list must be JiraIssue instances")
    
    def has_results(self) -> bool:
        """Check if search returned any results.
        
        Returns:
            True if there are results
        """
        return len(self.issues) > 0
    
    def get_summary(self) -> str:
        """Get search result summary.
        
        Returns:
            Formatted summary of search results
        """
        if not self.has_results():
            return "No issues found"
        
        query_text = f" for '{self.search_query}'" if self.search_query else ""
        filter_text = ""
        
        if self.filters_applied:
            filter_parts = []
            for key, value in self.filters_applied.items():
                if value:
                    filter_parts.append(f"{key}={value}")
            if filter_parts:
                filter_text = f" ({', '.join(filter_parts)})"
        
        return f"Found {len(self.issues)} of {self.total_count} issues{query_text}{filter_text}"

    def get_issues_by_priority(self) -> Dict[IssuePriority, List[JiraIssue]]:
        """Group issues by priority.
        
        Returns:
            Dictionary mapping priorities to issue lists
        """
        result: Dict[IssuePriority, List[JiraIssue]] = {}
        for issue in self.issues:
            if issue.priority not in result:
                result[issue.priority] = []
            result[issue.priority].append(issue)
        return result

    def get_issues_by_status(self) -> Dict[Optional[IssueStatus], List[JiraIssue]]:
        """Group issues by status.
        
        Returns:
            Dictionary mapping statuses to issue lists
        """
        result: Dict[Optional[IssueStatus], List[JiraIssue]] = {}
        for issue in self.issues:
            if issue.status not in result:
                result[issue.status] = []
            result[issue.status].append(issue)
        return result

    def get_overdue_issues(self) -> List[JiraIssue]:
        """Get list of overdue issues.
        
        Returns:
            List of overdue issues
        """
        return [issue for issue in self.issues if issue.is_overdue()]

    def __len__(self) -> int:
        """Get number of issues in results."""
        return len(self.issues)

    def __iter__(self):
        """Iterate over issues."""
        return iter(self.issues)

    def __getitem__(self, index: int) -> JiraIssue:
        """Get issue by index."""
        return self.issues[index]
    
    
    