#!/usr/bin/env python3
"""
Project handlers for the Telegram-Jira bot.

Handles project-related commands including listing, selection, and management
of Jira projects through Telegram.
"""

import logging
import re
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .base_handler import BaseHandler
from models.project import Project, ProjectSummary
from models.user import User
from models.enums import UserRole, ErrorType
from services.database import DatabaseError
from services.jira_service import JiraAPIError
from utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES
from utils.validators import InputValidator, ValidationResult
from utils.formatters import MessageFormatter


class ProjectHandlers(BaseHandler):
    """Handles project-related commands and operations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = MessageFormatter(
            compact_mode=self.config.compact_mode,
            use_emoji=True
        )
        self.validator = InputValidator()

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "ProjectHandlers"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to project operations."""
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
                f"Project operation failed: {str(error)}",
                ErrorType.UNKNOWN_ERROR
            )

    # =============================================================================
    # PROJECT LISTING AND INFORMATION COMMANDS
    # =============================================================================

    async def list_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /projects command - list available projects."""
        self.log_handler_start(update, "list_projects")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get user's accessible projects
            projects = await self.db.get_user_projects(user.user_id)
            
            if not projects:
                message = f"""
{EMOJI.get('PROJECTS', '📁')} **Available Projects**

No projects available. 

**Next Steps:**
• Contact your admin to add projects
• Use `/help` for more information
                """
                await self.send_message(update, message)
                return

            # Get user's default project
            default_project = await self.db.get_user_default_project(user.user_id)
            default_key = default_project.key if default_project else None

            # Format projects list
            message_lines = [
                f"{EMOJI.get('PROJECTS', '📁')} **Available Projects** ({len(projects)} total)",
                ""
            ]

            for i, project in enumerate(projects, 1):
                status_emoji = "✅" if project.is_active else "❌"
                default_indicator = " 🌟" if project.key == default_key else ""
                
                project_line = f"{i}. {status_emoji} **{project.key}**: {project.name}{default_indicator}"
                
                if not self.config.compact_mode and project.description:
                    description = self.formatter._truncate_text(project.description, 100)
                    project_line += f"\n   📄 {description}"
                
                # Add quick stats if available
                try:
                    issue_count = await self.db.get_project_issue_count(project.key)
                    if issue_count > 0:
                        project_line += f"\n   📊 {issue_count} issues"
                except Exception:
                    pass  # Ignore stats errors
                
                message_lines.append(project_line)

            if default_key:
                message_lines.append("")
                message_lines.append("🌟 = Your default project for quick issue creation")

            message = "\n".join(message_lines)

            # Add action buttons
            keyboard_buttons = []
            
            # Quick action buttons for first few projects
            for project in projects[:5]:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"📝 Create Issue in {project.key}",
                        callback_data=f"create_issue_{project.key}"
                    )
                ])

            # Management buttons
            keyboard_buttons.extend([
                [
                    InlineKeyboardButton("⭐ Set Default Project", callback_data="change_default_project"),
                    InlineKeyboardButton("🔄 Refresh List", callback_data="refresh_projects")
                ]
            ])

            # Add admin buttons if user is admin
            if self.is_admin(user):
                keyboard_buttons.append([
                    InlineKeyboardButton("➕ Add Project", callback_data="add_project_admin"),
                    InlineKeyboardButton("🔄 Sync from Jira", callback_data="sync_projects_admin")
                ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "list_projects")

        except Exception as e:
            await self.handle_error(update, e, "list_projects")
            self.log_handler_end(update, "list_projects", success=False)

    async def get_project_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /project command - show detailed project information."""
        self.log_handler_start(update, "get_project_details")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "**Usage:** `/project <PROJECT_KEY>`\n\nExample: `/project WEBAPP`"
                )
                return

            project_key = context.args[0].upper()
            
            # Get project from database
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project '{project_key}' not found.")
                return

            # Check if user has access to this project
            user_projects = await self.db.get_user_projects(user.user_id)
            if not any(p.key == project_key for p in user_projects):
                await self.send_error_message(
                    update, 
                    f"You don't have access to project '{project_key}'."
                )
                return

            # Get project statistics
            try:
                project_stats = await self.db.get_project_statistics(project_key)
            except Exception:
                project_stats = {}

            # Format detailed project information
            message = f"""
{EMOJI.get('PROJECT', '📁')} **Project Details: {project.key}**

**Name:** {project.name}
**Status:** {'✅ Active' if project.is_active else '❌ Inactive'}
**URL:** [View in Jira]({project.url})

**Description:**
{project.description or 'No description available'}

**Statistics:**
• Total Issues: {project_stats.get('total_issues', 0)}
• Open Issues: {project_stats.get('open_issues', 0)}
• Closed Issues: {project_stats.get('closed_issues', 0)}
• Your Issues: {project_stats.get('user_issues', 0)}

**Recent Activity:**
Last updated: {project.updated_at.strftime('%Y-%m-%d %H:%M') if project.updated_at else 'Unknown'}
            """

            # Add action buttons
            keyboard_buttons = [
                [
                    InlineKeyboardButton("📝 Create Issue", callback_data=f"create_issue_{project_key}"),
                    InlineKeyboardButton("📋 List Issues", callback_data=f"list_issues_{project_key}")
                ],
                [
                    InlineKeyboardButton("⭐ Set as Default", callback_data=f"setdefault_{project_key}"),
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_project_{project_key}")
                ]
            ]

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "get_project_details")

        except Exception as e:
            await self.handle_error(update, e, "get_project_details")
            self.log_handler_end(update, "get_project_details", success=False)

    # =============================================================================
    # PROJECT PREFERENCE COMMANDS
    # =============================================================================

    async def set_default_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setdefault command - set user's default project."""
        self.log_handler_start(update, "set_default_project")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                # Show current default and available projects
                await self._show_project_selection_menu(update, user)
                return

            project_key = context.args[0].upper()
            
            # Validate project exists and user has access
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project '{project_key}' not found.")
                return

            # Check user access
            user_projects = await self.db.get_user_projects(user.user_id)
            if not any(p.key == project_key for p in user_projects):
                await self.send_error_message(
                    update, 
                    f"You don't have access to project '{project_key}'."
                )
                return

            # Set as default
            await self.db.set_user_default_project(user.user_id, project_key)

            success_message = self.formatter.format_success_message(
                f"Default project set to {project_key}",
                f"**{project.name}** is now your default project.\n\n"
                f"You can now create issues quickly by just typing:\n"
                f"`HIGH BUG Login button not working`"
            )

            await self.send_message(update, success_message)
            self.log_handler_end(update, "set_default_project")

        except Exception as e:
            await self.handle_error(update, e, "set_default_project")
            self.log_handler_end(update, "set_default_project", success=False)

    async def show_default_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /default command - show current default project."""
        self.log_handler_start(update, "show_default_project")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            default_project = await self.db.get_user_default_project(user.user_id)
            
            if not default_project:
                message = f"""
{EMOJI.get('PROJECT', '📁')} **Default Project**

You haven't set a default project yet.

**Set a default project to:**
• Create issues quickly by typing: `HIGH BUG Description`
• Skip project selection in wizards

Use `/setdefault <PROJECT_KEY>` or `/projects` to choose one.
                """
                await self.send_message(update, message)
                return

            # Get project statistics
            try:
                stats = await self.db.get_project_statistics(default_project.key)
                your_issues = stats.get('user_issues', 0)
            except Exception:
                your_issues = 0

            message = f"""
{EMOJI.get('PROJECT', '📁')} **Your Default Project**

🌟 **{default_project.key}: {default_project.name}**

**Status:** {'✅ Active' if default_project.is_active else '❌ Inactive'}
**Your Issues:** {your_issues}

**Quick Create Format:**
`[PRIORITY] [TYPE] Description`

**Examples:**
• `HIGH BUG Login not working`
• `MEDIUM TASK Update documentation`
• `LOWEST IMPROVEMENT Add dark mode`

**Change Default:** Use `/setdefault <PROJECT_KEY>`
            """

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📝 Create Issue", callback_data=f"create_issue_{default_project.key}"),
                    InlineKeyboardButton("📋 My Issues", callback_data="list_my_issues")
                ],
                [
                    InlineKeyboardButton("⭐ Change Default", callback_data="change_default_project"),
                    InlineKeyboardButton("📁 All Projects", callback_data="list_all_projects")
                ]
            ])

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "show_default_project")

        except Exception as e:
            await self.handle_error(update, e, "show_default_project")
            self.log_handler_end(update, "show_default_project", success=False)

    # =============================================================================
    # PROJECT SEARCH AND FILTERING
    # =============================================================================

    async def search_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /searchprojects command - search projects by name or description."""
        self.log_handler_start(update, "search_projects")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "**Usage:** `/searchprojects <query>`\n\nSearch projects by name, key, or description."
                )
                return

            query = ' '.join(context.args).lower()
            
            # Get user's projects
            user_projects = await self.db.get_user_projects(user.user_id)
            
            # Filter projects based on query
            matching_projects = []
            for project in user_projects:
                if (query in project.key.lower() or 
                    query in project.name.lower() or 
                    (project.description and query in project.description.lower())):
                    matching_projects.append(project)

            if not matching_projects:
                message = f"""
{EMOJI.get('SEARCH', '🔍')} **Project Search Results**

No projects found matching: **{query}**

**Tips:**
• Try different keywords
• Check spelling
• Use project key or name
                """
                await self.send_message(update, message)
                return

            # Format search results
            message_lines = [
                f"{EMOJI.get('SEARCH', '🔍')} **Project Search Results**",
                f"Found {len(matching_projects)} project(s) matching: **{query}**",
                ""
            ]

            for i, project in enumerate(matching_projects, 1):
                status_emoji = "✅" if project.is_active else "❌"
                project_line = f"{i}. {status_emoji} **{project.key}**: {project.name}"
                
                if not self.config.compact_mode and project.description:
                    description = self.formatter._truncate_text(project.description, 100)
                    project_line += f"\n   📄 {description}"
                
                message_lines.append(project_line)

            message = "\n".join(message_lines)
            await self.send_message(update, message)
            self.log_handler_end(update, "search_projects")

        except Exception as e:
            await self.handle_error(update, e, "search_projects")
            self.log_handler_end(update, "search_projects", success=False)

    # =============================================================================
    # CALLBACK QUERY HANDLERS
    # =============================================================================

    async def handle_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle project-related callback queries."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("setdefault_"):
            await self._handle_setdefault_callback(update, context)
        elif query.data.startswith("create_issue_"):
            await self._handle_create_issue_callback(update, context)
        elif query.data.startswith("list_issues_"):
            await self._handle_list_issues_callback(update, context)
        elif query.data.startswith("refresh_project_"):
            await self._handle_refresh_project_callback(update, context)
        elif query.data == "change_default_project":
            await self._handle_change_default_callback(update, context)
        elif query.data == "refresh_projects":
            await self.list_projects(update, context)
        elif query.data == "list_all_projects":
            await self.list_projects(update, context)
        elif query.data == "noop":
            # No operation - just acknowledge
            pass

    async def _handle_setdefault_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle set default project callback."""
        query = update.callback_query
        project_key = query.data.replace("setdefault_", "")

        user = await self.get_or_create_user(update)
        if not user:
            return

        try:
            # Verify project exists
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.edit_message(update, f"Project '{project_key}' not found.")
                return

            # Set as default
            await self.db.set_user_default_project(user.user_id, project_key)

            success_message = self.formatter.format_success_message(
                f"Default project updated",
                f"**{project.name}** is now your default project for quick issue creation."
            )

            await self.edit_message(update, success_message)

        except Exception as e:
            await self.edit_message(update, f"❌ Failed to set default project: {str(e)}")

    async def _handle_create_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle create issue callback."""
        query = update.callback_query
        project_key = query.data.replace("create_issue_", "")

        # Import here to avoid circular imports
        from .issue_handlers import IssueHandlers
        
        # Create issue in the specified project
        # This would typically redirect to the issue creation wizard
        # For now, we'll show a simple message
        await self.edit_message(
            update, 
            f"🚀 Starting issue creation for project **{project_key}**...\n\n"
            f"Use the `/create` command to create issues with the wizard."
        )

    async def _handle_list_issues_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle list issues callback."""
        query = update.callback_query
        project_key = query.data.replace("list_issues_", "")

        await self.edit_message(
            update,
            f"📋 Listing issues for project **{project_key}**...\n\n"
            f"Use `/listissues project={project_key}` to see all issues in this project."
        )

    async def _handle_refresh_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh project callback."""
        query = update.callback_query
        project_key = query.data.replace("refresh_project_", "")

        # Simulate project command
        context.args = [project_key]
        await self.get_project_details(update, context)

    async def _handle_change_default_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle change default project callback."""
        user = await self.get_or_create_user(update)
        if not user:
            return

        await self._show_project_selection_menu(update, user)

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    async def _show_project_selection_menu(self, update: Update, user: User) -> None:
        """Show project selection menu for setting default."""
        try:
            # Get user's projects
            projects = await self.db.get_user_projects(user.user_id)
            
            if not projects:
                message = f"""
{EMOJI.get('ERROR', '❌')} **No Projects Available**

You don't have access to any projects yet.
Contact your admin to add projects.
                """
                await self.send_message(update, message)
                return

            # Get current default
            current_default = await self.db.get_user_default_project(user.user_id)
            current_key = current_default.key if current_default else None

            message = f"""
{EMOJI.get('PROJECT', '📁')} **Set Default Project**

Current default: {f"**{current_key}**" if current_key else "None"}

Choose a new default project:
            """

            keyboard_buttons = []
            for project in projects:
                status_emoji = "✅" if project.is_active else "❌"
                default_indicator = " 🌟" if project.key == current_key else ""
                
                button_text = f"{status_emoji} {project.key}: {project.name}{default_indicator}"
                
                # Truncate long project names for button
                if len(button_text) > 60:
                    button_text = f"{status_emoji} {project.key}{default_indicator}"
                
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"setdefault_{project.key}"
                    )
                ])

            keyboard_buttons.append([
                InlineKeyboardButton("❌ Cancel", callback_data="noop")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            if hasattr(update, 'callback_query') and update.callback_query:
                await self.edit_message(update, message, reply_markup=keyboard)
            else:
                await self.send_message(update, message, reply_markup=keyboard)

        except Exception as e:
            error_msg = f"❌ Failed to load projects: {str(e)}"
            if hasattr(update, 'callback_query') and update.callback_query:
                await self.edit_message(update, error_msg)
            else:
                await self.send_message(update, error_msg)

    def _validate_project_key(self, project_key: str) -> bool:
        """Validate project key format."""
        return bool(re.match(r'^[A-Z][A-Z0-9_]*$', project_key))

    async def _get_project_summary_stats(self, project_key: str) -> Dict[str, int]:
        """Get summary statistics for a project."""
        try:
            stats = await self.db.get_project_statistics(project_key)
            return {
                'total_issues': stats.get('total_issues', 0),
                'open_issues': stats.get('open_issues', 0),
                'closed_issues': stats.get('closed_issues', 0)
            }
        except Exception:
            return {'total_issues': 0, 'open_issues': 0, 'closed_issues': 0}