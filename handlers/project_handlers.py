#!/usr/bin/env python3
"""
Project handlers for the Telegram-Jira bot.

Handles project-related commands including listing projects, setting defaults,
and project information display.
"""

import logging
from typing import Optional, List, Dict, Any, Union

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
        """Handle /projects command - list all available projects."""
        self.log_handler_start(update, "list_projects")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get all active projects
            projects = await self.db.get_all_active_projects()
            
            if not projects:
                message = self.formatter.format_warning_message(
                    "No projects available",
                    "Contact an administrator to add projects to the bot."
                )
                await self.send_message(update, message)
                return

            # Get user's default project
            default_project_key = await self.db.get_user_default_project(user.user_id)

            # Format project list with default indication
            message_lines = [
                f"{EMOJI.get('PROJECTS', '📋')} **Available Projects** ({len(projects)} total)",
                ""
            ]

            for i, project in enumerate(projects, 1):
                # Project status emoji
                status_emoji = "✅" if project.is_active else "❌"
                
                # Default project indicator
                default_indicator = " 🌟" if project.key == default_project_key else ""
                
                # Project line
                project_line = f"{i}. {status_emoji} **{project.key}**: {project.name}{default_indicator}"
                
                # Add issue count and description
                if not self.config.compact_mode:
                    if project.issue_count > 0:
                        project_line += f" ({project.issue_count} issues)"
                    
                    if project.description:
                        description = self.formatter._truncate_text(project.description, 80)
                        project_line += f"\n   📄 {description}"
                
                message_lines.append(project_line)

            # Add help text
            message_lines.extend([
                "",
                "🌟 = Your default project",
                "",
                "**Commands:**",
                "• `/setdefault <KEY>` - Set default project",
                "• `/project <KEY>` - View project details",
                "• `/create` - Create new issue"
            ])

            message = "\n".join(message_lines)
            
            # Add inline keyboard for quick actions
            if len(projects) <= 10:  # Only show keyboard for reasonable number of projects
                keyboard_buttons = []
                
                # Add set default buttons for top projects
                for project in projects[:5]:
                    button_text = f"Set {project.key} as Default"
                    if project.key == default_project_key:
                        button_text = f"✅ {project.key} (Current)"
                    
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            button_text,
                            callback_data=f"setdefault_{project.key}"
                        )
                    ])
                
                keyboard = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
            else:
                keyboard = None

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "list_projects")

        except Exception as e:
            await self.handle_error(update, e, "list_projects")
            self.log_handler_end(update, "list_projects", success=False)

    async def show_project_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /project command - show detailed project information.
        
        Usage: /project <KEY>
        """
        self.log_handler_start(update, "show_project_details")
        
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

            # Try to get updated info from Jira
            try:
                jira_project = await self.jira.get_project_by_key(project_key)
                if jira_project:
                    # Update project with latest Jira data
                    project.update_from_jira(jira_project.to_dict())
                    
                    # Update in database
                    await self.db.update_project(
                        key=project.key,
                        name=project.name,
                        description=project.description,
                        url=project.url,
                        is_active=project.is_active
                    )
            except JiraAPIError:
                # Continue with database info if Jira is unavailable
                pass

            # Format detailed project information
            message = self.formatter.format_project(project, include_details=True)
            
            # Add additional statistics
            try:
                # Get issue statistics for this project
                issue_stats = await self._get_project_issue_statistics(project.key)
                
                if issue_stats:
                    stats_lines = [
                        "",
                        "📊 **Issue Statistics:**"
                    ]
                    
                    for status, count in issue_stats.items():
                        if count > 0:
                            stats_lines.append(f"• {status}: {count}")
                    
                    message += "\n" + "\n".join(stats_lines)
                    
            except Exception as e:
                self.logger.warning(f"Failed to get issue statistics for {project_key}: {e}")

            # Check if this is user's default project
            default_project_key = await self.db.get_user_default_project(user.user_id)
            is_default = (project_key == default_project_key)

            # Add action buttons
            keyboard_buttons = []
            
            if not is_default:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        "🌟 Set as Default",
                        callback_data=f"setdefault_{project.key}"
                    )
                ])
            else:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        "✅ Current Default",
                        callback_data="noop"
                    )
                ])
            
            keyboard_buttons.extend([
                [InlineKeyboardButton(
                    "📝 Create Issue",
                    callback_data=f"create_issue_{project.key}"
                )],
                [InlineKeyboardButton(
                    "📋 View Issues",
                    callback_data=f"list_issues_{project.key}"
                )],
                [InlineKeyboardButton(
                    "🔄 Refresh from Jira",
                    callback_data=f"refresh_project_{project.key}"
                )]
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "show_project_details")

        except Exception as e:
            await self.handle_error(update, e, "show_project_details")
            self.log_handler_end(update, "show_project_details", success=False)

    # =============================================================================
    # DEFAULT PROJECT MANAGEMENT
    # =============================================================================

    async def set_default_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setdefault command - set user's default project.
        
        Usage: /setdefault <KEY>
        """
        self.log_handler_start(update, "set_default_project")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if not context.args:
                # Show available projects for selection
                projects = await self.db.get_all_active_projects()
                
                if not projects:
                    await self.send_message(update, INFO_MESSAGES['NO_PROJECTS'])
                    return

                message = f"""
{EMOJI.get('DEFAULT', '🌟')} **Set Default Project**

Choose a project to set as your default. This project will be used automatically when creating issues.

**Available Projects:**
                """

                keyboard_buttons = []
                for project in projects[:10]:  # Limit to 10 projects
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            f"{project.key}: {project.name[:30]}",
                            callback_data=f"setdefault_{project.key}"
                        )
                    ])

                keyboard = InlineKeyboardMarkup(keyboard_buttons)
                
                await self.send_message(update, message, reply_markup=keyboard)
                return

            project_key = context.args[0].upper()
            
            # Validate project key format
            validation_result = self.validator.validate_project_key(project_key)
            if not validation_result.is_valid:
                await self.handle_validation_error(update, validation_result, "project key")
                return

            # Check if project exists
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project '{project_key}' not found.")
                return

            if not project.is_active:
                await self.send_error_message(update, f"Project '{project_key}' is not active.")
                return

            # Set default project
            await self.db.set_user_default_project(user.user_id, project_key)

            # Success message
            success_message = self.formatter.format_success_message(
                f"Default project set to '{project_key}'",
                f"**{project.key}**: {project.name}\n\nThis project will be used automatically when creating issues."
            )

            await self.send_message(update, success_message)
            self.log_handler_end(update, "set_default_project")

        except Exception as e:
            await self.handle_error(update, e, "set_default_project")
            self.log_handler_end(update, "set_default_project", success=False)

    async def show_default_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /default command - show user's current default project."""
        self.log_handler_start(update, "show_default_project")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            default_project_key = await self.db.get_user_default_project(user.user_id)
            
            if not default_project_key:
                message = self.formatter.format_warning_message(
                    "No default project set",
                    "Use `/setdefault <PROJECT_KEY>` to set your default project, or `/projects` to see available projects."
                )
                await self.send_message(update, message)
                return

            # Get project details
            project = await self.db.get_project_by_key(default_project_key)
            if not project:
                # Default project no longer exists, clear it
                await self.db.clear_user_default_project(user.user_id)
                await self.send_error_message(update, "Your default project no longer exists. Please set a new one.")
                return

            # Format current default project info
            message = f"""
{EMOJI.get('DEFAULT', '🌟')} **Your Default Project**

{self.formatter.format_project(project, include_details=True)}

This project will be used automatically when creating issues without specifying a project.

**Change Default:**
Use `/setdefault <KEY>` or click the button below.
            """

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔄 Change Default",
                    callback_data="change_default_project"
                )],
                [InlineKeyboardButton(
                    "📝 Create Issue",
                    callback_data=f"create_issue_{project.key}"
                )]
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
        """Handle /searchprojects command - search projects by name or key.
        
        Usage: /searchprojects <query>
        """
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
            
            # Get all projects and filter
            all_projects = await self.db.get_all_projects()
            
            matching_projects = []
            for project in all_projects:
                if (query in project.key.lower() or 
                    query in project.name.lower() or 
                    query in project.description.lower()):
                    matching_projects.append(project)

            if not matching_projects:
                message = f"""
{EMOJI.get('SEARCH', '🔍')} **Project Search Results**

No projects found matching: **{query}**

Try a different search term or use `/projects` to see all available projects.
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

            # Set default project
            await self.db.set_user_default_project(user.user_id, project_key)

            success_message = self.formatter.format_success_message(
                f"Default project set to '{project_key}'",
                f"**{project.name}** is now your default project."
            )

            await self.edit_message(update, success_message)

        except DatabaseError as e:
            await self.edit_message(
                update,
                self.formatter.format_error_message(
                    "Database Error",
                    f"Failed to set default project: {str(e)}"
                )
            )

    async def _handle_create_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle create issue callback."""
        query = update.callback_query
        project_key = query.data.replace("create_issue_", "")

        # Start issue creation wizard with pre-selected project
        from .wizard_handlers import WizardHandlers
        wizard_handler = WizardHandlers(
            config=self.config,
            database=self.db,
            jira_service=self.jira,
            telegram_service=self.telegram
        )

        # Store project in context and start wizard
        context.user_data['selected_project_key'] = project_key
        await wizard_handler.quick_command(update, context)

    async def _handle_list_issues_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle list issues callback."""
        query = update.callback_query
        project_key = query.data.replace("list_issues_", "")

        # Redirect to issue handlers
        from .issue_handlers import IssueHandlers
        issue_handler = IssueHandlers(
            config=self.config,
            database=self.db,
            jira_service=self.jira,
            telegram_service=self.telegram
        )

        # Simulate command with project filter
        context.args = ['project=' + project_key]
        await issue_handler.list_all_issues(update, context)

    async def _handle_refresh_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh project from Jira callback."""
        query = update.callback_query
        project_key = query.data.replace("refresh_project_", "")

        try:
            # Get latest data from Jira
            jira_project = await self.jira.get_project_by_key(project_key)
            if not jira_project:
                await self.edit_message(update, f"Project '{project_key}' not found in Jira.")
                return

            # Update in database
            await self.db.update_project(
                key=jira_project.key,
                name=jira_project.name,
                description=jira_project.description,
                url=jira_project.url,
                is_active=jira_project.is_active
            )

            success_message = self.formatter.format_success_message(
                f"Project '{project_key}' refreshed from Jira",
                self.formatter.format_project(jira_project, include_details=True)
            )

            await self.edit_message(update, success_message)

        except JiraAPIError as e:
            await self.edit_message(
                update,
                self.formatter.format_error_message(
                    "Jira API Error",
                    f"Failed to refresh project: {str(e)}"
                )
            )

    async def _handle_change_default_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle change default project callback."""
        # Show project selection for changing default
        projects = await self.db.get_all_active_projects()
        
        if not projects:
            await self.edit_message(update, INFO_MESSAGES['NO_PROJECTS'])
            return

        message = f"""
{EMOJI.get('DEFAULT', '🌟')} **Choose New Default Project**

Select a project to set as your default:
        """

        keyboard_buttons = []
        for project in projects[:10]:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{project.key}: {project.name[:30]}",
                    callback_data=f"setdefault_{project.key}"
                )
            ])

        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await self.edit_message(update, message, reply_markup=keyboard)

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    async def _get_project_issue_statistics(self, project_key: str) -> Dict[str, int]:
        """Get issue statistics for a project.
        
        Args:
            project_key: Project key
            
        Returns:
            Dictionary of status -> count
        """
        try:
            # This would ideally query Jira for real-time stats
            # For now, return database stats
            stats = await self.db.get_project_issue_statistics(project_key)
            return stats
        except Exception as e:
            self.logger.warning(f"Failed to get issue statistics for {project_key}: {e}")
            return {}

    def _format_project_summary(self, project: Project, is_default: bool = False) -> str:
        """Format a single project for summary display.
        
        Args:
            project: Project to format
            is_default: Whether this is the user's default project
            
        Returns:
            Formatted project summary string
        """
        status_emoji = "✅" if project.is_active else "❌"
        default_indicator = " 🌟" if is_default else ""
        
        summary = f"{status_emoji} **{project.key}**: {project.name}{default_indicator}"
        
        if not self.config.compact_mode:
            if project.issue_count > 0:
                summary += f" ({project.issue_count} issues)"
            
            if project.description:
                description = self.formatter._truncate_text(project.description, 60)
                summary += f"\n   📄 {description}"
        
        return summary

    async def _validate_project_access(self, user: User, project: Project) -> bool:
        """Validate if user can access a project.
        
        Args:
            user: User requesting access
            project: Project to access
            
        Returns:
            True if access is allowed
        """
        # Basic validation - can be extended with more complex logic
        if not project.is_active and user.role == UserRole.USER:
            return False
        
        return True