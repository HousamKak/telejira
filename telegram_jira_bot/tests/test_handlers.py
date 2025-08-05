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
            database=database,
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
    
    # This would call a start_command method if it exists on BaseHandler
    # Note: start_command may need to be implemented in BaseHandler or tested via subclass
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
        # Mock existing user
        base_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        base_handler.database.update_user = AsyncMock()
        
        await base_handler.start_command(telegram_update, mock_context)
        
        # Verify no user creation for existing users
        base_handler.database.get_user_by_telegram_id.assert_called_once()
        base_handler.database.update_user.assert_called_once()  # Update last activity
        
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
        base_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
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
        base_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        base_handler.database.get_user_stats = AsyncMock(return_value={
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
    async def test_permission_check_user(
        self,
        base_handler: BaseHandler,
        sample_user: BotUser
    ) -> None:
        """Test permission checking for regular user."""
        # User role
        result = await base_handler._check_user_permission(sample_user, UserRole.USER)
        assert result is True
        
        # Admin role (should fail for regular user)
        result = await base_handler._check_user_permission(sample_user, UserRole.ADMIN)
        assert result is False
        
        # Super admin role (should fail for regular user)  
        result = await base_handler._check_user_permission(sample_user, UserRole.SUPER_ADMIN)
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
        result = await base_handler._check_user_permission(admin_user, UserRole.USER)
        assert result is True
        
        # Admin role
        result = await base_handler._check_user_permission(admin_user, UserRole.ADMIN)
        assert result is True
        
        # Super admin role (should fail for regular admin)
        result = await base_handler._check_user_permission(admin_user, UserRole.SUPER_ADMIN)
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
        base_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        # Create update with callback query
        update = Update(update_id=1, callback_query=telegram_callback_query)
        
        await base_handler.handle_callback_query(update, mock_context)
        
        # Verify callback query was answered
        mock_context.bot.answer_callback_query.assert_called_once()


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
            database=database,
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
        project_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        project_handler.database.get_all_projects = AsyncMock(return_value=sample_projects)
        
        await project_handler.list_projects(telegram_update, mock_context)
        
        # Verify projects were fetched
        project_handler.database.get_all_projects.assert_called_once()
        
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
        
        project_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        project_handler.database.get_project_by_key = AsyncMock(return_value=sample_project)
        project_handler.database.update_user = AsyncMock()
        
        await project_handler.set_default_project(telegram_update, mock_context)
        
        # Verify project lookup
        project_handler.database.get_project_by_key.assert_called_once_with('TEST')
        
        # Verify user update
        project_handler.database.update_user.assert_called_once()
        
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
        mock_context.args = ['INVALID']
        
        project_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        project_handler.database.get_project_by_key = AsyncMock(return_value=None)
        
        await project_handler.set_default_project(telegram_update, mock_context)
        
        # Verify error message
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "not found" in call_args[1]['text'].lower()


class TestIssueHandlers:
    """Test cases for IssueHandlers class."""
    
    @pytest.fixture
    def issue_handler(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service
    ) -> IssueHandlers:
        """Create IssueHandlers instance for testing."""
        return IssueHandlers(
            config=test_config,
            database=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
    
    @pytest.mark.asyncio
    async def test_create_issue_wizard(
        self,
        issue_handler: IssueHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_projects: List[Project]
    ) -> None:
        """Test /create command handling."""
        issue_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        issue_handler.database.get_all_projects = AsyncMock(return_value=sample_projects)
        
        await issue_handler.create_issue_wizard(telegram_update, mock_context)
        
        # Verify projects were fetched for selection
        issue_handler.database.get_all_projects.assert_called_once()
        
        # Verify message with project selection was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        assert 'reply_markup' in call_args[1]  # Should have inline keyboard
    
    @pytest.mark.asyncio
    async def test_list_user_issues(
        self,
        issue_handler: IssueHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_issue: JiraIssue
    ) -> None:
        """Test /myissues command handling."""
        issue_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        issue_handler.database.get_issues_by_user = AsyncMock(return_value=[sample_issue])
        
        await issue_handler.list_user_issues(telegram_update, mock_context)
        
        # Verify user issues were fetched
        issue_handler.database.get_issues_by_user.assert_called_once_with(
            sample_user.id, 
            limit=issue_handler.config.max_issues_per_page
        )
        
        # Verify message was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        issues_text = call_args[1]['text']
        
        # Check that issue information is included
        assert sample_issue.key in issues_text
        assert sample_issue.summary in issues_text
    
    @pytest.mark.asyncio
    async def test_handle_message_issue_creation(
        self,
        issue_handler: IssueHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_project: Project
    ) -> None:
        """Test issue creation from plain text message."""
        # Set user with default project
        sample_user.default_project_id = sample_project.id
        
        # Modify update to have plain text message
        telegram_update.message.text = "HIGH BUG Login button not working"
        
        issue_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        issue_handler.database.get_project_by_id = AsyncMock(return_value=sample_project)
        issue_handler.database.create_issue = AsyncMock(return_value=1)
        
        # Mock successful Jira issue creation
        mock_jira_issue = {
            'id': '10001',
            'key': 'TEST-1',
            'fields': {
                'summary': 'Login button not working',
                'priority': {'name': 'High'},
                'issuetype': {'name': 'Bug'},
                'status': {'name': 'To Do'}
            }
        }
        issue_handler.jira_service.create_issue = AsyncMock(return_value=mock_jira_issue)
        
        await issue_handler.handle_message_issue_creation(telegram_update, mock_context)
        
        # Verify Jira issue creation
        issue_handler.jira_service.create_issue.assert_called_once()
        
        # Verify database issue creation
        issue_handler.database.create_issue.assert_called_once()
        
        # Verify success message
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert 'TEST-1' in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_search_issues(
        self,
        issue_handler: IssueHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /searchissues command handling."""
        mock_context.args = ['login', 'error']
        
        issue_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        issue_handler.database.search_issues = AsyncMock(return_value=[])
        
        await issue_handler.search_issues(telegram_update, mock_context)
        
        # Verify search was performed
        issue_handler.database.search_issues.assert_called_once()
        
        # Verify message was sent
        mock_context.bot.send_message.assert_called_once()


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
            database=database,
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
        
        admin_handler.database.get_user_by_telegram_id = AsyncMock(return_value=admin_user)
        admin_handler.database.get_project_by_key = AsyncMock(return_value=None)
        admin_handler.database.create_project = AsyncMock(return_value=1)
        
        # Mock Jira project creation
        mock_jira_project = {
            'id': '10003',
            'key': 'NEWPROJ',
            'name': 'New Project'
        }
        admin_handler.jira_service.create_project = AsyncMock(return_value=mock_jira_project)
        
        await admin_handler.add_project(telegram_update, mock_context)
        
        # Verify project creation
        admin_handler.database.create_project.assert_called_once()
        
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
        
        admin_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        await admin_handler.add_project(telegram_update, mock_context)
        
        # Verify permission denied message
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert 'permission' in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_list_users(
        self,
        admin_handler: AdminHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        admin_user: BotUser,
        sample_user: BotUser
    ) -> None:
        """Test /users command handling."""
        admin_handler.database.get_user_by_telegram_id = AsyncMock(return_value=admin_user)
        admin_handler.database.get_all_users = AsyncMock(return_value=[admin_user, sample_user])
        admin_handler.database.get_user_stats = AsyncMock(return_value={
            'total_issues': 10,
            'active_issues': 7
        })
        
        await admin_handler.list_users(telegram_update, mock_context)
        
        # Verify users were fetched
        admin_handler.database.get_all_users.assert_called_once()
        
        # Verify message was sent
        mock_context.bot.send_message.assert_called_once()
        
        call_args = mock_context.bot.send_message.call_args
        users_text = call_args[1]['text']
        
        # Check that user information is included
        assert admin_user.get_display_name() in users_text
        assert sample_user.get_display_name() in users_text
    
    @pytest.mark.asyncio
    async def test_sync_jira(
        self,
        admin_handler: AdminHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        admin_user: BotUser
    ) -> None:
        """Test /syncjira command handling."""
        admin_handler.database.get_user_by_telegram_id = AsyncMock(return_value=admin_user)
        admin_handler.database.get_all_projects = AsyncMock(return_value=[])
        
        await admin_handler.sync_jira(telegram_update, mock_context)
        
        # Verify sync started message
        mock_context.bot.send_message.assert_called()
        
        # Check that sync operation was initiated
        call_args_list = mock_context.bot.send_message.call_args_list
        sync_messages = [call[1]['text'] for call in call_args_list]
        assert any('sync' in msg.lower() for msg in sync_messages)


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
            database=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
    
    @pytest.mark.asyncio
    async def test_start_wizard(
        self,
        wizard_handler: WizardHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test /wizard command handling."""
        wizard_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        
        result = await wizard_handler.start_wizard(telegram_update, mock_context)
        
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
    async def test_wizard_conversation_flow(
        self,
        wizard_handler: WizardHandlers,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser,
        sample_projects: List[Project]
    ) -> None:
        """Test wizard conversation flow."""
        wizard_handler.database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        wizard_handler.database.get_all_projects = AsyncMock(return_value=sample_projects)
        
        # Start wizard
        await wizard_handler.start_wizard(telegram_update, mock_context)
        
        # Simulate project selection
        telegram_update.message.text = "1"  # Select first project
        
        result = await wizard_handler.handle_project_selection(telegram_update, mock_context)
        
        # Should move to next step
        assert isinstance(result, int)
        
        # Verify project selection message
        mock_context.bot.send_message.assert_called()


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
        admin_handler = AdminHandlers(
            config=test_config,
            database=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        # Test admin command with regular user
        regular_user = BotUser(
            id=1,
            user_id="123456789",
            username="regularuser",
            first_name="Regular",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc)
        )
        
        database.get_user_by_telegram_id = AsyncMock(return_value=regular_user)
        mock_context.args = ['TEST', 'Test Project']
        
        await admin_handler.add_project(telegram_update, mock_context)
        
        # Should receive permission denied
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert 'permission' in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_error_handling_in_handlers(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test error handling in command handlers."""
        issue_handler = IssueHandlers(
            config=test_config,
            database=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        # Mock database error
        database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        database.get_issues_by_user = AsyncMock(side_effect=Exception("Database error"))
        
        await issue_handler.list_user_issues(telegram_update, mock_context)
        
        # Should handle error gracefully
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert 'error' in call_args[1]['text'].lower()
    
    @pytest.mark.asyncio
    async def test_user_session_management(
        self,
        test_config,
        database,
        mock_jira_service,
        mock_telegram_service,
        telegram_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
        sample_user: BotUser
    ) -> None:
        """Test user session management across handlers."""
        base_handler = BaseHandler(
            config=test_config,
            database=database,
            jira_service=mock_jira_service,
            telegram_service=mock_telegram_service
        )
        
        database.get_user_by_telegram_id = AsyncMock(return_value=sample_user)
        database.update_user = AsyncMock()
        
        # Simulate multiple commands from same user
        await base_handler.start_command(telegram_update, mock_context)
        await base_handler.help_command(telegram_update, mock_context)
        await base_handler.status_command(telegram_update, mock_context)
        
        # User should be looked up multiple times
        assert database.get_user_by_telegram_id.call_count == 3
        
        # Last activity should be updated
        assert database.update_user.called