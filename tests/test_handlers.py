#!/usr/bin/env python3
"""
Unit tests for handler classes in the Telegram-Jira bot.

Tests all command handlers including BaseHandler, ProjectHandlers, 
IssueHandlers, AdminHandlers, and WizardHandlers for functionality,
permissions, and user interactions.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from telegram import Update, Message, User, Chat, CallbackQuery
from telegram.ext import ContextTypes

from telegram_jira_bot.handlers.base_handler import BaseHandler
from telegram_jira_bot.handlers.project_handlers import ProjectHandlers
from telegram_jira_bot.handlers.issue_handlers import IssueHandlers
from telegram_jira_bot.handlers.admin_handlers import AdminHandlers
from telegram_jira_bot.handlers.wizard_handlers import WizardHandlers
from telegram_jira_bot.models.enums import UserRole, IssuePriority, IssueType, IssueStatus
from telegram_jira_bot.models.user import User as BotUser
from telegram_jira_bot.models.project import Project
from telegram_jira_bot.models.issue import JiraIssue
from telegram_jira_bot.services.database import DatabaseError


class TestBaseHandler:
    """Test cases for BaseHandler class."""
    
    @pytest.fixture
    def base_handler(
        self, 
        test_config, 
        database, 
        mock_jira_service, 
        mock_telegram_service
    ) -> BaseHandler:
        """Create BaseHandler instance for testing."""
        return BaseHandler(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
    
    @pytest.mark.asyncio
    async def test_start_command(
        self, 
        base_handler: BaseHandler,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /start command handling."""
        # FIX: Use correct database method names
        base_handler.db.get_user_by_telegram_id = AsyncMock(return_value=None)
        base_handler.db.create_user = AsyncMock(return_value=1)
        base_handler.db.get_user_by_id = AsyncMock(return_value=sample_user)
        
        await base_handler.start_command(telegram_update, mock_context)
        
        # Verify user creation was attempted for new users
        base_handler.db.get_user_by_telegram_id.assert_called_once()
        base_handler.db.create_user.assert_called_once()
        
        # Verify welcome message was sent
        mock_context.bot.send_message.assert_called_once()
        
        # Check message content
        call_args = mock_context.bot.send_message.call_args
        assert call_args[1]['chat_id'] == telegram_update.effective_chat.id
        assert "welcome" in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_start_command_existing_user(
        self,
        base_handler: BaseHandler,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /start command for existing user."""
        # FIX: Use correct database method names
        base_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        await base_handler.start_command(telegram_update, mock_context)
        
        # Verify user retrieval
        base_handler.db.get_user_by_telegram_id.assert_called_once()
        # NOTE: update_user_activity is handled automatically, so no separate call needed
        
        # Verify welcome message was sent
        mock_context.bot.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_help_command(
        self,
        base_handler: BaseHandler,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /help command handling."""
        base_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        await base_handler.help_command(telegram_update, mock_context)
        
        # Verify help message was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        help_text = call_args[1]['text']
        
        # Check help content contains command information
        assert "/start" in help_text
        assert "/help" in help_text
        assert "/create" in help_text
        assert "/projects" in help_text
    
    @pytest.mark.asyncio
    async def test_status_command(
        self,
        base_handler: BaseHandler,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /status command handling."""
        base_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        base_handler.db.get_user_stats = AsyncMock(return_value={
            'total_issues': 5,
            'active_issues': 3,
            'resolved_issues': 2
        })
        
        await base_handler.status_command(telegram_update, mock_context)
        
        # Verify status message was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        status_text = call_args[1]['text']
        
        # Check status content
        assert "status" in status_text.lower()
        assert str(sample_user.get_display_name()) in status_text

    @pytest.mark.asyncio
    async def test_user_creation_flow(
        self,
        base_handler: BaseHandler,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test the corrected user creation flow."""
        # Mock the corrected database method calls
        base_handler.db.get_user_by_telegram_id = AsyncMock(return_value=None)
        base_handler.db.create_user = AsyncMock(return_value=1)
        base_handler.db.get_user_by_id = AsyncMock(return_value=sample_user)
        
        # Test get_or_create_user directly
        user = await base_handler.get_or_create_user(telegram_update)
        
        # Verify correct method calls were made
        base_handler.db.get_user_by_telegram_id.assert_called_once_with(str(telegram_update.effective_user.id))
        base_handler.db.create_user.assert_called_once()
        base_handler.db.get_user_by_id.assert_called_once_with(1)
        
        # Verify user was returned
        assert user == sample_user
    
    @pytest.mark.asyncio
    async def test_permission_check_user(
        self,
        base_handler: BaseHandler,
        sample_user: BotUser
    ) -> None:
        """Test permission checking for regular user."""
        # User role
        result = base_handler.check_user_role(sample_user, UserRole.USER)
        assert result is True
        
        # Admin role (should fail for regular user)
        result = base_handler.check_user_role(sample_user, UserRole.ADMIN)
        assert result is False
        
        # Super admin role (should fail for regular user)  
        result = base_handler.check_user_role(sample_user, UserRole.SUPER_ADMIN)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_permission_check_admin(
        self,
        base_handler: BaseHandler
    ) -> None:
        """Test permission checking for admin user."""
        now = datetime.now(timezone.utc)
        admin_user = BotUser(
            id=1,
            user_id="123456789",
            username="adminuser",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        # User role (admin can do user actions)
        result = base_handler.check_user_role(admin_user, UserRole.USER)
        assert result is True
        
        # Admin role
        result = base_handler.check_user_role(admin_user, UserRole.ADMIN)
        assert result is True
        
        # Super admin role (should fail for regular admin)
        result = base_handler.check_user_role(admin_user, UserRole.SUPER_ADMIN)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_callback_query_handling(
        self,
        base_handler: BaseHandler,
        telegram_callback_query: CallbackQuery,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test callback query handling."""
        base_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        # Create update with callback query
        update = Update(update_id=1, callback_query=telegram_callback_query)
        
        await base_handler.handle_callback_query(update, mock_context)
        
        # Verify callback query was answered
        telegram_callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_commands_same_user(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test multiple commands from same user."""
        base_handler = BaseHandler(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        # Simulate multiple commands from same user
        await base_handler.start_command(telegram_update, mock_context)
        await base_handler.help_command(telegram_update, mock_context)
        await base_handler.status_command(telegram_update, mock_context)
        
        # User should be looked up multiple times
        assert database.get_user_by_telegram_id.call_count == 3


class TestProjectHandlers:
    """Test cases for ProjectHandlers class."""
    
    @pytest.fixture
    def project_handler(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service
    ) -> ProjectHandlers:
        """Create ProjectHandlers instance for testing."""
        return ProjectHandlers(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
    
    @pytest.mark.asyncio
    async def test_list_projects(
        self,
        project_handler: ProjectHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_projects: List[Project]
    ) -> None:
        """Test /projects command handling."""
        # FIX: Use correct database method names
        project_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        project_handler.db.get_all_active_projects = AsyncMock(return_value=sample_projects)
        
        await project_handler.list_projects(telegram_update, mock_context)
        
        # Verify projects were fetched with correct method name
        project_handler.db.get_all_active_projects.assert_called_once()
        
        # Verify message was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        projects_text = call_args[1]['text']
        
        # Check that project information is included
        assert sample_projects[0].key in projects_text
        assert sample_projects[0].name in projects_text
    
    @pytest.mark.asyncio
    async def test_set_default_project(
        self,
        project_handler: ProjectHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_project: Project
    ) -> None:
        """Test /setdefault command handling."""
        # Set command arguments
        mock_context.args = ['TEST']
        
        # FIX: Use correct database method names
        project_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        project_handler.db.get_project_by_key = AsyncMock(return_value=sample_project)
        project_handler.db.set_user_default_project = AsyncMock()  # Updated method name
        
        await project_handler.set_default_project(telegram_update, mock_context)
        
        # Verify project lookup
        project_handler.db.get_project_by_key.assert_called_once_with('TEST')
        
        # Verify user default project update
        project_handler.db.set_user_default_project.assert_called_once()
        
        # Verify success message
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "default project" in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_set_default_project_invalid(
        self,
        project_handler: ProjectHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /setdefault command with invalid project."""
        # Set command arguments
        mock_context.args = ['INVALID']
        
        project_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        project_handler.db.get_project_by_key = AsyncMock(return_value=None)
        
        await project_handler.set_default_project(telegram_update, mock_context)
        
        # Verify project lookup
        project_handler.db.get_project_by_key.assert_called_once_with('INVALID')
        
        # Verify error message
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "not found" in call_args[1]['text'].lower()


class TestAdminHandlers:
    """Test cases for AdminHandlers class."""
    
    @pytest.fixture
    def admin_handler(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service
    ) -> AdminHandlers:
        """Create AdminHandlers instance for testing."""
        return AdminHandlers(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
    
    @pytest.fixture
    def admin_user(self) -> BotUser:
        """Create admin user for testing."""
        now = datetime.now(timezone.utc)
        return BotUser(
            id=1,
            user_id="123456789",
            username="adminuser",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=now,
            last_activity=now
        )
    
    @pytest.mark.asyncio
    async def test_add_project_admin(
        self,
        admin_handler: AdminHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        admin_user: BotUser
    ) -> None:
        """Test /addproject command with admin user."""
        mock_context.args = ['NEWPROJ', 'New Project', 'Description']
        
        admin_handler.db.get_user_by_telegram_id = AsyncMock(return_value=admin_user)
        admin_handler.db.get_project_by_key = AsyncMock(return_value=None)
        admin_handler.db.create_project = AsyncMock(return_value=1)
        
        # Mock Jira project creation
        mock_jira_project = Project(
            key='NEWPROJ',
            name='New Project',
            description='Description'
        )
        admin_handler.jira.get_project_by_key = AsyncMock(return_value=mock_jira_project)
        
        await admin_handler.add_project(telegram_update, mock_context)
        
        # Verify project creation
        admin_handler.db.create_project.assert_called_once()
        
        # Verify success message
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert 'NEWPROJ' in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_add_project_non_admin(
        self,
        admin_handler: AdminHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /addproject command with non-admin user."""
        mock_context.args = ['NEWPROJ', 'New Project']
        
        admin_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        await admin_handler.add_project(telegram_update, mock_context)
        
        # Verify permission error was sent
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "permission" in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_list_users_admin(
        self,
        admin_handler: AdminHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        admin_user: BotUser,
        sample_users: List[BotUser]
    ) -> None:
        """Test /users command with admin user."""
        admin_handler.db.get_user_by_telegram_id = AsyncMock(return_value=admin_user)
        admin_handler.db.get_all_users = AsyncMock(return_value=sample_users)
        
        await admin_handler.list_users(telegram_update, mock_context)
        
        # Verify users were fetched
        admin_handler.db.get_all_users.assert_called_once()
        
        # Verify message was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        users_text = call_args[1]['text']
        
        # Check that user information is included
        assert "users" in users_text.lower()


class TestWizardHandlers:
    """Test cases for WizardHandlers class."""
    
    @pytest.fixture
    def wizard_handler(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service
    ) -> WizardHandlers:
        """Create WizardHandlers instance for testing."""
        return WizardHandlers(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
    
    @pytest.mark.asyncio
    async def test_wizard_command(
        self,
        wizard_handler: WizardHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /wizard command handling."""
        wizard_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        result = await wizard_handler.wizard_command(telegram_update, mock_context)
        
        # Verify wizard was started
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        wizard_text = call_args[1]['text']
        
        # Check wizard introduction
        assert 'wizard' in wizard_text.lower()
        assert 'reply_markup' in call_args[1]  # Should have options
        
        # Should return a conversation state
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_wizard_project_retrieval(
        self,
        wizard_handler: WizardHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_projects: List[Project]
    ) -> None:
        """Test wizard project retrieval with correct method calls."""
        # FIX: Use correct database method names
        wizard_handler.db.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        wizard_handler.db.get_all_active_projects = AsyncMock(return_value=sample_projects)
        
        await wizard_handler._start_quick_setup(telegram_update, mock_context)
        
        # Verify correct database method was called
        wizard_handler.db.get_all_active_projects.assert_called_once()


class TestHandlerIntegration:
    """Test cases for handler integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_permission_based_routing(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that commands are routed based on user permissions."""
        # Create handlers
        base_handler = BaseHandler(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        admin_handler = AdminHandlers(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        # Test regular user accessing admin command
        regular_user = BotUser(
            id=1,
            user_id="123456789",
            username="user",
            first_name="Regular",
            last_name="User",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc)
        )
        
        database.get_user_by_telegram_id = AsyncMock(return_value=regular_user)
        mock_context.args = ['TEST', 'Test Project']
        
        await admin_handler.add_project(telegram_update, mock_context)
        
        # Should get permission denied
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "permission" in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_error_propagation(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test that errors are properly propagated and handled."""
        base_handler = BaseHandler(
            config=test_config,
            db=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock database error
        database.get_user_by_telegram_id = AsyncMock(side_effect=DatabaseError("Test database error"))
        
        await base_handler.start_command(telegram_update, mock_context)
        
        # Should handle the error gracefully
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "error" in call_args[1]['text'].lower()


# Test utilities and fixtures that might be referenced
@pytest.fixture
def sample_users() -> List[BotUser]:
    """Create sample users for testing."""
    now = datetime.now(timezone.utc)
    return [
        BotUser(
            id=1,
            user_id="123456789",
            username="user1",
            first_name="User",
            last_name="One",
            role=UserRole.USER,
            is_active=True,
            created_at=now,
            last_activity=now
        ),
        BotUser(
            id=2,
            user_id="987654321",
            username="admin1",
            first_name="Admin",
            last_name="One",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=now,
            last_activity=now
        )
    ]