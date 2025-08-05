#!/usr/bin/env python3
"""
Issue model for the Telegram-Jira bot.

Contains the JiraIssue dataclass and related functionality.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from .enums import IssuePriority, IssueType, IssueStatus


@dataclass
class JiraIssue:
    """Jira issue data model."""
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
            raise TypeError("created_at must be a datetime")
        
        optional_datetime_fields = [
            self.updated_at, self.resolution_date, self.due_date
        ]
        for dt_field in optional_datetime_fields:
            if dt_field is not None and not isinstance(dt_field, datetime):
                raise TypeError("datetime fields must be datetime instances or None")

    def _validate_optional_fields(self) -> None:
        """Validate optional fields."""
        if self.story_points is not None and (not isinstance(self.story_points, int) or self.story_points < 0):
            raise ValueError("story_points must be a non-negative integer or None")
        
        time_fields = [self.original_estimate, self.remaining_estimate, self.time_spent]
        for time_field in time_fields:
            if time_field is not None and (not isinstance(time_field, int) or time_field < 0):
                raise ValueError("time fields must be non-negative integers or None")
        
        telegram_id_fields = [self.telegram_user_id, self.telegram_message_id]
        for id_field in telegram_id_fields:
            if id_field is not None and (not isinstance(id_field, int) or id_field <= 0):
                raise ValueError("telegram ID fields must be positive integers or None")

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to dictionary for serialization."""
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
            'labels': self.labels,
            'components': self.components,
            'fix_versions': self.fix_versions,
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
        """Create JiraIssue from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse enum fields
        priority = IssuePriority.from_string(data['priority'])
        issue_type = IssueType.from_string(data['issue_type'])
        status = None
        if data.get('status'):
            status = IssueStatus.from_string(data['status'])

        # Parse datetime fields
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = None
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        resolution_date = None
        if data.get('resolution_date'):
            resolution_date = datetime.fromisoformat(data['resolution_date'])
            
        due_date = None
        if data.get('due_date'):
            due_date = datetime.fromisoformat(data['due_date'])

        return cls(
            key=data['key'],
            summary=data['summary'],
            description=data.get('description', ''),
            priority=priority,
            issue_type=issue_type,
            project_key=data['project_key'],
            url=data['url'],
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

    @classmethod  
    def from_jira_data(cls, jira_data: Dict[str, Any], project_key: str, base_url: str) -> 'JiraIssue':
        """Create JiraIssue from Jira API response data."""
        if not isinstance(jira_data, dict):
            raise TypeError("jira_data must be a dictionary")

        fields = jira_data.get('fields', {})
        key = jira_data.get('key', '')
        
        # Extract basic fields
        summary = fields.get('summary', '')
        description_field = fields.get('description', {})
        
        # Handle different description formats (Atlassian Document Format)
        description = ''
        if isinstance(description_field, dict):
            content = description_field.get('content', [])
            if content:
                # Extract text from ADF format
                description = cls._extract_text_from_adf(content)
        elif isinstance(description_field, str):
            description = description_field

        # Parse enums
        priority_data = fields.get('priority', {})
        priority_name = priority_data.get('name', 'Medium')
        try:
            priority = IssuePriority.from_string(priority_name)
        except ValueError:
            priority = IssuePriority.MEDIUM

        issue_type_data = fields.get('issuetype', {})
        issue_type_name = issue_type_data.get('name', 'Task')
        try:
            issue_type = IssueType.from_string(issue_type_name)
        except ValueError:
            issue_type = IssueType.TASK

        status_data = fields.get('status', {})
        status_name = status_data.get('name', '')
        status = None
        if status_name:
            try:
                status = IssueStatus.from_string(status_name)
            except ValueError:
                pass

        # Parse dates
        created_str = fields.get('created', '')
        created_at = cls._parse_jira_datetime(created_str) or datetime.now(timezone.utc)
        
        updated_str = fields.get('updated', '')
        updated_at = cls._parse_jira_datetime(updated_str)
        
        resolution_date_str = fields.get('resolutiondate', '')
        resolution_date = cls._parse_jira_datetime(resolution_date_str)
        
        due_date_str = fields.get('duedate', '')
        due_date = cls._parse_jira_datetime(due_date_str)

        # Extract user information
        assignee_data = fields.get('assignee', {})
        assignee = assignee_data.get('displayName') if assignee_data else None
        
        reporter_data = fields.get('reporter', {})
        reporter = reporter_data.get('displayName') if reporter_data else None

        # Extract arrays
        labels = fields.get('labels', [])
        
        components_data = fields.get('components', [])
        components = [comp.get('name', '') for comp in components_data if isinstance(comp, dict)]
        
        fix_versions_data = fields.get('fixVersions', [])
        fix_versions = [ver.get('name', '') for ver in fix_versions_data if isinstance(ver, dict)]

        # Extract numeric fields
        story_points = fields.get('customfield_10016')  # Common field ID for story points
        if story_points is not None:
            try:
                story_points = int(float(story_points))
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
        
        epic_link = fields.get('customfield_10014')  # Common field ID for epic link

        # Resolution
        resolution_data = fields.get('resolution', {})
        resolution = resolution_data.get('name') if resolution_data else None

        # Build URL
        url = f"{base_url}/browse/{key}"

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

    @staticmethod
    def _extract_text_from_adf(content: List[Dict[str, Any]]) -> str:
        """Extract plain text from Atlassian Document Format."""
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
                text_parts.append(' '.join(paragraph_text))
            elif item_type == 'text':
                text_parts.append(item.get('text', ''))
        
        return '\n'.join(text_parts).strip()

    @staticmethod
    def _parse_jira_datetime(date_str: str) -> Optional[datetime]:
        """Parse Jira datetime string."""
        if not date_str:
            return None
        
        try:
            # Jira typically uses ISO format: 2023-12-01T10:30:00.000+0000
            if date_str.endswith('+0000'):
                date_str = date_str[:-5] + '+00:00'
            elif date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            elif '.' in date_str and not date_str.endswith('+00:00'):
                # Handle timezone offset
                if '+' in date_str:
                    parts = date_str.split('+')
                    date_str = parts[0] + '+' + parts[1][:2] + ':' + parts[1][2:]
                elif date_str.count('-') > 2:  # Negative timezone
                    parts = date_str.rsplit('-', 1)
                    if len(parts[1]) == 4:
                        date_str = parts[0] + '-' + parts[1][:2] + ':' + parts[1][2:]
            
            return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _parse_time_duration(duration_str: Optional[str]) -> Optional[int]:
        """Parse Jira time duration to minutes."""
        if not duration_str:
            return None
        
        try:
            # Common formats: "2h 30m", "1d 4h", "45m", "3h", "1w 2d"
            total_minutes = 0
            
            # Convert weeks to minutes (1w = 5 working days = 2400 minutes)
            if 'w' in duration_str:
                import re
                weeks = re.findall(r'(\d+)w', duration_str)
                if weeks:
                    total_minutes += int(weeks[0]) * 5 * 8 * 60  # 5 days * 8 hours * 60 minutes
            
            # Convert days to minutes (1d = 8 hours = 480 minutes)
            if 'd' in duration_str:
                import re
                days = re.findall(r'(\d+)d', duration_str)
                if days:
                    total_minutes += int(days[0]) * 8 * 60
            
            # Convert hours to minutes
            if 'h' in duration_str:
                import re
                hours = re.findall(r'(\d+)h', duration_str)
                if hours:
                    total_minutes += int(hours[0]) * 60
            
            # Add minutes
            if 'm' in duration_str:
                import re
                minutes = re.findall(r'(\d+)m', duration_str)
                if minutes:
                    total_minutes += int(minutes[0])
            
            return total_minutes if total_minutes > 0 else None
        except (ValueError, AttributeError):
            return None

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update issue fields from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        updatable_fields = {
            'summary', 'description', 'assignee', 'labels', 'components',
            'fix_versions', 'story_points', 'due_date', 'epic_link'
        }
        
        for field, value in data.items():
            if field in updatable_fields and hasattr(self, field):
                if field == 'due_date' and value:
                    if isinstance(value, str):
                        value = datetime.fromisoformat(value)
                setattr(self, field, value)
        
        # Handle enum updates
        if 'priority' in data:
            if isinstance(data['priority'], str):
                self.priority = IssuePriority.from_string(data['priority'])
            elif isinstance(data['priority'], IssuePriority):
                self.priority = data['priority']
        
        if 'issue_type' in data:
            if isinstance(data['issue_type'], str):
                self.issue_type = IssueType.from_string(data['issue_type'])
            elif isinstance(data['issue_type'], IssueType):
                self.issue_type = data['issue_type']
        
        if 'status' in data:
            if isinstance(data['status'], str):
                self.status = IssueStatus.from_string(data['status'])
            elif isinstance(data['status'], IssueStatus):
                self.status = data['status']
        
        self.updated_at = datetime.now(timezone.utc)
        
        # Re-validate after update
        self.__post_init__()

    def get_formatted_summary(self, include_url: bool = True, max_description_length: int = 100) -> str:
        """Get formatted summary for display."""
        priority_emoji = self.priority.get_emoji()
        type_emoji = self.issue_type.get_emoji()
        status_emoji = self.status.get_emoji() if self.status else ""
        
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
        
        if include_url:
            summary += f"\n🔗 [View in Jira]({self.url})"
        
        return summary

    def get_short_summary(self) -> str:
        """Get short summary for lists."""
        priority_emoji = self.priority.get_emoji()
        type_emoji = self.issue_type.get_emoji()
        return f"{priority_emoji} {type_emoji} `{self.key}`: {self.summary[:50]}{'...' if len(self.summary) > 50 else ''}"

    def is_overdue(self) -> bool:
        """Check if issue is overdue."""
        if not self.due_date:
            return False
        return datetime.now(timezone.utc) > self.due_date and self.status not in [IssueStatus.DONE, IssueStatus.CLOSED, IssueStatus.RESOLVED]

    def get_age_days(self) -> int:
        """Get age of issue in days."""
        return (datetime.now(timezone.utc) - self.created_at).days

    def get_time_estimates_summary(self) -> Optional[str]:
        """Get formatted time estimates."""
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

    def __str__(self) -> str:
        """String representation of the issue."""
        return f"{self.key}: {self.summary}"

    def __repr__(self) -> str:
        """Developer representation of the issue."""
        return (f"JiraIssue(key='{self.key}', project='{self.project_key}', "
                f"type={self.issue_type.value}, priority={self.priority.value})")


@dataclass
class IssueSearchResult:
    """Result of an issue search operation."""
    issues: List[JiraIssue]
    total_count: int
    search_query: Optional[str] = None
    filters_applied: Dict[str, Any] = field(default_factory=dict)
    
    def has_results(self) -> bool:
        """Check if search returned any results."""
        return len(self.issues) > 0
    
    def get_summary(self) -> str:
        """Get search result summary."""
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


@dataclass
class IssueComment:
    """Represents a comment on a Jira issue."""
    id: str
    author: str
    body: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    visibility: Optional[str] = None  # For restricted comments
    
    def get_formatted_comment(self, max_length: int = 200) -> str:
        """Get formatted comment for display."""
        body_preview = self.body[:max_length]
        if len(self.body) > max_length:
            body_preview += "..."
        
        created_date = self.created_at.strftime('%Y-%m-%d %H:%M')
        
        comment = f"💬 **{self.author}** ({created_date})\n"
        comment += f"{body_preview}"
        
        if self.visibility:
            comment += f"\n🔒 Visible to: {self.visibility}"
        
        return comment