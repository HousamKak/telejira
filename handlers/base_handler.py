#!/usr/bin/env python3
"""
Base handler for the Telegram-Jira bot.

Provides common functionality and base methods for all handler classes.
Includes user management, error handling, message formatting, and shared utilities.
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from datetime import datetime, timezone
from abc import ABC, abstractmethod

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest, Forbidden

if TYPE_CHECKING:
    from config.settings import BotConfig
    from services.database import DatabaseManager
    from services.jira_service import JiraService
    from services.telegram_service import TelegramService

from models.user import User
from models.enums import UserRole, ErrorType
from services.database import DatabaseError
from services.jira_service import JiraAPIError
from utils.constants import EMOJI, SUCCESS_MESSAGES, ERROR_MESSAGES, INFO_MESSAGES, BOT_INFO
from utils.validators import InputValidator, ValidationResult
from utils.formatters import MessageFormatter


class BaseHandler(ABC):
    """Base class for all bot handlers with common functionality."""

    def __init__(
        self,
        config: 'BotConfig',
        db: 'DatabaseManager',
        jira_service: 'JiraService',
        telegram_service: 'TelegramService'
    ) -> None:
        """Initialize base handler.
        
        Args:
            config: Bot configuration
            db: Database manager instance
            jira_service: Jira service instance
            telegram_service: Telegram service instance
        """
        self.config = config
        self.db = db
        self.jira = jira_service
        self.telegram = telegram_service
        
        # Initialize logger with handler name
        self.logger = logging.getLogger(f"{__name__}.{self.get_handler_name()}")
        
        # Initialize utilities
        self.formatter = MessageFormatter(
            compact_mode=config.compact_mode,
            use_emoji=True
        )
        self.validator = InputValidator()

    @abstractmethod
    def get_handler_name(self) -> str:
        """Get the handler name for logging purposes."""
        pass

    # =============================================================================
    # CORE COMMAND HANDLERS
    # =============================================================================

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - welcome message and initial setup."""
        self.log_handler_start(update, "start_command")
        
        try:
            user = await self.get_or_create_user(update)
            if not user:
                return

            # Log user action
            self.log_user_action(user, "start_command")

            # Check if this is a new user
            is_new_user = user.created_at and (
                datetime.now(timezone.utc) - user.created_at
            ).total_seconds() < 300  # Less than 5 minutes ago

            if is_new_user:
                welcome_message = f"""
{EMOJI.get('WELCOME', '👋')} **Welcome to {BOT_INFO['NAME']}!**

Hi **{user.username}**! I'm your Jira assistant bot.

**🚀 Quick Start:**
1. Use `/wizard` for guided setup
2. Set your default project with `/projects`
3. Create issues by typing: `HIGH BUG Something is broken`

**📋 Essential Commands:**
• `/help` - Complete command reference
• `/projects` - View available projects
• `/create` - Interactive issue creation
• `/myissues` - Your recent issues

**Role:** {user.role.value.replace('_', ' ').title()}

Ready to get started? Try `/wizard` for step-by-step setup!
                """
            else:
                # Get user statistics
                try:
                    user_stats = await self.db.get_user_statistics(user.user_id)
                    issues_created = user_stats.get('issues_created', 0)
                    last_activity = user_stats.get('last_activity')
                except Exception:
                    issues_created = 0
                    last_activity = None

                # Get default project
                default_project = await self.db.get_user_default_project(user.user_id)

                welcome_message = f"""
{EMOJI.get('WELCOME', '👋')} **Welcome back, {user.username}!**

**Your Status:**
• Issues Created: {issues_created}
• Default Project: {default_project.key if default_project else 'Not set'}
• Role: {user.role.value.replace('_', ' ').title()}

**Quick Actions:**
            """

            # Add action buttons
            keyboard_buttons = []

            if default_project:
                keyboard_buttons.append([
                    InlineKeyboardButton("📝 Create Issue", callback_data="quick_create"),
                    InlineKeyboardButton("📋 My Issues", callback_data="my_issues")
                ])
            else:
                keyboard_buttons.append([
                    InlineKeyboardButton("🧙‍♂️ Run Setup Wizard", callback_data="run_wizard")
                ])

            keyboard_buttons.extend([
                [
                    InlineKeyboardButton("📁 Projects", callback_data="list_projects"),
                    InlineKeyboardButton("❓ Help", callback_data="show_help")
                ],
                [
                    InlineKeyboardButton("📊 Status", callback_data="show_status")
                ]
            ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, welcome_message, reply_markup=keyboard)
            self.log_handler_end(update, "start_command")

        except Exception as e:
            await self.handle_error(update, e, "start_command")
            self.log_handler_end(update, "start_command", success=False)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command - show comprehensive help."""
        self.log_handler_start(update, "help_command")
        
        try:
            user = await self.get_or_create_user(update)
            if not user:
                return

            # Log user action
            self.log_user_action(user, "help_command")

            # Build help message based on user role
            help_message = f"""
{EMOJI.get('HELP', '❓')} **{BOT_INFO['NAME']} Help**

**🚀 Quick Issue Creation:**
Just type: `[PRIORITY] [TYPE] Description`

**Examples:**
• `HIGH BUG Login button not working`
• `MEDIUM TASK Update documentation`
• `LOW IMPROVEMENT Add dark mode`

**📋 Basic Commands:**
• `/start` - Welcome message and setup
• `/help` - Show this help message
• `/wizard` - Interactive setup wizard
• `/status` - Your statistics and bot status

**📁 Project Commands:**
• `/projects` - List available projects
• `/setdefault <KEY>` - Set your default project

**📝 Issue Commands:**
• `/create` - Interactive issue creation
• `/myissues` - View your recent issues
• `/listissues [filters]` - List all issues
• `/searchissues <query>` - Search issues
• `/view <KEY>` - View issue details
• `/comment <KEY> <text>` - Add comment

**⚡ Shortcuts (if enabled):**
• `/c` = `/create`
• `/mi` = `/myissues` 
• `/p` = `/projects`
• `/w` = `/wizard`
• `/q` = `/quick`
            """

            # Add admin commands if user is admin
            if self.is_admin(user):
                help_message += f"""

**🔧 Admin Commands:**
• `/admin` - Admin control panel
• `/addproject <KEY> "<name>" [desc]` - Add project
• `/adduser @username <role>` - Add user
• `/listusers` - List all users
• `/stats` - System statistics
• `/refresh` - Sync with Jira
                """

            # Add super admin commands if user is super admin
            if self.is_super_admin(user):
                help_message += f"""

**⚙️ Super Admin Commands:**
• `/config` - Bot configuration
• `/broadcast <message>` - Message all users
• `/maintenance` - System maintenance
                """

            help_message += f"""

**💡 Tips:**
• Set a default project for faster issue creation
• Use inline keyboards for easier navigation
• Type `/cancel` in wizards to exit

**Current Role:** {user.role.value.replace('_', ' ').title()}

**Need more help?** Contact your administrator.
            """

            # Add help navigation buttons
            keyboard_buttons = [
                [
                    InlineKeyboardButton("🧙‍♂️ Setup Wizard", callback_data="run_wizard"),
                    InlineKeyboardButton("📊 Bot Status", callback_data="show_status")
                ],
                [
                    InlineKeyboardButton("📁 Projects", callback_data="list_projects"),
                    InlineKeyboardButton("📝 Create Issue", callback_data="quick_create")
                ]
            ]

            if self.is_admin(user):
                keyboard_buttons.append([
                    InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_menu")
                ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, help_message, reply_markup=keyboard)
            self.log_handler_end(update, "help_command")

        except Exception as e:
            await self.handle_error(update, e, "help_command")
            self.log_handler_end(update, "help_command", success=False)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command - show user and bot status."""
        self.log_handler_start(update, "status_command")
        
        try:
            user = await self.get_or_create_user(update)
            if not user:
                return

            # Log user action
            self.log_user_action(user, "status_command")

            # Get user statistics
            try:
                user_stats = await self.db.get_user_statistics(user.user_id)
            except Exception:
                user_stats = {}

            # Get default project
            default_project = await self.db.get_user_default_project(user.user_id)

            # Get accessible projects count
            projects = await self.db.get_user_projects(user.user_id)

            # Format status message
            status_message = f"""
{EMOJI.get('STATUS', '📊')} **Bot Status & Your Statistics**

**👤 Your Account:**
• Username: @{user.username}
• Role: {user.role.value.replace('_', ' ').title()}
• Joined: {user.created_at.strftime('%Y-%m-%d') if user.created_at else 'Unknown'}
• Status: {'🟢 Active' if user.is_active else '🔴 Inactive'}

**📊 Your Activity:**
• Issues Created: {user_stats.get('issues_created', 0)}
• Comments Added: {user_stats.get('comments_added', 0)}
• Commands Used: {user_stats.get('commands_used', 0)}
• Last Activity: {user_stats.get('last_activity', 'Unknown')}

**📁 Project Access:**
• Available Projects: {len(projects)}
• Default Project: {default_project.key if default_project else 'Not set'}

**🤖 Bot Information:**
• Bot Version: {BOT_INFO['VERSION']}
• Bot Status: 🟢 Online
• Jira Domain: {self.config.jira_domain}
• Features: {'Quick Create, ' if self.config.enable_quick_create else ''}{'Shortcuts, ' if self.config.enable_shortcuts else ''}{'Wizards' if self.config.enable_wizards else ''}
            """

            # Add management buttons
            keyboard_buttons = [
                [
                    InlineKeyboardButton("📁 My Projects", callback_data="list_projects"),
                    InlineKeyboardButton("📋 My Issues", callback_data="my_issues")
                ],
                [
                    InlineKeyboardButton("⚙️ Preferences", callback_data="user_preferences"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")
                ]
            ]

            if self.is_admin(user):
                keyboard_buttons.append([
                    InlineKeyboardButton("📊 System Stats", callback_data="system_stats"),
                    InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_menu")
                ])

            keyboard = InlineKeyboardMarkup(keyboard_buttons)

            await self.send_message(update, status_message, reply_markup=keyboard)
            self.log_handler_end(update, "status_command")

        except Exception as e:
            await self.handle_error(update, e, "status_command")
            self.log_handler_end(update, "status_command", success=False)

    # =============================================================================
    # CALLBACK QUERY HANDLER
    # =============================================================================

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Central callback query handler that routes to appropriate handlers."""
        if not update.callback_query:
            return

        query = update.callback_query
        self.log_handler_start(update, f"callback_query:{query.data}")

        try:
            # Always answer the callback query to remove loading state
            await query.answer()

            # Route to appropriate handler based on callback data
            if query.data.startswith(("quick_create", "my_issues", "list_projects", "show_help", "show_status", "run_wizard")):
                await self._handle_navigation_callback(update, context)
            elif query.data.startswith(("view_issue_", "edit_issue_", "transition_issue_", "create_issue_", "confirm_create_")):
                # Route to issue handlers
                from .issue_handlers import IssueHandlers
                if hasattr(self, 'issue_handlers') and isinstance(self.issue_handlers, IssueHandlers):
                    await self.issue_handlers.handle_issue_callback(update, context)
                else:
                    await self._handle_fallback_callback(update, context)
            elif query.data.startswith(("setdefault_", "project_", "refresh_project_")):
                # Route to project handlers  
                from .project_handlers import ProjectHandlers
                if hasattr(self, 'project_handlers') and isinstance(self.project_handlers, ProjectHandlers):
                    await self.project_handlers.handle_project_callback(update, context)
                else:
                    await self._handle_fallback_callback(update, context)
            elif query.data.startswith(("admin_", "remove_user_", "add_project_")):
                # Route to admin handlers
                from .admin_handlers import AdminHandlers
                if hasattr(self, 'admin_handlers') and isinstance(self.admin_handlers, AdminHandlers):
                    await self.admin_handlers.handle_admin_callback(update, context)
                else:
                    await self._handle_fallback_callback(update, context)
            else:
                # Handle unknown callbacks
                await self._handle_unknown_callback(update, context)

            self.log_handler_end(update, f"callback_query:{query.data}")

        except Exception as e:
            await self.handle_error(update, e, f"callback_query:{query.data}")
            self.log_handler_end(update, f"callback_query:{query.data}", success=False)

    async def _handle_navigation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle navigation callbacks from start command."""
        query = update.callback_query
        
        if query.data == "quick_create":
            await query.edit_message_text(
                "🚀 Starting quick issue creation...\n\n"
                "Use `/create` or `/quick` commands to create issues with the wizard."
            )
        elif query.data == "my_issues":
            await query.edit_message_text(
                "📋 Loading your issues...\n\n"
                "Use `/myissues` command to see your recent issues."
            )
        elif query.data == "list_projects":
            await query.edit_message_text(
                "📁 Loading projects...\n\n"
                "Use `/projects` command to see all available projects."
            )
        elif query.data == "show_help":
            await self.help_command(update, context)
        elif query.data == "show_status":
            await self.status_command(update, context)
        elif query.data == "run_wizard":
            await query.edit_message_text(
                "🧙‍♂️ Starting setup wizard...\n\n"
                "Use `/wizard` command to run the interactive setup."
            )
        elif query.data == "refresh_status":
            await self.status_command(update, context)

    async def _handle_fallback_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback when specific handler is not available."""
        await update.callback_query.edit_message_text(
            "⚠️ This feature requires additional setup. Please contact your administrator."
        )

    async def _handle_unknown_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown callback queries."""
        self.logger.warning(f"Unknown callback query: {update.callback_query.data}")
        await update.callback_query.edit_message_text(
            "❌ Unknown action. Please try again or use /help for available commands."
        )

    # =============================================================================
    # USER MANAGEMENT AND ACCESS CONTROL
    # =============================================================================

    async def get_or_create_user(self, update: Update) -> Optional[User]:
        """Get or create user from update."""
        if not update.effective_user:
            self.logger.error("No effective user in update")
            return None

        try:
            telegram_user = update.effective_user
            
            # Try to get existing user
            user = await self.db.get_user_by_telegram_id(telegram_user.id)
            
            if user:
                # Update last activity
                await self.db.update_user_last_activity(user.user_id)
                return user

            # Check if user is pre-authorized
            username = telegram_user.username or f"user_{telegram_user.id}"
            authorized_role = await self.db.get_preauthorized_user_role(username)
            
            if not authorized_role:
                # User not authorized
                await self.send_message(
                    update,
                    f"❌ **Access Denied**\n\n"
                    f"You are not authorized to use this bot.\n"
                    f"Contact your administrator to request access.\n\n"
                    f"**Your Info:**\n"
                    f"• Username: @{username}\n"
                    f"• Telegram ID: {telegram_user.id}"
                )
                return None

            # Create new user
            user = await self.db.create_user(
                telegram_id=telegram_user.id,
                username=username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                role=authorized_role,
                is_active=True
            )

            self.logger.info(f"Created new user: {username} (ID: {user.user_id}) with role {authorized_role.value}")
            return user

        except Exception as e:
            self.logger.error(f"Error getting/creating user: {e}")
            await self.send_error_message(
                update,
                "Failed to authenticate user. Please try again later.",
                ErrorType.AUTHENTICATION_ERROR
            )
            return None

    async def enforce_user_access(self, update: Update) -> Optional[User]:
        """Enforce user access and return user if authorized."""
        user = await self.get_or_create_user(update)
        if not user or not user.is_active:
            return None
        return user

    async def enforce_role(self, update: Update, required_role: UserRole) -> Optional[User]:
        """Enforce minimum role requirement."""
        user = await self.enforce_user_access(update)
        if not user:
            return None

        if not self.has_role(user, required_role):
            await self.send_error_message(
                update,
                f"This command requires {required_role.value.replace('_', ' ').title()} role or higher.",
                ErrorType.PERMISSION_ERROR
            )
            return None

        return user

    def has_role(self, user: User, required_role: UserRole) -> bool:
        """Check if user has required role or higher."""
        role_hierarchy = {
            UserRole.USER: 1,
            UserRole.ADMIN: 2,
            UserRole.SUPER_ADMIN: 3
        }
        
        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(required_role, 999)
        
        return user_level >= required_level

    def is_admin(self, user: User) -> bool:
        """Check if user is admin or higher."""
        return self.has_role(user, UserRole.ADMIN)

    def is_super_admin(self, user: User) -> bool:
        """Check if user is super admin."""
        return user.role == UserRole.SUPER_ADMIN

    # =============================================================================
    # MESSAGE AND ERROR HANDLING
    # =============================================================================

    async def send_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message: bool = False,
        parse_mode: str = "Markdown"
    ) -> Optional[Message]:
        """Send message with error handling."""
        try:
            chat_id = update.effective_chat.id
            reply_to_message_id = None
            
            if reply_to_message and update.message:
                reply_to_message_id = update.message.message_id

            message = await self.telegram.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode
            )
            
            return message

        except TelegramError as e:
            self.logger.error(f"Failed to send message: {e}")
            return None

    async def edit_message(
        self,
        update: Update,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: str = "Markdown"
    ) -> bool:
        """Edit message with error handling."""
        try:
            if update.callback_query and update.callback_query.message:
                await update.callback_query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                return True
            else:
                # Fallback to sending new message
                await self.send_message(update, text, reply_markup, parse_mode=parse_mode)
                return False

        except BadRequest as e:
            if "Message is not modified" in str(e):
                # Message content is the same, ignore
                return True
            self.logger.error(f"Failed to edit message: {e}")
            return False
        except TelegramError as e:
            self.logger.error(f"Failed to edit message: {e}")
            return False

    async def send_error_message(
        self,
        update: Update,
        error_text: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR
    ) -> None:
        """Send formatted error message."""
        emoji = EMOJI.get('ERROR', '❌')
        error_message = f"{emoji} **Error**\n\n{error_text}"
        
        await self.send_message(update, error_message)

    async def send_success_message(
        self,
        update: Update,
        success_text: str,
        details: Optional[str] = None
    ) -> None:
        """Send formatted success message."""
        emoji = EMOJI.get('SUCCESS', '✅')
        message = f"{emoji} **Success**\n\n{success_text}"
        
        if details:
            message += f"\n\n{details}"
        
        await self.send_message(update, message)

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors with appropriate user feedback."""
        error_context = f" in {context}" if context else ""
        self.logger.error(f"Error{error_context}: {str(error)}", exc_info=True)

        # Determine error type and user message
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        elif isinstance(error, TelegramError):
            await self.handle_telegram_error(update, error, context)
        else:
            await self.send_error_message(
                update,
                "An unexpected error occurred. Please try again later.",
                ErrorType.UNKNOWN_ERROR
            )

    async def handle_database_error(self, update: Update, error: DatabaseError, context: str = "") -> None:
        """Handle database-specific errors."""
        await self.send_error_message(
            update,
            "Database operation failed. Please try again later.",
            ErrorType.DATABASE_ERROR
        )

    async def handle_jira_error(self, update: Update, error: JiraAPIError, context: str = "") -> None:
        """Handle Jira API-specific errors."""
        if error.status_code == 401:
            message = "Jira authentication failed. Please contact your administrator."
        elif error.status_code == 403:
            message = "Insufficient Jira permissions for this operation."
        elif error.status_code == 404:
            message = "Requested Jira resource not found."
        else:
            message = f"Jira operation failed: {str(error)}"

        await self.send_error_message(update, message, ErrorType.JIRA_ERROR)

    async def handle_telegram_error(self, update: Update, error: TelegramError, context: str = "") -> None:
        """Handle Telegram API-specific errors."""
        if isinstance(error, Forbidden):
            self.logger.warning(f"Bot blocked by user: {update.effective_user.id if update.effective_user else 'Unknown'}")
        else:
            self.logger.error(f"Telegram error: {error}")

    # =============================================================================
    # LOGGING AND ANALYTICS
    # =============================================================================

    def log_handler_start(self, update: Update, handler_name: str) -> None:
        """Log handler start."""
        user_info = "Unknown"
        if update.effective_user:
            user_info = f"{update.effective_user.username or update.effective_user.id}"
        
        self.logger.debug(f"🔄 {handler_name} started by {user_info}")

    def log_handler_end(self, update: Update, handler_name: str, success: bool = True) -> None:
        """Log handler completion."""
        user_info = "Unknown"
        if update.effective_user:
            user_info = f"{update.effective_user.username or update.effective_user.id}"
        
        status = "✅" if success else "❌"
        self.logger.debug(f"{status} {handler_name} completed for {user_info}")

    def log_user_action(self, user: User, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log user action for analytics."""
        self.logger.info(f"User action: {user.username} -> {action}")
        
        # Store in database for analytics (fire and forget)
        asyncio.create_task(self._store_user_action(user.user_id, action, details))

    async def _store_user_action(self, user_id: int, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Store user action in database."""
        try:
            await self.db.log_user_action(user_id, action, details)
        except Exception as e:
            self.logger.error(f"Failed to store user action: {e}")

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def format_timestamp(self, dt: datetime) -> str:
        """Format timestamp for display."""
        if not dt:
            return "Unknown"
        
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        if diff.days > 7:
            return dt.strftime("%Y-%m-%d")
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "Just now"

    def truncate_text(self, text: str, max_length: int = 100) -> str:
        """Truncate text with ellipsis."""
        if not text or len(text) <= max_length:
            return text or ""
        
        return text[:max_length-3] + "..."

    async def validate_input(self, value: str, validation_type: str) -> ValidationResult:
        """Validate user input."""
        return self.validator.validate(value, validation_type)