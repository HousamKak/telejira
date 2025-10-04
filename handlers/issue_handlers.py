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
from models import User,IssuePriority, IssueType, IssueStatus, UserRole, ErrorType, JiraIssue, IssueComment, Project

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

    async def create_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /create command - start issue creation wizard."""
        self.log_handler_start(update, "create_issue")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Start the wizard
            await self.create_issue_wizard(update, context)
            self.log_handler_end(update, "create_issue")

        except Exception as e:
            await self.handle_error(update, e, "create_issue")
            self.log_handler_end(update, "create_issue", success=False)

    async def create_issue_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start interactive issue creation wizard."""
        self.log_handler_start(update, "create_issue_wizard")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get user's projects
            projects = await self.db.list_user_projects(user.user_id)
            
            if not projects:
                message = f"""
{EMOJI.get('ERROR', '❌')} No Projects Available

You don't have access to any projects yet.

Next Steps:
• Contact your admin to add projects
• Or use `/help` for more information
                """
                await self.send_message(update, message)
                return

            # Show project selection
            message = f"""
{EMOJI.get('CREATE', '📝')} Create New Issue

Step 1: Choose a project

Available projects:
            """

            keyboard_buttons = []
            for project in projects:
                status_emoji = "✅" if project.is_active else "❌"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"{status_emoji} {project.key}: {project.name}",
                        callback_data=f"create_issue_project_{project.key}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_create")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            await self.send_message(update, message, reply_markup=keyboard)
            
            self.log_handler_end(update, "create_issue_wizard")

        except Exception as e:
            await self.handle_error(update, e, "create_issue_wizard")
            self.log_handler_end(update, "create_issue_wizard", success=False)

    async def create_idea(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /idea command - create an issue and set status to Idea."""
        self.log_handler_start(update, "create_idea")

        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Check if summary is provided
            if not context.args:
                await self.send_message(
                    update,
                    "Usage: /idea <summary>\n\nExample: /idea New feature for user dashboard\n\nThis will create an issue with 'Idea' status."
                )
                return

            # Get summary from arguments
            summary = ' '.join(context.args)

            # Get user's default project
            project = await self.db.get_user_default_project(user.user_id)
            if not project:
                await self.send_message(
                    update,
                    f"{EMOJI.get('ERROR', '❌')} No default project set.\n\nUse /setdefault <project_key> to set one."
                )
                return

            # Create the issue with Task type and Medium priority
            created_issue = await self.jira.create_issue(
                project_key=project.key,
                summary=summary,
                description="Created as an idea via Telegram bot",
                issue_type=IssueType.TASK,
                priority=IssuePriority.MEDIUM,
            )

            # Try to transition to "Idea" status
            try:
                transitions = await self.jira.list_transitions(created_issue.key)

                # Find "Idea" transition
                idea_transition = None
                for transition in transitions:
                    if 'idea' in transition['name'].lower():
                        idea_transition = transition
                        break

                if idea_transition:
                    await self.jira.transition_issue(created_issue.key, idea_transition['id'])
                    status_msg = "Status: Idea"
                else:
                    status_msg = f"Status: {created_issue.status} (Idea status not available in workflow)"

            except Exception as e:
                self.logger.warning(f"Could not transition to Idea status: {e}")
                status_msg = f"Status: {created_issue.status}"

            # Show success message
            message = f"""
{EMOJI.get('SUCCESS', '✅')} Idea Created

{created_issue.key}: {created_issue.summary}
Project: {project.key}
{status_msg}

Use /view {created_issue.key} to see details.
            """

            await self.send_message(update, message)

            # Log the action
            await self.db.log_user_action(user.user_id, "idea.created", {
                "issue_key": created_issue.key,
                "project_key": project.key,
            })

            self.log_handler_end(update, "create_idea")

        except JiraAPIError as e:
            await self.send_error_message(update, f"Failed to create idea: {str(e)}")
            self.log_handler_end(update, "create_idea", success=False)
        except Exception as e:
            await self.handle_error(update, e, "create_idea")
            self.log_handler_end(update, "create_idea", success=False)

    async def handle_message_issue_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle issue creation from plain text messages."""
        self.log_handler_start(update, "handle_message_issue_creation")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not update.message or not update.message.text:
                return

            text = update.message.text.strip()
            
            # Skip if message is too short or looks like a command
            if len(text) < 10 or text.startswith('/'):
                return

            # Parse the text for issue format
            parsed_issue = self._parse_quick_issue_text(text)
            if not parsed_issue:
                return

            # Get user's default project
            project = await self.db.get_user_default_project(user.user_id)
            if not project:
                await self.send_message(
                    update,
                    f"❌ No default project set. Use `/setdefault <project_key>` to set one."
                )
                return

            # Show issue creation confirmation
            await self._show_quick_issue_confirmation(update, context, project, parsed_issue)
            self.log_handler_end(update, "handle_message_issue_creation")

        except Exception as e:
            await self.handle_error(update, e, "handle_message_issue_creation")
            self.log_handler_end(update, "handle_message_issue_creation", success=False)

    # =============================================================================
    # ISSUE LISTING AND SEARCHING COMMANDS
    # =============================================================================

    async def list_my_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /myissues command - list user's recent issues."""
        await self.list_user_issues(update, context)

    async def list_user_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /allissues command - list issues from all projects, categorized by project."""
        self.log_handler_start(update, "list_user_issues")

        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get all projects
            projects = await self.db.list_projects()

            if not projects:
                message = f"""
{EMOJI.get('ERROR', '❌')} No Projects Found

No projects are available. Use /refresh to sync from Jira.
                """
                await self.send_message(update, message)
                return

            # Build JQL query for all projects
            # Jira requires at least one filter, so we filter by project keys
            project_keys = [p.key for p in projects]
            if len(project_keys) == 1:
                jql_query = f"project = {project_keys[0]} ORDER BY updated DESC"
            else:
                # Use IN clause for multiple projects
                projects_filter = ", ".join(project_keys)
                jql_query = f"project IN ({projects_filter}) ORDER BY updated DESC"

            search_result = await self.jira.search_issues(jql_query, max_results=50)
            all_issues = search_result.issues

            if not all_issues:
                message = f"""
{EMOJI.get('ISSUES', '📋')} All Issues

No issues found across all projects.

Get Started:
• Use /create to start the issue creation wizard
                """
                await self.send_message(update, message)
                return

            # Group issues by project
            from collections import defaultdict
            issues_by_project = defaultdict(list)
            for issue in all_issues:
                issues_by_project[issue.project_key].append(issue)

            # Build message with issues categorized by project
            message_lines = [f"{EMOJI.get('ISSUES', '📋')} All Issues ({len(all_issues)} total)", ""]

            for project_key in sorted(issues_by_project.keys()):
                project_issues = issues_by_project[project_key]
                project_name = project_issues[0].project_name if project_issues else project_key

                message_lines.append(f"\n{project_name} ({project_key}) - {len(project_issues)} issues")

                # Show up to 5 issues per project
                for i, issue in enumerate(project_issues[:5], 1):
                    priority_emoji = issue.priority.get_emoji() if hasattr(issue.priority, 'get_emoji') else ""
                    type_emoji = issue.issue_type.get_emoji() if hasattr(issue.issue_type, 'get_emoji') else ""
                    message_lines.append(f"{i}. {priority_emoji}{type_emoji} {issue.key}: {issue.summary[:50]}")

                if len(project_issues) > 5:
                    message_lines.append(f"   ... and {len(project_issues) - 5} more")

            message = "\n".join(message_lines)

            # Add action buttons
            keyboard_buttons = []

            # Quick action buttons for first few issues
            for issue in all_issues[:3]:
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

    async def list_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /listissues command - list issues with optional filters."""
        await self.list_all_issues(update, context)

    async def list_all_issues(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /listissues command - list issues with optional filters."""
        self.log_handler_start(update, "list_all_issues")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Parse filter arguments
            filters = {}
            if context.args:
                filters = self._parse_issue_filters(context.args)

            # Build JQL query based on filters
            jql_parts = []
            
            if 'project' in filters:
                jql_parts.append(f"project = {filters['project']}")
            
            if 'type' in filters:
                jql_parts.append(f"type = {filters['type']}")
                
            if 'priority' in filters:
                jql_parts.append(f"priority = {filters['priority']}")
                
            if 'status' in filters:
                jql_parts.append(f"status = {filters['status']}")

            # Default query if no filters - restrict to user's default project or recent issues
            if not jql_parts:
                # Get user's default project
                default_project = await self.db.get_user_default_project(user.user_id)
                if default_project:
                    jql_parts.append(f"project = {default_project.key}")
                else:
                    # If no default project, limit to issues updated in last 30 days
                    jql_parts.append("updated >= -30d")

            # Add ORDER BY clause
            jql_parts.append("ORDER BY updated DESC")

            # Build final query
            jql_query = " AND ".join(jql_parts[:-1]) + " " + jql_parts[-1] if len(jql_parts) > 1 else jql_parts[0]

            # Search issues
            search_result = await self.jira.search_issues(jql_query, max_results=20)
            issues = search_result.issues

            if not issues:
                message = f"""
{EMOJI.get('SEARCH', '🔍')} No Issues Found

No issues match your criteria.

Try:
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
        """Handle /search command - search issues by text."""
        self.log_handler_start(update, "search_issues")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "Usage: `/search <query>`\n\nSearch issues by summary, description, or key."
                )
                return

            query = ' '.join(context.args)

            # Build search JQL with date restriction to avoid unbounded queries
            jql_query = f'text ~ "{query}" AND updated >= -90d ORDER BY updated DESC'

            # Search issues
            search_result = await self.jira.search_issues(jql_query, max_results=20)
            issues = search_result.issues

            if not issues:
                message = f"""
{EMOJI.get('SEARCH', '🔍')} No Results Found

No issues found matching: {query}

Tips:
• Try different keywords
• Check spelling
• Use simpler terms
                """
                await self.send_message(update, message)
                return

            # Format results
            title = f"Search Results for '{query}'"
            message = self.formatter.format_issue_list(issues, title)

            # Add action buttons
            keyboard_buttons = []
            
            if len(issues) == 20:
                keyboard_buttons.append([
                    InlineKeyboardButton("📄 Load More", callback_data=f"search_more_{query}")
                ])
            
            keyboard_buttons.append([
                InlineKeyboardButton("🔄 New Search", callback_data="new_search")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "search_issues")

        except Exception as e:
            await self.handle_error(update, e, "search_issues")
            self.log_handler_end(update, "search_issues", success=False)

    # =============================================================================
    # ISSUE DETAILS AND EDITING COMMANDS
    # =============================================================================

    async def view_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /view command - view issue details."""
        await self.view_issue_details(update, context)

    async def view_issue_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /issue command - view detailed issue information."""
        self.log_handler_start(update, "view_issue_details")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "Usage: `/view <ISSUE_KEY>`\n\nExample: `/view WEBAPP-123`"
                )
                return

            issue_key = context.args[0].upper()
            
            # Validate issue key format
            if not self._validate_issue_key(issue_key):
                await self.send_error_message(update, "Invalid issue key format. Example: WEBAPP-123")
                return

            # Get issue from Jira
            try:
                issue = await self.jira.get_issue(issue_key)
            except JiraAPIError as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                    return
                raise

            if not issue:
                await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                return

            # Format issue details
            message = self.formatter.format_issue(issue, include_description=True)

            # Add action buttons
            keyboard_buttons = [
                [
                    InlineKeyboardButton("💬 Comments", callback_data=f"view_comments_{issue_key}"),
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_issue_{issue_key}")
                ],
                [
                    InlineKeyboardButton("✏️ Edit", callback_data=f"edit_issue_{issue_key}"),
                    InlineKeyboardButton("🔄 Transition", callback_data=f"transition_issue_{issue_key}")
                ]
            ]

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "view_issue_details")

        except Exception as e:
            await self.handle_error(update, e, "view_issue_details")
            self.log_handler_end(update, "view_issue_details", success=False)

    async def edit_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /edit command - edit issue."""
        self.log_handler_start(update, "edit_issue")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "Usage: `/edit <ISSUE_KEY>`\n\nExample: `/edit WEBAPP-123`"
                )
                return

            issue_key = context.args[0].upper()
            
            # Validate issue key format
            if not self._validate_issue_key(issue_key):
                await self.send_error_message(update, "Invalid issue key format.")
                return

            # Check if issue exists
            try:
                issue = await self.jira.get_issue(issue_key)
                if not issue:
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                    return
            except JiraAPIError as e:
                if "404" in str(e):
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                    return
                raise

            # Show edit options
            await self._show_edit_issue_menu(update, issue_key)
            self.log_handler_end(update, "edit_issue")

        except Exception as e:
            await self.handle_error(update, e, "edit_issue")
            self.log_handler_end(update, "edit_issue", success=False)

    async def assign_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /assign command - assign issue to user."""
        self.log_handler_start(update, "assign_issue")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args or len(context.args) < 2:
                await self.send_message(
                    update,
                    "Usage: `/assign <ISSUE_KEY> <USERNAME>`\n\nExample: `/assign WEBAPP-123 john.doe`"
                )
                return

            issue_key = context.args[0].upper()
            assignee = context.args[1]

            # Validate issue key format
            if not self._validate_issue_key(issue_key):
                await self.send_error_message(update, "Invalid issue key format.")
                return

            # Assign issue
            try:
                await self.jira.assign_issue(issue_key, assignee)
                
                success_message = self.formatter.format_success_message(
                    f"Issue {issue_key} assigned",
                    f"Issue has been assigned to @{assignee}"
                )
                
                await self.send_message(update, success_message)

            except JiraAPIError as e:
                if "404" in str(e):
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                elif "User does not exist" in str(e):
                    await self.send_error_message(update, f"User '{assignee}' not found.")
                else:
                    await self.send_error_message(update, f"Failed to assign issue: {str(e)}")

            self.log_handler_end(update, "assign_issue")

        except Exception as e:
            await self.handle_error(update, e, "assign_issue")
            self.log_handler_end(update, "assign_issue", success=False)

    async def comment_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /comment command - add comment to issue."""
        await self.add_comment(update, context)

    async def add_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /comment command - add comment to issue."""
        self.log_handler_start(update, "add_comment")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args or len(context.args) < 2:
                await self.send_message(
                    update,
                    "Usage: `/comment <ISSUE_KEY> <comment text>`\n\nExample: `/comment WEBAPP-123 This issue is resolved`"
                )
                return

            issue_key = context.args[0].upper()
            comment_text = ' '.join(context.args[1:])

            # Validate inputs
            if not self._validate_issue_key(issue_key):
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
                    f"Your comment has been posted successfully.\n\n💬 Comment: "
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

    async def transition_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /transition command - transition issue status."""
        self.log_handler_start(update, "transition_issue")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "Usage: `/transition <ISSUE_KEY> [status]`\n\nExample: `/transition WEBAPP-123 Done`"
                )
                return

            issue_key = context.args[0].upper()
            
            # Validate issue key format
            if not self._validate_issue_key(issue_key):
                await self.send_error_message(update, "Invalid issue key format.")
                return

            if len(context.args) == 1:
                # Show available transitions
                await self._show_available_transitions(update, issue_key)
            else:
                # Try to transition to specified status
                target_status = ' '.join(context.args[1:])
                await self._perform_transition(update, issue_key, target_status)

            self.log_handler_end(update, "transition_issue")

        except Exception as e:
            await self.handle_error(update, e, "transition_issue")
            self.log_handler_end(update, "transition_issue", success=False)

    async def delete_issue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /delete command - delete an issue with confirmation."""
        self.log_handler_start(update, "delete_issue")

        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "Usage: `/delete <ISSUE_KEY>`\n\nExample: `/delete MBA-123`\n\n⚠️ This will permanently delete the issue!"
                )
                return

            issue_key = context.args[0].upper()

            # Validate issue key format
            if not self._validate_issue_key(issue_key):
                await self.send_error_message(update, "Invalid issue key format.")
                return

            # Check if issue exists
            try:
                issue = await self.jira.get_issue(issue_key)
                if not issue:
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                    return
            except JiraAPIError as e:
                if "404" in str(e):
                    await self.send_error_message(update, f"Issue '{issue_key}' not found.")
                    return
                raise

            # Show confirmation dialog
            message = f"""
⚠️ Delete Issue Confirmation

Are you sure you want to delete this issue?

{issue_key}: {issue.summary}
Type: {issue.issue_type.value}
Status: {issue.status}

This action cannot be undone!**
            """

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ Yes, Delete", callback_data=f"confirm_delete_{issue_key}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete")]
            ])

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "delete_issue")

        except Exception as e:
            await self.handle_error(update, e, "delete_issue")
            self.log_handler_end(update, "delete_issue", success=False)

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
        elif query.data.startswith("edit_summary_"):
            await self._handle_edit_summary_callback(update, context)
        elif query.data.startswith("edit_description_"):
            await self._handle_edit_description_callback(update, context)
        elif query.data.startswith("edit_priority_"):
            await self._handle_edit_priority_callback(update, context)
        elif query.data.startswith("edit_assignee_"):
            await self._handle_edit_assignee_callback(update, context)
        elif query.data.startswith("set_priority_"):
            await self._handle_set_priority_callback(update, context)
        elif query.data.startswith("edit_issue_"):
            await self._handle_edit_issue_callback(update, context)
        elif query.data.startswith("transition_issue_"):
            await self._handle_transition_issue_callback(update, context)
        elif query.data.startswith("confirm_create_"):
            await self._handle_confirm_create_callback(update, context)
        elif query.data.startswith("confirm_delete_"):
            await self._handle_confirm_delete_callback(update, context)
        elif query.data == "cancel_delete":
            await self._handle_cancel_delete_callback(update, context)
        elif query.data == "create_new_issue":
            await self._handle_create_new_issue_callback(update, context)
        elif query.data == "refresh_my_issues":
            await self._handle_refresh_my_issues_callback(update, context)

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _parse_quick_issue_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse quick issue text format."""
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
        """Parse issue filter arguments."""
        filters = {}
        
        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                filters[key.lower()] = value
        
        return filters

    def _format_filter_description(self, filters: Dict[str, str]) -> str:
        """Format filter description for display."""
        if not filters:
            return ""
        
        filter_parts = []
        for key, value in filters.items():
            filter_parts.append(f"{key}={value}")
        
        return f" (filtered by: {', '.join(filter_parts)})"

    def _validate_issue_key(self, issue_key: str) -> bool:
        """Validate issue key format."""
        return bool(re.match(r'^[A-Z][A-Z0-9_]*-\d+$', issue_key))

    async def _show_quick_issue_confirmation(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        project: Project, 
        parsed_issue: Dict[str, Any]
    ) -> None:
        """Show confirmation for quick issue creation."""
        priority_emoji = parsed_issue['priority'].get_emoji()
        type_emoji = parsed_issue['issue_type'].get_emoji()
        
        message = f"""
{EMOJI.get('CONFIRM', '✅')} Confirm Issue Creation

Project: {project.key}: {project.name}
Type: {type_emoji} {parsed_issue['issue_type'].value}
Priority: {priority_emoji} {parsed_issue['priority'].value}
Summary: {parsed_issue['summary']}

Create this issue?
        """

        # Store issue data for creation
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

    async def _show_edit_issue_menu(self, update: Update, issue_key: str) -> None:
        """Show edit issue menu."""
        message = f"""
✏️ Edit Issue: {issue_key}

What would you like to edit?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Summary", callback_data=f"edit_summary_{issue_key}")],
            [InlineKeyboardButton("📄 Description", callback_data=f"edit_description_{issue_key}")],
            [InlineKeyboardButton("🎯 Priority", callback_data=f"edit_priority_{issue_key}")],
            [InlineKeyboardButton("👤 Assignee", callback_data=f"edit_assignee_{issue_key}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"view_issue_{issue_key}")]
        ])

        await self.send_message(update, message, reply_markup=keyboard)

    async def _show_available_transitions(self, update: Update, issue_key: str) -> None:
        """Show available transitions for an issue."""
        try:
            transitions = await self.jira.list_transitions(issue_key)
            
            if not transitions:
                await self.send_message(update, f"No transitions available for {issue_key}.")
                return

            message = f"""
🔄 Available Transitions for {issue_key}

Choose a new status:
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
                InlineKeyboardButton("❌ Cancel", callback_data=f"view_issue_{issue_key}")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            await self.send_message(update, message, reply_markup=keyboard)

        except JiraAPIError as e:
            await self.send_error_message(update, f"Failed to get transitions: {str(e)}")

    async def _perform_transition(self, update: Update, issue_key: str, target_status: str) -> None:
        """Perform transition to target status."""
        try:
            # Get available transitions
            transitions = await self.jira.list_transitions(issue_key)
            
            # Find matching transition
            matching_transition = None
            for transition in transitions:
                if transition['name'].lower() == target_status.lower():
                    matching_transition = transition
                    break

            if not matching_transition:
                available = [t['name'] for t in transitions]
                await self.send_error_message(
                    update, 
                    f"Status '{target_status}' not available. Available: {', '.join(available)}"
                )
                return

            # Perform transition
            await self.jira.transition_issue(issue_key, matching_transition['id'])
            
            success_message = self.formatter.format_success_message(
                f"Issue {issue_key} transitioned",
                f"Status changed to {matching_transition['name']}"
            )
            
            await self.send_message(update, success_message)

        except JiraAPIError as e:
            await self.send_error_message(update, f"Failed to transition issue: {str(e)}")

    # Callback handlers
    async def _handle_view_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle view issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("view_issue_", "")
        context.args = [issue_key]
        await self.view_issue_details(update, context)

    async def _handle_view_comments_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle view comments callback."""
        query = update.callback_query
        issue_key = query.data.replace("view_comments_", "")
        
        try:
            comments = await self.jira.list_comments(issue_key)
            
            if not comments:
                await self.edit_message(update, f"No comments found for {issue_key}.")
                return

            # Format comments
            message_lines = [
                f"💬 Comments for {issue_key} ({len(comments)} total)",
                ""
            ]

            for i, comment in enumerate(comments[-10:], 1):  # Show last 10 comments
                comment_preview = self.formatter.truncate_text(comment.body, 100)
                age = comment.get_age_string()
                
                comment_line = f"{i}. {comment.author_display_name} ({age})\n   {comment_preview}"
                message_lines.append(comment_line)

            message = "\n\n".join(message_lines)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Issue", callback_data=f"view_issue_{issue_key}")]
            ])

            await self.edit_message(update, message, reply_markup=keyboard)

        except JiraAPIError as e:
            await self.edit_message(update, f"Failed to get comments: {str(e)}")

    async def _handle_refresh_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("refresh_issue_", "")
        context.args = [issue_key]
        await self.view_issue_details(update, context)

    async def _handle_edit_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edit issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("edit_issue_", "")
        await self._show_edit_issue_menu(update, issue_key)

    async def _handle_transition_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle transition issue callback."""
        query = update.callback_query
        issue_key = query.data.replace("transition_issue_", "")
        await self._show_available_transitions(update, issue_key)

    async def _handle_confirm_create_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle confirm create callback."""
        query = update.callback_query
        project_key = query.data.replace("confirm_create_", "")
        
        # Get issue data from context
        issue_data = context.user_data.get('quick_issue_data')
        if not issue_data:
            await self.edit_message(update, "❌ Issue data not found. Please try again.")
            return

        try:
            # Create issue in Jira
            created_issue = await self.jira.create_issue(
                project_key=issue_data['project_key'],
                summary=issue_data['summary'],
                description="Created via Telegram bot",
                issue_type=issue_data['issue_type'].value,
                priority=issue_data['priority'].value
            )

            success_message = self.formatter.format_success_message(
                "Issue created successfully!",
                f"{created_issue.key}: {created_issue.summary}\n"
                f"🔗 View in Jira: {created_issue.url}"
            )

            await self.edit_message(update, success_message)

            # Clear stored data
            context.user_data.pop('quick_issue_data', None)

        except JiraAPIError as e:
            await self.edit_message(update, f"❌ Failed to create issue: {str(e)}")

    async def _handle_create_new_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle create new issue callback."""
        await self.create_issue_wizard(update, context)

    async def _handle_refresh_my_issues_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh my issues callback."""
        await self.list_user_issues(update, context)

    async def _handle_edit_summary_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edit summary callback."""
        query = update.callback_query
        issue_key = query.data.replace("edit_summary_", "")

        message = f"📝 Edit Summary for {issue_key}\n\nPlease send the new summary text:"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"view_issue_{issue_key}")]
        ])

        # Store the issue key and field being edited
        context.user_data['editing_issue'] = {
            'issue_key': issue_key,
            'field': 'summary'
        }

        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

    async def _handle_edit_description_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edit description callback."""
        query = update.callback_query
        issue_key = query.data.replace("edit_description_", "")

        message = f"📄 Edit Description for {issue_key}\n\nPlease send the new description text:"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"view_issue_{issue_key}")]
        ])

        # Store the issue key and field being edited
        context.user_data['editing_issue'] = {
            'issue_key': issue_key,
            'field': 'description'
        }

        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

    async def _handle_edit_priority_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edit priority callback."""
        query = update.callback_query
        issue_key = query.data.replace("edit_priority_", "")

        message = f"🎯 Edit Priority for {issue_key}\n\nSelect new priority:"

        # Create priority selection keyboard
        priorities = [IssuePriority.HIGHEST, IssuePriority.HIGH, IssuePriority.MEDIUM,
                     IssuePriority.LOW, IssuePriority.LOWEST]
        keyboard_buttons = []

        for priority in priorities:
            emoji = priority.get_emoji()
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{emoji} {priority.value}",
                    callback_data=f"set_priority_{issue_key}_{priority.name}"
                )
            ])

        keyboard_buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data=f"view_issue_{issue_key}")
        ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

    async def _handle_edit_assignee_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edit assignee callback."""
        query = update.callback_query
        issue_key = query.data.replace("edit_assignee_", "")

        message = f"👤 Edit Assignee for {issue_key}\n\nPlease send the assignee's account ID or username:"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"view_issue_{issue_key}")]
        ])

        # Store the issue key and field being edited
        context.user_data['editing_issue'] = {
            'issue_key': issue_key,
            'field': 'assignee'
        }

        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

    async def _handle_set_priority_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle set priority callback."""
        query = update.callback_query
        # Parse: set_priority_MBA-7_HIGH
        parts = query.data.replace("set_priority_", "").rsplit("_", 1)
        issue_key = parts[0]
        priority_name = parts[1]

        try:
            priority = IssuePriority[priority_name]

            # Update the issue
            updated_issue = await self.jira.update_issue(issue_key, priority=priority)

            # Show success message
            emoji = priority.get_emoji()
            message = f"✅ Priority Updated\n\n{issue_key} priority set to {emoji} {priority.value}"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Issue", callback_data=f"view_issue_{issue_key}")]
            ])

            await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

        except Exception as e:
            await query.edit_message_text(
                f"❌ Failed to update priority: {str(e)}\n\nTry again with /edit {issue_key}",
                parse_mode="Markdown"
            )

    async def handle_edit_field_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle message input for editing issue fields."""
        # Check if user is editing an issue
        if not context.user_data or 'editing_issue' not in context.user_data:
            return

        editing_data = context.user_data['editing_issue']
        issue_key = editing_data['issue_key']
        field = editing_data['field']
        new_value = update.message.text.strip()

        try:
            if field == 'summary':
                updated_issue = await self.jira.update_issue(issue_key, summary=new_value)
                field_display = "Summary"
            elif field == 'description':
                updated_issue = await self.jira.update_issue(issue_key, description=new_value)
                field_display = "Description"
            elif field == 'assignee':
                await self.jira.assign_issue(issue_key, new_value)
                field_display = "Assignee"
            else:
                await update.message.reply_text("❌ Invalid field")
                return

            # Clear editing state
            context.user_data.pop('editing_issue', None)

            # Show success message
            message = f"✅ {field_display} Updated\n\n{issue_key} {field} has been updated successfully."

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Issue", callback_data=f"view_issue_{issue_key}")]
            ])

            await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")

        except JiraAPIError as e:
            await update.message.reply_text(
                f"❌ Failed to update {field}: {str(e)}\n\nTry again with /edit {issue_key}",
                parse_mode="Markdown"
            )
            context.user_data.pop('editing_issue', None)

    async def _handle_confirm_delete_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle confirm delete callback."""
        query = update.callback_query
        issue_key = query.data.replace("confirm_delete_", "")

        try:
            # Delete the issue
            await self.jira.delete_issue(issue_key)

            # Show success message
            message = f"✅ Issue Deleted\n\n{issue_key} has been permanently deleted from Jira."

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 My Issues", callback_data="refresh_my_issues")]
            ])

            await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

            # Log the action
            user = await self.get_or_create_user(update)
            if user:
                await self.db.log_user_action(user.user_id, "issue.deleted", {
                    "issue_key": issue_key
                })

        except JiraAPIError as e:
            error_msg = f"❌ Failed to delete issue: {str(e)}"
            await query.edit_message_text(error_msg, parse_mode="Markdown")

    async def _handle_cancel_delete_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle cancel delete callback."""
        query = update.callback_query
        await query.edit_message_text("❌ Delete cancelled.", parse_mode="Markdown")