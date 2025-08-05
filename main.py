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
        from logging.handlers import RotatingFileHandler

        # Create logs directory if it doesn't exist
        log_file_path = Path(self.config.log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Setup file handler with rotation
        file_handler = RotatingFileHandler(
            filename=self.config.log_file,
            maxBytes=self.config.log_max_size,
            backupCount=self.config.log_backup_count,
            encoding="utf-8",
        )

        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # Add file handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        # Set specific log levels for external libraries
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.INFO)
        logging.getLogger("aiohttp").setLevel(logging.WARNING)

    async def _initialize_services(self) -> None:
        """Initialize all services and dependencies.

        Raises:
            RuntimeError: If service initialization fails
        """
        try:
            self.logger.info("Initializing services...")

            # Initialize database
            self.database = DatabaseManager(
                db_path=self.config.database_path,
                pool_size=self.config.database_pool_size,
                timeout=self.config.database_timeout,
            )
            await self.database.initialize()
            self.logger.info("✅ Database initialized successfully")

            # Initialize Jira service
            self.jira_service = JiraService(
                domain=self.config.jira_domain,
                email=self.config.jira_email,
                api_token=self.config.jira_api_token,
                timeout=self.config.jira_timeout,
                max_retries=self.config.jira_max_retries,
                retry_delay=self.config.jira_retry_delay,
                page_size=self.config.jira_page_size,
            )

            # Initialize Telegram service
            self.telegram_service = TelegramService(
                token=self.config.telegram_token,
                timeout=self.config.telegram_timeout,
                use_inline_keyboards=True,
                compact_mode=False,
            )
            self.logger.info("✅ Telegram service initialized successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize services: {e}")
            raise RuntimeError(f"Service initialization failed: {e}") from e

    async def _test_jira_connection(self) -> None:
        """Test Jira API connection and permissions.

        Raises:
            JiraAPIError: If connection test fails
        """
        if not self.jira_service:
            raise RuntimeError("Jira service not initialized")

        try:
            self.logger.info("Testing Jira connection...")

            # Test basic connectivity and permissions
            user_info = await self.jira_service.get_current_user()
            projects = await self.jira_service.get_projects(max_results=1)

            self.logger.info(
                f"✅ Jira connection successful - User: {user_info.get('displayName', 'Unknown')}, "
                f"Projects accessible: {len(projects)}"
            )

        except JiraAPIError as e:
            self.logger.error(f"❌ Jira connection failed: {e}")
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
            self.logger.error(f"❌ Unexpected error testing Jira connection: {e}")
            raise JiraAPIError(f"Failed to test Jira connection: {e}") from e

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

        if not all(
            [
                self.base_handler,
                self.admin_handlers,
                self.project_handlers,
                self.issue_handlers,
                self.wizard_handlers,
            ]
        ):
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
                CommandHandler("issues", self.issue_handlers.list_issues),
                CommandHandler("myissues", self.issue_handlers.list_my_issues),
                CommandHandler("search", self.issue_handlers.search_issues),
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
                    CommandHandler("refresh", self.admin_handlers.refresh_projects),
                    CommandHandler("stats", self.admin_handlers.show_stats),
                ]
                command_handlers.extend(admin_commands)

            # Add shortcut handlers if enabled
            if self.config.enable_shortcuts:
                shortcut_handlers = [
                    CommandHandler("c", self.issue_handlers.create_issue),
                    CommandHandler("i", self.issue_handlers.list_issues),
                    CommandHandler("mi", self.issue_handlers.list_my_issues),
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

    async def _graceful_shutdown(self) -> None:
        """Perform graceful shutdown of all services."""
        self.logger.info("Starting graceful shutdown...")

        try:
            # Close database connections
            if self.database:
                await self.database.close()
                self.logger.info("✅ Database connections closed")

            # Close Jira service
            if self.jira_service:
                await self.jira_service.close()
                self.logger.info("✅ Jira service closed")

            # Close Telegram service
            if self.telegram_service:
                # Add any cleanup for telegram service if needed
                pass

            self.logger.info("✅ Graceful shutdown completed")

        except Exception as e:
            self.logger.error(f"❌ Error during graceful shutdown: {e}")

    def create_application(self) -> Application:
        """Create and configure the Telegram application.
        
        Returns:
            Configured Application instance
        """
        # Build Telegram application
        application = (
            Application.builder()
            .token(self.config.telegram_token)
            .pool_timeout(self.config.telegram_pool_timeout)
            .connection_pool_size(self.config.telegram_connection_pool_size)
            .build()
        )

        # Store the application instance
        self.application = application
        return application


async def runner(bot: TelegramJiraBot) -> None:
    """
    Async runner that handles the complete PTB lifecycle.
    
    Args:
        bot: The TelegramJiraBot instance
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Create Application & register handlers
        application = bot.create_application()
        bot._register_handlers()

        # Initialize services that belong to PTB
        await application.initialize()
        await application.start()
        
        logger.info("✅ Bot initialized successfully!")
        logger.info("🔄 Bot is now running... Press Ctrl+C to stop.")

        # Start polling (async path)
        await application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

        # Wait until a stop signal (Ctrl+C) or .stop() is called
        await application.updater.wait()

    except Exception as e:
        logger.error(f"❌ Error in runner: {e}")
        raise
    finally:
        # Stop PTB cleanly
        if application:
            try:
                await application.stop()
                await application.shutdown()
                logger.info("✅ Telegram application stopped")
            except Exception as e:
                logger.error(f"❌ Error stopping application: {e}")

        # Close your own services
        await bot._graceful_shutdown()


def main() -> None:
    """
    Main entry point that uses a single event loop for the entire bot lifecycle.
    """
    # Basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)

    # Windows event loop policy
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Load config
    try:
        config = load_config_from_env(env_file=str(Path(__file__).parent / ".env"))
        logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    except Exception as e:
        logger.error(f"❌ Failed to load configuration: {e}")
        sys.exit(1)

    # Build bot
    try:
        bot = TelegramJiraBot(config)
        logger.info(f"🚀 Starting {BOT_INFO['NAME']} v{BOT_INFO['VERSION']}")
        logger.info(f"📍 Jira Domain: {config.jira_domain}")
        logger.info(f"👤 Jira User: {config.jira_email}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot: {e}")
        sys.exit(1)

    # Run everything inside ONE event loop
    async def bootstrap_and_run():
        """Bootstrap the bot and run it."""
        try:
            # Initialize your services (DB, Jira, TelegramService)
            await bot._initialize_services()
            # Optional: quick Jira health check
            await bot._test_jira_connection()
            # Init handlers (your own synchronous step)
            bot._initialize_handlers()
            
            logger.info("✅ Services initialized successfully")
            
            # Hand off to PTB runner
            await runner(bot)
            
        except JiraAPIError as e:
            logger.error(f"❌ Jira API error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error in bootstrap: {e}")
            raise

    try:
        asyncio.run(bootstrap_and_run())
    except KeyboardInterrupt:
        logger.info("🛑 Received keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        # Best-effort shutdown
        try:
            asyncio.run(bot._graceful_shutdown())
        except Exception as se:
            logger.error(f"❌ Error during shutdown: {se}")
        sys.exit(1)
    finally:
        logger.info("👋 Bot stopped")


if __name__ == "__main__":
    main()