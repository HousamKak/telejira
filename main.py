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
from services.database import DatabaseManager
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
        self.database: Optional[DatabaseManager] = None
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

    def _setup_logging(self) -> None:
        """Setup logging configuration with rotation and formatting."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper(), logging.INFO),
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("bot.log", encoding='utf-8')
            ]
        )

        # Set specific logger levels
        logging.getLogger("telegram").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    async def initialize_services(self) -> None:
        """Initialize all required services.

        Raises:
            RuntimeError: If service initialization fails
        """
        try:
            self.logger.info("Initializing services...")

            # Initialize database
            self.database = DatabaseManager(
                db_path=self.config.database_path,
                backup_enabled=self.config.backup_enabled,
                backup_interval_hours=self.config.backup_interval_hours
            )
            await self.database.initialize()
            self.logger.info("✅ Database initialized successfully")

            # Initialize Jira service
            self.jira_service = JiraService(
                domain=self.config.jira_domain,
                email=self.config.jira_email,
                api_token=self.config.jira_api_token,
                timeout=self.config.request_timeout,
                max_retries=self.config.max_retries
            )
            self.logger.info("✅ Jira service initialized successfully")

            # Initialize Telegram service
            self.telegram_service = TelegramService(
                bot_token=self.config.telegram_bot_token,
                timeout=self.config.request_timeout,
                max_retries=self.config.max_retries
            )
            await self.telegram_service.initialize()
            self.logger.info("✅ Telegram service initialized successfully")

            self.logger.info("✅ Services initialized successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize services: {e}")
            raise RuntimeError(f"Service initialization failed: {e}") from e

    async def test_connections(self) -> None:
        """Test connections to external services.

        Raises:
            JiraAPIError: If Jira connection fails
            RuntimeError: If other connections fail
        """
        self.logger.info("Testing connections...")

        try:
            # Test Jira connection
            self.logger.info("Testing Jira connection...")
            user_info = await self.jira_service.get_current_user()
            projects = await self.jira_service.get_all_projects()
            
            self.logger.info(
                f"✅ Jira connection successful - User: {user_info.get('displayName', 'Unknown')}, "
                f"Projects accessible: {len(projects)}"
            )

        except JiraAPIError as e:
            if e.status_code == 401:
                raise JiraAPIError(
                    "Jira authentication failed. Please check your email and API token.",
                    status_code=e.status_code,
                ) from e
            elif e.status_code == 403:
                raise JiraAPIError(
                    "Jira access denied. Please check your account permissions.",
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

            # Initialize base handler
            self.base_handler = BaseHandler(
                config=self.config,
                db=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            # Initialize specialized handlers
            self.admin_handlers = AdminHandlers(
                config=self.config,
                db=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.project_handlers = ProjectHandlers(
                config=self.config,
                db=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.issue_handlers = IssueHandlers(
                config=self.config,
                db=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.wizard_handlers = WizardHandlers(
                config=self.config,
                db=self.database,
                jira_service=self.jira_service,
                telegram_service=self.telegram_service,
            )

            self.logger.info("✅ Handlers initialized successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize handlers: {e}")
            raise RuntimeError(f"Handler initialization failed: {e}") from e

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
                CommandHandler("myissues", self.issue_handlers.list_my_issues),
                CommandHandler("listissues", self.issue_handlers.list_issues),
                CommandHandler("searchissues", self.issue_handlers.search_issues),
                CommandHandler("view", self.issue_handlers.view_issue),
                CommandHandler("edit", self.issue_handlers.edit_issue),
                CommandHandler("assign", self.issue_handlers.assign_issue),
                CommandHandler("comment", self.issue_handlers.comment_issue),
                CommandHandler("transition", self.issue_handlers.transition_issue),
            ]

            # Add admin commands if enabled
            if self.config.enable_admin:
                admin_commands = [
                    CommandHandler("admin", self.admin_handlers.admin_menu),
                    CommandHandler("adduser", self.admin_handlers.add_user),
                    CommandHandler("removeuser", self.admin_handlers.remove_user),
                    CommandHandler("listusers", self.admin_handlers.list_users),
                    CommandHandler("setrole", self.admin_handlers.set_user_role),
                    CommandHandler("addproject", self.admin_handlers.add_project),
                    CommandHandler("refresh", self.admin_handlers.refresh_projects),
                    CommandHandler("stats", self.admin_handlers.show_stats),
                ]
                command_handlers.extend(admin_commands)

            # Add shortcut handlers if enabled
            if self.config.enable_shortcuts:
                shortcut_handlers = [
                    CommandHandler("c", self.issue_handlers.create_issue),
                    CommandHandler("mi", self.issue_handlers.list_my_issues),
                    CommandHandler("li", self.issue_handlers.list_issues),
                    CommandHandler("s", self.issue_handlers.search_issues),
                    CommandHandler("p", self.project_handlers.list_projects),
                ]
                command_handlers.extend(shortcut_handlers)

                # Note: Wizard shortcuts (/w, /q) are already handled in the ConversationHandler
                # They are registered as entry_points in wizard_handlers.get_conversation_handler()

            # Register all command handlers
            for handler in command_handlers:
                self.application.add_handler(handler)

            # Register callback query handler for inline keyboards
            self.application.add_handler(
                CallbackQueryHandler(self.base_handler.handle_callback_query)
            )

            # Register message handler for issue creation from plain text
            if self.config.enable_quick_create:
                self.application.add_handler(
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.issue_handlers.handle_message_issue_creation,
                    )
                )

            # Register error handler
            self.application.add_error_handler(self._error_handler)

            self.logger.info("✅ All handlers registered successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to register handlers: {e}")
            raise RuntimeError(f"Handler registration failed: {e}") from e
    
    async def _error_handler(self, update: Update, context) -> None:
        """Handle errors in bot updates.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        self.logger.error(f"Exception while handling an update: {context.error}")

        # Send error message to user if possible
        if update and update.effective_chat:
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ An error occurred while processing your request. Please try again later.",
                )
            except Exception as send_error:
                self.logger.error(f"Failed to send error message to user: {send_error}")

    def create_application(self) -> Application:
        """Create and configure the Telegram application.

        Returns:
            Configured Application instance

        Raises:
            RuntimeError: If application creation fails
        """
        try:
            self.logger.info("Creating Telegram application...")

            # Create application
            self.application = (
                Application.builder()
                .token(self.config.telegram_bot_token)
                .read_timeout(self.config.request_timeout)
                .write_timeout(self.config.request_timeout)
                .connect_timeout(self.config.request_timeout)
                .pool_timeout(self.config.request_timeout)
                .build()
            )

            # Initialize handlers
            self._initialize_handlers()

            self.logger.info("✅ Telegram application created successfully")
            return self.application

        except Exception as e:
            self.logger.error(f"❌ Failed to create application: {e}")
            raise RuntimeError(f"Application creation failed: {e}") from e

    async def _graceful_shutdown(self) -> None:
        """Perform graceful shutdown of all services."""
        self.logger.info("Starting graceful shutdown...")

        try:
            # Close database connections
            if self.database:
                await self.database.close()
                self.logger.info("✅ Database connections closed")

            # Close Jira service connections  
            if self.jira_service:
                await self.jira_service.close()
                self.logger.info("✅ Jira service closed")

            # Close Telegram service connections
            if self.telegram_service:
                await self.telegram_service.close()
                self.logger.info("✅ Telegram service closed")

        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

        self.logger.info("✅ Graceful shutdown completed")

    async def run(self) -> None:
        """Run the bot with proper lifecycle management.

        Raises:
            RuntimeError: If bot execution fails
        """
        try:
            # Initialize services
            await self.initialize_services()

            # Test connections
            await self.test_connections()

            # Create and configure application
            self.create_application()

            # Register handlers
            self._register_handlers()

            self.logger.info("✅ Bot initialized successfully!")

            # Start the application
            await self.application.initialize()
            await self.application.start()

            self.logger.info("🔄 Bot is now running... Press Ctrl+C to stop.")

            # Start polling
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
            )

            # Wait for stop signal
            await self.application.updater.wait()

        except KeyboardInterrupt:
            self.logger.info("👋 Received shutdown signal")
        except Exception as e:
            self.logger.error(f"❌ Error in runner: {e}")
            raise RuntimeError(f"Bot execution failed: {e}") from e
        finally:
            # Stop the application
            if self.application:
                try:
                    await self.application.stop()
                    await self.application.shutdown()
                    self.logger.info("✅ Telegram application stopped")
                except Exception as e:
                    self.logger.error(f"❌ Error stopping application: {e}")

            # Perform graceful shutdown
            await self._graceful_shutdown()


async def run_bot(bot: TelegramJiraBot) -> None:
    """Run the bot with proper error handling.

    Args:
        bot: The TelegramJiraBot instance

    Raises:
        RuntimeError: If bot execution fails
    """
    logger = logging.getLogger(__name__)
    
    try:
        await bot.run()
    except Exception as e:
        logger.error(f"❌ Error in runner: {e}")
        raise


def main() -> None:
    """Main entry point that uses a single event loop for the entire bot lifecycle."""
    # Basic logging setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)

    # Windows event loop policy
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Load configuration
    try:
        config = load_config_from_env(env_file=str(Path(__file__).parent / ".env"))
        logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    except Exception as e:
        logger.error(f"❌ Failed to load configuration: {e}")
        sys.exit(1)

    # Create bot instance
    try:
        bot = TelegramJiraBot(config)
        logger.info(f"🚀 Starting {BOT_INFO['NAME']} v{BOT_INFO['VERSION']}")
        logger.info(f"📍 Jira Domain: {config.jira_domain}")
        logger.info(f"👤 Jira User: {config.jira_email}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot: {e}")
        sys.exit(1)

    # Run the bot with proper error handling
    async def bootstrap_and_run():
        """Bootstrap the bot and run it."""
        try:
            await run_bot(bot)
        except Exception as e:
            logger.error(f"❌ Error in bootstrap: {e}")
            raise
        finally:
            logger.info("👋 Bot stopped")

    # Signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        # The asyncio loop will handle the shutdown via KeyboardInterrupt
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the bot
    try:
        asyncio.run(bootstrap_and_run())
    except KeyboardInterrupt:
        logger.info("👋 Shutdown completed")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()