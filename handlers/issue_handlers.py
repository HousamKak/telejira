#!/usr/bin/env python3
"""
Issue handlers for the Telegram-Jira bot.

Handles issue-related commands including creation, listing, searching,
editing, and management of Jira issues through Telegram.
"""

import logging
import re
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .base_handler import BaseHandler
from models.project import Project
from models.issue import JiraIssue, IssueComment
from models.user import User
from models.enums import IssuePriority, IssueType, IssueStatus, UserRole, ErrorType
from services.database import DatabaseError
from services.jira_service import JiraAPIError
from utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES
from utils.validators import InputValidator, ValidationResult
from utils.formatters import MessageFormatter


class IssueHandlers(BaseHandler):
    """Handles issue-related commands and operations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = MessageFormatter(
            compact_mode=self.config.compact_mode,
            use_emoji=True
        )
        self.validator = InputValidator()

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "IssueHandlers"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to issue operations."""
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        elif isinstance(error, ValueError):
            await self.send_error_message(
                update, 
                f"Invalid input: {str(error)}", 
                ErrorType.VALIDATION_ERROR
            )
        else:
            await self.send_error_message(
                update,
                f"Issue operation failed: {str(error)}",
                ErrorType.UNKNOWN_ERROR
            )

    # =============================================================================
    # ISSUE CREATION COMMANDS
    # =============================================================================

    async def create_issue_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /create command - start issue creation wizard."""
        self.log_handler_start(update, "create_issue_wizard")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Delegate to wizard handler
            from .wizard_handlers import WizardHandlers
            wizard_handler = WizardHandlers(
                config=self.config,
                database=self.db,
                jira_service=self.jira,
                telegram_service=self.telegram
            )

            await wizard_handler.quick_command(update, context)
            self.log_handler_end(update, "create_issue_wizard")

        except Exception as e:
            await self.handle_error(update, e, "create_issue_wizard")
            self.log_handler_end(update, "create_issue_wizard", success=False)

    async def handle_quick_issue_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle quick issue creation from plain text message.
        
        Parses messages like: "HIGH BUG Login button not working on mobile devices"
        Format: [PRIORITY] [TYPE] <summary>
        """
        self.log_handler_start(update, "handle_quick_issue_text")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        if not update.message or not update.message.text:
            return

        try:
            message_text = update.message.text.strip()
            
            # Skip if it looks like a command
            if message_text.startswith('/'):
                return

            # Parse the message for priority, type, and summary
            parsed_issue = self._parse_quick_issue_text(message_text)
            if not parsed_issue:
                # Not a recognized issue format, ignore
                return

            # Get user's default project
            default_project_key = await self.db.get_user_default_project(user.user_id)
            if not default_project_key:
                await self.send_message(
                    update,
                    ERROR_MESSAGES['NO_DEFAULT_PROJECT'],
                    reply_to_message=True
                )
                return

            # Get project details
            project = await self.db.get_project_by_key(default_project_key)
            if not project:
                await self.send_error_message(update, "Your default project no longer exists. Please set a new one.")
                return

            # Show issue creation confirmation
            await self._show_quick_issue_confirmation(update, context, project, parsed_issue)
            self.log_handler_end(update, "handle_quick_issue_text")

        except Exception as e:
            await self.handle_error(update, e, "handle_quick_issue_text")
            self.log_handler_end(update, "handle_quick_issue_text", success=False)

    # =============================================================================
    # ISSUE LISTING AND SEARCHING COMMANDS
    # =============================================================================

    async def list_user_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /myissues command - list user's recent issues."""
        self.log_handler_start(update, "list_user_issues")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get user's issues from database
            user_issues = await self.db.get_user_issues(user.user_id, limit=20)
            
            if not user_issues:
                message = f"""
{EMOJI.get('ISSUES', '📋')} **Your Issues**

You haven't created any issues yet.

**Get Started:**
• Use `/create` to start the issue creation wizard
• Or just type: `HIGH BUG Login button broken`
• Use `/projects` to see available projects
                """
                await self.send_message(update, message)
                return

            # Format issues list
            message = self.formatter.format_issue_list(user_issues, "Your Recent Issues")
            
            # Add action buttons
            keyboard_buttons = []
            
            # Quick action buttons for first few issues
            for issue in user_issues[:3]:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"View {issue.key}",
                        callback_data=f"view_issue_{issue.key}"
                    )
                ])

            keyboard_buttons.extend([
                [InlineKeyboardButton("📝 Create New Issue", callback_data="create_new_issue")],
                [InlineKeyboardButton("🔄 Refresh List", callback_data="refresh_my_issues")]
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "list_user_issues")

        except Exception as e:
            await self.handle_error(update, e, "list_user_issues")
            self.log_handler_end(update, "list_user_issues", success=False)

    async def list_all_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /listissues command - list issues with optional filters.
        
        Usage: /listissues [filters]
        Filters: project=KEY, assignee=NAME, status=STATUS, priority=PRIORITY
        """
        self.log_handler_start(update, "list_all_issues")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Parse filters from arguments
            filters = self._parse_issue_filters(context.args) if context.args else {}
            
            # Build JQL query
            jql_parts = []
            
            # Project filter
            if 'project' in filters:
                project_key = filters['project'].upper()
                jql_parts.append(f"project = {project_key}")
            else:
                # If no project specified, use user's accessible projects
                projects = await self.db.get_all_active_projects()
                if projects:
                    project_keys = [p.key for p in projects[:10]]  # Limit projects
                    jql_parts.append(f"project in ({','.join(project_keys)})")

            # Additional filters
            if 'assignee' in filters:
                jql_parts.append(f"assignee = '{filters['assignee']}'")
            
            if 'status' in filters:
                jql_parts.append(f"status = '{filters['status']}'")
            
            if 'priority' in filters:
                jql_parts.append(f"priority = '{filters['priority']}'")
            
            if 'type' in filters:
                jql_parts.append(f"issuetype = '{filters['type']}'")

            # Default: recent issues
            if not jql_parts:
                jql_parts.append("created >= -30d")  # Last 30 days

            jql_query = " AND ".join(jql_parts)
            jql_query += " ORDER BY created DESC"

            # Search Jira
            try:
                issues = await self.jira.search_issues(jql_query, max_results=20)
            except JiraAPIError as e:
                if "JQL" in str(e):
                    await self.send_error_message(update, f"Invalid search filters: {str(e)}")
                    return
                raise

            if not issues:
                filter_desc = self._format_filter_description(filters)
                message = f"""
{EMOJI.get('SEARCH', '🔍')} **Issue Search Results**

No issues found{filter_desc}.

**Try:**
• Different filter criteria
• `/myissues` for your issues
• `/projects` to see available projects
                """
                await self.send_message(update, message)
                return

            # Format results
            filter_desc = self._format_filter_description(filters)
            title = f"Issues{filter_desc}"
            message = self.formatter.format_issue_list(issues, title)

            # Add filter management buttons
            keyboard_buttons = []
            
            if len(issues) == 20:
                keyboard_buttons.append([
                    InlineKeyboardButton("📄 Load More", callback_data="load_more_issues")
                ])
            
            keyboard_buttons.extend([
                [InlineKeyboardButton("🔍 Modify Filters", callback_data="modify_issue_filters")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_issue_list")]
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "list_all_issues")

        except Exception as e:
            await self.handle_error(update, e, "list_all_issues")
            self.log_handler_end(update, "list_all_issues", success=False)

    async def search_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /searchissues command - search issues by text.
        
        Usage: /searchissues <query>
        """
        self.log_handler_start(update, "search_issues")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "**Usage:** `/searchissues <query>`\n\nSearch issues by summary, description, or key."
                )
                return

            search_query = ' '.join(context.args)
            
            # Build JQL query for text search
            jql_query = f'text ~ "{search_query}" ORDER BY created DESC'

            try:
                issues = await self.jira.search_issues(jql_query, max_results=15)
            except JiraAPIError as e:
                await self.send_error_message(update, f"Search failed: {str(e)}")
                return

            if not issues:
                message = f"""
{EMOJI.get('SEARCH', '🔍')} **Search Results**

No issues found matching: **{search_query}**

**Tips:**
• Try different keywords
• Check spelling
• Use broader search terms
                """
                await self.send_message(update, message)
                return

            # Format search results
            title = f"Search Results for '{search_query}'"
            message = self.formatter.format_issue_list(issues, title)

            # Add search refinement buttons
            keyboard_buttons = []
            
            # Quick view buttons for top results
            for issue in issues[:3]:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"View {issue.key}",
                        callback_data=f"view_issue_{issue.key}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton("🔍 New Search", callback_data="new_issue_search")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "search_issues")

        except Exception as e:
            await self.handle_error(update, e, "search_issues")
            self.log_handler_end(update, "search_issues", success=False)

    # =============================================================================
    # ISSUE VIEWING AND DETAILS
    # =============================================================================

    async def view_issue_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /issue command - view detailed issue information.
        
        Usage: /issue <KEY>
        """
        self.log_handler_start(update, "view_issue_details")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "**Usage:** `/issue <ISSUE_KEY>`\n\nExample: `/issue WEBAPP-123`"
                )
                return

            issue_key = context.args[0].upper()
            
            # Validate issue key format
            if not re.match(r'^[A-Z][A-Z0-9_]*-\d+$', issue_key):
                await self.send_error_message(update, "Invalid issue key format. Example: WEBAPP-123")
                return

            # Get issue from Jira
            try:
                issue = await self.jira.get_issue_by_key(issue_key)
            except JiraAPIError as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                    return
                raise

            if not issue:
                await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                return

            # Format detailed issue information
            message = self.formatter.format_issue(issue, include_description=True)

            # Add action buttons based on user permissions
            keyboard_buttons = []
            
            # Basic actions available to all users
            keyboard_buttons.extend([
                [
                    InlineKeyboardButton("💬 Comments", callback_data=f"view_comments_{issue.key}"),
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_issue_{issue.key}")
                ],
                [
                    InlineKeyboardButton("🔗 Open in Jira", url=issue.url)
                ]
            ])

            # Admin actions
            if user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
                keyboard_buttons.insert(-1, [
                    InlineKeyboardButton("✏️ Edit", callback_data=f"edit_issue_{issue.key}"),
                    InlineKeyboardButton("🔄 Transition", callback_data=f"transition_issue_{issue.key}")
                ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "view_issue_details")

        except Exception as e:
            await self.handle_error(update, e, "view_issue_details")
            self.log_handler_end(update, "view_issue_details", success=False)

    # =============================================================================
    # ISSUE COMMENTS
    # =============================================================================

    async def add_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /comment command - add comment to issue.
        
        Usage: /comment <KEY> <comment text>
        """
        self.log_handler_start(update, "add_comment")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args or len(context.args) < 2:
                await self.send_message(
                    update,
                    "**Usage:** `/comment <ISSUE_KEY> <comment text>`\n\nExample: `/comment WEBAPP-123 This issue is resolved`"
                )
                return

            issue_key = context.args[0].upper()
            comment_text = ' '.join(context.args[1:])

            # Validate inputs
            if not re.match(r'^[A-Z][A-Z0-9_]*-\d+$', issue_key):
                await self.send_error_message(update, "Invalid issue key format.")
                return

            if len(comment_text.strip()) < 3:
                await self.send_error_message(update, "Comment text must be at least 3 characters long.")
                return

            # Add comment via Jira
            try:
                comment = await self.jira.add_comment(issue_key, comment_text)
                comment_id = comment.get("id") if isinstance(comment, dict) else getattr(comment, "id", None)
                details = (
                    f"Your comment has been posted successfully.\n\n💬 **Comment:** "
                    f"{comment_text[:100]}{'...' if len(comment_text) > 100 else ''}"
                )
                if comment_id:
                    details += f"\n🆔 Comment ID: {comment_id}"
                    
                success_message = self.formatter.format_success_message(
                    f"Comment added to {issue_key}",
                    details
                )

                await self.send_message(update, success_message)

            except JiraAPIError as e:
                if "404" in str(e):
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                else:
                    await self.send_error_message(update, f"Failed to add comment: {str(e)}")

            self.log_handler_end(update, "add_comment")

        except Exception as e:
            await self.handle_error(update, e, "add_comment")
            self.log_handler_end(update, "add_comment", success=False)

    # =============================================================================
    # CALLBACK QUERY HANDLERS
    # =============================================================================

    async def handle_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle issue-related callback queries."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("view_issue_"):
            await self._handle_view_issue_callback(update, context)
        elif query.data.startswith("view_comments_"):
            await self._handle_view_comments_callback(update, context)
        elif query.data.startswith("refresh_issue_"):
            await self._handle_refresh_issue_callback(update, context)
        elif query.data.startswith("edit_issue_"):
            await self._handle_edit_issue_callback(update, context)
        elif query.data.startswith("transition_issue_"):
            await self._handle_transition_issue_callback(update, context)
        elif query.data.startswith("confirm_create_"):
            await self._handle_confirm_create_callback(update, context)
        elif query.data == "create_new_issue":
            await self._handle_create_new_issue_callback(update, context)
        elif query.data == "refresh_my_issues":
            await self._handle_refresh_my_issues_callback(update, context)

    async def _handle_view_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle view issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("view_issue_", "")

        # Simulate issue command
        context.args = [issue_key]
        await self.view_issue_details(update, context)

    async def _handle_view_comments_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle view comments callback."""
        query = update.callback_query
        issue_key = query.data.replace("view_comments_", "")

        try:
            comments = await self.jira.get_issue_comments(issue_key)
            
            if not comments:
                await self.edit_message(update, f"No comments found for {issue_key}.")
                return

            # Format comments
            message_lines = [
                f"💬 **Comments for {issue_key}** ({len(comments)} total)",
                ""
            ]

            for i, comment in enumerate(comments[-10:], 1):  # Show last 10 comments
                comment_preview = self.formatter._truncate_text(comment.body, 100)
                age = comment.get_age_string()
                
                comment_line = f"{i}. **{comment.author_display_name}** ({age})"
                comment_line += f"\n   {comment_preview}"
                
                if comment.is_edited():
                    comment_line += " *(edited)*"
                
                message_lines.append(comment_line)

            if len(comments) > 10:
                message_lines.append(f"\n... and {len(comments) - 10} earlier comments")

            message = "\n".join(message_lines)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Issue", callback_data=f"view_issue_{issue_key}")]
            ])

            await self.edit_message(update, message, reply_markup=keyboard)

        except JiraAPIError as e:
            await self.edit_message(update, f"Failed to load comments: {str(e)}")

    async def _handle_refresh_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("refresh_issue_", "")

        # Reload issue details
        context.args = [issue_key]
        await self.view_issue_details(update, context)

    async def _handle_confirm_create_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle confirm issue creation callback."""
        query = update.callback_query
        
        # Extract data from callback
        parts = query.data.replace("confirm_create_", "").split("_")
        if len(parts) < 3:
            await self.edit_message(update, "Invalid creation data.")
            return

        # Get stored issue data from context
        issue_data = context.user_data.get('quick_issue_data')
        if not issue_data:
            await self.edit_message(update, "Issue creation data not found. Please try again.")
            return

        try:
            # Create issue in Jira
            issue = await self.jira.create_issue(
                project_key=issue_data['project_key'],
                summary=issue_data['summary'],
                description=issue_data.get('description', ''),
                priority=issue_data['priority'],
                issue_type=issue_data['issue_type']
            )

            # Store in database
            user = await self.get_or_create_user(update)
            if user and update.callback_query.message:
                await self.db.create_issue(
                    telegram_user_id=user.user_id,
                    telegram_message_id=update.callback_query.message.message_id,
                    jira_key=issue.key,
                    project_key=issue.project_key,
                    summary=issue.summary,
                    description=issue.description,
                    priority=issue.priority.value,
                    issue_type=issue.issue_type.value,
                    url=issue.url
                )

            # Success message
            success_message = self.formatter.format_success_message(
                "Issue created successfully!",
                f"**{issue.key}**: {issue.summary}\n\n🔗 [View in Jira]({issue.url})"
            )

            await self.edit_message(update, success_message)

            # Clean up
            if 'quick_issue_data' in context.user_data:
                del context.user_data['quick_issue_data']

        except JiraAPIError as e:
            await self.edit_message(
                update,
                self.formatter.format_error_message(
                    "Failed to create issue",
                    str(e),
                    "Please check the project settings and try again."
                )
            )

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _parse_quick_issue_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse quick issue text format.
        
        Args:
            text: Message text to parse
            
        Returns:
            Dictionary with parsed issue data or None if not recognized
        """
        # Pattern: [PRIORITY] [TYPE] <summary>
        # Examples: "HIGH BUG Login broken", "MEDIUM TASK Update documentation"
        
        words = text.split()
        if len(words) < 2:
            return None

        parsed = {}
        word_index = 0

        # Try to parse priority
        try:
            priority = IssuePriority.from_string(words[word_index])
            parsed['priority'] = priority
            word_index += 1
        except (ValueError, IndexError):
            parsed['priority'] = IssuePriority.MEDIUM  # Default

        # Try to parse issue type
        if word_index < len(words):
            try:
                issue_type = IssueType.from_string(words[word_index])
                parsed['issue_type'] = issue_type
                word_index += 1
            except (ValueError, IndexError):
                parsed['issue_type'] = IssueType.TASK  # Default

        # Remaining words are the summary
        if word_index < len(words):
            parsed['summary'] = ' '.join(words[word_index:])
        else:
            return None  # No summary provided

        # Validate summary length
        if len(parsed['summary']) < 10:
            return None

        return parsed

    def _parse_issue_filters(self, args: List[str]) -> Dict[str, str]:
        """Parse issue filter arguments.
        
        Args:
            args: Command arguments
            
        Returns:
            Dictionary of filter key-value pairs
        """
        filters = {}
        
        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                filters[key.lower()] = value
        
        return filters

    def _format_filter_description(self, filters: Dict[str, str]) -> str:
        """Format filter description for display.
        
        Args:
            filters: Applied filters
            
        Returns:
            Formatted filter description
        """
        if not filters:
            return ""
        
        filter_parts = []
        for key, value in filters.items():
            filter_parts.append(f"{key}={value}")
        
        return f" (filtered by: {', '.join(filter_parts)})"

    async def _show_quick_issue_confirmation(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        project: Project, 
        parsed_issue: Dict[str, Any]
    ) -> None:
        """Show confirmation for quick issue creation.  This now properly receives the Telegram ``context`` so that we can
        store the issue data for later use when the user confirms creation."""
        priority_emoji = parsed_issue['priority'].get_emoji()
        type_emoji = parsed_issue['issue_type'].get_emoji()
        
        message = f"""
{EMOJI.get('CONFIRM', '✅')} **Confirm Issue Creation**

**Project:** {project.key}: {project.name}
**Type:** {type_emoji} {parsed_issue['issue_type'].value}
**Priority:** {priority_emoji} {parsed_issue['priority'].value}
**Summary:** {parsed_issue['summary']}

Create this issue?
        """

        # Store issue data for creation so the confirmation callback can
        # access it later from ``context.user_data``
        context.user_data['quick_issue_data'] = {
            'project_key': project.key,
            'summary': parsed_issue['summary'],
            'priority': parsed_issue['priority'],
            'issue_type': parsed_issue['issue_type'],
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Create Issue", callback_data=f"confirm_create_{project.key}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_create")]
        ])

        await self.send_message(update, message, reply_markup=keyboard, reply_to_message=True)


    def _validate_issue_key(self, issue_key: str) -> bool:
        """Validate issue key format.
        
        Args:
            issue_key: Issue key to validate
            
        Returns:
            True if valid format
        """
        return bool(re.match(r'^[A-Z][A-Z0-9_]*-\d+$', issue_key))

    async def _get_user_assignable_issues(self, user: User, limit: int = 20) -> List[JiraIssue]:
        """Get issues that can be assigned to the user.
        
        Args:
            user: User to get assignable issues for
            limit: Maximum number of issues to return
            
        Returns:
            List of assignable issues
        """
        try:
            # Build JQL for assignable issues
            jql_query = "assignee = currentUser() OR assignee is EMPTY ORDER BY updated DESC"
            
            issues = await self.jira.search_issues(jql_query, max_results=limit)
            return issues
            
        except JiraAPIError as e:
            self.logger.warning(f"Failed to get assignable issues for user {user.user_id}: {e}")
            return []

    async def _handle_create_new_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle create new issue callback."""
        # Start issue creation wizard
        await self.create_issue_wizard(update, context)

    async def _handle_refresh_my_issues_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh my issues callback."""
        # Reload user's issues
        await self.list_user_issues(update, context)

    async def _handle_edit_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edit issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("edit_issue_", "")

        # Show edit options
        message = f"""
✏️ **Edit Issue: {issue_key}**

What would you like to edit?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Summary", callback_data=f"edit_summary_{issue_key}")],
            [InlineKeyboardButton("📄 Description", callback_data=f"edit_description_{issue_key}")],
            [InlineKeyboardButton("🎯 Priority", callback_data=f"edit_priority_{issue_key}")],
            [InlineKeyboardButton("👤 Assignee", callback_data=f"edit_assignee_{issue_key}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"view_issue_{issue_key}")]
        ])

        await self.edit_message(update, message, reply_markup=keyboard)

    async def _handle_transition_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle transition issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("transition_issue_", "")

        try:
            # Get available transitions
            transitions = await self.jira.get_available_transitions(issue_key)
            
            if not transitions:
                await self.edit_message(update, f"No transitions available for {issue_key}.")
                return

            message = f"""
🔄 **Transition Issue: {issue_key}**

Available transitions:
            """

            keyboard_buttons = []
            for transition in transitions[:10]:  # Limit to 10 transitions
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        transition['name'],
                        callback_data=f"do_transition_{issue_key}_{transition['id']}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton("🔙 Back", callback_data=f"view_issue_{issue_key}")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            await self.edit_message(update, message, reply_markup=keyboard)

        except JiraAPIError as e:
            await self.edit_message(update, f"Failed to get transitions: {str(e)}")