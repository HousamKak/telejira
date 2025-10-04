#!/usr/bin/env python3
"""
Message formatters for the Telegram-Jira bot.

Contains formatting utilities for Telegram messages including issue formatting,
project information, user data, and various bot responses.
"""

import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union, Tuple
from urllib.parse import quote

from models import Project,IssuePriority, IssueType, IssueStatus, UserRole,JiraIssue,User

from .constants import EMOJI, MAX_MESSAGE_LENGTH, MAX_SUMMARY_LENGTH


def truncate_text(text: str, max_length: int) -> str:
    """Truncate text to specified length (standalone function).

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if not isinstance(text, str):
        return str(text)

    if len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."


class MessageFormatter:
    """Utility class for formatting Telegram messages."""

    def __init__(self, compact_mode: bool = False, use_emoji: bool = True):
        """Initialize message formatter.

        Args:
            compact_mode: Whether to use compact formatting
            use_emoji: Whether to include emojis in messages
        """
        self.compact_mode = compact_mode
        self.use_emoji = use_emoji

    def truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to specified length.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text
        """
        if not isinstance(text, str):
            return str(text)

        if len(text) <= max_length:
            return text

        return text[:max_length - 3] + "..."

    def format_issue(self, issue: JiraIssue, include_description: bool = True) -> str:
        """Format a Jira issue for display.
        
        Args:
            issue: Jira issue to format
            include_description: Whether to include description
            
        Returns:
            Formatted issue message
        """
        if not isinstance(issue, JiraIssue):
            raise TypeError("issue must be a JiraIssue instance")

        # Build header with emojis
        priority_emoji = issue.priority.get_emoji() if self.use_emoji else ""
        type_emoji = issue.issue_type.get_emoji() if self.use_emoji else ""

        # Status emoji mapping (status is a string, not an enum)
        status_emoji_map = {
            'To Do': '📋',
            'In Progress': '🔄',
            'Done': '✅',
            'Closed': '✅',
            'Blocked': '🚫',
            'In Review': '👀',
            'Open': '📂',
        }
        status_emoji = status_emoji_map.get(issue.status, '📌') if self.use_emoji and issue.status else ""

        header_parts = []
        if priority_emoji:
            header_parts.append(f"{priority_emoji} {issue.priority.value}")
        if type_emoji:
            header_parts.append(f"{type_emoji} {issue.issue_type.value}")
        if status_emoji and issue.status:
            header_parts.append(f"{status_emoji} {issue.status}")

        header = " • ".join(header_parts) if header_parts else ""

        # Format main content
        lines = []
        
        # Title line
        title_line = f"{issue.key}: {self.truncate_text(issue.summary, MAX_SUMMARY_LENGTH)}"
        lines.append(title_line)
        
        # Header line with priority, type, status
        if header and not self.compact_mode:
            lines.append(header)
        
        # Project and assignee info
        info_parts = []
        if issue.project_key:
            info_parts.append(f"📋 Project: {issue.project_key}")
        if issue.assignee:
            assignee_emoji = EMOJI.get('USER', '👤') if self.use_emoji else ""
            info_parts.append(f"{assignee_emoji} Assignee: {issue.assignee}")
        if issue.reporter:
            reporter_emoji = EMOJI.get('REPORTER', '📝') if self.use_emoji else ""
            info_parts.append(f"{reporter_emoji} Reporter: {issue.reporter}")
        
        if info_parts and not self.compact_mode:
            lines.append(" • ".join(info_parts))

        # Description
        if include_description and issue.description and not self.compact_mode:
            description = self.truncate_text(issue.description, 300)
            lines.append(f"📄 Description: {description}")

        # Additional details for non-compact mode
        if not self.compact_mode:
            details = []
            
            # Labels
            if issue.labels:
                labels_str = ", ".join(issue.labels[:5])  # Limit to 5 labels
                if len(issue.labels) > 5:
                    labels_str += f" (+{len(issue.labels) - 5} more)"
                details.append(f"🏷️ Labels: {labels_str}")
            
            # Components
            if issue.components:
                components_str = ", ".join(issue.components[:3])
                if len(issue.components) > 3:
                    components_str += f" (+{len(issue.components) - 3} more)"
                details.append(f"🧩 Components: {components_str}")

            # Story points (if available)
            if hasattr(issue, 'story_points') and issue.story_points:
                details.append(f"📊 Story Points: {issue.story_points}")

            # Due date (if available)
            if hasattr(issue, 'due_date') and issue.due_date:
                due_str = self._format_datetime(issue.due_date)
                is_overdue = issue.due_date < datetime.now(timezone.utc)
                due_emoji = EMOJI.get('OVERDUE', '🚨') if is_overdue else EMOJI.get('DEADLINE', '📅')
                details.append(f"{due_emoji} Due: {due_str}")
            
            if details:
                lines.append(" • ".join(details))

        # Timestamps
        created_str = self._format_datetime(issue.created)
        time_line = f"⏰ Created: {created_str}"

        if issue.updated and issue.updated != issue.created:
            updated_str = self._format_datetime(issue.updated)
            time_line += f" • Updated: {updated_str}"
        
        lines.append(time_line)

        # URL
        if issue.url:
            lines.append(f"🔗 [View in Jira]({issue.url})")

        return "\n".join(lines)

    def format_issue_list(self, issues: List[JiraIssue], title: str = "Issues") -> str:
        """Format a list of issues for display.
        
        Args:
            issues: List of issues to format
            title: Title for the list
            
        Returns:
            Formatted issue list message
        """
        if not isinstance(issues, list):
            raise TypeError("issues must be a list")
        
        if not issues:
            return f"📋 {title}\n\nNo issues found."

        lines = [f"📋 {title} ({len(issues)} total)"]
        lines.append("")

        for i, issue in enumerate(issues[:20], 1):  # Limit to 20 issues
            priority_emoji = issue.priority.get_emoji() if self.use_emoji else ""
            type_emoji = issue.issue_type.get_emoji() if self.use_emoji else ""
            
            # Create compact issue line
            issue_line = f"{i}. {priority_emoji}{type_emoji} {issue.key}: {self.truncate_text(issue.summary, 60)}"
            
            if issue.assignee and not self.compact_mode:
                issue_line += f" (👤 {issue.assignee})"
            
            lines.append(issue_line)

        if len(issues) > 20:
            lines.append(f"\n... and {len(issues) - 20} more issues")

        return "\n".join(lines)

    def format_project(self, project: Project, include_details: bool = True) -> str:
        """Format a project for display.
        
        Args:
            project: Project to format
            include_details: Whether to include detailed information
            
        Returns:
            Formatted project message
        """
        if not isinstance(project, Project):
            raise TypeError("project must be a Project instance")

        lines = []
        
        # Title with status
        status_emoji = "✅" if project.is_active else "❌"
        title = f"{status_emoji} {project.key}: {project.name}"
        lines.append(title)

        # Description
        if project.description:
            description = self.truncate_text(project.description, 200)
            lines.append(f"📄 {description}")

        if include_details:
            # Project details
            details = []
            
            if project.lead:
                details.append(f"👤 Lead: {project.lead}")
            
            details.append(f"📊 Issues: {project.issue_count}")
            details.append(f"🏷️ Type: {project.project_type.title()}")
            
            if details:
                lines.append("")
                lines.append(" • ".join(details))
            
            # Timestamps
            created_str = self._format_datetime(project.created_at)
            time_info = f"⏰ Created: {created_str}"
            
            if project.updated_at and project.updated_at != project.created_at:
                updated_str = self._format_datetime(project.updated_at)
                time_info += f" • Updated: {updated_str}"
            
            lines.append("")
            lines.append(time_info)

        # URL
        if project.url:
            lines.append("")
            lines.append(f"🔗 [View in Jira]({project.url})")

        return "\n".join(lines)


    def format_user(self, user: User, include_stats: bool = True) -> str:
        """Format user information for display.
        
        Args:
            user: User to format
            include_stats: Whether to include user statistics
            
        Returns:
            Formatted user message
        """
        if not isinstance(user, User):
            raise TypeError("user must be a User instance")

        lines = []
        
        # User header
        display_name = self._get_user_display_name(user)
        role_emoji = self._get_role_emoji(user.role)
        
        header = f"{role_emoji} {display_name}"
        if user.role != UserRole.USER:
            header += f" ({user.role.value.replace('_', ' ').title()})"
        
        lines.append(header)

        # User details
        details = []
        if user.username:
            details.append(f"📱 @{user.username}")
        
        details.append(f"🆔 ID: {user.user_id}")
        
        if user.preferred_language:
            details.append(f"🌐 Language: {user.preferred_language}")
        
        if user.timezone:
            details.append(f"🕐 Timezone: {user.timezone}")
        
        if details:
            lines.append(" • ".join(details))

        if include_stats:
            # Statistics
            stats = []
            if user.issues_created > 0:
                stats.append(f"📊 Issues Created: {user.issues_created}")
            
            # Activity status
            activity_str = self._format_datetime(user.last_activity)
            stats.append(f"⏰ Last Active: {activity_str}")
            
            # Account status
            status = "✅ Active" if user.is_active else "❌ Inactive"
            stats.append(f"🔐 Status: {status}")
            
            if stats:
                lines.append("")
                lines.append(" • ".join(stats))

        # Join date
        joined_str = self._format_datetime(user.created_at)
        lines.append("")
        lines.append(f"📅 Joined: {joined_str}")

        return "\n".join(lines)

    def format_error_message(self, error_type: str, message: str, suggestion: Optional[str] = None) -> str:
        """Format an error message.
        
        Args:
            error_type: Type of error
            message: Error message
            suggestion: Optional suggestion for fixing the error
            
        Returns:
            Formatted error message
        """
        error_emoji = EMOJI.get('ERROR', '❌') if self.use_emoji else ""
        
        lines = [f"{error_emoji} Error: {message}"]
        
        if suggestion:
            lines.append("")
            lines.append(f"💡 Suggestion: {suggestion}")
        
        return "\n".join(lines)

    def format_success_message(self, message: str, details: Optional[str] = None) -> str:
        """Format a success message.
        
        Args:
            message: Success message
            details: Optional additional details
            
        Returns:
            Formatted success message
        """
        success_emoji = EMOJI.get('SUCCESS', '✅') if self.use_emoji else ""
        
        lines = [f"{success_emoji} Success: {message}"]
        
        if details:
            lines.append("")
            lines.append(details)
        
        return "\n".join(lines)

    def format_warning_message(self, message: str, details: Optional[str] = None) -> str:
        """Format a warning message.
        
        Args:
            message: Warning message
            details: Optional additional details
            
        Returns:
            Formatted warning message
        """
        warning_emoji = EMOJI.get('WARNING', '⚠️') if self.use_emoji else ""
        
        lines = [f"{warning_emoji} Warning: {message}"]
        
        if details:
            lines.append("")
            lines.append(details)
        
        return "\n".join(lines)

    def format_help_message(self, commands: Dict[str, str], title: str = "Available Commands") -> str:
        """Format a help message with commands.
        
        Args:
            commands: Dictionary of command -> description
            title: Title for the help message
            
        Returns:
            Formatted help message
        """
        help_emoji = EMOJI.get('HELP', '❓') if self.use_emoji else ""
        
        lines = [f"{help_emoji} {title}"]
        lines.append("")
        
        for command, description in commands.items():
            lines.append(f"/{command} - {description}")
        
        return "\n".join(lines)

    def format_statistics(self, stats: Dict[str, Any], title: str = "Statistics") -> str:
        """Format statistics data.
        
        Args:
            stats: Dictionary of statistics
            title: Title for the statistics
            
        Returns:
            Formatted statistics message
        """
        stats_emoji = EMOJI.get('STATS', '📊') if self.use_emoji else ""
        
        lines = [f"{stats_emoji} {title}"]
        lines.append("")
        
        for key, value in stats.items():
            # Format the key nicely
            formatted_key = key.replace('_', ' ').title()
            lines.append(f"• {formatted_key}: {value}")
        
        return "\n".join(lines)

    def format_keyboard_options(self, options: List[Tuple[str, str]], title: str = "Options") -> str:
        """Format options for inline keyboard.
        
        Args:
            options: List of (display_text, callback_data) tuples
            title: Title for the options
            
        Returns:
            Formatted options message
        """
        lines = [f"{title}"]
        lines.append("")
        lines.append("Please select an option:")
        
        return "\n".join(lines)


    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime for display.
        
        Args:
            dt: Datetime to format
            
        Returns:
            Formatted datetime string
        """
        if not isinstance(dt, datetime):
            return str(dt)
        
        # Convert to UTC if timezone-aware
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        # Format based on time difference
        if diff.days == 0:
            if diff.seconds < 3600:  # Less than 1 hour
                minutes = diff.seconds // 60
                return f"{minutes}m ago" if minutes > 0 else "just now"
            else:  # Less than 1 day
                hours = diff.seconds // 3600
                return f"{hours}h ago"
        elif diff.days == 1:
            return "yesterday"
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

    def _get_user_display_name(self, user: User) -> str:
        """Get display name for user.
        
        Args:
            user: User object
            
        Returns:
            Formatted display name
        """
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        elif user.username:
            return f"@{user.username}"
        else:
            return f"User {user.user_id}"

    def _get_role_emoji(self, role: UserRole) -> str:
        """Get emoji for user role.
        
        Args:
            role: User role
            
        Returns:
            Role emoji
        """
        if not self.use_emoji:
            return ""
        
        role_emojis = {
            UserRole.USER: EMOJI.get('USER', '👤'),
            UserRole.ADMIN: EMOJI.get('ADMIN', '🛡️'),
            UserRole.SUPER_ADMIN: EMOJI.get('SUPER_ADMIN', '👑')
        }
        
        return role_emojis.get(role, EMOJI.get('USER', '👤'))

    def sanitize_markdown(self, text: str) -> str:
        """Sanitize text for Markdown formatting.
        
        Args:
            text: Text to sanitize
            
        Returns:
            Sanitized text
        """
        if not isinstance(text, str):
            return str(text)
        
        # Escape special Markdown characters
        markdown_chars = ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in markdown_chars:
            text = text.replace(char, f'\\{char}')
        
        return text

    def create_issue_url(self, base_url: str, issue_key: str) -> str:
        """Create URL for Jira issue.
        
        Args:
            base_url: Base Jira URL
            issue_key: Issue key
            
        Returns:
            Full issue URL
        """
        if not base_url.endswith('/'):
            base_url += '/'
        
        return f"{base_url}browse/{quote(issue_key)}"

    def create_project_url(self, base_url: str, project_key: str) -> str:
        """Create URL for Jira project.
        
        Args:
            base_url: Base Jira URL
            project_key: Project key
            
        Returns:
            Full project URL
        """
        if not base_url.endswith('/'):
            base_url += '/'
        
        return f"{base_url}projects/{quote(project_key)}"

    def format_jql_query(self, filters: Dict[str, Any]) -> str:
        """Format filters into JQL query.
        
        Args:
            filters: Dictionary of filter criteria
            
        Returns:
            JQL query string
        """
        jql_parts = []
        
        if filters.get('project'):
            jql_parts.append(f"project = {filters['project']}")
        
        if filters.get('assignee'):
            jql_parts.append(f"assignee = '{filters['assignee']}'")
        
        if filters.get('reporter'):
            jql_parts.append(f"reporter = '{filters['reporter']}'")
        
        if filters.get('status'):
            jql_parts.append(f"status = '{filters['status']}'")
        
        if filters.get('priority'):
            jql_parts.append(f"priority = '{filters['priority']}'")
        
        if filters.get('issue_type'):
            jql_parts.append(f"issuetype = '{filters['issue_type']}'")
        
        if filters.get('labels'):
            labels = filters['labels']
            if isinstance(labels, list):
                label_conditions = [f"labels = '{label}'" for label in labels]
                jql_parts.append(f"({' OR '.join(label_conditions)})")
            else:
                jql_parts.append(f"labels = '{labels}'")
        
        if filters.get('created_after'):
            jql_parts.append(f"created >= '{filters['created_after']}'")
        
        if filters.get('updated_after'):
            jql_parts.append(f"updated >= '{filters['updated_after']}'")
        
        return ' AND '.join(jql_parts) if jql_parts else ""

    def validate_message_length(self, message: str) -> str:
        """Validate and truncate message if needed.
        
        Args:
            message: Message to validate
            
        Returns:
            Validated message
        """
        if len(message) <= MAX_MESSAGE_LENGTH:
            return message
        
        # Truncate and add warning
        truncated = message[:MAX_MESSAGE_LENGTH - 100]
        truncated += "\n\n⚠️ Message truncated due to length limit."
        
        return truncated