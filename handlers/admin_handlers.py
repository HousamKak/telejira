#!/usr/bin/env python3
"""
Admin handlers for the Telegram-Jira bot.

Handles administrative commands including user management, project management,
system configuration, and maintenance operations.
"""

import asyncio
import logging
import shlex
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .base_handler import BaseHandler
from models.project import Project, ProjectSummary
from models.user import User
from models.enums import UserRole, IssuePriority, IssueType, ErrorType
from services.database import DatabaseError
from services.jira_service import JiraAPIError
from utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES
from utils.validators import InputValidator, ValidationResult
from utils.formatters import MessageFormatter


class AdminHandlers(BaseHandler):
    """Handles administrative commands and operations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = MessageFormatter(
            compact_mode=self.config.compact_mode,
            use_emoji=True
        )
        self.validator = InputValidator()

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "AdminHandlers"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to admin operations."""
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        elif isinstance(error, PermissionError):
            await self.send_error_message(
                update, 
                "Insufficient permissions for this operation", 
                ErrorType.PERMISSION_ERROR
            )
        else:
            await self.send_error_message(
                update,
                f"Admin operation failed: {str(error)}",
                ErrorType.UNKNOWN_ERROR
            )

    # =============================================================================
    # ADMIN MENU AND GENERAL COMMANDS
    # =============================================================================

    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /admin command - show admin menu."""
        self.log_handler_start(update, "admin_menu")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Get system statistics
            stats = await self._get_system_statistics()
            
            message = f"""
{EMOJI.get('ADMIN', '⚙️')} **Admin Control Panel**

**System Overview:**
• Users: {stats['user_count']}
• Projects: {stats['project_count']}
• Issues Created: {stats['issue_count']}
• Active Sessions: {stats.get('active_sessions', 'N/A')}

**Quick Actions:**
            """

            keyboard_buttons = [
                [
                    InlineKeyboardButton("👥 Manage Users", callback_data="admin_users"),
                    InlineKeyboardButton("📁 Manage Projects", callback_data="admin_projects")
                ],
                [
                    InlineKeyboardButton("📊 View Statistics", callback_data="admin_stats"),
                    InlineKeyboardButton("🔄 Sync with Jira", callback_data="admin_sync")
                ]
            ]

            # Add super admin options if applicable
            if self.is_super_admin(user):
                keyboard_buttons.extend([
                    [
                        InlineKeyboardButton("⚙️ Bot Config", callback_data="admin_config"),
                        InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
                    ],
                    [
                        InlineKeyboardButton("🔧 Maintenance", callback_data="admin_maintenance")
                    ]
                ])

            keyboard_buttons.append([
                InlineKeyboardButton("❌ Close", callback_data="admin_close")
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "admin_menu")

        except Exception as e:
            await self.handle_error(update, e, "admin_menu")
            self.log_handler_end(update, "admin_menu", success=False)

    # =============================================================================
    # USER MANAGEMENT COMMANDS
    # =============================================================================

    async def add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /adduser command - add new user."""
        self.log_handler_start(update, "add_user")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if not context.args or len(context.args) < 2:
                await self.send_message(
                    update,
                    "**Usage:** `/adduser <telegram_username> <role>`\n\n"
                    "**Roles:** user, admin, super_admin\n"
                    "**Example:** `/adduser @johndoe user`"
                )
                return

            telegram_username = context.args[0].lstrip('@')
            role_str = context.args[1].lower()

            # Validate role
            try:
                role = UserRole.from_string(role_str)
            except ValueError:
                await self.send_error_message(
                    update, 
                    f"Invalid role '{role_str}'. Valid roles: user, admin, super_admin"
                )
                return

            # Check if user already exists
            existing_user = await self.db.get_user_by_username(telegram_username)
            if existing_user:
                await self.send_error_message(
                    update, 
                    f"User @{telegram_username} already exists with role {existing_user.role.value}"
                )
                return

            # Create user (will be activated when they first interact with bot)
            new_user = User(
                user_id=0,  # Will be set when user first interacts
                username=telegram_username,
                role=role,
                is_active=False  # Will be activated on first interaction
            )

            # Store in pre-authorized users list
            await self.db.add_preauthorized_user(telegram_username, role)

            success_message = self.formatter.format_success_message(
                f"User @{telegram_username} pre-authorized",
                f"**Role:** {role.value.replace('_', ' ').title()}\n"
                f"User will be activated when they first interact with the bot."
            )

            await self.send_message(update, success_message)
            self.log_handler_end(update, "add_user")

        except Exception as e:
            await self.handle_error(update, e, "add_user")
            self.log_handler_end(update, "add_user", success=False)

    async def remove_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /removeuser command - remove user."""
        self.log_handler_start(update, "remove_user")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update,
                    "**Usage:** `/removeuser <telegram_username>`\n\n"
                    "**Example:** `/removeuser @johndoe`"
                )
                return

            telegram_username = context.args[0].lstrip('@')

            # Get user
            target_user = await self.db.get_user_by_username(telegram_username)
            if not target_user:
                await self.send_error_message(update, f"User @{telegram_username} not found.")
                return

            # Prevent removing super admins (unless current user is super admin)
            if target_user.role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update, 
                    "Cannot remove super admin users. Contact a super admin."
                )
                return

            # Show confirmation
            await self._show_remove_user_confirmation(update, target_user)
            self.log_handler_end(update, "remove_user")

        except Exception as e:
            await self.handle_error(update, e, "remove_user")
            self.log_handler_end(update, "remove_user", success=False)

    async def list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /listusers command - list all users with statistics."""
        self.log_handler_start(update, "list_users")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Get all users
            users = await self.db.get_all_users()
            
            if not users:
                message = f"""
{EMOJI.get('USERS', '👥')} **User Management**

No users found in the system.

Use `/adduser @username role` to add users.
                """
                await self.send_message(update, message)
                return

            # Format users list
            message_lines = [
                f"{EMOJI.get('USERS', '👥')} **System Users** ({len(users)} total)",
                ""
            ]

            # Group users by role for better organization
            users_by_role = {}
            for u in users:
                role_name = u.role.value.replace('_', ' ').title()
                if role_name not in users_by_role:
                    users_by_role[role_name] = []
                users_by_role[role_name].append(u)

            # Display by role hierarchy
            role_order = ['Super Admin', 'Admin', 'User']
            for role_name in role_order:
                if role_name in users_by_role:
                    message_lines.append(f"**{role_name}s:**")
                    
                    for u in users_by_role[role_name]:
                        status_emoji = "✅" if u.is_active else "⏸️"
                        
                        # Get user stats
                        user_stats = await self.db.get_user_statistics(u.user_id)
                        issues_count = user_stats.get('issues_created', 0)
                        
                        user_line = (
                            f"  {status_emoji} **@{u.username}** "
                            f"({issues_count} issues, joined {u.created_at.strftime('%Y-%m-%d')})"
                        )
                        message_lines.append(user_line)
                    
                    message_lines.append("")

            message = "\n".join(message_lines)

            # Add management buttons
            keyboard_buttons = [
                [
                    InlineKeyboardButton("➕ Add User", callback_data="add_user_dialog"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="refresh_users")
                ],
                [
                    InlineKeyboardButton("📊 User Stats", callback_data="detailed_user_stats")
                ]
            ]

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "list_users")

        except Exception as e:
            await self.handle_error(update, e, "list_users")
            self.log_handler_end(update, "list_users", success=False)

    async def set_user_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setrole command - set user role."""
        self.log_handler_start(update, "set_user_role")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if not context.args or len(context.args) < 2:
                await self.send_message(
                    update,
                    "**Usage:** `/setrole <telegram_username> <role>`\n\n"
                    "**Roles:** user, admin, super_admin\n"
                    "**Example:** `/setrole @johndoe admin`"
                )
                return

            telegram_username = context.args[0].lstrip('@')
            role_str = context.args[1].lower()

            # Validate role
            try:
                new_role = UserRole.from_string(role_str)
            except ValueError:
                await self.send_error_message(
                    update, 
                    f"Invalid role '{role_str}'. Valid roles: user, admin, super_admin"
                )
                return

            # Get target user
            target_user = await self.db.get_user_by_username(telegram_username)
            if not target_user:
                await self.send_error_message(update, f"User @{telegram_username} not found.")
                return

            # Check permissions
            if new_role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update, 
                    "Only super admins can grant super admin role."
                )
                return

            if target_user.role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update, 
                    "Only super admins can modify other super admin roles."
                )
                return

            # Update role
            await self.db.update_user_role(target_user.user_id, new_role)

            success_message = self.formatter.format_success_message(
                f"Role updated for @{telegram_username}",
                f"**Previous Role:** {target_user.role.value.replace('_', ' ').title()}\n"
                f"**New Role:** {new_role.value.replace('_', ' ').title()}"
            )

            await self.send_message(update, success_message)
            self.log_handler_end(update, "set_user_role")

        except Exception as e:
            await self.handle_error(update, e, "set_user_role")
            self.log_handler_end(update, "set_user_role", success=False)

    # =============================================================================
    # PROJECT MANAGEMENT COMMANDS
    # =============================================================================

    async def add_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /addproject command - add new project."""
        self.log_handler_start(update, "add_project")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if not context.args or len(context.args) < 2:
                await self.send_message(
                    update,
                    "**Usage:** `/addproject <KEY> \"<Project Name>\" [\"Description\"]`\n\n"
                    "**Example:** `/addproject WEBAPP \"Web Application\" \"Main web app project\"`"
                )
                return

            # Parse quoted arguments
            args_text = ' '.join(context.args)
            parsed_args = self._parse_quoted_arguments(args_text)

            if len(parsed_args) < 2:
                await self.send_error_message(
                    update, 
                    "Project key and name are required. Use quotes for multi-word names."
                )
                return

            project_key = parsed_args[0].upper()
            project_name = parsed_args[1]
            project_description = parsed_args[2] if len(parsed_args) > 2 else ""

            # Validate project key
            if not re.match(r'^[A-Z][A-Z0-9_]*$', project_key):
                await self.send_error_message(
                    update, 
                    "Invalid project key. Must start with a letter and contain only uppercase letters, numbers, and underscores."
                )
                return

            # Check if project already exists
            existing_project = await self.db.get_project_by_key(project_key)
            if existing_project:
                await self.send_error_message(
                    update, 
                    f"Project '{project_key}' already exists."
                )
                return

            # Try to get project from Jira first
            jira_project = await self.jira.get_project_by_key(project_key)
            if jira_project:
                # Use Jira project data
                project = jira_project
                if project_description:
                    project.description = project_description
            else:
                # Create new project locally
                project = Project(
                    key=project_key,
                    name=project_name,
                    description=project_description,
                    url=f"https://{self.config.jira_domain}/projects/{project_key}",
                    is_active=True
                )

            # Store in database
            await self.db.create_project(
                key=project.key,
                name=project.name,
                description=project.description,
                url=project.url,
                is_active=project.is_active
            )

            # Success message
            success_message = self.formatter.format_success_message(
                f"Project '{project_key}' added successfully!",
                self.formatter.format_project(project, include_details=False)
            )
            
            await self.send_message(update, success_message)
            self.log_handler_end(update, "add_project")

        except Exception as e:
            await self.handle_error(update, e, "add_project")
            self.log_handler_end(update, "add_project", success=False)

    async def refresh_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /refresh command - refresh projects from Jira."""
        self.log_handler_start(update, "refresh_projects")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            await self.send_message(update, "🔄 Refreshing projects from Jira...")

            # Get projects from Jira
            jira_projects = await self.jira.get_all_projects()
            
            sync_stats = {
                'updated': 0,
                'added': 0,
                'errors': 0
            }

            for jira_project in jira_projects:
                try:
                    # Check if project exists in database
                    existing_project = await self.db.get_project_by_key(jira_project.key)
                    
                    if existing_project:
                        # Update existing project
                        await self.db.update_project(
                            project_key=jira_project.key,
                            name=jira_project.name,
                            description=jira_project.description,
                            url=jira_project.url,
                            is_active=jira_project.is_active
                        )
                        sync_stats['updated'] += 1
                    else:
                        # Add new project
                        await self.db.create_project(
                            key=jira_project.key,
                            name=jira_project.name,
                            description=jira_project.description,
                            url=jira_project.url,
                            is_active=jira_project.is_active
                        )
                        sync_stats['added'] += 1

                except Exception as e:
                    self.logger.error(f"Error syncing project {jira_project.key}: {e}")
                    sync_stats['errors'] += 1

            # Report results
            success_message = self.formatter.format_success_message(
                "Project synchronization completed",
                f"**Added:** {sync_stats['added']} projects\n"
                f"**Updated:** {sync_stats['updated']} projects\n"
                f"**Errors:** {sync_stats['errors']} projects"
            )

            await self.send_message(update, success_message)
            self.log_handler_end(update, "refresh_projects")

        except Exception as e:
            await self.handle_error(update, e, "refresh_projects")
            self.log_handler_end(update, "refresh_projects", success=False)

    # =============================================================================
    # STATISTICS AND MONITORING
    # =============================================================================

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command - show detailed system statistics."""
        self.log_handler_start(update, "show_stats")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Get comprehensive statistics
            stats = await self._get_comprehensive_statistics()

            message = f"""
{EMOJI.get('STATS', '📊')} **System Statistics**

**Users:**
• Total Users: {stats['users']['total']}
• Active Users: {stats['users']['active']}
• Admins: {stats['users']['admins']}
• New This Week: {stats['users']['new_this_week']}

**Projects:**
• Total Projects: {stats['projects']['total']}
• Active Projects: {stats['projects']['active']}
• Issues Created: {stats['projects']['total_issues']}

**Activity (Last 7 Days):**
• Commands Executed: {stats['activity']['commands']}
• Issues Created: {stats['activity']['issues_created']}
• Comments Added: {stats['activity']['comments']}

**System Health:**
• Database Size: {stats['system']['db_size']}
• Uptime: {stats['system']['uptime']}
• Last Jira Sync: {stats['system']['last_sync']}
            """

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📈 Detailed Analytics", callback_data="detailed_analytics"),
                    InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_stats")
                ],
                [
                    InlineKeyboardButton("📋 Export Report", callback_data="export_stats_report")
                ]
            ])

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "show_stats")

        except Exception as e:
            await self.handle_error(update, e, "show_stats")
            self.log_handler_end(update, "show_stats", success=False)

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _parse_quoted_arguments(self, text: str) -> List[str]:
        """Parse quoted arguments from text."""
        try:
            return shlex.split(text)
        except ValueError:
            return []

    async def _show_remove_user_confirmation(self, update: Update, target_user: User) -> None:
        """Show user removal confirmation."""
        message = f"""
{EMOJI.get('WARNING', '⚠️')} **Confirm User Removal**

You are about to remove user:
**@{target_user.username}** ({target_user.role.value.replace('_', ' ').title()})

⚠️ **This action cannot be undone!**
The user will lose access to the bot and all their data will be preserved but inaccessible.

Are you sure you want to remove this user?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Yes, Remove", callback_data=f"remove_user_confirm_{target_user.user_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="remove_user_cancel")]
        ])

        await self.send_message(update, message, reply_markup=keyboard)

    async def _get_system_statistics(self) -> Dict[str, Any]:
        """Get basic system statistics."""
        try:
            # Get basic counts
            user_count = await self.db.get_user_count()
            project_count = await self.db.get_project_count()
            issue_count = await self.db.get_total_issue_count()

            return {
                'user_count': user_count,
                'project_count': project_count,
                'issue_count': issue_count,
                'active_sessions': 0,  # Placeholder
                'uptime': 'N/A',  # Placeholder
                'db_size': 'N/A',  # Placeholder
                'last_sync': 'N/A'  # Placeholder
            }

        except Exception as e:
            self.logger.error(f"Error getting system statistics: {e}")
            return {
                'user_count': 0,
                'project_count': 0,
                'issue_count': 0,
                'active_sessions': 0,
                'uptime': 'N/A',
                'db_size': 'N/A',
                'last_sync': 'N/A'
            }

    async def _get_comprehensive_statistics(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        try:
            # Get user statistics
            users_stats = await self.db.get_user_statistics_summary()
            
            # Get project statistics
            projects_stats = await self.db.get_project_statistics_summary()
            
            # Get activity statistics
            activity_stats = await self.db.get_activity_statistics(days=7)
            
            # Get system information
            system_stats = await self._get_system_statistics()

            return {
                'users': {
                    'total': users_stats.get('total', 0),
                    'active': users_stats.get('active', 0),
                    'admins': users_stats.get('admins', 0),
                    'new_this_week': users_stats.get('new_this_week', 0)
                },
                'projects': {
                    'total': projects_stats.get('total', 0),
                    'active': projects_stats.get('active', 0),
                    'total_issues': projects_stats.get('total_issues', 0)
                },
                'activity': {
                    'commands': activity_stats.get('commands', 0),
                    'issues_created': activity_stats.get('issues_created', 0),
                    'comments': activity_stats.get('comments', 0)
                },
                'system': system_stats
            }

        except Exception as e:
            self.logger.error(f"Error getting comprehensive statistics: {e}")
            # Return default values
            return {
                'users': {'total': 0, 'active': 0, 'admins': 0, 'new_this_week': 0},
                'projects': {'total': 0, 'active': 0, 'total_issues': 0},
                'activity': {'commands': 0, 'issues_created': 0, 'comments': 0},
                'system': self._get_system_statistics()
            }

    # =============================================================================
    # CALLBACK QUERY HANDLERS
    # =============================================================================

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle admin-related callback queries."""
        query = update.callback_query
        await query.answer()

        if query.data == "admin_users":
            await self.list_users(update, context)
        elif query.data == "admin_projects":
            await self._show_project_management(update, context)
        elif query.data == "admin_stats":
            await self.show_stats(update, context)
        elif query.data == "admin_sync":
            await self.refresh_projects(update, context)
        elif query.data.startswith("remove_user_confirm_"):
            await self._handle_remove_user_confirm(update, context)
        elif query.data == "remove_user_cancel":
            await self.edit_message(update, "User removal cancelled.")

    async def _show_project_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show project management interface."""
        projects = await self.db.get_all_projects()
        
        message = f"""
{EMOJI.get('PROJECTS', '📁')} **Project Management**

Found {len(projects)} projects in the system.

**Management Options:**
        """

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Add Project", callback_data="add_project_dialog"),
                InlineKeyboardButton("🔄 Sync with Jira", callback_data="admin_sync")
            ],
            [
                InlineKeyboardButton("📋 List All Projects", callback_data="list_all_projects")
            ],
            [
                InlineKeyboardButton("🔙 Back to Admin", callback_data="back_to_admin")
            ]
        ])

        await self.edit_message(update, message, reply_markup=keyboard)

    async def _handle_remove_user_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user removal confirmation."""
        query = update.callback_query
        user_id = int(query.data.replace("remove_user_confirm_", ""))

        try:
            # Get user info for confirmation message
            target_user = await self.db.get_user_by_id(user_id)
            if not target_user:
                await self.edit_message(update, "❌ User not found.")
                return

            # Remove user (mark as inactive rather than deleting)
            await self.db.deactivate_user(user_id)

            success_message = self.formatter.format_success_message(
                f"User @{target_user.username} removed",
                "User has been deactivated and can no longer access the bot."
            )

            await self.edit_message(update, success_message)

        except Exception as e:
            await self.edit_message(update, f"❌ Failed to remove user: {str(e)}")