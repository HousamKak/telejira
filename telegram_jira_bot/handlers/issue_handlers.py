#!/usr/bin/env python3
"""
Issue handlers for the Telegram-Jira bot.

Handles issue-related commands and operations.
"""

import re
from typing import Optional, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .base_handler import BaseHandler
from ..models.issue import JiraIssue
from ..models.project import Project
from ..models.user import User, UserPreferences
from ..models.enums import IssuePriority, IssueType, IssueStatus, ErrorType
from ..services.database import DatabaseError
from ..services.jira_service import JiraAPIError
from ..utils.constants import EMOJI
from ..utils.validators import ValidationResult


class IssueHandler(BaseHandler):
    """Handles issue-related operations."""

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "IssueHandler"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to issue operations."""
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        else:
            await self.send_error_message(update, f"Unexpected error: {str(error)}")

    # Command handlers
    async def create_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /create command - interactive issue creation."""
        self.log_handler_start(update, "create_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get available projects
            projects = await self.db.get_projects(active_only=True)
            if not projects:
                await self.send_info_message(
                    update,
                    f"{EMOJI['INFO']} No projects available. Ask an admin to add projects first."
                )
                self.log_handler_end(update, "create_command")
                return

            # Show project selection
            await self._show_project_selection_for_creation(update, projects)
            
            self.log_handler_end(update, "create_command")

        except Exception as e:
            await self.handle_error(update, e, "create_command")
            self.log_handler_end(update, "create_command", success=False)

    async def myissues_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /myissues command - show user's recent issues."""
        self.log_handler_start(update, "myissues_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get user preferences for pagination
            preferences = await self.get_user_preferences(user.user_id)
            page_size = preferences.max_issues_per_page if preferences else self.config.max_issues_per_page

            # Search for user's issues
            search_result = await self.db.search_issues(
                user_id=user.user_id,
                limit=page_size,
                offset=0
            )

            if not search_result.has_results():
                await self.send_info_message(
                    update,
                    f"{EMOJI['INFO']} You haven't created any issues yet.\n"
                    "Send any message to create your first issue!"
                )
                self.log_handler_end(update, "myissues_command")
                return

            # Format and send issue list
            text = self.telegram.formatter.format_issue_list(
                search_result.issues,
                title="Your Recent Issues",
                show_project=True,
                show_description=False
            )

            # Create navigation keyboard
            keyboard = []
            if search_result.total_count > len(search_result.issues):
                keyboard.append([
                    InlineKeyboardButton(
                        f"{EMOJI['NEXT']} Show More",
                        callback_data=f"issues_my_page_1"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['REFRESH']} Refresh",
                    callback_data="issues_my_refresh"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['SEARCH']} Search",
                    callback_data="issues_search_start"
                )
            ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await self.send_message(update, text, reply_markup)

            self.log_user_action(user, "view_my_issues", {"issue_count": len(search_result.issues)})
            self.log_handler_end(update, "myissues_command")

        except Exception as e:
            await self.handle_error(update, e, "myissues_command")
            self.log_handler_end(update, "myissues_command", success=False)

    async def listissues_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /listissues command - list all issues with filters."""
        self.log_handler_start(update, "listissues_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Parse command arguments for filters
            args = self.parse_command_args(update, 0)  # Optional filters
            filters = self._parse_issue_filters(args)

            # Get user preferences
            preferences = await self.get_user_preferences(user.user_id)
            page_size = preferences.max_issues_per_page if preferences else self.config.max_issues_per_page

            # Search issues with filters
            search_result = await self.db.search_issues(
                project_key=filters.get('project'),
                issue_type=filters.get('type'),
                priority=filters.get('priority'),
                status=filters.get('status'),
                assignee=filters.get('assignee'),
                limit=page_size,
                offset=0
            )

            if not search_result.has_results():
                await self.send_info_message(
                    update,
                    f"{EMOJI['INFO']} No issues found matching your criteria."
                )
                self.log_handler_end(update, "listissues_command")
                return

            # Format and send issue list
            text = self.telegram.formatter.format_search_results(search_result)

            # Create navigation keyboard
            keyboard = self._create_issue_list_keyboard(search_result, filters)
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            await self.send_message(update, text, reply_markup)

            self.log_user_action(user, "list_issues", {"filters": filters, "result_count": len(search_result.issues)})
            self.log_handler_end(update, "listissues_command")

        except Exception as e:
            await self.handle_error(update, e, "listissues_command")
            self.log_handler_end(update, "listissues_command", success=False)

    async def searchissues_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /searchissues command - search issues by text."""
        self.log_handler_start(update, "searchissues_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        args = self.parse_command_args(update, 1)  # Require search query
        if not args:
            await self._send_searchissues_usage(update)
            self.log_handler_end(update, "searchissues_command")
            return

        search_query = " ".join(args)
        
        try:
            # Validate search query
            validation = self.telegram.validator.validate_search_query(search_query)
            if not validation.is_valid:
                await self.handle_validation_error(update, validation, "search query")
                self.log_handler_end(update, "searchissues_command", success=False)
                return

            # Get user preferences
            preferences = await self.get_user_preferences(user.user_id)
            page_size = preferences.max_issues_per_page if preferences else self.config.max_issues_per_page

            # Search issues
            search_result = await self.db.search_issues(
                query=search_query,
                limit=page_size,
                offset=0
            )

            if not search_result.has_results():
                await self.send_info_message(
                    update,
                    f"{EMOJI['SEARCH']} No issues found for '{search_query}'."
                )
                self.log_handler_end(update, "searchissues_command")
                return

            # Format and send results
            text = self.telegram.formatter.format_search_results(search_result)

            # Create keyboard
            keyboard = []
            if search_result.total_count > len(search_result.issues):
                keyboard.append([
                    InlineKeyboardButton(
                        f"{EMOJI['NEXT']} Show More",
                        callback_data=f"issues_search_page_1_{search_query}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['REFRESH']} Refresh",
                    callback_data=f"issues_search_refresh_{search_query}"
                )
            ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await self.send_message(update, text, reply_markup)

            self.log_user_action(user, "search_issues", {"query": search_query, "result_count": len(search_result.issues)})
            self.log_handler_end(update, "searchissues_command")

        except Exception as e:
            await self.handle_error(update, e, "searchissues_command")
            self.log_handler_end(update, "searchissues_command", success=False)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular messages and create issues."""
        self.log_handler_start(update, "handle_message")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        if not update.message or not update.message.text:
            return

        # Check if user is in a wizard or conversation
        session = await self.get_user_session(user.user_id)
        if session and session.is_in_wizard():
            # Let wizard handler deal with this
            return

        message_text = update.message.text.strip()
        
        try:
            # Parse message for priority and type prefixes
            priority, issue_type, clean_text = self._parse_message_prefixes(message_text)

            # Get user's default project
            preferences = await self.get_user_preferences(user.user_id)
            if not preferences or not preferences.default_project_key:
                await self._show_no_default_project_message(update)
                self.log_handler_end(update, "handle_message")
                return

            # Create issue in default project
            await self._create_issue_from_message(
                update, 
                user, 
                preferences.default_project_key,
                clean_text,
                priority or preferences.default_priority,
                issue_type or preferences.default_issue_type
            )

            self.log_handler_end(update, "handle_message")

        except Exception as e:
            await self.handle_error(update, e, "handle_message")
            self.log_handler_end(update, "handle_message", success=False)

    # Callback handlers
    async def handle_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle issue-related callbacks."""
        callback_data = self.extract_callback_data(update)
        if not callback_data:
            return

        parts = self.parse_callback_data(callback_data)
        if len(parts) < 2:
            return

        action = parts[1]  # issues_<action>

        if action == "my_refresh":
            await self.myissues_command(update, context)
        elif action.startswith("my_page_"):
            page = int(parts[2]) if len(parts) > 2 else 0
            await self._show_my_issues_page(update, page)
        elif action.startswith("search_"):
            await self._handle_search_callback(update, parts[2:])
        elif action.startswith("create_"):
            await self._handle_create_callback(update, parts[2:])
        elif action.startswith("view_"):
            issue_key = parts[2] if len(parts) > 2 else None
            if issue_key:
                await self._show_issue_details(update, issue_key)
        elif action.startswith("edit_"):
            issue_key = parts[2] if len(parts) > 2 else None
            if issue_key:
                await self._show_issue_edit_options(update, issue_key)

    # Private helper methods
    def _parse_message_prefixes(self, message_text: str) -> tuple[Optional[IssuePriority], Optional[IssueType], str]:
        """Parse priority and issue type prefixes from message text."""
        original_text = message_text
        priority = None
        issue_type = None

        # Check for priority prefix
        priority_match = re.match(r'^(LOWEST|LOW|MEDIUM|HIGH|HIGHEST)\s+(.+)', message_text, re.IGNORECASE)
        if priority_match:
            try:
                priority = IssuePriority.from_string(priority_match.group(1))
                message_text = priority_match.group(2)
            except ValueError:
                pass

        # Check for issue type prefix
        type_match = re.match(r'^(TASK|BUG|STORY|EPIC|IMPROVEMENT|SUBTASK)\s+(.+)', message_text, re.IGNORECASE)
        if type_match:
            try:
                issue_type = IssueType.from_string(type_match.group(1))
                message_text = type_match.group(2)
            except ValueError:
                pass

        return priority, issue_type, message_text

    def _parse_issue_filters(self, args: Optional[List[str]]) -> Dict[str, str]:
        """Parse issue filter arguments."""
        filters = {}
        if not args:
            return filters

        # Simple key=value parsing
        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                key = key.lower()
                if key in ['project', 'type', 'priority', 'status', 'assignee']:
                    filters[key] = value

        return filters

    def _create_issue_list_keyboard(self, search_result, filters: Dict[str, str]) -> List[List[InlineKeyboardButton]]:
        """Create keyboard for issue list navigation."""
        keyboard = []

        # Pagination
        if search_result.total_count > len(search_result.issues):
            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['NEXT']} Show More",
                    callback_data="issues_list_page_1"
                )
            ])

        # Actions
        action_row = []
        action_row.append(InlineKeyboardButton(
            f"{EMOJI['REFRESH']} Refresh",
            callback_data="issues_list_refresh"
        ))
        action_row.append(InlineKeyboardButton(
            f"{EMOJI['FILTER']} Filter",
            callback_data="issues_list_filter"
        ))
        keyboard.append(action_row)

        return keyboard

    async def _send_searchissues_usage(self, update: Update) -> None:
        """Send usage instructions for searchissues command."""
        text = f"{EMOJI['INFO']} **Search Issues Usage**\n\n"
        text += "**Syntax:** `/searchissues <query>`\n\n"
        text += "**Examples:**\n"
        text += "• `/searchissues login bug` - Search for 'login bug'\n"
        text += "• `/searchissues authentication` - Search for 'authentication'\n"
        text += "• `/searchissues \"user interface\"` - Search for exact phrase\n\n"
        text += "The search looks in issue summaries and descriptions."
        
        await self.send_message(update, text)

    async def _show_project_selection_for_creation(self, update: Update, projects: List[Project]) -> None:
        """Show project selection for issue creation."""
        text = f"{EMOJI['ISSUE']} **Create New Issue**\n\n"
        text += "First, select the project for your issue:"

        keyboard = self.telegram.create_project_selection_keyboard(
            projects,
            callback_prefix="issues_create_project",
            show_cancel=True
        )

        await self.send_message(update, text, keyboard)

    async def _show_no_default_project_message(self, update: Update) -> None:
        """Show message when user has no default project set."""
        text = f"{EMOJI['WARNING']} **No Default Project Set**\n\n"
        text += "You need to set a default project before creating issues from messages.\n\n"
        text += "**Options:**\n"
        text += "• Use `/setdefault` to set your default project\n"
        text += "• Use `/create` to create an issue with project selection"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['SETTINGS']} Set Default Project",
                    callback_data="projects_set_default"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['ISSUE']} Create Issue",
                    callback_data="issues_create_start"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _create_issue_from_message(
        self,
        update: Update,
        user: User,
        project_key: str,
        message_text: str,
        priority: IssuePriority,
        issue_type: IssueType
    ) -> None:
        """Create an issue from a message."""
        message_id = update.message.message_id if update.message else 0

        # Send processing message
        processing_msg = await self.send_message(update, f"{EMOJI['LOADING']} Creating Jira issue...")
        
        try:
            # Validate project exists and is active
            project = await self.db.get_project_by_key(project_key)
            if not project or not project.is_active:
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` is not available.",
                    ErrorType.NOT_FOUND_ERROR
                )
                return

            # Validate inputs
            summary_validation = self.validate_issue_summary(message_text)
            if not summary_validation.is_valid:
                await self.handle_validation_error(update, summary_validation, "issue summary")
                return

            # Create summary (truncate if needed)
            summary = message_text[:self.config.max_summary_length]
            if len(message_text) > self.config.max_summary_length:
                summary += "..."

            # Create Jira issue
            issue = await self.jira.create_issue(
                project_key=project_key,
                summary=summary,
                description=message_text,
                priority=priority,
                issue_type=issue_type
            )

            # Save to database
            await self.db.save_issue(user.user_id, message_id, issue)

            # Create success message
            text = f"{EMOJI['SUCCESS']} **Issue Created Successfully!**\n\n"
            text += f"**Project:** {project.name} (`{project_key}`)\n"
            text += f"**Issue:** `{issue.key}`\n"
            text += f"**Summary:** {issue.summary}\n"
            text += f"**Type:** {issue.issue_type.get_emoji()} {issue.issue_type.value}\n"
            text += f"**Priority:** {issue.priority.get_emoji()} {issue.priority.value}\n"

            # Create action buttons
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['LINK']} Open in Jira", url=issue.url)],
                [InlineKeyboardButton(f"{EMOJI['ISSUE']} Create Another", callback_data="issues_create_start")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            # Edit the processing message or send new one
            if processing_msg:
                await self.telegram.edit_message(update, text, reply_markup)
            else:
                await self.send_message(update, text, reply_markup)

            self.log_user_action(
                user,
                "create_issue",
                {
                    "issue_key": issue.key,
                    "project_key": project_key,
                    "priority": priority.value,
                    "issue_type": issue_type.value
                }
            )

        except JiraAPIError as e:
            await self.handle_jira_error(update, e, "create_issue_from_message")
        except DatabaseError as e:
            await self.handle_database_error(update, e, "create_issue_from_message")

    async def _show_my_issues_page(self, update: Update, page: int) -> None:
        """Show specific page of user's issues."""
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            preferences = await self.get_user_preferences(user.user_id)
            page_size = preferences.max_issues_per_page if preferences else self.config.max_issues_per_page
            offset = page * page_size

            search_result = await self.db.search_issues(
                user_id=user.user_id,
                limit=page_size,
                offset=offset
            )

            if not search_result.has_results():
                await self.send_info_message(update, "No more issues to show.")
                return

            # Format issue list with page info
            page_info = {
                'current_page': page,
                'total_pages': (search_result.total_count + page_size - 1) // page_size,
                'total_items': search_result.total_count
            }

            text = self.telegram.formatter.format_issue_list(
                search_result.issues,
                title="Your Issues",
                show_project=True,
                page_info=page_info
            )

            # Create pagination keyboard
            keyboard = []
            nav_row = []
            
            if page > 0:
                nav_row.append(InlineKeyboardButton(
                    f"{EMOJI['PREVIOUS']} Previous",
                    callback_data=f"issues_my_page_{page - 1}"
                ))
            
            if offset + len(search_result.issues) < search_result.total_count:
                nav_row.append(InlineKeyboardButton(
                    f"{EMOJI['NEXT']} Next",
                    callback_data=f"issues_my_page_{page + 1}"
                ))
            
            if nav_row:
                keyboard.append(nav_row)

            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['REFRESH']} Refresh",
                    callback_data="issues_my_refresh"
                )
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await self.edit_message(update, text, reply_markup)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "show_my_issues_page")

    async def _handle_search_callback(self, update: Update, action_parts: List[str]) -> None:
        """Handle search-related callbacks."""
        if not action_parts:
            return

        action = action_parts[0]

        if action == "start":
            await self._show_search_interface(update)
        elif action == "refresh" and len(action_parts) > 1:
            query = "_".join(action_parts[1:])
            await self._refresh_search_results(update, query)
        elif action == "page" and len(action_parts) > 2:
            page = int(action_parts[1])
            query = "_".join(action_parts[2:])
            await self._show_search_page(update, query, page)

    async def _handle_create_callback(self, update: Update, action_parts: List[str]) -> None:
        """Handle create-related callbacks."""
        if not action_parts:
            return

        action = action_parts[0]

        if action == "start":
            await self.create_command(update, None)
        elif action == "project" and len(action_parts) > 1:
            project_key = action_parts[1]
            await self._show_issue_creation_form(update, project_key)

    async def _show_search_interface(self, update: Update) -> None:
        """Show search interface."""
        text = f"{EMOJI['SEARCH']} **Search Issues**\n\n"
        text += "Use the command format:\n"
        text += "`/searchissues <your search terms>`\n\n"
        text += "**Examples:**\n"
        text += "• `/searchissues login bug`\n"
        text += "• `/searchissues authentication error`\n"
        text += "• `/searchissues user interface`\n\n"
        text += "The search will look through issue summaries and descriptions."

        await self.edit_message(update, text)

    async def _refresh_search_results(self, update: Update, query: str) -> None:
        """Refresh search results for a query."""
        # Redirect to search command
        if update.effective_user:
            # Simulate command message
            context = ContextTypes.DEFAULT_TYPE()
            context.args = query.split('_')
            await self.searchissues_command(update, context)

    async def _show_search_page(self, update: Update, query: str, page: int) -> None:
        """Show specific page of search results."""
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            preferences = await self.get_user_preferences(user.user_id)
            page_size = preferences.max_issues_per_page if preferences else self.config.max_issues_per_page
            offset = page * page_size

            # Decode query
            search_query = query.replace('_', ' ')

            search_result = await self.db.search_issues(
                query=search_query,
                limit=page_size,
                offset=offset
            )

            if not search_result.has_results():
                await self.send_info_message(update, "No more results to show.")
                return

            # Format results with page info
            page_info = {
                'current_page': page,
                'total_pages': (search_result.total_count + page_size - 1) // page_size,
                'total_items': search_result.total_count
            }

            text = self.telegram.formatter.format_search_results(search_result)

            # Create pagination keyboard
            keyboard = []
            nav_row = []
            
            if page > 0:
                nav_row.append(InlineKeyboardButton(
                    f"{EMOJI['PREVIOUS']} Previous",
                    callback_data=f"issues_search_page_{page - 1}_{query}"
                ))
            
            if offset + len(search_result.issues) < search_result.total_count:
                nav_row.append(InlineKeyboardButton(
                    f"{EMOJI['NEXT']} Next",
                    callback_data=f"issues_search_page_{page + 1}_{query}"
                ))
            
            if nav_row:
                keyboard.append(nav_row)

            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['REFRESH']} Refresh",
                    callback_data=f"issues_search_refresh_{query}"
                )
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await self.edit_message(update, text, reply_markup)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "show_search_page")

    async def _show_issue_creation_form(self, update: Update, project_key: str) -> None:
        """Show issue creation form for specific project."""
        try:
            # Verify project
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project `{project_key}` not found.")
                return

            text = f"{EMOJI['ISSUE']} **Create Issue in {project.name}**\n\n"
            text += f"**Project:** `{project.key}` - {project.name}\n\n"
            text += "Next, select the issue type:"

            # Create issue type selection keyboard
            keyboard = self.telegram.create_issue_type_selection_keyboard(
                callback_prefix=f"issues_create_type_{project_key}"
            )

            await self.edit_message(update, text, keyboard)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "show_issue_creation_form")

    async def _show_issue_details(self, update: Update, issue_key: str) -> None:
        """Show detailed information about an issue."""
        try:
            # Get issue from Jira for most up-to-date info
            issue = await self.jira.get_issue(issue_key)
            
            text = self.telegram.formatter.format_issue_summary(
                issue,
                show_project=True,
                show_description=True,
                show_details=True,
                max_description_length=200
            )

            # Create action keyboard
            keyboard = self.telegram.create_issue_actions_keyboard(issue)
            
            await self.edit_message(update, text, keyboard)

        except JiraAPIError as e:
            await self.handle_jira_error(update, e, "show_issue_details")

    async def _show_issue_edit_options(self, update: Update, issue_key: str) -> None:
        """Show issue editing options."""
        text = f"{EMOJI['EDIT']} **Edit Issue Options**\n\n"
        text += f"**Issue:** `{issue_key}`\n\n"
        text += "What would you like to edit?"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['EDIT']} Summary",
                    callback_data=f"issues_edit_{issue_key}_summary"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['EDIT']} Description",
                    callback_data=f"issues_edit_{issue_key}_description"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['PRIORITY_MEDIUM']} Priority",
                    callback_data=f"issues_edit_{issue_key}_priority"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['USER']} Assignee",
                    callback_data=f"issues_edit_{issue_key}_assignee"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data=f"issues_view_{issue_key}"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.edit_message(update, text, reply_markup)