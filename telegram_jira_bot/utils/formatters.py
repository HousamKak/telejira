#!/usr/bin/env python3
"""
Formatters for the Telegram-Jira bot.

Contains utilities for formatting messages, text, and data for Telegram display.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Union
from urllib.parse import quote

from ..models.project import Project, ProjectStats
from ..models.issue import JiraIssue, IssueSearchResult
from ..models.user import User, UserPreferences
from ..models.enums import IssuePriority, IssueType, IssueStatus
from .constants import EMOJI, MAX_MESSAGE_LENGTH, DATE_FORMATS


class MessageFormatter:
    """Formats messages and content for Telegram display."""

    def __init__(self, compact_mode: bool = False, max_length: int = MAX_MESSAGE_LENGTH):
        """Initialize the formatter.
        
        Args:
            compact_mode: Whether to use compact formatting
            max_length: Maximum message length
        """
        self.compact_mode = compact_mode
        self.max_length = max_length

    def format_project_summary(
        self,
        project: Project,
        show_details: bool = True,
        show_stats: bool = False,
        user_default: Optional[str] = None
    ) -> str:
        """Format a single project summary.
        
        Args:
            project: Project to format
            show_details: Whether to show detailed information
            show_stats: Whether to show statistics
            user_default: User's default project key for marking
            
        Returns:
            Formatted project summary
        """
        default_marker = f" {EMOJI['DEFAULT']}" if project.key == user_default else ""
        status_emoji = EMOJI['ACTIVE'] if project.is_active else EMOJI['INACTIVE']
        
        if self.compact_mode:
            text = f"{status_emoji} **{project.key}**{default_marker} - {project.name}"
            if not project.is_active:
                text += " (inactive)"
            return text
        
        text = f"{status_emoji} **{project.key}**{default_marker}\n"
        text += f"└ **{project.name}**\n"
        
        if show_details:
            if project.description:
                desc = self._truncate_text(project.description, 100)
                text += f"└ _{desc}_\n"
            
            if project.lead:
                text += f"└ {EMOJI['USER']} Lead: {project.lead}\n"
            
            if project.category:
                text += f"└ {EMOJI['TAG']} Category: {project.category}\n"
            
            if project.url:
                text += f"└ {EMOJI['LINK']} [View in Jira]({project.url})\n"
        
        if show_stats and project.issue_count > 0:
            text += f"└ {EMOJI['ISSUE']} Issues: {project.issue_count}\n"
        
        return text

    def format_project_list(
        self,
        projects: List[Project],
        title: str = "Projects",
        user_default: Optional[str] = None,
        show_details: bool = True,
        page_info: Optional[Dict[str, int]] = None
    ) -> str:
        """Format a list of projects.
        
        Args:
            projects: List of projects to format
            title: Title for the list
            user_default: User's default project key
            show_details: Whether to show project details
            page_info: Optional pagination info (current_page, total_pages, total_items)
            
        Returns:
            Formatted project list
        """
        if not projects:
            return f"{EMOJI['INFO']} No projects found."
        
        # Header
        header = f"{EMOJI['PROJECT']} **{title}"
        if page_info:
            header += f" (Page {page_info['current_page'] + 1}/{page_info['total_pages']}, {page_info['total_items']} total)"
        else:
            header += f" ({len(projects)})"
        header += "**\n\n"
        
        # Project list
        project_texts = []
        for project in projects:
            project_text = self.format_project_summary(
                project, show_details=show_details, user_default=user_default
            )
            project_texts.append(project_text)
        
        content = header + "\n\n".join(project_texts)
        
        # Footer
        if user_default:
            content += f"\n\n{EMOJI['DEFAULT']} Your default: **{user_default}**"
        else:
            content += f"\n\n{EMOJI['INFO']} No default project set. Use `/setdefault` to choose one."
        
        return self._truncate_message(content)

    def format_issue_summary(
        self,
        issue: JiraIssue,
        show_project: bool = True,
        show_description: bool = False,
        show_details: bool = True,
        max_description_length: int = 100
    ) -> str:
        """Format a single issue summary.
        
        Args:
            issue: Issue to format
            show_project: Whether to show project information
            show_description: Whether to show description
            show_details: Whether to show detailed information
            max_description_length: Maximum description length
            
        Returns:
            Formatted issue summary
        """
        priority_emoji = issue.priority.get_emoji()
        type_emoji = issue.issue_type.get_emoji()
        status_emoji = issue.status.get_emoji() if issue.status else ""
        
        if self.compact_mode:
            text = f"{priority_emoji}{type_emoji} **{issue.key}**: {self._truncate_text(issue.summary, 50)}"
            if show_project:
                text += f" ({issue.project_key})"
            return text
        
        # Main issue line
        text = f"{priority_emoji} {type_emoji} **{issue.key}**: {issue.summary}\n"
        
        if show_project:
            text += f"└ {EMOJI['PROJECT']} Project: {issue.project_key}\n"
        
        if show_details:
            if issue.status:
                text += f"└ {status_emoji} Status: {issue.status.value}\n"
            
            if issue.assignee:
                text += f"└ {EMOJI['USER']} Assignee: {issue.assignee}\n"
            
            if issue.priority != IssuePriority.MEDIUM:  # Only show if not default
                text += f"└ {priority_emoji} Priority: {issue.priority.value}\n"
            
            if issue.labels:
                labels_text = ", ".join(issue.labels[:3])
                if len(issue.labels) > 3:
                    labels_text += f" (+{len(issue.labels) - 3} more)"
                text += f"└ {EMOJI['LABEL']} Labels: {labels_text}\n"
            
            if issue.due_date:
                due_text = self._format_date(issue.due_date, 'SHORT')
                if issue.is_overdue():
                    due_text = f"{EMOJI['OVERDUE']} {due_text} (overdue)"
                text += f"└ {EMOJI['CALENDAR']} Due: {due_text}\n"
            
            # Time tracking
            time_summary = issue.get_time_estimates_summary()
            if time_summary:
                text += f"└ {EMOJI['CLOCK']} Time: {time_summary}\n"
            
            # Age
            age_days = issue.get_age_days()
            if age_days > 0:
                text += f"└ {EMOJI['CLOCK']} Age: {age_days} days\n"
        
        if show_description and issue.description.strip():
            desc = self._truncate_text(issue.description, max_description_length)
            text += f"└ {EMOJI['MESSAGE']} {desc}\n"
        
        # Link to Jira
        text += f"└ {EMOJI['LINK']} [View in Jira]({issue.url})\n"
        
        return text

    def format_issue_list(
        self,
        issues: List[JiraIssue],
        title: str = "Issues",
        show_project: bool = True,
        show_description: bool = False,
        page_info: Optional[Dict[str, int]] = None
    ) -> str:
        """Format a list of issues.
        
        Args:
            issues: List of issues to format
            title: Title for the list
            show_project: Whether to show project information
            show_description: Whether to show descriptions
            page_info: Optional pagination info
            
        Returns:
            Formatted issue list
        """
        if not issues:
            return f"{EMOJI['INFO']} No issues found."
        
        # Header
        header = f"{EMOJI['ISSUE']} **{title}"
        if page_info:
            header += f" (Page {page_info['current_page'] + 1}/{page_info['total_pages']}, {page_info['total_items']} total)"
        else:
            header += f" ({len(issues)})"
        header += "**\n\n"
        
        # Issue list
        issue_texts = []
        for issue in issues:
            issue_text = self.format_issue_summary(
                issue,
                show_project=show_project,
                show_description=show_description,
                show_details=not self.compact_mode
            )
            issue_texts.append(issue_text)
        
        content = header + "\n".join(issue_texts)
        return self._truncate_message(content)

    def format_search_results(self, search_result: IssueSearchResult) -> str:
        """Format issue search results.
        
        Args:
            search_result: Search result object
            
        Returns:
            Formatted search results
        """
        if not search_result.has_results():
            query_text = f" for '{search_result.search_query}'" if search_result.search_query else ""
            return f"{EMOJI['SEARCH']} No issues found{query_text}."
        
        # Header with search info
        header = f"{EMOJI['SEARCH']} **Search Results**\n\n"
        header += f"**Query:** {search_result.search_query or 'All issues'}\n"
        
        if search_result.filters_applied:
            filter_parts = []
            for key, value in search_result.filters_applied.items():
                filter_parts.append(f"{key}: {value}")
            header += f"**Filters:** {', '.join(filter_parts)}\n"
        
        header += f"**Found:** {len(search_result.issues)} of {search_result.total_count} issues\n\n"
        
        # Issue list
        issue_texts = []
        for issue in search_result.issues:
            issue_text = self.format_issue_summary(
                issue, show_project=True, show_details=not self.compact_mode
            )
            issue_texts.append(issue_text)
        
        content = header + "\n".join(issue_texts)
        return self._truncate_message(content)

    def format_user_profile(
        self,
        user: User,
        preferences: Optional[UserPreferences] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format user profile information.
        
        Args:
            user: User to format
            preferences: User preferences
            stats: Additional statistics
            
        Returns:
            Formatted user profile
        """
        text = f"{EMOJI['USER']} **User Profile**\n\n"
        
        # Basic info
        text += f"**Name:** {user.get_display_name()}\n"
        text += f"**ID:** `{user.user_id}`\n"
        text += f"**Role:** {user.role.value.title()}\n"
        
        if user.username:
            text += f"**Username:** @{user.username}\n"
        
        # Status
        status_emoji = EMOJI['ACTIVE'] if user.is_active else EMOJI['INACTIVE']
        text += f"**Status:** {status_emoji} {'Active' if user.is_active else 'Inactive'}\n"
        
        # Activity
        text += f"\n{EMOJI['STATS']} **Activity**\n"
        text += f"└ Issues Created: {user.issues_created}\n"
        
        days_since_joined = (datetime.now(timezone.utc) - user.created_at).days
        days_since_activity = (datetime.now(timezone.utc) - user.last_activity).days
        text += f"└ Member Since: {days_since_joined} days ago\n"
        text += f"└ Last Active: {days_since_activity} days ago\n"
        
        if user.timezone:
            text += f"└ Timezone: {user.timezone}\n"
        
        # Additional stats
        if stats:
            if stats.get('recent_issues_count', 0) > 0:
                text += f"└ Recent Issues: {stats['recent_issues_count']}\n"
        
        # Preferences
        if preferences:
            text += f"\n{EMOJI['SETTINGS']} **Preferences**\n"
            text += f"└ Default Project: {preferences.default_project_key or 'None'}\n"
            text += f"└ Default Priority: {preferences.default_priority.get_emoji()} {preferences.default_priority.value}\n"
            text += f"└ Default Type: {preferences.default_issue_type.get_emoji()} {preferences.default_issue_type.value}\n"
            text += f"└ Notifications: {'✅' if preferences.notifications_enabled else '❌'}\n"
            text += f"└ Quick Create: {'✅' if preferences.quick_create_mode else '❌'}\n"
        
        return text

    def format_project_stats(self, stats: ProjectStats) -> str:
        """Format project statistics.
        
        Args:
            stats: Project statistics
            
        Returns:
            Formatted statistics
        """
        text = f"{EMOJI['STATS']} **{stats.project_key} Statistics**\n\n"
        text += f"**Total Issues:** {stats.total_issues}\n"
        
        if stats.issues_by_type:
            text += f"\n**By Type:**\n"
            for issue_type, count in stats.issues_by_type.items():
                try:
                    emoji = IssueType.from_string(issue_type).get_emoji()
                except (ValueError, AttributeError):
                    emoji = EMOJI['ISSUE']
                text += f"└ {emoji} {issue_type}: {count}\n"
        
        if stats.issues_by_priority:
            text += f"\n**By Priority:**\n"
            for priority, count in stats.issues_by_priority.items():
                try:
                    emoji = IssuePriority.from_string(priority).get_emoji()
                except (ValueError, AttributeError):
                    emoji = EMOJI['PRIORITY_MEDIUM']
                text += f"└ {emoji} {priority}: {count}\n"
        
        if stats.issues_by_status:
            text += f"\n**By Status:**\n"
            for status, count in stats.issues_by_status.items():
                try:
                    emoji = IssueStatus.from_string(status).get_emoji()
                except (ValueError, AttributeError):
                    emoji = EMOJI['INFO']
                text += f"└ {emoji} {status}: {count}\n"
        
        text += f"\n**Activity:**\n"
        text += f"└ {EMOJI['CALENDAR']} This month: {stats.created_this_month}\n"
        text += f"└ {EMOJI['CALENDAR']} This week: {stats.created_this_week}\n"
        
        if stats.last_activity:
            activity_date = self._format_date(stats.last_activity, 'MEDIUM')
            text += f"└ {EMOJI['CLOCK']} Last activity: {activity_date}\n"
        
        return text

    def format_help_text(
        self,
        user_role: str = "user",
        show_shortcuts: bool = True,
        show_examples: bool = True,
        sections: Optional[List[str]] = None
    ) -> str:
        """Format help text based on user role and preferences.
        
        Args:
            user_role: User's role (user, admin, super_admin)
            show_shortcuts: Whether to show command shortcuts
            show_examples: Whether to show usage examples
            sections: Specific sections to include
            
        Returns:
            Formatted help text
        """
        text = f"{EMOJI['HELP']} **Telegram-Jira Bot Help**\n\n"
        
        all_sections = ['basic', 'issues', 'examples', 'admin', 'shortcuts', 'tips']
        if sections:
            sections_to_show = [s for s in sections if s in all_sections]
        else:
            sections_to_show = all_sections
        
        if 'basic' in sections_to_show:
            text += f"{EMOJI['COMMAND']} **Basic Commands**\n"
            text += "• `/start` - Welcome message and setup\n"
            text += "• `/help` - Show this help message\n"
            text += "• `/status` - Bot status and your statistics\n"
            text += "• `/projects` - List available projects\n"
            text += "• `/setdefault <KEY>` - Set your default project\n"
            text += "• `/preferences` - Configure your preferences\n\n"
        
        if 'issues' in sections_to_show:
            text += f"{EMOJI['ISSUE']} **Issue Management**\n"
            text += "• `/create` - Interactive issue creation\n"
            text += "• `/myissues` - Your recent issues\n"
            text += "• `/listissues` - List all issues\n"
            text += "• `/searchissues <query>` - Search issues\n"
            text += "• Send any message - Create issue in default project\n\n"
        
        if 'examples' in sections_to_show and show_examples:
            text += f"{EMOJI['MAGIC']} **Quick Create Examples**\n"
            text += "• `Login button not working` → Medium Task\n"
            text += "• `HIGH BUG App crashes on startup` → High Bug\n"
            text += "• `STORY User wants export feature` → Medium Story\n"
            text += "• `LOWEST IMPROVEMENT Add dark mode` → Lowest Improvement\n\n"
        
        if 'admin' in sections_to_show and user_role in ["admin", "super_admin"]:
            text += f"{EMOJI['ADMIN']} **Admin Commands**\n"
            text += "• `/addproject <KEY> <Name> [Description]` - Add project\n"
            text += "• `/editproject <KEY>` - Edit project\n"
            text += "• `/deleteproject <KEY>` - Delete project\n"
            text += "• `/users` - List users and statistics\n"
            text += "• `/syncjira` - Sync data with Jira\n\n"
        
        if 'shortcuts' in sections_to_show and show_shortcuts:
            text += f"{EMOJI['SHORTCUT']} **Command Shortcuts**\n"
            text += "• `/p` → `/projects`\n"
            text += "• `/c` → `/create`\n"
            text += "• `/mi` → `/myissues`\n"
            text += "• `/s` → `/status`\n"
            text += "• `/w` → `/wizard`\n"
            
            if user_role in ["admin", "super_admin"]:
                text += "• `/ap` → `/addproject`\n"
                text += "• `/u` → `/users`\n"
            text += "\n"
        
        if 'tips' in sections_to_show:
            text += f"{EMOJI['TIP']} **Tips**\n"
            text += "• Use `/wizard` for step-by-step guidance\n"
            text += "• Set a default project for quick issue creation\n"
            text += "• Use priority/type prefixes (HIGH BUG, STORY, etc.)\n"
            text += "• All issues are linked to your Telegram account\n"
            text += "• Use inline keyboards for easier navigation\n"
        
        return self._truncate_message(text)

    def format_status_message(
        self,
        jira_connected: bool,
        db_connected: bool,
        user_stats: Optional[Dict[str, Any]] = None,
        system_stats: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format bot status message.
        
        Args:
            jira_connected: Whether Jira is connected
            db_connected: Whether database is connected
            user_stats: User-specific statistics
            system_stats: System-wide statistics
            
        Returns:
            Formatted status message
        """
        text = f"{EMOJI['ROBOT']} **Bot Status**\n\n"
        
        # Connection status
        text += f"**Connections:**\n"
        jira_emoji = EMOJI['SUCCESS'] if jira_connected else EMOJI['ERROR']
        text += f"└ {jira_emoji} Jira API: {'Connected' if jira_connected else 'Failed'}\n"
        
        db_emoji = EMOJI['SUCCESS'] if db_connected else EMOJI['ERROR']
        text += f"└ {db_emoji} Database: {'Connected' if db_connected else 'Failed'}\n"
        
        # User stats
        if user_stats:
            text += f"\n**Your Statistics:**\n"
            text += f"└ {EMOJI['ISSUE']} Issues Created: {user_stats.get('issues_created', 0)}\n"
            text += f"└ {EMOJI['PROJECT']} Default Project: {user_stats.get('default_project', 'None')}\n"
            
            if user_stats.get('recent_issues'):
                text += f"└ {EMOJI['CLOCK']} Recent Issues: {len(user_stats['recent_issues'])}\n"
        
        # System stats
        if system_stats:
            text += f"\n**System Statistics:**\n"
            text += f"└ {EMOJI['USER']} Total Users: {system_stats.get('total_users', 0)}\n"
            text += f"└ {EMOJI['PROJECT']} Total Projects: {system_stats.get('total_projects', 0)}\n"
            text += f"└ {EMOJI['ISSUE']} Total Issues: {system_stats.get('total_issues', 0)}\n"
            
            if system_stats.get('active_users_24h'):
                text += f"└ {EMOJI['ACTIVE']} Active (24h): {system_stats['active_users_24h']}\n"
        
        # Timestamp
        current_time = self._format_date(datetime.now(timezone.utc), 'MEDIUM')
        text += f"\n{EMOJI['CLOCK']} Last updated: {current_time}"
        
        return text

    def format_error_message(
        self,
        error_type: str,
        error_message: str,
        include_help: bool = True,
        include_support: bool = False
    ) -> str:
        """Format error message with consistent styling.
        
        Args:
            error_type: Type of error
            error_message: Error message text
            include_help: Whether to include help text
            include_support: Whether to include support information
            
        Returns:
            Formatted error message
        """
        text = f"{EMOJI['ERROR']} **Error**\n\n"
        text += f"**Type:** {error_type}\n"
        text += f"**Message:** {error_message}\n"
        
        if include_help:
            text += f"\n{EMOJI['TIP']} Type `/help` for assistance."
        
        if include_support:
            text += f"\n{EMOJI['USER']} Contact an administrator if the problem persists."
        
        return text

    def format_success_message(
        self,
        action: str,
        details: Optional[str] = None,
        next_steps: Optional[str] = None
    ) -> str:
        """Format success message with consistent styling.
        
        Args:
            action: Action that was successful
            details: Optional details about the success
            next_steps: Optional next steps or suggestions
            
        Returns:
            Formatted success message
        """
        text = f"{EMOJI['SUCCESS']} **{action}**\n"
        
        if details:
            text += f"\n{details}\n"
        
        if next_steps:
            text += f"\n{EMOJI['TIP']} {next_steps}"
        
        return text

    def format_wizard_step(
        self,
        step_title: str,
        step_description: str,
        step_number: Optional[int] = None,
        total_steps: Optional[int] = None,
        current_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format wizard step message.
        
        Args:
            step_title: Title of the current step
            step_description: Description of what to do
            step_number: Current step number
            total_steps: Total number of steps
            current_data: Current wizard data
            
        Returns:
            Formatted wizard step message
        """
        text = f"{EMOJI['WIZARD']} **Setup Wizard**\n\n"
        
        if step_number and total_steps:
            text += f"**Step {step_number} of {total_steps}**\n\n"
        
        text += f"**{step_title}**\n\n"
        text += f"{step_description}\n"
        
        if current_data:
            text += f"\n**Current Selection:**\n"
            for key, value in current_data.items():
                if value:
                    display_key = key.replace('_', ' ').title()
                    text += f"└ {display_key}: {value}\n"
        
        return text

    # Private utility methods
    def _truncate_text(self, text: str, max_length: int, suffix: str = "...") -> str:
        """Truncate text to specified length."""
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix

    def _truncate_message(self, text: str) -> str:
        """Truncate message to maximum allowed length."""
        if len(text) <= self.max_length:
            return text
        
        truncated = text[:self.max_length - 20]  # Leave room for truncation notice
        truncated += f"\n\n{EMOJI['WARNING']} Message truncated..."
        return truncated

    def _format_date(
        self,
        date: datetime,
        format_type: str = 'MEDIUM',
        relative: bool = False
    ) -> str:
        """Format datetime for display.
        
        Args:
            date: Datetime to format
            format_type: Format type (SHORT, MEDIUM, LONG, etc.)
            relative: Whether to show relative time
            
        Returns:
            Formatted date string
        """
        if relative:
            now = datetime.now(timezone.utc)
            diff = now - date
            
            if diff.days == 0:
                if diff.seconds < 3600:  # Less than 1 hour
                    minutes = diff.seconds // 60
                    return f"{minutes} minutes ago" if minutes > 1 else "1 minute ago"
                else:
                    hours = diff.seconds // 3600
                    return f"{hours} hours ago" if hours > 1 else "1 hour ago"
            elif diff.days == 1:
                return "yesterday"
            elif diff.days < 7:
                return f"{diff.days} days ago"
            elif diff.days < 30:
                weeks = diff.days // 7
                return f"{weeks} weeks ago" if weeks > 1 else "1 week ago"
            elif diff.days < 365:
                months = diff.days // 30
                return f"{months} months ago" if months > 1 else "1 month ago"
            else:
                years = diff.days // 365
                return f"{years} years ago" if years > 1 else "1 year ago"
        
        format_string = DATE_FORMATS.get(format_type, DATE_FORMATS['MEDIUM'])
        return date.strftime(format_string)

    def _escape_markdown(self, text: str) -> str:
        """Escape special markdown characters for Telegram."""
        # Characters that need escaping in Telegram MarkdownV2
        special_chars = r'_*[]()~`>#+-=|{}.!'
        
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        
        return text

    def _format_duration(self, minutes: int) -> str:
        """Format duration in minutes to human readable format."""
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:  # Less than a day
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes == 0:
                return f"{hours}h"
            else:
                return f"{hours}h {remaining_minutes}m"
        else:  # Days
            days = minutes // 1440
            remaining_hours = (minutes % 1440) // 60
            if remaining_hours == 0:
                return f"{days}d"
            else:
                return f"{days}d {remaining_hours}h"

    def format_inline_mention(self, user: User) -> str:
        """Format user mention for inline use."""
        if user.username:
            return f"@{user.username}"
        else:
            return f"[{user.get_display_name()}](tg://user?id={user.user_id})"

    def format_code_block(self, code: str, language: str = "") -> str:
        """Format text as code block."""
        return f"```{language}\n{code}\n```"

    def format_inline_code(self, code: str) -> str:
        """Format text as inline code."""
        return f"`{code}`"

    def format_bold(self, text: str) -> str:
        """Format text as bold."""
        return f"**{text}**"

    def format_italic(self, text: str) -> str:
        """Format text as italic."""
        return f"_{text}_"

    def format_link(self, text: str, url: str) -> str:
        """Format text as link."""
        return f"[{text}]({url})"

    def format_list(self, items: List[str], ordered: bool = False) -> str:
        """Format list of items."""
        if ordered:
            return "\n".join([f"{i+1}. {item}" for i, item in enumerate(items)])
        else:
            return "\n".join([f"• {item}" for item in items])