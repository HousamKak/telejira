#!/usr/bin/env python3
"""
Project handlers for the Telegram-Jira bot.

Handles project-related commands and operations.
"""

from typing import Optional, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .base_handler import BaseHandler
from ..models.project import Project
from ..models.user import User, UserPreferences
from ..models.enums import UserRole, ErrorType
from ..services.database import DatabaseError
from ..services.jira_service import JiraAPIError
from ..utils.constants import EMOJI
from ..utils.validators import ValidationResult


class ProjectHandler(BaseHandler):
    """Handles project-related operations."""

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "ProjectHandler"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to project operations."""
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        else:
            await self.send_error_message(update, f"Unexpected error: {str(error)}")

    # Command handlers
    async def projects_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /projects command - list all available projects."""
        self.log_handler_start(update, "projects_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Get projects and user preferences
            projects = await self.db.get_projects(active_only=True)
            preferences = await self.get_user_preferences(user.user_id)
            default_project = preferences.default_project_key if preferences else None

            if not projects:
                await self.send_info_message(
                    update,
                    f"{EMOJI['INFO']} No projects available yet.\n"
                    "Ask an admin to add projects using `/addproject`."
                )
                self.log_handler_end(update, "projects_command")
                return

            # Format project list
            text = self.telegram.formatter.format_project_list(
                projects,
                title="Available Projects",
                user_default=default_project,
                show_details=not self.telegram.compact_mode
            )

            # Create keyboard with options
            keyboard = []
            if not default_project:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{EMOJI['SETTINGS']} Set Default Project",
                        callback_data="projects_set_default"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{EMOJI['REFRESH']} Refresh",
                    callback_data="projects_refresh"
                )
            ])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await self.send_message(update, text, reply_markup)

            self.log_user_action(user, "list_projects", {"project_count": len(projects)})
            self.log_handler_end(update, "projects_command")

        except Exception as e:
            await self.handle_error(update, e, "projects_command")
            self.log_handler_end(update, "projects_command", success=False)

    async def addproject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /addproject command - add a new project (admin only)."""
        self.log_handler_start(update, "addproject_command")
        
        user = await self.enforce_admin(update)
        if not user:
            return

        args = self.parse_command_args(update, 2)  # At least key and name
        if not args:
            await self._send_addproject_usage(update)
            self.log_handler_end(update, "addproject_command")
            return

        project_key = args[0].upper()
        project_name = args[1]
        project_description = " ".join(args[2:]) if len(args) > 2 else ""

        try:
            # Validate inputs
            key_validation = self.validate_project_key(project_key)
            if not key_validation.is_valid:
                await self.handle_validation_error(update, key_validation, "project key")
                self.log_handler_end(update, "addproject_command", success=False)
                return

            name_validation = self.validate_project_name(project_name)
            if not name_validation.is_valid:
                await self.handle_validation_error(update, name_validation, "project name")
                self.log_handler_end(update, "addproject_command", success=False)
                return

            # Check if project already exists
            existing_project = await self.db.get_project_by_key(project_key)
            if existing_project:
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` already exists.",
                    ErrorType.VALIDATION_ERROR
                )
                self.log_handler_end(update, "addproject_command", success=False)
                return

            # Verify project exists in Jira
            jira_exists = await self.jira.verify_project(project_key)
            if not jira_exists:
                await self._handle_jira_project_not_found(update, project_key, project_name, project_description)
                self.log_handler_end(update, "addproject_command")
                return

            # Create and add project
            await self._create_project(update, project_key, project_name, project_description, user)
            self.log_handler_end(update, "addproject_command")

        except Exception as e:
            await self.handle_error(update, e, "addproject_command")
            self.log_handler_end(update, "addproject_command", success=False)

    async def editproject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /editproject command - edit an existing project (admin only)."""
        self.log_handler_start(update, "editproject_command")
        
        user = await self.enforce_admin(update)
        if not user:
            return

        args = self.parse_command_args(update, 1)  # Just project key
        if not args:
            await self._send_editproject_usage(update)
            self.log_handler_end(update, "editproject_command")
            return

        project_key = args[0].upper()

        try:
            # Get existing project
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` not found.",
                    ErrorType.NOT_FOUND_ERROR
                )
                self.log_handler_end(update, "editproject_command", success=False)
                return

            # Show edit options
            await self._show_project_edit_options(update, project)
            self.log_handler_end(update, "editproject_command")

        except Exception as e:
            await self.handle_error(update, e, "editproject_command")
            self.log_handler_end(update, "editproject_command", success=False)

    async def deleteproject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /deleteproject command - delete a project (admin only)."""
        self.log_handler_start(update, "deleteproject_command")
        
        user = await self.enforce_admin(update)
        if not user:
            return

        args = self.parse_command_args(update, 1)  # Just project key
        if not args:
            await self._send_deleteproject_usage(update)
            self.log_handler_end(update, "deleteproject_command")
            return

        project_key = args[0].upper()

        try:
            # Get existing project
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` not found.",
                    ErrorType.NOT_FOUND_ERROR
                )
                self.log_handler_end(update, "deleteproject_command", success=False)
                return

            # Check if project can be deleted
            warning = project.get_deletion_warning()
            if warning:
                await self._show_project_delete_confirmation(update, project, warning)
            else:
                await self._show_project_delete_confirmation(update, project)
            
            self.log_handler_end(update, "deleteproject_command")

        except Exception as e:
            await self.handle_error(update, e, "deleteproject_command")
            self.log_handler_end(update, "deleteproject_command", success=False)

    async def setdefault_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setdefault command - set user's default project."""
        self.log_handler_start(update, "setdefault_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        args = self.parse_command_args(update, 0)  # Optional project key
        
        try:
            if args and len(args) > 0:
                # Set specific project as default
                project_key = args[0].upper()
                await self._set_user_default_project(update, user, project_key)
            else:
                # Show project selection
                await self._show_default_project_selection(update, user)
            
            self.log_handler_end(update, "setdefault_command")

        except Exception as e:
            await self.handle_error(update, e, "setdefault_command")
            self.log_handler_end(update, "setdefault_command", success=False)

    # Callback handlers
    async def handle_projects_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle project-related callbacks."""
        callback_data = self.extract_callback_data(update)
        if not callback_data:
            return

        parts = self.parse_callback_data(callback_data)
        if len(parts) < 2:
            return

        action = parts[1]  # projects_<action>

        if action == "refresh":
            await self.projects_command(update, context)
        elif action == "set_default":
            user = await self.enforce_user_access(update)
            if user:
                await self._show_default_project_selection(update, user)
        elif action.startswith("default_"):
            project_key = action.replace("default_", "")
            user = await self.enforce_user_access(update)
            if user:
                await self._set_user_default_project(update, user, project_key)
        elif action.startswith("edit_"):
            project_key = action.replace("edit_", "")
            await self._handle_project_edit_callback(update, project_key, parts[2:])
        elif action.startswith("delete_"):
            project_key = action.replace("delete_", "")
            await self._handle_project_delete_callback(update, project_key, parts[2:])

    # Private helper methods
    async def _send_addproject_usage(self, update: Update) -> None:
        """Send usage instructions for addproject command."""
        text = f"{EMOJI['INFO']} **Add Project Usage**\n\n"
        text += "**Syntax:** `/addproject <KEY> <Name> [Description]`\n\n"
        text += "**Examples:**\n"
        text += "• `/addproject WEBAPP Web Application Main web app project`\n"
        text += "• `/addproject API Backend API REST API backend`\n\n"
        text += "**Notes:**\n"
        text += "• Project key must be uppercase (2-10 characters)\n"
        text += "• Project must exist in Jira\n"
        text += "• Description is optional"
        
        await self.send_message(update, text)

    async def _send_editproject_usage(self, update: Update) -> None:
        """Send usage instructions for editproject command."""
        text = f"{EMOJI['INFO']} **Edit Project Usage**\n\n"
        text += "**Syntax:** `/editproject <KEY>`\n\n"
        text += "**Example:** `/editproject WEBAPP`\n\n"
        text += "This will show editing options for the specified project."
        
        await self.send_message(update, text)

    async def _send_deleteproject_usage(self, update: Update) -> None:
        """Send usage instructions for deleteproject command."""
        text = f"{EMOJI['INFO']} **Delete Project Usage**\n\n"
        text += "**Syntax:** `/deleteproject <KEY>`\n\n"
        text += "**Example:** `/deleteproject WEBAPP`\n\n"
        text += f"{EMOJI['WARNING']} **Warning:** This will permanently delete the project!"
        
        await self.send_message(update, text)

    async def _handle_jira_project_not_found(
        self,
        update: Update,
        project_key: str,
        project_name: str,
        project_description: str
    ) -> None:
        """Handle case where project is not found in Jira."""
        text = f"{EMOJI['WARNING']} **Jira Project Not Found**\n\n"
        text += f"Project `{project_key}` was not found in Jira.\n\n"
        text += "This might mean:\n"
        text += "• Project doesn't exist in Jira\n"
        text += "• You don't have access to it\n"
        text += "• Project key is misspelled\n\n"
        text += "Do you want to add it anyway?"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['SUCCESS']} Add Anyway",
                    callback_data=f"projects_force_add_{project_key}_{project_name}_{project_description}"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="projects_cancel_add"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _create_project(
        self,
        update: Update,
        project_key: str,
        project_name: str,
        project_description: str,
        user: User
    ) -> None:
        """Create a new project."""
        try:
            # Try to get additional project info from Jira
            jira_project = await self.jira.get_project(project_key)
            
            if jira_project:
                # Use Jira project data
                project = jira_project
            else:
                # Create project with provided data
                project = Project(
                    key=project_key,
                    name=project_name,
                    description=project_description
                )

            # Add to database
            await self.db.add_project(project)

            # Send success message
            text = f"{EMOJI['SUCCESS']} **Project Added Successfully!**\n\n"
            text += f"**Key:** `{project.key}`\n"
            text += f"**Name:** {project.name}\n"
            text += f"**Description:** {project.description or 'None'}\n"
            
            if project.url:
                text += f"**Jira URL:** [View Project]({project.url})\n"
            
            text += f"\nUsers can now create issues in this project!"

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{EMOJI['PROJECTS']} View All Projects",
                        callback_data="projects_refresh"
                    )
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await self.send_message(update, text, reply_markup)

            self.log_user_action(
                user,
                "create_project",
                {"project_key": project_key, "project_name": project_name}
            )

        except DatabaseError as e:
            if "already exists" in str(e):
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` already exists.",
                    ErrorType.DATABASE_ERROR
                )
            else:
                await self.handle_database_error(update, e, "create_project")
        except JiraAPIError as e:
            await self.handle_jira_error(update, e, "create_project")

    async def _show_project_edit_options(self, update: Update, project: Project) -> None:
        """Show project editing options."""
        text = f"{EMOJI['EDIT']} **Edit Project: {project.key}**\n\n"
        text += f"**Current Settings:**\n"
        text += f"• Name: {project.name}\n"
        text += f"• Description: {project.description or 'None'}\n"
        text += f"• Status: {'Active' if project.is_active else 'Inactive'}\n"
        text += f"• Issues: {project.issue_count}\n\n"
        text += "What would you like to edit?"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['EDIT']} Edit Name",
                    callback_data=f"projects_edit_{project.key}_name"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['EDIT']} Edit Description",
                    callback_data=f"projects_edit_{project.key}_description"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['SETTINGS']} Toggle Status",
                    callback_data=f"projects_edit_{project.key}_status"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['REFRESH']} Sync with Jira",
                    callback_data=f"projects_edit_{project.key}_sync"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['STATS']} View Statistics",
                    callback_data=f"projects_edit_{project.key}_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="projects_refresh"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.edit_message(update, text, reply_markup)

    async def _show_project_delete_confirmation(
        self,
        update: Update,
        project: Project,
        warning: Optional[str] = None
    ) -> None:
        """Show project deletion confirmation."""
        text = f"{EMOJI['WARNING']} **Delete Project Confirmation**\n\n"
        text += f"**Project:** `{project.key}` - {project.name}\n"
        text += f"**Issues:** {project.issue_count}\n\n"
        
        if warning:
            text += f"{warning}\n\n"
        
        text += f"{EMOJI['ERROR']} **This action cannot be undone!**\n\n"
        text += "Are you sure you want to delete this project?"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['ERROR']} Delete Project",
                    callback_data=f"projects_delete_{project.key}_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['ERROR']} Force Delete (with issues)",
                    callback_data=f"projects_delete_{project.key}_force"
                )
            ] if project.issue_count > 0 else [],
            [
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="projects_refresh"
                )
            ]
        ]

        # Remove empty rows
        keyboard = [row for row in keyboard if row]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.edit_message(update, text, reply_markup)

    async def _show_default_project_selection(self, update: Update, user: User) -> None:
        """Show default project selection interface."""
        try:
            projects = await self.db.get_projects(active_only=True)
            preferences = await self.get_user_preferences(user.user_id)
            current_default = preferences.default_project_key if preferences else None

            if not projects:
                await self.send_info_message(
                    update,
                    "No projects available. Ask an admin to add projects first."
                )
                return

            text = f"{EMOJI['SETTINGS']} **Set Default Project**\n\n"
            text += f"**Current Default:** {current_default or 'None'}\n\n"
            text += "Select a project to set as your default:"

            keyboard = self.telegram.create_project_selection_keyboard(
                projects,
                callback_prefix="projects_default",
                show_cancel=True
            )

            if update.callback_query:
                await self.edit_message(update, text, keyboard)
            else:
                await self.send_message(update, text, keyboard)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "show_default_project_selection")

    async def _set_user_default_project(self, update: Update, user: User, project_key: str) -> None:
        """Set user's default project."""
        try:
            # Verify project exists and is active
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` not found.",
                    ErrorType.NOT_FOUND_ERROR
                )
                return

            if not project.is_active:
                await self.send_error_message(
                    update,
                    f"Project `{project_key}` is not active.",
                    ErrorType.VALIDATION_ERROR
                )
                return

            # Get or create user preferences
            preferences = await self.get_user_preferences(user.user_id)
            if not preferences:
                from ..models.user import UserPreferences
                preferences = UserPreferences(user_id=user.user_id)

            # Update default project
            preferences.default_project_key = project_key
            await self.db.save_user_preferences(preferences)

            # Send success message
            text = f"{EMOJI['SUCCESS']} **Default Project Set**\n\n"
            text += f"**Project:** `{project.key}` - {project.name}\n\n"
            text += "Now when you send messages, issues will be created in this project by default."

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{EMOJI['ISSUE']} Create Test Issue",
                        callback_data=f"issue_create_quick_{project.key}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{EMOJI['PROJECTS']} View Projects",
                        callback_data="projects_refresh"
                    )
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await self.edit_message(update, text, reply_markup)
            else:
                await self.send_message(update, text, reply_markup)

            self.log_user_action(
                user,
                "set_default_project",
                {"project_key": project_key}
            )

        except DatabaseError as e:
            await self.handle_database_error(update, e, "set_user_default_project")

    async def _handle_project_edit_callback(self, update: Update, project_key: str, action_parts: List[str]) -> None:
        """Handle project edit callbacks."""
        if not action_parts:
            return

        user = await self.enforce_admin(update)
        if not user:
            return

        action = action_parts[0]

        try:
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project `{project_key}` not found.")
                return

            if action == "name":
                await self._edit_project_name(update, project)
            elif action == "description":
                await self._edit_project_description(update, project)
            elif action == "status":
                await self._toggle_project_status(update, project, user)
            elif action == "sync":
                await self._sync_project_with_jira(update, project, user)
            elif action == "stats":
                await self._show_project_statistics(update, project)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "handle_project_edit_callback")

    async def _handle_project_delete_callback(self, update: Update, project_key: str, action_parts: List[str]) -> None:
        """Handle project delete callbacks."""
        if not action_parts:
            return

        user = await self.enforce_admin(update)  
        if not user:
            return

        action = action_parts[0]

        try:
            if action == "confirm":
                await self._delete_project(update, project_key, user, force=False)
            elif action == "force":
                await self._delete_project(update, project_key, user, force=True)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "handle_project_delete_callback")

    async def _edit_project_name(self, update: Update, project: Project) -> None:
        """Handle project name editing."""
        # This would typically involve setting up a conversation handler
        # For now, show instructions
        text = f"{EMOJI['EDIT']} **Edit Project Name**\n\n"
        text += f"**Current Name:** {project.name}\n\n"
        text += f"To edit the project name, use:\n"
        text += f"`/editproject {project.key} name <new_name>`\n\n"
        text += f"**Example:** `/editproject {project.key} name New Project Name`"
        
        await self.edit_message(update, text)

    async def _edit_project_description(self, update: Update, project: Project) -> None:
        """Handle project description editing."""
        text = f"{EMOJI['EDIT']} **Edit Project Description**\n\n"
        text += f"**Current Description:** {project.description or 'None'}\n\n"
        text += f"To edit the project description, use:\n"
        text += f"`/editproject {project.key} description <new_description>`\n\n"
        text += f"**Example:** `/editproject {project.key} description Updated project description`"
        
        await self.edit_message(update, text)

    async def _toggle_project_status(self, update: Update, project: Project, user: User) -> None:
        """Toggle project active status."""
        try:
            new_status = not project.is_active
            await self.db.update_project(project.key, is_active=new_status)
            
            status_text = "activated" if new_status else "deactivated"
            text = f"{EMOJI['SUCCESS']} Project `{project.key}` has been {status_text}."
            
            await self.edit_message(update, text)
            
            self.log_user_action(
                user,
                "toggle_project_status",
                {"project_key": project.key, "new_status": new_status}
            )

        except DatabaseError as e:
            await self.handle_database_error(update, e, "toggle_project_status")

    async def _sync_project_with_jira(self, update: Update, project: Project, user: User) -> None:
        """Sync project with Jira."""
        try:
            jira_project = await self.jira.get_project(project.key)
            if jira_project:
                # Update project with Jira data
                update_data = {
                    'name': jira_project.name,
                    'description': jira_project.description,
                    'jira_project_id': jira_project.jira_project_id,
                    'project_type': jira_project.project_type,
                    'lead': jira_project.lead,
                    'url': jira_project.url,
                    'avatar_url': jira_project.avatar_url,
                    'category': jira_project.category
                }
                
                await self.db.update_project(project.key, **update_data)
                
                text = f"{EMOJI['SUCCESS']} Project `{project.key}` synchronized with Jira successfully."
                
                self.log_user_action(
                    user,
                    "sync_project",
                    {"project_key": project.key}
                )
            else:
                text = f"{EMOJI['WARNING']} Project `{project.key}` not found in Jira."
            
            await self.edit_message(update, text)

        except (DatabaseError, JiraAPIError) as e:
            await self.handle_error(update, e, "sync_project_with_jira")

    async def _show_project_statistics(self, update: Update, project: Project) -> None:
        """Show project statistics."""
        try:
            stats = await self.db.get_project_stats(project.key)
            text = self.telegram.formatter.format_project_stats(stats)
            
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{EMOJI['BACK']} Back to Edit",
                        callback_data=f"projects_edit_{project.key}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.edit_message(update, text, reply_markup)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "show_project_statistics")

    async def _delete_project(self, update: Update, project_key: str, user: User, force: bool = False) -> None:
        """Delete a project."""
        try:
            success = await self.db.delete_project(project_key, force=force)
            
            if success:
                text = f"{EMOJI['SUCCESS']} Project `{project_key}` has been deleted successfully."
                
                self.log_user_action(
                    user,
                    "delete_project",
                    {"project_key": project_key, "force": force}
                )
            else:
                text = f"{EMOJI['ERROR']} Failed to delete project `{project_key}`."
            
            # Show projects list
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{EMOJI['PROJECTS']} View Projects",
                        callback_data="projects_refresh"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.edit_message(update, text, reply_markup)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "delete_project")