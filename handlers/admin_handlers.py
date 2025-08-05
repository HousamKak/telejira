#!/usr/bin/env python3
"""
Admin handlers for the Telegram-Jira bot.

Handles administrative commands including user management, project management,
system configuration, and maintenance operations.
"""

import asyncio
import logging
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
            compact_mode=self.config.compact_messages,
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
    # PROJECT MANAGEMENT COMMANDS
    # =============================================================================

    async def add_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /addproject command - add new project.
        
        Usage: /addproject <KEY> "<NAME>" ["<DESCRIPTION>"]
        """
        self.log_handler_start(update, "add_project")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Parse arguments
            if not context.args or len(context.args) < 2:
                usage_msg = """
**Usage:** `/addproject <KEY> "<NAME>" ["<DESCRIPTION>"]`

**Examples:**
• `/addproject WEBAPP "Web Application" "Main company website"`
• `/addproject MOBILE "Mobile App"`

**Requirements:**
• KEY: Uppercase letters, numbers, underscores (2-20 chars)
• NAME: Project name in quotes if it contains spaces
• DESCRIPTION: Optional description in quotes
                """
                await self.send_message(update, usage_msg)
                return

            project_key = context.args[0].upper()
            
            # Extract name and description from quoted strings
            remaining_args = ' '.join(context.args[1:])
            parsed_args = self._parse_quoted_arguments(remaining_args)
            
            if not parsed_args:
                await self.send_error_message(update, "Invalid arguments format. Use quotes for names with spaces.")
                return
            
            project_name = parsed_args[0]
            project_description = parsed_args[1] if len(parsed_args) > 1 else ""

            # Validate inputs
            validation_result = self.validator.validate_project_key(project_key)
            if not validation_result.is_valid:
                await self.handle_validation_error(update, validation_result, "project key")
                return

            validation_result = self.validator.validate_project_name(project_name)
            if not validation_result.is_valid:
                await self.handle_validation_error(update, validation_result, "project name")
                return

            # Check if project already exists
            existing_project = await self.db.get_project_by_key(project_key)
            if existing_project:
                await self.send_error_message(update, f"Project with key '{project_key}' already exists.")
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

    async def edit_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /editproject command - edit existing project.
        
        Usage: /editproject <KEY>
        """
        self.log_handler_start(update, "edit_project")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(update, "**Usage:** `/editproject <PROJECT_KEY>`")
                return

            project_key = context.args[0].upper()
            
            # Get project
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project '{project_key}' not found.")
                return

            # Show edit menu
            await self._show_project_edit_menu(update, project)
            self.log_handler_end(update, "edit_project")

        except Exception as e:
            await self.handle_error(update, e, "edit_project")
            self.log_handler_end(update, "edit_project", success=False)

    async def delete_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /deleteproject command - delete project.
        
        Usage: /deleteproject <KEY>
        """
        self.log_handler_start(update, "delete_project")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(update, "**Usage:** `/deleteproject <PROJECT_KEY>`")
                return

            project_key = context.args[0].upper()
            
            # Get project
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project '{project_key}' not found.")
                return

            # Check if project has issues
            issue_count = await self.db.get_project_issue_count(project_key)
            if issue_count > 0:
                await self.send_error_message(
                    update, 
                    f"Cannot delete project '{project_key}' - it contains {issue_count} issues."
                )
                return

            # Show confirmation
            await self._show_delete_project_confirmation(update, project)
            self.log_handler_end(update, "delete_project")

        except Exception as e:
            await self.handle_error(update, e, "delete_project")
            self.log_handler_end(update, "delete_project", success=False)

    # =============================================================================
    # USER MANAGEMENT COMMANDS
    # =============================================================================

    async def list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /users command - list all users with statistics."""
        self.log_handler_start(update, "list_users")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            users = await self.db.get_all_users()
            
            if not users:
                await self.send_message(update, INFO_MESSAGES['NO_USERS'])
                return

            # Format user list
            message_lines = [f"{EMOJI.get('USERS', '👥')} **User Statistics** ({len(users)} total)"]
            message_lines.append("")

            # Group users by role
            users_by_role = {
                UserRole.SUPER_ADMIN: [],
                UserRole.ADMIN: [],
                UserRole.USER: []
            }

            for u in users:
                users_by_role[u.role].append(u)

            # Display by role
            for role in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.USER]:
                role_users = users_by_role[role]
                if not role_users:
                    continue

                role_emoji = self.formatter._get_role_emoji(role)
                role_name = role.value.replace('_', ' ').title()
                message_lines.append(f"{role_emoji} **{role_name}s** ({len(role_users)})")

                for u in role_users:
                    display_name = self.formatter._get_user_display_name(u)
                    status = "✅" if u.is_active else "❌"
                    activity = self.formatter._format_datetime(u.last_activity)
                    
                    user_line = f"• {status} {display_name}"
                    if u.username:
                        user_line += f" (@{u.username})"
                    user_line += f" - {u.issues_created} issues, {activity}"
                    
                    message_lines.append(user_line)
                
                message_lines.append("")

            # Overall statistics
            total_issues = sum(u.issues_created for u in users)
            active_users = len([u for u in users if u.is_active])
            
            message_lines.extend([
                "📊 **Overall Statistics:**",
                f"• Total Issues Created: {total_issues}",
                f"• Active Users: {active_users}/{len(users)}",
                f"• Admins: {len(users_by_role[UserRole.ADMIN]) + len(users_by_role[UserRole.SUPER_ADMIN])}"
            ])

            message = "\n".join(message_lines)
            await self.send_message(update, message)
            self.log_handler_end(update, "list_users")

        except Exception as e:
            await self.handle_error(update, e, "list_users")
            self.log_handler_end(update, "list_users", success=False)

    # =============================================================================
    # SYSTEM MANAGEMENT COMMANDS
    # =============================================================================

    async def sync_jira(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /syncjira command - synchronize data with Jira."""
        self.log_handler_start(update, "sync_jira")
        
        user = await self.enforce_role(update, UserRole.ADMIN)
        if not user:
            return

        try:
            # Show progress message
            progress_message = await self.send_message(
                update, 
                f"{EMOJI.get('SYNC', '🔄')} **Synchronizing with Jira...**\n\nPlease wait..."
            )

            # Sync projects
            projects_synced = 0
            issues_updated = 0

            try:
                # Get all projects from Jira
                jira_projects = await self.jira.get_all_projects(include_archived=False)
                
                for jira_project in jira_projects:
                    try:
                        # Update or create project in database
                        existing_project = await self.db.get_project_by_key(jira_project.key)
                        
                        if existing_project:
                            # Update existing project
                            await self.db.update_project(
                                key=jira_project.key,
                                name=jira_project.name,
                                description=jira_project.description,
                                url=jira_project.url,
                                is_active=jira_project.is_active
                            )
                        else:
                            # Create new project
                            await self.db.create_project(
                                key=jira_project.key,
                                name=jira_project.name,
                                description=jira_project.description,
                                url=jira_project.url,
                                is_active=jira_project.is_active
                            )
                        
                        projects_synced += 1
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to sync project {jira_project.key}: {e}")
                
                # Update issue counts
                for project in await self.db.get_all_projects():
                    try:
                        # Count issues for this project
                        jql_query = f"project = {project.key}"
                        jira_issues = await self.jira.search_issues(jql_query, max_results=1)
                        
                        # This is a simple count - in production you might want more sophisticated sync
                        issues_updated += 1
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to update issue count for {project.key}: {e}")

                # Success message
                success_message = self.formatter.format_success_message(
                    "Jira synchronization completed!",
                    f"• Projects synchronized: {projects_synced}\n• Issue counts updated: {issues_updated}"
                )
                
                await self.edit_message(update, success_message)

            except JiraAPIError as e:
                await self.edit_message(
                    update,
                    self.formatter.format_error_message(
                        "Jira API Error",
                        f"Failed to sync with Jira: {str(e)}",
                        "Check your Jira configuration and try again."
                    )
                )

            self.log_handler_end(update, "sync_jira")

        except Exception as e:
            await self.handle_error(update, e, "sync_jira")
            self.log_handler_end(update, "sync_jira", success=False)

    async def show_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /config command - show bot configuration."""
        self.log_handler_start(update, "show_config")
        
        user = await self.enforce_role(update, UserRole.SUPER_ADMIN)
        if not user:
            return

        try:
            config_info = [
                f"{EMOJI.get('CONFIG', '⚙️')} **Bot Configuration**",
                "",
                "**Jira Settings:**",
                f"• Domain: {self.config.jira_domain}",
                f"• Email: {self.config.jira_email}",
                f"• API Token: {'*' * 20}",
                "",
                "**Bot Settings:**",
                f"• Database: {self.config.database_path}",
                f"• Log Level: {self.config.log_level}",
                f"• Max Summary Length: {self.config.max_summary_length}",
                f"• Rate Limit: {self.config.rate_limit_per_minute}/min",
                "",
                "**Features:**",
                f"• Wizards: {'✅' if self.config.enable_wizards else '❌'}",
                f"• Shortcuts: {'✅' if self.config.enable_shortcuts else '❌'}",
                f"• Compact Messages: {'✅' if self.config.compact_messages else '❌'}",
                "",
                "**Access Control:**",
                f"• Allowed Users: {len(self.config.allowed_users)} configured",
                f"• Admin Users: {len(self.config.admin_users)} configured",
                f"• Super Admin Users: {len(self.config.super_admin_users)} configured",
            ]

            message = "\n".join(config_info)
            await self.send_message(update, message)
            self.log_handler_end(update, "show_config")

        except Exception as e:
            await self.handle_error(update, e, "show_config")
            self.log_handler_end(update, "show_config", success=False)

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /broadcast command - send message to all users."""
        self.log_handler_start(update, "broadcast_message")
        
        user = await self.enforce_role(update, UserRole.SUPER_ADMIN)
        if not user:
            return

        try:
            if not context.args:
                await self.send_message(
                    update, 
                    "**Usage:** `/broadcast <message>`\n\nSends a message to all active bot users."
                )
                return

            broadcast_text = ' '.join(context.args)
            
            # Get all active users
            users = await self.db.get_all_users()
            active_users = [u for u in users if u.is_active]

            if not active_users:
                await self.send_message(update, "No active users found.")
                return

            # Show confirmation
            confirmation_message = f"""
{EMOJI.get('BROADCAST', '📢')} **Confirm Broadcast**

**Message:** {broadcast_text}

**Recipients:** {len(active_users)} active users

Send this broadcast message?
            """

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Send Broadcast", callback_data=f"broadcast_confirm_{user.user_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]
            ])

            await self.send_message(update, confirmation_message, reply_markup=keyboard)
            
            # Store broadcast data for confirmation
            context.user_data['broadcast_data'] = {
                'message': broadcast_text,
                'recipients': [u.user_id for u in active_users]
            }

            self.log_handler_end(update, "broadcast_message")

        except Exception as e:
            await self.handle_error(update, e, "broadcast_message")
            self.log_handler_end(update, "broadcast_message", success=False)

    async def maintenance_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /maintenance command - show maintenance menu."""
        self.log_handler_start(update, "maintenance_menu")
        
        user = await self.enforce_role(update, UserRole.SUPER_ADMIN)
        if not user:
            return

        try:
            # Get system statistics
            stats = await self._get_system_statistics()
            
            message = f"""
{EMOJI.get('MAINTENANCE', '🔧')} **System Maintenance**

**Database Statistics:**
• Users: {stats['user_count']}
• Projects: {stats['project_count']}
• Issues: {stats['issue_count']}
• Database Size: {stats['db_size']}

**System Health:**
• Bot Uptime: {stats['uptime']}
• Memory Usage: {stats['memory_usage']}
• Last Jira Sync: {stats['last_sync']}

Choose a maintenance operation:
            """

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Test Jira Connection", callback_data="maint_test_jira")],
                [InlineKeyboardButton("📊 Detailed Statistics", callback_data="maint_stats")],
                [InlineKeyboardButton("🗄️ Database Maintenance", callback_data="maint_database")],
                [InlineKeyboardButton("📝 View Logs", callback_data="maint_logs")],
                [InlineKeyboardButton("🔄 Restart Bot", callback_data="maint_restart")],
                [InlineKeyboardButton("❌ Close", callback_data="maint_close")]
            ])

            await self.send_message(update, message, reply_markup=keyboard)
            self.log_handler_end(update, "maintenance_menu")

        except Exception as e:
            await self.handle_error(update, e, "maintenance_menu")
            self.log_handler_end(update, "maintenance_menu", success=False)

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _parse_quoted_arguments(self, text: str) -> List[str]:
        """Parse quoted arguments from text.
        
        Args:
            text: Text containing quoted arguments
            
        Returns:
            List of parsed arguments
        """
        import shlex
        try:
            return shlex.split(text)
        except ValueError:
            return []

    async def _show_project_edit_menu(self, update: Update, project: Project) -> None:
        """Show project edit menu."""
        message = f"""
{EMOJI.get('EDIT', '✏️')} **Edit Project: {project.key}**

{self.formatter.format_project(project, include_details=True)}

What would you like to edit?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Name", callback_data=f"edit_project_name_{project.key}")],
            [InlineKeyboardButton("📄 Description", callback_data=f"edit_project_desc_{project.key}")],
            [InlineKeyboardButton("🔗 URL", callback_data=f"edit_project_url_{project.key}")],
            [InlineKeyboardButton("⚡ Status", callback_data=f"edit_project_status_{project.key}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="edit_project_cancel")]
        ])

        await self.send_message(update, message, reply_markup=keyboard)

    async def _show_delete_project_confirmation(self, update: Update, project: Project) -> None:
        """Show project deletion confirmation."""
        message = f"""
{EMOJI.get('WARNING', '⚠️')} **Confirm Project Deletion**

You are about to delete project:
**{project.key}: {project.name}**

⚠️ **This action cannot be undone!**

Are you sure you want to delete this project?
        """

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Yes, Delete", callback_data=f"delete_project_confirm_{project.key}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="delete_project_cancel")]
        ])

        await self.send_message(update, message, reply_markup=keyboard)

    async def _get_system_statistics(self) -> Dict[str, Any]:
        """Get system statistics for maintenance menu.
        
        Returns:
            Dictionary of system statistics
        """
        try:
            # Database statistics
            user_count = len(await self.db.get_all_users())
            project_count = len(await self.db.get_all_projects())
            issue_count = await self.db.get_total_issue_count()
            
            # Database size
            import os
            try:
                db_size_bytes = os.path.getsize(self.config.database_path)
                db_size = self._format_file_size(db_size_bytes)
            except (OSError, AttributeError):
                db_size = "Unknown"
            
            # System information
            import psutil
            memory_usage = f"{psutil.virtual_memory().percent:.1f}%"
            
            # Bot uptime (simplified)
            uptime = "Unknown"
            
            # Last sync time (placeholder)
            last_sync = "Never"

            return {
                'user_count': user_count,
                'project_count': project_count,
                'issue_count': issue_count,
                'db_size': db_size,
                'memory_usage': memory_usage,
                'uptime': uptime,
                'last_sync': last_sync
            }
            
        except Exception as e:
            self.logger.error(f"Error getting system statistics: {e}")
            return {
                'user_count': 0,
                'project_count': 0,
                'issue_count': 0,
                'db_size': "Unknown",
                'memory_usage': "Unknown",
                'uptime': "Unknown",
                'last_sync': "Unknown"
            }

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"

    # =============================================================================
    # CALLBACK QUERY HANDLERS
    # =============================================================================

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle admin-related callback queries."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("broadcast_confirm_"):
            await self._handle_broadcast_confirmation(update, context)
        elif query.data == "broadcast_cancel":
            await self._handle_broadcast_cancellation(update, context)
        elif query.data.startswith("delete_project_confirm_"):
            await self._handle_delete_project_confirmation(update, context)
        elif query.data == "delete_project_cancel":
            await self._handle_delete_project_cancellation(update, context)
        elif query.data.startswith("maint_"):
            await self._handle_maintenance_callback(update, context)

    async def _handle_broadcast_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle broadcast confirmation."""
        broadcast_data = context.user_data.get('broadcast_data')
        if not broadcast_data:
            await self.edit_message(update, "Broadcast data not found.")
            return

        message = broadcast_data['message']
        recipients = broadcast_data['recipients']

        # Send broadcast
        sent_count = 0
        failed_count = 0

        for user_id in recipients:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 **Broadcast Message**\n\n{message}"
                )
                sent_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to send broadcast to {user_id}: {e}")
                failed_count += 1

        # Update message with results
        result_message = f"""
✅ **Broadcast Sent**

**Message:** {message}

**Results:**
• Sent successfully: {sent_count}
• Failed to send: {failed_count}
• Total recipients: {len(recipients)}
        """

        await self.edit_message(update, result_message)

        # Clean up
        if 'broadcast_data' in context.user_data:
            del context.user_data['broadcast_data']

    async def _handle_broadcast_cancellation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle broadcast cancellation."""
        await self.edit_message(update, "❌ Broadcast cancelled.")
        
        # Clean up
        if 'broadcast_data' in context.user_data:
            del context.user_data['broadcast_data']

    async def _handle_delete_project_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle project deletion confirmation."""
        query = update.callback_query
        project_key = query.data.replace("delete_project_confirm_", "")

        try:
            # Delete project from database
            await self.db.delete_project(project_key)

            success_message = self.formatter.format_success_message(
                f"Project '{project_key}' deleted successfully!",
                "The project has been removed from the bot database."
            )

            await self.edit_message(update, success_message)

        except DatabaseError as e:
            await self.edit_message(
                update,
                self.formatter.format_error_message(
                    "Database Error",
                    f"Failed to delete project: {str(e)}"
                )
            )

    async def _handle_delete_project_cancellation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle project deletion cancellation."""
        await self.edit_message(update, "❌ Project deletion cancelled.")

    async def _handle_maintenance_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle maintenance menu callbacks."""
        query = update.callback_query
        action = query.data.replace("maint_", "")

        if action == "test_jira":
            await self._test_jira_connection(update)
        elif action == "stats":
            await self._show_detailed_statistics(update)
        elif action == "database":
            await self._show_database_maintenance(update)
        elif action == "logs":
            await self._show_recent_logs(update)
        elif action == "restart":
            await self._handle_restart_request(update)
        elif action == "close":
            await self.edit_message(update, "Maintenance menu closed.")

    async def _test_jira_connection(self, update: Update) -> None:
        """Test Jira connection."""
        try:
            server_info = await self.jira.get_server_info()
            
            success_message = f"""
✅ **Jira Connection Test Successful**

**Server Information:**
• Version: {server_info.get('version', 'Unknown')}
• Build: {server_info.get('buildNumber', 'Unknown')}
• Title: {server_info.get('serverTitle', 'Unknown')}

Connection is working properly!
            """
            
            await self.edit_message(update, success_message)
            
        except JiraAPIError as e:
            error_message = f"""
❌ **Jira Connection Test Failed**

**Error:** {str(e)}

Please check your Jira configuration.
            """
            
            await self.edit_message(update, error_message)

    async def _show_detailed_statistics(self, update: Update) -> None:
        """Show detailed system statistics."""
        stats = await self._get_system_statistics()
        
        # Add more detailed stats
        users = await self.db.get_all_users()
        projects = await self.db.get_all_projects()
        
        # User activity analysis
        active_users = len([u for u in users if u.is_active])
        users_with_issues = len([u for u in users if u.issues_created > 0])
        
        # Project analysis
        active_projects = len([p for p in projects if p.is_active])
        
        detailed_stats = f"""
📊 **Detailed System Statistics**

**Users:**
• Total: {len(users)}
• Active: {active_users}
• With Issues: {users_with_issues}
• Admins: {len([u for u in users if u.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]])}

**Projects:**
• Total: {len(projects)}
• Active: {active_projects}
• Average Issues per Project: {stats['issue_count'] / max(len(projects), 1):.1f}

**Issues:**
• Total Created: {stats['issue_count']}
• Average per User: {stats['issue_count'] / max(len(users), 1):.1f}

**System:**
• Database Size: {stats['db_size']}
• Memory Usage: {stats['memory_usage']}
• Bot Uptime: {stats['uptime']}
        """
        
        await self.edit_message(update, detailed_stats)

    async def _show_database_maintenance(self, update: Update) -> None:
        """Show database maintenance options."""
        message = """
🗄️ **Database Maintenance**

Database maintenance operations:

• **Vacuum**: Optimize database storage
• **Backup**: Create database backup  
• **Cleanup**: Remove orphaned records
• **Reindex**: Rebuild database indexes

⚠️ These operations may temporarily affect bot performance.

Use with caution in production environments.
        """
        
        await self.edit_message(update, message)

    async def _show_recent_logs(self, update: Update) -> None:
        """Show recent log entries."""
        try:
            # Read last 20 lines of log file
            import os
            if os.path.exists(self.config.log_file):
                with open(self.config.log_file, 'r') as f:
                    lines = f.readlines()
                    recent_lines = lines[-20:] if len(lines) > 20 else lines
                    
                log_content = ''.join(recent_lines)
                
                message = f"""
📝 **Recent Log Entries**

```
{log_content[-3000:]}  # Limit to prevent message overflow
```

Showing last {len(recent_lines)} entries.
                """
            else:
                message = "Log file not found."
                
            await self.edit_message(update, message)
            
        except Exception as e:
            await self.edit_message(update, f"Error reading logs: {str(e)}")

    async def _handle_restart_request(self, update: Update) -> None:
        """Handle bot restart request."""
        message = """
🔄 **Bot Restart**

⚠️ **Warning**: This will restart the entire bot application.

• All active conversations will be interrupted
• Users will need to restart their interactions
• The bot will be unavailable for a few seconds

This should only be used in emergency situations.

Are you sure you want to restart the bot?
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Yes, Restart Bot", callback_data="restart_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="restart_cancel")]
        ])
        
        await self.edit_message(update, message, reply_markup=keyboard)