"""
Admin Handlers for Telegram Jira Bot.

This module contains all administrative functionality including user management,
project synchronization, statistics, and system administration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config.settings import BotConfig
from .base_handler import BaseHandler
from services.database import DatabaseService
from services.jira_service import JiraService
from models import User, UserRole
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)


class AdminHandlers(BaseHandler):
    """
    Handler class for administrative commands and operations.
    
    Provides functionality for user management, project synchronization,
    statistics viewing, and system administration.
    """

    def __init__(
        self,
        config: BotConfig,
        database_service: DatabaseService,
        jira_service: JiraService,
        telegram_service: TelegramService,
    ) -> None:
        """Initialize admin handlers with required services."""
        super().__init__(config,database_service, jira_service, telegram_service)

    # ---- Public Commands ----

    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Show main admin menu with available administrative actions.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "admin_menu")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Create admin menu keyboard
            keyboard = []
            
            # User management section
            keyboard.append([
                InlineKeyboardButton("👥 User Management", callback_data="admin_users"),
                InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            ])
            
            # Project management section
            keyboard.append([
                InlineKeyboardButton("🏗 Project Management", callback_data="admin_projects"),
                InlineKeyboardButton("🔄 Refresh Projects", callback_data="admin_refresh_projects"),
            ])
            
            # System management (super admin only)
            if self.is_super_admin(user):
                keyboard.append([
                    InlineKeyboardButton("⚙️ System Health", callback_data="admin_health"),
                    InlineKeyboardButton("📋 Comprehensive Stats", callback_data="admin_comprehensive_stats"),
                ])
            
            # Close button
            keyboard.append([InlineKeyboardButton("❌ Close", callback_data="admin_close")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            menu_text = (
                f"🔧 **Admin Panel**\n\n"
                f"Welcome, {user.display_name}!\n"
                f"Role: {user.role.display_name}\n\n"
                f"Choose an administrative action:"
            )
            
            await self.send_message(update, menu_text, reply_markup=reply_markup)
            self.log_handler_end(update, "admin_menu", success=True)
            
        except Exception as e:
            logger.error(f"Error in admin_menu: {e}")
            await self.send_error_message(update, "Failed to load admin menu")
            self.log_handler_end(update, "admin_menu", success=False)

    async def add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Add a preauthorized user to the system.
        
        Usage: /adduser <username> <role>
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "add_user")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            args = self._extract_command_args(update)
            
            if len(args) != 2:
                help_text = (
                    "**Usage:** `/adduser <username> <role>`\n\n"
                    "**Available roles:**\n"
                    "• `guest` - Limited access\n"
                    "• `user` - Standard user access\n"
                    "• `admin` - Administrative access\n"
                    "• `super_admin` - Full system access (super admin only)\n\n"
                    "**Example:** `/adduser johndoe user`"
                )
                await self.send_message(update, help_text)
                return

            username = args[0].lower().replace('@', '')  # Remove @ if present
            role_str = args[1].lower()
            
            # Validate role
            try:
                role = UserRole(role_str)
            except ValueError:
                await self.send_error_message(
                    update,
                    f"Invalid role '{role_str}'. Valid roles: guest, user, admin, super_admin"
                )
                return
            
            # Only super admin can create super admin users
            if role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update,
                    "Only super administrators can create super admin users"
                )
                return
            
            # Check if user already exists
            existing_user = await self.db.get_user_by_username(username)
            if existing_user:
                await self.send_error_message(
                    update,
                    f"User @{username} already exists in the system"
                )
                return
            
            # Add preauthorized user
            await self.db.add_preauthorized_user(username, role)
            
            # Log the action
            await self.db.log_user_action(user.user_id, "add_preauthorized_user", {
                "target_username": username,
                "assigned_role": role.value,
            })
            
            success_text = (
                f"✅ **User Added Successfully**\n\n"
                f"Username: @{username}\n"
                f"Role: {role.display_name}\n\n"
                f"The user can now start the bot and will be automatically registered with the specified role."
            )
            
            await self.send_message(update, success_text)
            self.log_handler_end(update, "add_user", success=True)
            
        except Exception as e:
            logger.error(f"Error in add_user: {e}")
            await self.handle_database_error(update, e, "adding user")
            self.log_handler_end(update, "add_user", success=False)

    async def remove_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Remove/deactivate a user from the system.
        
        Usage: /removeuser <username>
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "remove_user")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            args = self._extract_command_args(update)
            
            if len(args) != 1:
                help_text = (
                    "**Usage:** `/removeuser <username>`\n\n"
                    "**Example:** `/removeuser johndoe`\n\n"
                    "This will deactivate the user's account."
                )
                await self.send_message(update, help_text)
                return

            username = args[0].lower().replace('@', '')  # Remove @ if present
            
            # Find target user
            target_user = await self.db.get_user_by_username(username)
            if not target_user:
                await self.send_error_message(
                    update,
                    f"User @{username} not found in the system"
                )
                return
            
            # Prevent removing super admin (unless super admin removes themselves)
            if target_user.role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update,
                    "Only super administrators can remove super admin users"
                )
                return
            
            # Prevent removing themselves
            if target_user.user_id == user.user_id:
                await self.send_error_message(
                    update,
                    "You cannot remove yourself. Ask another administrator to deactivate your account."
                )
                return
            
            # Show confirmation
            await self._show_remove_user_confirmation(update, target_user)
            self.log_handler_end(update, "remove_user", success=True)
            
        except Exception as e:
            logger.error(f"Error in remove_user: {e}")
            await self.handle_database_error(update, e, "removing user")
            self.log_handler_end(update, "remove_user", success=False)

    async def list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        List all users in the system with their roles and status.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "list_users")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            users = await self.db.list_users()
            
            if not users:
                await self.send_message(update, "📭 No users found in the system.")
                return
            
            # Group users by role
            users_by_role = {}
            for u in users:
                role_name = u.role.display_name
                if role_name not in users_by_role:
                    users_by_role[role_name] = []
                users_by_role[role_name].append(u)
            
            # Build user list text
            text_parts = [f"👥 **System Users ({len(users)} total)**\n"]
            
            # Define role order for display
            role_order = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.USER, UserRole.GUEST]
            
            for role in role_order:
                role_name = role.display_name
                if role_name in users_by_role:
                    role_users = users_by_role[role_name]
                    text_parts.append(f"\n**{role_name} ({len(role_users)}):**")
                    
                    for u in sorted(role_users, key=lambda x: x.username or x.display_name):
                        status_emoji = "✅" if u.is_active else "❌"
                        username_part = f"@{u.username}" if u.username else "No username"
                        name_part = f"({u.display_name})" if u.display_name != username_part else ""
                        
                        last_seen = ""
                        if u.last_activity:
                            last_seen = f" - Last seen: {u.last_activity.strftime('%Y-%m-%d')}"
                        
                        text_parts.append(f"  {status_emoji} {username_part} {name_part}{last_seen}")
            
            full_text = "\n".join(text_parts)
            await self.send_message(update, full_text)
            self.log_handler_end(update, "list_users", success=True)
            
        except Exception as e:
            logger.error(f"Error in list_users: {e}")
            await self.handle_database_error(update, e, "listing users")
            self.log_handler_end(update, "list_users", success=False)

    async def set_user_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Change a user's role.
        
        Usage: /setrole <username> <new_role>
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "set_user_role")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            args = self._extract_command_args(update)
            
            if len(args) != 2:
                help_text = (
                    "**Usage:** `/setrole <username> <new_role>`\n\n"
                    "**Available roles:**\n"
                    "• `guest` - Limited access\n"
                    "• `user` - Standard user access\n"
                    "• `admin` - Administrative access\n"
                    "• `super_admin` - Full system access (super admin only)\n\n"
                    "**Example:** `/setrole johndoe admin`"
                )
                await self.send_message(update, help_text)
                return

            username = args[0].lower().replace('@', '')
            role_str = args[1].lower()
            
            # Validate role
            try:
                new_role = UserRole(role_str)
            except ValueError:
                await self.send_error_message(
                    update,
                    f"Invalid role '{role_str}'. Valid roles: guest, user, admin, super_admin"
                )
                return
            
            # Only super admin can set super admin role
            if new_role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update,
                    "Only super administrators can assign super admin role"
                )
                return
            
            # Find target user
            target_user = await self.db.get_user_by_username(username)
            if not target_user:
                await self.send_error_message(
                    update,
                    f"User @{username} not found in the system"
                )
                return
            
            # Prevent changing own role
            if target_user.user_id == user.user_id:
                await self.send_error_message(
                    update,
                    "You cannot change your own role. Ask another administrator."
                )
                return
            
            # Prevent non-super-admin from changing super admin role
            if target_user.role == UserRole.SUPER_ADMIN and not self.is_super_admin(user):
                await self.send_error_message(
                    update,
                    "Only super administrators can change super admin roles"
                )
                return
            
            old_role = target_user.role
            
            if old_role == new_role:
                await self.send_message(
                    update,
                    f"User @{username} already has role {new_role.display_name}"
                )
                return
            
            # Update role
            await self.db.update_user_role(target_user.row_id, new_role)
            
            # Log the action
            await self.db.log_user_action(user.user_id, "change_user_role", {
                "target_username": username,
                "old_role": old_role.value,
                "new_role": new_role.value,
            })
            
            success_text = (
                f"✅ **Role Updated Successfully**\n\n"
                f"User: @{username}\n"
                f"Previous role: {old_role.display_name}\n"
                f"New role: {new_role.display_name}"
            )
            
            await self.send_message(update, success_text)
            self.log_handler_end(update, "set_user_role", success=True)
            
        except Exception as e:
            logger.error(f"Error in set_user_role: {e}")
            await self.handle_database_error(update, e, "setting user role")
            self.log_handler_end(update, "set_user_role", success=False)

    async def refresh_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Synchronize projects from Jira to local database.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "refresh_projects")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Send initial message
            status_msg = await self.send_message(update, "🔄 Refreshing projects from Jira...")
            
            # Get projects from Jira
            jira_projects = await self.jira.list_projects(limit=1000)
            
            if not jira_projects:
                await self.send_message(update, "⚠️ No projects found in Jira or API access issue.")
                return
            
            # Update database
            created_count = 0
            updated_count = 0
            error_count = 0
            
            for jira_project in jira_projects:
                try:
                    # Check if project exists
                    existing_project = await self.db.get_project_by_key(jira_project.key)
                    
                    if existing_project:
                        # Update existing project
                        await self.db.update_project(
                            project_key=jira_project.key,
                            name=jira_project.name,
                            description=jira_project.description,
                            url=jira_project.url,
                            project_type=jira_project.project_type,
                            lead=jira_project.lead,
                            avatar_url=jira_project.avatar_url,
                        )
                        updated_count += 1
                    else:
                        # Create new project
                        await self.db.create_project(
                            key=jira_project.key,
                            name=jira_project.name,
                            description=jira_project.description,
                            url=jira_project.url,
                            project_type=jira_project.project_type,
                            lead=jira_project.lead,
                            avatar_url=jira_project.avatar_url,
                        )
                        created_count += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to sync project {jira_project.key}: {e}")
                    error_count += 1
            
            # Log the action
            await self.db.log_user_action(user.user_id, "refresh_projects", {
                "total_projects": len(jira_projects),
                "created": created_count,
                "updated": updated_count,
                "errors": error_count,
            })
            
            # Send summary
            summary_text = (
                f"✅ **Project Refresh Complete**\n\n"
                f"📊 **Summary:**\n"
                f"• Total Jira projects: {len(jira_projects)}\n"
                f"• New projects created: {created_count}\n"
                f"• Existing projects updated: {updated_count}"
            )
            
            if error_count > 0:
                summary_text += f"\n• Errors encountered: {error_count}"
            
            await self.send_message(update, summary_text)
            self.log_handler_end(update, "refresh_projects", success=True)
            
        except Exception as e:
            logger.error(f"Error in refresh_projects: {e}")
            await self.handle_jira_error(update, e, "refreshing projects")
            self.log_handler_end(update, "refresh_projects", success=False)

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Show system statistics and health information.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.log_handler_start(update, "show_stats")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Get system statistics
            stats = await self._get_system_statistics()
            
            # Format statistics message
            stats_text = (
                f"📊 **System Statistics**\n\n"
                f"👥 **Users:**\n"
                f"• Total users: {stats['users']['total']}\n"
                f"• Active today: {stats['users']['active_today']}\n"
                f"• New this week: {stats['users']['new_this_week']}\n\n"
                f"🏗 **Projects:**\n"
                f"• Total projects: {stats['projects']['total']}\n"
                f"• Active projects: {stats['projects']['active']}\n\n"
                f"📈 **Activity:**\n"
                f"• Actions today: {stats['activity']['actions_today']}\n"
                f"• Total actions (7 days): {stats['activity']['actions_week']}\n\n"
                f"🎯 **Issues:**\n"
                f"• Total tracked: {stats['issues']['total']}\n\n"
                f"🔧 **System Health:**\n"
                f"• Database: {stats['health']['database']}\n"
                f"• Jira API: {stats['health']['jira']}\n"
                f"• Telegram API: {stats['health']['telegram']}"
            )
            
            # Add role distribution for super admins
            if self.is_super_admin(user) and stats['users']['role_distribution']:
                stats_text += "\n\n👤 **Role Distribution:**\n"
                for role, count in stats['users']['role_distribution'].items():
                    stats_text += f"• {role.title()}: {count}\n"
            
            await self.send_message(update, stats_text)
            self.log_handler_end(update, "show_stats", success=True)
            
        except Exception as e:
            logger.error(f"Error in show_stats: {e}")
            await self.send_error_message(update, "Failed to retrieve system statistics")
            self.log_handler_end(update, "show_stats", success=False)

    # ---- Callback Handler ----

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle admin menu callback queries.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("admin_"):
            return

        await self._answer_callback_query(update)
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if callback_data == "admin_users":
                await self._show_user_management(update, context)
            elif callback_data == "admin_stats":
                await self.show_stats(update, context)
            elif callback_data == "admin_projects":
                await self._show_project_management(update, context)
            elif callback_data == "admin_refresh_projects":
                await self.refresh_projects(update, context)
            elif callback_data == "admin_health":
                if self.is_super_admin(user):
                    await self._show_system_health(update, context)
            elif callback_data == "admin_comprehensive_stats":
                if self.is_super_admin(user):
                    await self._show_comprehensive_stats(update, context)
            elif callback_data == "admin_close":
                await self.edit_message(update, "Admin panel closed.")
            elif callback_data.startswith("admin_remove_user_"):
                await self._handle_remove_user_confirm(update, context)
            
        except Exception as e:
            logger.error(f"Error in admin callback {callback_data}: {e}")
            await self.send_error_message(update, "An error occurred processing your request")

    # ---- Private Helper Methods ----

    async def _get_system_statistics(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        try:
            # Get basic counts
            user_count = await self.db.get_user_count()
            project_count = await self.db.get_project_count()
            issue_count = await self.db.get_total_issue_count()
            
            # Get detailed user stats
            user_stats = await self.db.get_user_statistics_summary()
            
            # Get activity stats
            activity_stats = await self.db.get_activity_statistics(days=7)
            
            # Check service health
            health_status = {
                'database': 'Healthy' if self.db.is_initialized() else 'Unhealthy',
                'jira': 'Unknown',
                'telegram': 'Unknown',
            }
            
            try:
                jira_health = await self.jira.health_check()
                health_status['jira'] = jira_health.get('status', 'Unknown').title()
            except Exception:
                health_status['jira'] = 'Unhealthy'
            
            try:
                telegram_health = await self.telegram.health_check()
                health_status['telegram'] = telegram_health.get('status', 'Unknown').title()
            except Exception:
                health_status['telegram'] = 'Unhealthy'
            
            return {
                'users': {
                    'total': user_count,
                    'active_today': user_stats.get('active_today', 0),
                    'new_this_week': user_stats.get('new_users_this_week', 0),
                    'role_distribution': user_stats.get('role_distribution', {}),
                },
                'projects': {
                    'total': project_count,
                    'active': project_count,  # Assuming all are active
                },
                'activity': {
                    'actions_today': user_stats.get('activities_today', 0),
                    'actions_week': activity_stats.get('total_activities', 0),
                },
                'issues': {
                    'total': issue_count,
                },
                'health': health_status,
            }
            
        except Exception as e:
            logger.error(f"Error getting system statistics: {e}")
            return {
                'users': {'total': 0, 'active_today': 0, 'new_this_week': 0, 'role_distribution': {}},
                'projects': {'total': 0, 'active': 0},
                'activity': {'actions_today': 0, 'actions_week': 0},
                'issues': {'total': 0},
                'health': {'database': 'Unknown', 'jira': 'Unknown', 'telegram': 'Unknown'},
            }

    async def _get_comprehensive_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics for super admins."""
        basic_stats = await self._get_system_statistics()
        
        try:
            # Get additional detailed stats
            project_stats = await self.db.get_project_statistics_summary()
            activity_30_days = await self.db.get_activity_statistics(days=30)
            
            # Add comprehensive data
            basic_stats.update({
                'projects_detailed': project_stats,
                'activity_30_days': activity_30_days,
            })
            
        except Exception as e:
            logger.error(f"Error getting comprehensive statistics: {e}")
        
        return basic_stats

    async def _show_remove_user_confirmation(self, update: Update, target_user: User) -> None:
        """Show confirmation dialog for user removal."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"admin_remove_user_{target_user.row_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="admin_close"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        confirmation_text = (
            f"⚠️ **Confirm User Removal**\n\n"
            f"Are you sure you want to deactivate this user?\n\n"
            f"**User:** @{target_user.username or 'No username'}\n"
            f"**Name:** {target_user.display_name}\n"
            f"**Role:** {target_user.role.display_name}\n\n"
            f"This action will deactivate the user's account. They will no longer be able to use the bot."
        )
        
        await self.send_message(update, confirmation_text, reply_markup=reply_markup)

    async def _handle_remove_user_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle confirmed user removal."""
        callback_data = self._get_callback_data(update)
        if not callback_data or not callback_data.startswith("admin_remove_user_"):
            return
        
        try:
            target_row_id = int(callback_data.split("_")[-1])
            
            # Get the user to remove
            target_user = await self.db.get_user_by_row_id(target_row_id)
            if not target_user:
                await self.edit_message(update, "❌ User not found.")
                return
            
            # Get current user for logging
            current_user = await self.enforce_user_access(update)
            if not current_user:
                return
            
            # Deactivate user
            await self.db.deactivate_user(target_row_id)
            
            # Log the action
            await self.db.log_user_action(current_user.user_id, "deactivate_user", {
                "target_username": target_user.username,
                "target_user_id": target_user.user_id,
            })
            
            success_text = (
                f"✅ **User Deactivated**\n\n"
                f"User @{target_user.username or 'No username'} has been deactivated successfully."
            )
            
            await self.edit_message(update, success_text)
            
        except Exception as e:
            logger.error(f"Error confirming user removal: {e}")
            await self.edit_message(update, "❌ Failed to deactivate user.")

    async def _show_user_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show user management options."""
        keyboard = [
            [InlineKeyboardButton("👥 List Users", callback_data="admin_list_users")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "👥 **User Management**\n\n"
            "Choose an action or use commands:\n\n"
            "**Commands:**\n"
            "• `/adduser <username> <role>` - Add preauthorized user\n"
            "• `/removeuser <username>` - Deactivate user\n"
            "• `/setrole <username> <role>` - Change user role\n"
            "• `/listusers` - List all users"
        )
        
        await self.edit_message(update, text, reply_markup=reply_markup)

    async def _show_project_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show project management options."""
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh from Jira", callback_data="admin_refresh_projects")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🏗 **Project Management**\n\n"
            "Manage projects synchronized from Jira:\n\n"
            "**Available Actions:**\n"
            "• Refresh projects from Jira API\n"
            "• View project statistics\n\n"
            "Projects are automatically synchronized from your Jira instance. "
            "Use refresh to get the latest project information."
        )
        
        await self.edit_message(update, text, reply_markup=reply_markup)

    async def _show_system_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show detailed system health information (super admin only)."""
        try:
            health_data = {
                'database': 'Unknown',
                'jira': 'Unknown', 
                'telegram': 'Unknown',
            }
            
            # Check database
            health_data['database'] = 'Healthy' if self.db.is_initialized() else 'Unhealthy'
            
            # Check Jira
            try:
                jira_health = await self.jira.health_check()
                health_data['jira'] = f"Healthy - {jira_health.get('server_title', 'Unknown')}"
            except Exception as e:
                health_data['jira'] = f"Unhealthy - {str(e)[:50]}..."
            
            # Check Telegram
            try:
                telegram_health = await self.telegram.health_check()
                bot_username = telegram_health.get('bot_username', 'Unknown')
                health_data['telegram'] = f"Healthy - @{bot_username}"
            except Exception as e:
                health_data['telegram'] = f"Unhealthy - {str(e)[:50]}..."
            
            text = (
                f"🔧 **System Health Status**\n\n"
                f"🗄 **Database:** {health_data['database']}\n"
                f"🔧 **Jira API:** {health_data['jira']}\n"
                f"🤖 **Telegram API:** {health_data['telegram']}\n\n"
                f"_Last checked: Now_"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.edit_message(update, text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error showing system health: {e}")
            await self.edit_message(update, "❌ Failed to retrieve system health information.")

    async def _show_comprehensive_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show comprehensive statistics (super admin only)."""
        try:
            stats = await self._get_comprehensive_statistics()
            
            text_parts = [
                "📊 **Comprehensive System Statistics**\n",
                f"👥 **Users:** {stats['users']['total']} total, {stats['users']['active_today']} active today",
                f"🏗 **Projects:** {stats['projects']['total']} total, {stats['projects']['active']} active",
                f"🎯 **Issues:** {stats['issues']['total']} tracked locally",
                f"📈 **Activity:** {stats['activity']['actions_today']} today, {stats['activity']['actions_week']} this week",
            ]
            
            # Add role distribution
            if stats['users']['role_distribution']:
                text_parts.append("\n👤 **Role Distribution:**")
                for role, count in stats['users']['role_distribution'].items():
                    text_parts.append(f"• {role.title()}: {count}")
            
            # Add popular projects if available
            if stats.get('projects_detailed', {}).get('popular_projects'):
                text_parts.append("\n🏆 **Popular Projects:**")
                for proj in stats['projects_detailed']['popular_projects'][:5]:
                    text_parts.append(f"• {proj['name']} ({proj['user_count']} users)")
            
            text = "\n".join(text_parts)
            
            keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.edit_message(update, text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error showing comprehensive stats: {e}")
            await self.edit_message(update, "❌ Failed to retrieve comprehensive statistics.")