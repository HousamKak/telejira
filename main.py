#!/usr/bin/env python3
"""
Main entry point for the Telegram-Jira Bot.

A comprehensive Telegram bot that seamlessly integrates with Jira to help teams
manage issues and projects directly from Telegram.
"""

import asyncio
import logging
import signal
import sys
import os
from pathlib import Path
from typing import Optional, NoReturn

# Add the current directory to the Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config.settings import load_config_from_env, BotConfig
from services.database import DatabaseService
from services.jira_service import JiraService, JiraAPIError
from services.telegram_service import TelegramService
from handlers.admin_handlers import AdminHandlers
from handlers.project_handlers import ProjectHandlers
from handlers.issue_handlers import IssueHandlers
from handlers.wizard_handlers import WizardHandlers
from handlers.base_handler import BaseHandler
from utils.constants import BOT_INFO


class TelegramJiraBot:
    """Main bot application class."""

    def __init__(self, config: BotConfig) -> None:
        """Initialize the bot with configuration.

        Args:
            config: Bot configuration object

        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If initialization fails
        """
        # Validate configuration
        if not isinstance(config, BotConfig):
            raise TypeError("config must be a BotConfig instance")

        self.config: BotConfig = config
        self.application: Optional[Application] = None
        self.database: Optional[DatabaseService] = None
        self.jira_service: Optional[JiraService] = None
        self.telegram_service: Optional[TelegramService] = None

        # Handler instances
        self.admin_handlers: Optional[AdminHandlers] = None
        self.project_handlers: Optional[ProjectHandlers] = None
        self.issue_handlers: Optional[IssueHandlers] = None
        self.wizard_handlers: Optional[WizardHandlers] = None
        self.base_handler: Optional[BaseHandler] = None

        # Initialize logger
        self._setup_logging()
        self.logger = logging.getLogger(__name__)

        # Shutdown flag
        self._shutdown_requested = False

    def _setup_logging(self) -> None:
        """Setup logging configuration with rotation and formatting."""
        try:
            from logging.handlers import RotatingFileHandler
            
            # Create formatters
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # Setup root logger
            root_logger = logging.getLogger()
            root_logger.setLevel(getattr(logging, self.config.log_level.upper()))

            # Clear existing handlers
            root_logger.handlers.clear()

            # Console handler with UTF-8 encoding for Windows
            # Reconfigure stdout to handle UTF-8 on Windows
            if sys.platform == 'win32':
                import io
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer,
                    encoding='utf-8',
                    errors='replace',  # Replace characters that can't be encoded
                    line_buffering=True
                )

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(logging.INFO)
            root_logger.addHandler(console_handler)

            # File handler with rotation
            if self.config.log_file:
                file_handler = RotatingFileHandler(
                    self.config.log_file,
                    maxBytes=self.config.log_max_size,
                    backupCount=self.config.log_backup_count,
                    encoding='utf-8'
                )
                file_handler.setFormatter(file_formatter)
                file_handler.setLevel(getattr(logging, self.config.log_level.upper()))
                root_logger.addHandler(file_handler)

            # Reduce noise from some third-party libraries
            logging.getLogger('httpx').setLevel(logging.WARNING)
            logging.getLogger('telegram').setLevel(logging.WARNING)
            logging.getLogger('urllib3').setLevel(logging.WARNING)

        except Exception as e:
            print(f"Failed to setup logging: {e}")
            logging.basicConfig(level=logging.INFO)

    async def initialize(self) -> None:
        """Initialize all bot components.

        Raises:
            RuntimeError: If initialization fails
        """
        try:
            self.logger.info("🤖 Initializing Telegram-Jira Bot...")
            self.logger.info(f"📝 Config: {self.config.jira_domain}, DB: {self.config.database_path}")

            # Initialize services
            await self._initialize_services()
            await self._test_connections()
            
            # Initialize handlers
            self._initialize_handlers()

            # Initialize Telegram application
            self._initialize_telegram_app()
            
            # Register handlers with the application
            self._register_handlers()

            self.logger.info("✅ Bot initialization completed successfully")

        except Exception as e:
            self.logger.error(f"❌ Bot initialization failed: {e}")
            raise RuntimeError(f"Bot initialization failed: {e}") from e

    async def _initialize_services(self) -> None:
        """Initialize core services (database, Jira, Telegram).

        Raises:
            RuntimeError: If service initialization fails
        """
        try:
            self.logger.info("Initializing services...")

            # Initialize database
            self.database = DatabaseService(
                database_path=self.config.database_path,
            )
            await self.database.initialize()
            self.logger.info("✅ Database service initialized")

            # Initialize Jira service - FIXED PARAMETERS
            self.jira_service = JiraService(
                base_url=self.config.get_jira_base_url(),  # Use method to get proper URL format
                username=self.config.jira_email,  # Changed from 'email' to 'username'
                api_token=self.config.jira_api_token,
                timeout=self.config.jira_timeout,
                max_retries=self.config.jira_max_retries,
            )
            self.logger.info("✅ Jira service initialized")

            # Initialize Telegram service - FIXED PARAMETER
            self.telegram_service = TelegramService(
                bot_token=self.config.telegram_token,  # Changed from 'token' to 'bot_token'
            )
            self.logger.info("✅ Telegram service initialized")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize services: {e}")
            raise RuntimeError(f"Service initialization failed: {e}") from e

    async def _test_connections(self) -> None:
        """Test connections to external services.

        Raises:
            RuntimeError: If connection tests fail
        """
        try:
            self.logger.info("Testing service connections...")

            # Test database connection
            if self.database:
                user_count = await self.database.get_user_count()
                self.logger.info(f"✅ Database connection OK ({user_count} users)")

            # Test Jira connection
            if self.jira_service:
                current_user = await self.jira_service.get_current_user()
                self.logger.info(f"✅ Jira connection OK (user: {current_user.get('displayName', 'Unknown')})")

            # Telegram connection will be tested when the bot starts

        except JiraAPIError as e:
            if e.status_code == 401:
                raise RuntimeError(
                    "Jira authentication failed. Please check your API token and email. "
                    "Visit https://id.atlassian.com/manage-profile/security/api-tokens to create a new token."
                ) from e
            elif e.status_code == 403:
                raise RuntimeError(
                    "Jira access forbidden. Please check your account permissions.",
                    status_code=e.status_code,
                ) from e
            else:
                raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error testing connections: {e}")
            raise RuntimeError(f"Failed to test connections: {e}") from e

    def _initialize_handlers(self) -> None:
        """Initialize all command and message handlers.

        Raises:
            RuntimeError: If handler initialization fails
        """
        try:
            if not self.database or not self.jira_service or not self.telegram_service:
                raise RuntimeError("Services must be initialized before handlers")

            self.logger.info("Initializing handlers...")

            # Initialize base handler - ADD CONFIG PARAMETER
            self.base_handler = BaseHandler(
                config=self.config,  # ADD THIS LINE
                database_service=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            # Initialize specialized handlers - ADD CONFIG PARAMETER
            self.admin_handlers = AdminHandlers(
                config=self.config,  # ADD THIS LINE
                database_service=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.project_handlers = ProjectHandlers(
                config=self.config,  # ADD THIS LINE
                database_service=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.issue_handlers = IssueHandlers(
                config=self.config,  # ADD THIS LINE
                database_service=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.wizard_handlers = WizardHandlers(
                config=self.config,  # ADD THIS LINE
                database_service=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.logger.info("✅ Handlers initialized successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize handlers: {e}")
            raise RuntimeError(f"Handler initialization failed: {e}") from e

    def _initialize_telegram_app(self) -> None:
        """Initialize the Telegram application.

        Raises:
            RuntimeError: If Telegram app initialization fails
        """
        try:
            self.logger.info("Initializing Telegram application...")
            
            self.application = (
                Application.builder()
                .token(self.config.telegram_token)
                .pool_timeout(self.config.telegram_pool_timeout)
                .connection_pool_size(self.config.telegram_connection_pool_size)
                .read_timeout(self.config.telegram_timeout)
                .write_timeout(self.config.telegram_timeout)
                .build()
            )

            self.logger.info("✅ Telegram application initialized")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Telegram app: {e}")
            raise RuntimeError(f"Telegram app initialization failed: {e}") from e

    def _register_handlers(self) -> None:
        """Register all handlers with the Telegram application.

        Raises:
            RuntimeError: If application is not initialized
        """
        if not self.application:
            raise RuntimeError(
                "Application must be initialized before registering handlers"
            )

        if not all([
            self.base_handler,
            self.admin_handlers,
            self.project_handlers,
            self.issue_handlers,
            self.wizard_handlers,
        ]):
            raise RuntimeError("All handlers must be initialized before registration")

        try:
            self.logger.info("Registering handlers...")

            # Register conversation handlers first (they have higher priority)
            # The wizard ConversationHandler already includes /wizard, /quick, /w, and /q commands
            if self.config.enable_wizards:
                wizard_conv_handler = self.wizard_handlers.get_conversation_handler()
                if wizard_conv_handler:
                    self.application.add_handler(wizard_conv_handler)
                    self.logger.info("✅ Wizard conversation handler registered")

            # Register command handlers
            command_handlers = [
                # Basic commands
                CommandHandler("start", self.base_handler.start_command),
                CommandHandler("help", self.base_handler.help_command),
                CommandHandler("status", self.base_handler.status_command),
                
                # Project commands
                CommandHandler("projects", self.project_handlers.list_projects),
                CommandHandler("setdefault", self.project_handlers.set_default_project),
                
                # Issue commands
                CommandHandler("create", self.issue_handlers.create_issue),
                CommandHandler("idea", self.issue_handlers.create_idea),
                CommandHandler("allissues", self.issue_handlers.list_my_issues),
                CommandHandler("myissues", self.issue_handlers.list_my_issues),  # Alias for backwards compatibility
                CommandHandler("listissues", self.issue_handlers.list_issues),
                CommandHandler("searchissues", self.issue_handlers.search_issues),
                CommandHandler("view", self.issue_handlers.view_issue),
                CommandHandler("edit", self.issue_handlers.edit_issue),
                CommandHandler("assign", self.issue_handlers.assign_issue),
                CommandHandler("comment", self.issue_handlers.comment_issue),
                CommandHandler("transition", self.issue_handlers.transition_issue),
                CommandHandler("delete", self.issue_handlers.delete_issue),
            ]

            # Add admin commands if enabled
            admin_commands = [
                CommandHandler("admin", self.admin_handlers.admin_menu),
                CommandHandler("adduser", self.admin_handlers.add_user),
                CommandHandler("removeuser", self.admin_handlers.remove_user),
                CommandHandler("listusers", self.admin_handlers.list_users),
                CommandHandler("setrole", self.admin_handlers.set_user_role),
                CommandHandler("addproject", self.admin_handlers.add_project),
                CommandHandler("refresh", self.admin_handlers.refresh_projects),
                CommandHandler("sync", self.admin_handlers.refresh_projects),  # Alias for refresh
                CommandHandler("stats", self.admin_handlers.show_stats),
            ]
            command_handlers.extend(admin_commands)

            # Add shortcut handlers if enabled
            if self.config.enable_shortcuts:
                shortcut_handlers = [
                    CommandHandler("s", self.base_handler.start_command),
                    CommandHandler("h", self.base_handler.help_command),
                    CommandHandler("c", self.issue_handlers.create_issue),
                    CommandHandler("l", self.issue_handlers.list_issues),
                    CommandHandler("m", self.issue_handlers.list_my_issues),
                    CommandHandler("p", self.project_handlers.list_projects),
                    CommandHandler("r", self.admin_handlers.refresh_projects),
                ]
                command_handlers.extend(shortcut_handlers)

            # Register all command handlers
            for handler in command_handlers:
                self.application.add_handler(handler)

            # Register callback query handlers (for inline keyboards)
            self.application.add_handler(
                CallbackQueryHandler(self.project_handlers.handle_project_callback, pattern=r'^project_.*')
            )
            self.application.add_handler(
                CallbackQueryHandler(self.issue_handlers.handle_issue_callback, pattern=r'^(view_issue_|view_comments_|refresh_issue_|edit_summary_|edit_description_|edit_priority_|edit_assignee_|set_priority_|edit_issue_|transition_issue_|do_transition_|confirm_create_|confirm_delete_|cancel_delete|create_new_issue|refresh_my_issues|cancel_create|create_issue_project_|search_more_)')
            )
            self.application.add_handler(
                CallbackQueryHandler(self.admin_handlers.handle_admin_callback, pattern=r'^admin_.*')
            )

            # Register message handlers for shortcuts and natural language
            if self.config.enable_shortcuts:
                # Natural language issue creation (e.g., "HIGH BUG Login broken")
                # TODO: Implement create_issue_from_text method in IssueHandlers
                # self.application.add_handler(
                #     MessageHandler(
                #         filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(LOW|MEDIUM|HIGH|CRITICAL|HIGHEST)\s+(BUG|TASK|STORY|EPIC)\s+.+'),
                #         self.issue_handlers.create_issue_from_text
                #     )
                # )
                pass

            # Handler for editing issue fields (must come before general handler)
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.issue_handlers.handle_edit_field_message)
            )

            # General message handler (for fallback)
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.base_handler.handle_unknown)
            )

            # Error handler
            self.application.add_error_handler(self._error_handler)

            self.logger.info("✅ All handlers registered successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to register handlers: {e}")
            raise RuntimeError(f"Handler registration failed: {e}") from e

    async def _error_handler(self, update: Update, context) -> None:
        """Handle errors that occur during message processing."""
        try:
            error = context.error
            self.logger.error(f"Update {update} caused error {error}")

            # Try to send a user-friendly error message
            if update and update.effective_chat:
                error_message = (
                    "❌ <b>Something went wrong</b>\n\n"
                    "An unexpected error occurred. Please try again.\n\n"
                    "If the problem persists, contact your administrator."
                )
                
                try:
                    if update.callback_query:
                        await update.callback_query.edit_message_text(
                            error_message, parse_mode="HTML"
                        )
                    elif update.message:
                        await update.message.reply_text(
                            error_message, parse_mode="HTML"
                        )
                except Exception as send_error:
                    self.logger.error(f"Failed to send error message: {send_error}")

        except Exception as handler_error:
            self.logger.error(f"Error in error handler: {handler_error}")

    async def start(self) -> None:
        """Start the bot and begin polling for updates.

        Raises:
            RuntimeError: If the bot fails to start
        """
        if not self.application:
            raise RuntimeError("Application must be initialized before starting")

        try:
            self.logger.info("🚀 Starting Telegram-Jira Bot...")

            # Start the application
            await self.application.initialize()
            await self.application.start()
            
            # Get bot info
            bot_info = await self.application.bot.get_me()
            self.logger.info(f"✅ Bot started successfully: @{bot_info.username}")
            self.logger.info(f"📊 Bot ID: {bot_info.id}")
            
            # Start polling
            self.logger.info("📡 Starting polling for updates...")
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=['message', 'callback_query', 'inline_query']
            )

            self.logger.info("🎉 Bot is now running and ready to receive messages!")

        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}")
            raise RuntimeError(f"Bot startup failed: {e}") from e

    async def stop(self) -> None:
        """Gracefully stop the bot and cleanup resources."""
        try:
            self.logger.info("🛑 Stopping Telegram-Jira Bot...")
            self._shutdown_requested = True

            if self.application:
                # Stop polling
                if self.application.updater.running:
                    await self.application.updater.stop()
                    self.logger.info("✅ Stopped polling for updates")

                # Stop the application
                await self.application.stop()
                await self.application.shutdown()
                self.logger.info("✅ Telegram application stopped")

            # Close services
            if self.jira_service:
                await self.jira_service.close()
                self.logger.info("✅ Jira service closed")

            if self.database:
                await self.database.close()
                self.logger.info("✅ Database connections closed")

            self.logger.info("👋 Bot stopped gracefully")

        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"🔔 Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def run(self) -> None:
        """Run the bot with proper initialization and cleanup."""
        try:
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Initialize and start the bot
            await self.initialize()
            await self.start()

            # Keep the bot running
            self.logger.info("🎯 Bot is running. Press Ctrl+C to stop.")
            
            # Wait until shutdown is requested
            while not self._shutdown_requested:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("🔔 Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"❌ Unexpected error in main loop: {e}")
        finally:
            await self.stop()


async def main() -> None:
    """Main entry point for the application."""
    try:
        env_path = Path(__file__).with_name(".env")  # resolves to ...\MVP\.env
        config = load_config_from_env(str(env_path))
        
        # Create and run the bot
        bot = TelegramJiraBot(config)
        await bot.run()

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        # Check Python version
        if sys.version_info < (3, 8):
            print("❌ Python 3.8+ is required")
            sys.exit(1)

        # Run the bot
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        sys.exit(1)