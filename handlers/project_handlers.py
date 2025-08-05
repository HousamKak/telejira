"""
Project Handlers for Telegram Jira Bot.

This module contains all project-related functionality including project listing,
selection, default project management, and project search.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config.settings import BotConfig
from .base_handler import BaseHandler
from services.database import DatabaseService
from services.jira_service import JiraService
from models import Project, User
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)


class ProjectHandlers(BaseHandler):
    """
    Handler class for project-related commands and operations.
    
    Provides functionality for project management, selection, search,
    and default project configuration.
    """

    def __init__(
        self,
        config: BotConfig,
        database_service: DatabaseService,
        jira_service: JiraService,
        telegram_service: TelegramService,
    ) -> None:
        """Initialize project handlers with required services."""
        super().__init__(config,database_service, jira_service, telegram_service)

    # ---- Public Commands ----

    async def list_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        List all available projects for the user.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "list_projects")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get user's projects
            user_projects = await self.db.list_user_projects(user.user_id)
            
            if not user_projects:
                # If user has no projects, show all available projects
                all_projects = await self.db.list_projects()
                
                if not all_projects:
                    await self.send_message(
                        update,
                        "📭 No projects found. Contact an administrator to refresh projects from Jira."
                    )
                    return
                
                # Show selection menu for first-time setup
                await self._show_project_selection_menu(update, user)
                return
            
            # Get default project
            default_project = await self.db.get_user_default_project(user.user_id)
            
            # Build project list
            text_parts = [f"🏗 **Your Projects ({len(user_projects)})**\n"]
            
            for project in user_projects:
                # Add default indicator
                default_indicator = " ⭐" if default_project and project.key == default_project.key else ""
                
                # Format project info
                project_line = f"**{project.name}** (`{project.key}`){default_indicator}"
                if project.description:
                    desc = project.description[:80] + "..." if len(project.description) > 80 else project.description
                    project_line += f"\n_{desc}_"
                
                text_parts.append(project_line)
            
            if default_project:
                text_parts.append(f"\n⭐ Default project: **{default_project.name}**")
            else:
                text_parts.append("\n💡 Use `/setdefault` to set your default project")
            
            # Add action buttons
            keyboard = [
                [
                    InlineKeyboardButton("🔍 Search Projects", callback_data="project_search"),
                    InlineKeyboardButton("⚙️ Change Default", callback_data="project_change_default"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            full_text = "\n\n".join(text_parts)
            await self.send_message(update, full_text, reply_markup=reply_markup)
            self.log_handler_end(update, "list_projects", success=True)
            
        except Exception as e:
            logger.error(f"Error in list_projects: {e}")
            await self.handle_database_error(update, e, "listing projects")
            self.log_handler_end(update, "list_projects", success=False)

    async def get_project_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Get detailed information about a specific project.
        
        Usage: /project <project_key>
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "get_project_details")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            args = self._extract_command_args(update)
            
            if len(args) != 1:
                help_text = (
                    "**Usage:** `/project <project_key>`\n\n"
                    "**Example:** `/project DEMO`\n\n"
                    "Get detailed information about a specific project."
                )
                await self.send_message(update, help_text)
                return

            project_key = args[0].upper()
            
            if not self._validate_project_key(project_key):
                await self.send_error_message(
                    update,
                    "Invalid project key format. Project keys should be 2-10 uppercase letters."
                )
                return
            
            # Get project from database
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(
                    update,
                    f"Project '{project_key}' not found. Use `/projects` to see available projects."
                )
                return
            
            # Get project statistics
            project_stats = await self._get_project_summary_stats(project_key)
            
            # Build detailed project view
            details_text = project.get_formatted_summary()
            
            # Add statistics
            if project_stats:
                details_text += f"\n\n📊 **Statistics:**"
                if project_stats.get('user_count', 0) > 0:
                    details_text += f"\n👥 Users: {project_stats['user_count']}"
                if project_stats.get('issue_count', 0) > 0:
                    details_text += f"\n🎯 Issues: {project_stats['issue_count']}"
            
            # Add action buttons
            keyboard = [
                [
                    InlineKeyboardButton("🎯 Create Issue", callback_data=f"project_create_issue_{project_key}"),
                    InlineKeyboardButton("📋 List Issues", callback_data=f"project_list_issues_{project_key}"),
                ],
                [
                    InlineKeyboardButton("⭐ Set as Default", callback_data=f"project_setdefault_{project_key}"),
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"project_refresh_{project_key}"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.send_message(update, details_text, reply_markup=reply_markup)
            self.log_handler_end(update, "get_project_details", success=True)
            
        except Exception as e:
            logger.error(f"Error in get_project_details: {e}")
            await self.handle_database_error(update, e, "getting project details")
            self.log_handler_end(update, "get_project_details", success=False)

    async def set_default_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Set user's default project for issue creation.
        
        Usage: /setdefault <project_key>
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "set_default_project")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            args = self._extract_command_args(update)
            
            if len(args) == 0:
                # Show project selection menu
                await self._show_project_selection_menu(update, user)
                return
            
            if len(args) != 1:
                help_text = (
                    "**Usage:** `/setdefault <project_key>`\n\n"
                    "**Example:** `/setdefault DEMO`\n\n"
                    "Or use `/setdefault` without arguments to choose from a menu."
                )
                await self.send_message(update, help_text)
                return

            project_key = args[0].upper()
            
            if not self._validate_project_key(project_key):
                await self.send_error_message(
                    update,
                    "Invalid project key format. Project keys should be 2-10 uppercase letters."
                )
                return
            
            # Verify project exists
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(
                    update,
                    f"Project '{project_key}' not found. Use `/projects` to see available projects."
                )
                return
            
            # Set as default
            await self.db.set_user_default_project(user.user_id, project_key)
            
            # Log the action
            await self.db.log_user_action(user.user_id, "set_default_project", {
                "project_key": project_key,
                "project_name": project.name,
            })
            
            success_text = (
                f"✅ **Default Project Set**\n\n"
                f"Your default project is now:\n"
                f"**{project.name}** (`{project.key}`)\n\n"
                f"This project will be pre-selected when creating new issues."
            )
            
            await self.send_message(update, success_text)
            self.log_handler_end(update, "set_default_project", success=True)
            
        except Exception as e:
            logger.error(f"Error in set_default_project: {e}")
            await self.handle_database_error(update, e, "setting default project")
            self.log_handler_end(update, "set_default_project", success=False)

    async def show_default_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Show user's current default project.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "show_default_project")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            default_project = await self.db.get_user_default_project(user.user_id)
            
            if not default_project:
                text = (
                    "🤷 **No Default Project Set**\n\n"
                    "You haven't set a default project yet.\n\n"
                    "Use `/setdefault <project_key>` to set one, or use `/projects` to see available projects."
                )
                
                keyboard = [
                    [InlineKeyboardButton("🏗 Choose Project", callback_data="project_change_default")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await self.send_message(update, text, reply_markup=reply_markup)
            else:
                text = (
                    f"⭐ **Your Default Project**\n\n"
                    f"{default_project.get_formatted_summary()}\n\n"
                    f"This project is pre-selected when creating new issues."
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("🎯 Create Issue", callback_data=f"project_create_issue_{default_project.key}"),
                        InlineKeyboardButton("🔄 Change Default", callback_data="project_change_default"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await self.send_message(update, text, reply_markup=reply_markup)
            
            self.log_handler_end(update, "show_default_project", success=True)
            
        except Exception as e:
            logger.error(f"Error in show_default_project: {e}")
            await self.handle_database_error(update, e, "showing default project")
            self.log_handler_end(update, "show_default_project", success=False)

    async def search_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Search for projects by name or key.
        
        Usage: /searchprojects <search_term>
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "search_projects")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            args = self._extract_command_args(update)
            
            if len(args) == 0:
                help_text = (
                    "**Usage:** `/searchprojects <search_term>`\n\n"
                    "**Examples:**\n"
                    "• `/searchprojects demo` - Search for projects containing 'demo'\n"
                    "• `/searchprojects web` - Search for projects containing 'web'\n\n"
                    "Search is case-insensitive and matches project names and keys."
                )
                await self.send_message(update, help_text)
                return

            search_term = " ".join(args).lower()
            
            # Get all projects and filter
            all_projects = await self.db.list_projects()
            
            if not all_projects:
                await self.send_Message(
                    update,
                    "📭 No projects found. Contact an administrator to refresh projects from Jira."
                )
                return
            
            # Filter projects by search term
            matching_projects = []
            for project in all_projects:
                if (search_term in project.name.lower() or 
                    search_term in project.key.lower() or
                    search_term in project.description.lower()):
                    matching_projects.append(project)
            
            if not matching_projects:
                await self.send_message(
                    update,
                    f"🔍 No projects found matching '{search_term}'\n\n"
                    f"Try a different search term or use `/projects` to see all available projects."
                )
                return
            
            # Build results text
            text_parts = [f"🔍 **Search Results for '{search_term}'** ({len(matching_projects)} found)\n"]
            
            for project in matching_projects[:10]:  # Limit to 10 results
                project_summary = f"**{project.name}** (`{project.key}`)"
                if project.description:
                    desc = project.description[:100] + "..." if len(project.description) > 100 else project.description
                    project_summary += f"\n_{desc}_"
                text_parts.append(project_summary)
            
            if len(matching_projects) > 10:
                text_parts.append(f"\n... and {len(matching_projects) - 10} more projects")
                text_parts.append("Use a more specific search term to narrow results.")
            
            full_text = "\n\n".join(text_parts)
            await self.send_message(update, full_text)
            self.log_handler_end(update, "search_projects", success=True)
            
        except Exception as e:
            logger.error(f"Error in search_projects: {e}")
            await self.handle_database_error(update, e, "searching projects")
            self.log_handler_end(update, "search_projects", success=False)

    # ---- Callback Handler ----

    async def handle_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle project-related callback queries.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("project_"):
            return

        await self._answer_callback_query(update)
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            if callback_data == "project_search":
                await self.edit_message(
                    update,
                    "🔍 Use the command `/searchprojects <search_term>` to search for projects."
                )
            elif callback_data == "project_change_default":
                await self._handle_change_default_callback(update, context)
            elif callback_data.startswith("project_setdefault_"):
                await self._handle_setdefault_callback(update, context)
            elif callback_data.startswith("project_create_issue_"):
                await self._handle_create_issue_callback(update, context)
            elif callback_data.startswith("project_list_issues_"):
                await self._handle_list_issues_callback(update, context)
            elif callback_data.startswith("project_refresh_"):
                await self._handle_refresh_project_callback(update, context)
            
        except Exception as e:
            logger.error(f"Error in project callback {callback_data}: {e}")
            await self.send_error_message(update, "An error occurred processing your request")

    # ---- Private Helper Methods ----

    async def _show_project_selection_menu(self, update: Update, user: User) -> None:
        """Show project selection menu for setting default project."""
        try:
            projects = await self.db.list_projects()
            
            if not projects:
                await self.send_message(
                    update,
                    "📭 No projects available. Contact an administrator to sync projects from Jira."
                )
                return
            
            # Create keyboard with projects (up to 10)
            keyboard = []
            for project in projects[:10]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{project.name} ({project.key})",
                        callback_data=f"project_setdefault_{project.key}"
                    )
                ])
            
            # Add navigation if more than 10 projects
            if len(projects) > 10:
                keyboard.append([
                    InlineKeyboardButton("📄 Show More", callback_data="project_show_more")
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                f"🏗 **Choose Your Default Project**\n\n"
                f"Select a project to set as your default.\n"
                f"This project will be pre-selected when creating new issues.\n\n"
                f"Showing {min(len(projects), 10)} of {len(projects)} projects:"
            )
            
            await self.send_message(update, text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error showing project selection menu: {e}")
            await self.send_error_message(update, "Failed to load project selection menu")

    def _validate_project_key(self, project_key: str) -> bool:
        """
        Validate project key format.
        
        Args:
            project_key: Project key to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(project_key, str):
            return False
        
        # Project keys should be 2-10 uppercase letters, may contain numbers
        pattern = r'^[A-Z][A-Z0-9]{1,9}$'
        return bool(re.match(pattern, project_key))

    async def _get_project_summary_stats(self, project_key: str) -> Dict[str, Any]:
        """Get summary statistics for a project."""
        try:
            stats = await self.db.get_project_statistics(project_key)
            return stats
        except Exception as e:
            logger.warning(f"Failed to get project stats for {project_key}: {e}")
            return {}

    # ---- Callback Handlers ----

    async def _handle_setdefault_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle set default project callback."""
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("project_setdefault_"):
            return
        
        try:
            project_key = callback_data.replace("project_setdefault_", "")
            
            user = await self.enforce_user_access(update)
            if not user:
                return
            
            # Verify project exists
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.edit_message(update, f"❌ Project '{project_key}' not found.")
                return
            
            # Set as default
            await self.db.set_user_default_project(user.user_id, project_key)
            
            # Log the action
            await self.db.log_user_action(user.user_id, "set_default_project", {
                "project_key": project_key,
                "project_name": project.name,
            })
            
            success_text = (
                f"✅ **Default Project Set**\n\n"
                f"**{project.name}** (`{project.key}`) is now your default project.\n\n"
                f"This project will be pre-selected when creating new issues."
            )
            
            await self.edit_message(update, success_text)
            
        except Exception as e:
            logger.error(f"Error setting default project: {e}")
            await self.edit_message(update, "❌ Failed to set default project.")

    async def _handle_create_issue_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle create issue callback."""
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("project_create_issue_"):
            return
        
        project_key = callback_data.replace("project_create_issue_", "")
        
        # Store project key in context for issue creation
        if context.user_data is not None:
            context.user_data['selected_project_key'] = project_key
        
        await self.edit_message(
            update,
            f"🎯 Use `/create` to create an issue in project **{project_key}**, "
            f"or `/quick` for the issue creation wizard."
        )

    async def _handle_list_issues_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle list issues callback."""
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("project_list_issues_"):
            return
        
        project_key = callback_data.replace("project_list_issues_", "")
        
        await self.edit_message(
            update,
            f"📋 Use `/listissues project = {project_key}` to see issues in this project."
        )

    async def _handle_refresh_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle refresh project callback."""
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("project_refresh_"):
            return
        
        try:
            project_key = callback_data.replace("project_refresh_", "")
            
            # Get updated project info from Jira
            jira_project = await self.jira.get_project(project_key)
            
            # Update in database
            await self.db.update_project(
                project_key=project_key,
                name=jira_project.name,
                description=jira_project.description,
                url=jira_project.url,
                project_type=jira_project.project_type,
                lead=jira_project.lead,
                avatar_url=jira_project.avatar_url,
            )
            
            # Get updated project stats
            project_stats = await self._get_project_summary_stats(project_key)
            
            # Build updated project view
            updated_text = jira_project.get_formatted_summary()
            
            if project_stats:
                updated_text += f"\n\n📊 **Statistics:**"
                if project_stats.get('user_count', 0) > 0:
                    updated_text += f"\n👥 Users: {project_stats['user_count']}"
                if project_stats.get('issue_count', 0) > 0:
                    updated_text += f"\n🎯 Issues: {project_stats['issue_count']}"
            
            updated_text += "\n\n🔄 _Project information refreshed from Jira_"
            
            # Recreate action buttons
            keyboard = [
                [
                    InlineKeyboardButton("🎯 Create Issue", callback_data=f"project_create_issue_{project_key}"),
                    InlineKeyboardButton("📋 List Issues", callback_data=f"project_list_issues_{project_key}"),
                ],
                [
                    InlineKeyboardButton("⭐ Set as Default", callback_data=f"project_setdefault_{project_key}"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.edit_message(update, updated_text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error refreshing project: {e}")
            await self.edit_message(update, "❌ Failed to refresh project information.")

    async def _handle_change_default_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle change default project callback."""
        user = await self.enforce_user_access(update)
        if not user:
            return
        
        await self._show_project_selection_menu(update, user)