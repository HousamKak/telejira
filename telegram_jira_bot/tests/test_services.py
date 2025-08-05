#!/usr/bin/env python3
"""
Unit tests for service classes in the Telegram-Jira bot.

Tests DatabaseManager, JiraService, and TelegramService classes
for functionality, error handling, and integration.
"""

import pytest
import aiohttp
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from telegram_jira_bot.services.database import DatabaseManager
from telegram_jira_bot.services.jira_service import JiraService, JiraAPIError
from telegram_jira_bot.services.telegram_service import TelegramService
from telegram_jira_bot.models.project import Project
from telegram_jira_bot.models.issue import JiraIssue
from telegram_jira_bot.models.user import User as BotUser
from telegram_jira_bot.models.enums import IssuePriority, IssueType, IssueStatus, UserRole


@pytest.mark.database
class TestDatabaseManager:
    """Test cases for DatabaseManager class."""
    
    @pytest.mark.asyncio
    async def test_database_initialization(self, temp_db_path: str) -> None:
        """Test database initialization and table creation."""
        db = DatabaseManager(db_path=temp_db_path, pool_size=1, timeout=30)
        
        await db.initialize()
        
        # Test that database is initialized
        assert db.is_initialized()
        
        # Test that tables exist
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = await cursor.fetchall()
            table_names = [table[0] for table in tables]
            
            # Expected tables (adjust based on your schema)
            expected_tables = ['users', 'projects', 'issues', 'comments', 'sessions']
            for table in expected_tables:
                assert table in table_names
        
        await db.close()
    
    @pytest.mark.asyncio
    async def test_user_operations(self, database: DatabaseManager) -> None:
        """Test user CRUD operations."""
        # Create user
        user_data = {
            'user_id': '123456789',
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User',
            'role': UserRole.USER.value,
            'is_active': True
        }
        
        user_id = await database.create_user(**user_data)
        assert isinstance(user_id, int)
        assert user_id > 0
        
        # Get user
        user = await database.get_user_by_telegram_id('123456789')
        assert user is not None
        assert user.user_id == '123456789'
        assert user.username == 'testuser'
        assert user.first_name == 'Test'
        assert user.role == UserRole.USER
        
        # Update user
        await database.update_user(
            user_id=user_id,
            username='updated_testuser',
            last_name='Updated'
        )
        
        updated_user = await database.get_user_by_id(user_id)
        assert updated_user is not None
        assert updated_user.username == 'updated_testuser'
        assert updated_user.last_name == 'Updated'
        
        # List users
        users = await database.get_all_users()
        assert len(users) >= 1
        assert any(u.user_id == '123456789' for u in users)
        
        # Delete user
        await database.delete_user(user_id)
        deleted_user = await database.get_user_by_id(user_id)
        assert deleted_user is None
    
    @pytest.mark.asyncio
    async def test_project_operations(self, database: DatabaseManager) -> None:
        """Test project CRUD operations."""
        # Create project
        project_data = {
            'key': 'TEST',
            'name': 'Test Project',
            'description': 'A test project',
            'jira_id': '10001',
            'is_active': True
        }
        
        project_id = await database.create_project(**project_data)
        assert isinstance(project_id, int)
        assert project_id > 0
        
        # Get project
        project = await database.get_project_by_key('TEST')
        assert project is not None
        assert project.key == 'TEST'
        assert project.name == 'Test Project'
        assert project.jira_id == '10001'
        
        # Update project
        await database.update_project(
            project_id=project_id,
            name='Updated Test Project',
            description='Updated description'
        )
        
        updated_project = await database.get_project_by_id(project_id)
        assert updated_project is not None
        assert updated_project.name == 'Updated Test Project'
        assert updated_project.description == 'Updated description'
        
        # List projects
        projects = await database.get_all_projects()
        assert len(projects) >= 1
        assert any(p.key == 'TEST' for p in projects)
        
        # Delete project
        await database.delete_project(project_id)
        deleted_project = await database.get_project_by_id(project_id)
        assert deleted_project is None
    
    @pytest.mark.asyncio
    async def test_issue_operations(self, database: DatabaseManager) -> None:
        """Test issue CRUD operations."""
        # First create user and project
        user_id = await database.create_user(
            user_id='123456789',
            username='testuser',
            first_name='Test',
            role=UserRole.USER.value,
            is_active=True
        )
        
        project_id = await database.create_project(
            key='TEST',
            name='Test Project',
            jira_id='10001',
            is_active=True
        )
        
        # Create issue
        issue_data = {
            'jira_id': '10001',
            'key': 'TEST-1',
            'summary': 'Test Issue',
            'description': 'Test description',
            'priority': IssuePriority.MEDIUM.value,
            'issue_type': IssueType.TASK.value,
            'status': IssueStatus.TODO.value,
            'project_id': project_id,
            'creator_id': user_id
        }
        
        issue_id = await database.create_issue(**issue_data)
        assert isinstance(issue_id, int)
        assert issue_id > 0
        
        # Get issue
        issue = await database.get_issue_by_key('TEST-1')
        assert issue is not None
        assert issue.key == 'TEST-1'
        assert issue.summary == 'Test Issue'
        assert issue.priority == IssuePriority.MEDIUM
        
        # Update issue
        await database.update_issue(
            issue_id=issue_id,
            summary='Updated Test Issue',
            status=IssueStatus.IN_PROGRESS.value
        )
        
        updated_issue = await database.get_issue_by_id(issue_id)
        assert updated_issue is not None
        assert updated_issue.summary == 'Updated Test Issue'
        assert updated_issue.status == IssueStatus.IN_PROGRESS
        
        # List issues by user
        user_issues = await database.get_issues_by_user(user_id)
        assert len(user_issues) >= 1
        assert any(i.key == 'TEST-1' for i in user_issues)
        
        # List issues by project
        project_issues = await database.get_issues_by_project(project_id)
        assert len(project_issues) >= 1
        assert any(i.key == 'TEST-1' for i in project_issues)
    
    @pytest.mark.asyncio
    async def test_connection_management(self, temp_db_path: str) -> None:
        """Test database connection management."""
        db = DatabaseManager(db_path=temp_db_path, pool_size=2, timeout=30)
        
        await db.initialize()
        
        # Test connection acquisition
        async with db.get_connection() as conn:
            assert conn is not None
            
            # Test query execution
            cursor = await conn.execute("SELECT 1")
            result = await cursor.fetchone()
            assert result[0] == 1
        
        # Test connection pool
        connections = []
        for _ in range(2):  # Pool size is 2
            conn = await db.get_connection().__aenter__()
            connections.append(conn)
        
        assert len(connections) == 2
        
        # Clean up connections
        for conn in connections:
            await db.get_connection().__aexit__(None, None, None)
        
        await db.close()
    
    @pytest.mark.asyncio
    async def test_transaction_management(self, database: DatabaseManager) -> None:
        """Test database transaction management."""
        # Test successful transaction
        async with database.transaction() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, first_name, role, is_active) VALUES (?, ?, ?, ?)",
                ('999888777', 'Transaction Test', UserRole.USER.value, True)
            )
        
        # Verify user was created
        user = await database.get_user_by_telegram_id('999888777')
        assert user is not None
        assert user.first_name == 'Transaction Test'
        
        # Test failed transaction (rollback)
        try:
            async with database.transaction() as conn:
                await conn.execute(
                    "INSERT INTO users (user_id, first_name, role, is_active) VALUES (?, ?, ?, ?)",
                    ('888777666', 'Rollback Test', UserRole.USER.value, True)
                )
                # Force an error
                await conn.execute("INVALID SQL STATEMENT")
        except Exception:
            pass  # Expected to fail
        
        # Verify user was not created due to rollback
        user = await database.get_user_by_telegram_id('888777666')
        assert user is None


@pytest.mark.network
class TestJiraService:
    """Test cases for JiraService class."""
    
    def test_jira_service_initialization(self) -> None:
        """Test JiraService initialization with valid parameters."""
        service = JiraService(
            domain="test.atlassian.net",
            email="test@example.com",
            api_token="test_token",
            timeout=30,
            max_retries=3
        )
        
        assert service.domain == "test.atlassian.net"
        assert service.email == "test@example.com"
        assert service.api_token == "test_token"
        assert service.timeout == 30
        assert service.max_retries == 3
    
    def test_jira_service_initialization_validation(self) -> None:
        """Test JiraService initialization with invalid parameters."""
        # Test empty domain
        with pytest.raises(ValueError, match="Domain cannot be empty"):
            JiraService(
                domain="",
                email="test@example.com",
                api_token="test_token"
            )
        
        # Test invalid email format
        with pytest.raises(ValueError, match="Invalid email format"):
            JiraService(
                domain="test.atlassian.net",
                email="invalid_email",
                api_token="test_token"
            )
        
        # Test empty API token
        with pytest.raises(ValueError, match="API token cannot be empty"):
            JiraService(
                domain="test.atlassian.net",
                email="test@example.com",
                api_token=""
            )
        
        # Test invalid timeout
        with pytest.raises(ValueError, match="Timeout must be positive"):
            JiraService(
                domain="test.atlassian.net",
                email="test@example.com",
                api_token="test_token",
                timeout=-1
            )
    
    @pytest.mark.asyncio
    async def test_jira_api_request_success(self, mock_aiohttp_session, mock_http_response) -> None:
        """Test successful Jira API request."""
        service = JiraService(
            domain="test.atlassian.net",
            email="test@example.com",
            api_token="test_token"
        )
        
        # Mock successful response
        mock_http_response.status = 200
        mock_http_response.json.return_value = {"status": "success", "data": "test"}
        mock_aiohttp_session.get.return_value = AsyncContextManagerMock(mock_http_response)
        
        # Patch the session
        with patch.object(service, '_session', mock_aiohttp_session):
            result = await service._make_request('GET', '/test/endpoint')
            
            assert result == {"status": "success", "data": "test"}
            mock_aiohttp_session.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_jira_api_request_error_handling(self, mock_aiohttp_session, mock_http_response) -> None:
        """Test Jira API request error handling."""
        service = JiraService(
            domain="test.atlassian.net",
            email="test@example.com",
            api_token="test_token"
        )
        
        # Mock error response
        mock_http_response.status = 404
        mock_http_response.json.return_value = {"error": "Not found"}
        mock_aiohttp_session.get.return_value = AsyncContextManagerMock(mock_http_response)
        
        with patch.object(service, '_session', mock_aiohttp_session):
            with pytest.raises(JiraAPIError) as exc_info:
                await service._make_request('GET', '/nonexistent/endpoint')
            
            assert exc_info.value.status_code == 404
            assert "Not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_jira_api_retry_logic(self, mock_aiohttp_session, mock_http_response) -> None:
        """Test Jira API retry logic for transient errors."""
        service = JiraService(
            domain="test.atlassian.net",
            email="test@example.com",
            api_token="test_token",
            max_retries=2,
            retry_delay=0.1  # Fast retry for testing
        )
        
        # Mock transient error followed by success
        responses = [
            # First call: server error
            AsyncContextManagerMock(MagicMock(status=500, json=AsyncMock(return_value={"error": "Server error"}))),
            # Second call: success
            AsyncContextManagerMock(MagicMock(status=200, json=AsyncMock(return_value={"data": "success"})))
        ]
        
        mock_aiohttp_session.get.side_effect = responses
        
        with patch.object(service, '_session', mock_aiohttp_session):
            result = await service._make_request('GET', '/test/endpoint')
            
            assert result == {"data": "success"}
            assert mock_aiohttp_session.get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_get_projects(self, mock_jira_service) -> None:
        """Test getting projects from Jira."""
        projects = await mock_jira_service.get_projects(max_results=10)
        
        assert isinstance(projects, list)
        assert len(projects) >= 1
        
        project = projects[0]
        assert 'id' in project
        assert 'key' in project
        assert 'name' in project
        
        mock_jira_service.get_projects.assert_called_once_with(max_results=10)
    
    @pytest.mark.asyncio
    async def test_create_issue(self, mock_jira_service) -> None:
        """Test creating an issue in Jira."""
        issue_data = {
            'project_key': 'TEST',
            'summary': 'Test Issue',
            'description': 'Test description',
            'issue_type': 'Task',
            'priority': 'Medium'
        }
        
        issue = await mock_jira_service.create_issue(**issue_data)
        
        assert isinstance(issue, dict)
        assert 'id' in issue
        assert 'key' in issue
        assert 'fields' in issue
        
        fields = issue['fields']
        assert fields['summary'] == 'Test Issue'
        assert fields['priority']['name'] == 'Medium'
        
        mock_jira_service.create_issue.assert_called_once_with(**issue_data)
    
    @pytest.mark.asyncio
    async def test_search_issues(self, mock_jira_service) -> None:
        """Test searching issues in Jira."""
        jql = 'project = TEST AND status = "To Do"'
        
        result = await mock_jira_service.search_issues(jql=jql, max_results=50)
        
        assert isinstance(result, dict)
        assert 'issues' in result
        assert 'total' in result
        assert isinstance(result['issues'], list)
        
        if result['issues']:
            issue = result['issues'][0]
            assert 'id' in issue
            assert 'key' in issue
            assert 'fields' in issue
        
        mock_jira_service.search_issues.assert_called_once_with(jql=jql, max_results=50)
    
    @pytest.mark.asyncio
    async def test_get_current_user(self, mock_jira_service) -> None:
        """Test getting current user information from Jira."""
        user = await mock_jira_service.get_current_user()
        
        assert isinstance(user, dict)
        assert 'displayName' in user
        assert 'emailAddress' in user
        
        mock_jira_service.get_current_user.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_jira_service_context_manager(self) -> None:
        """Test JiraService as async context manager."""
        async with JiraService(
            domain="test.atlassian.net",
            email="test@example.com",
            api_token="test_token"
        ) as service:
            assert service is not None
            assert hasattr(service, '_session')
        
        # Session should be closed after context exit
        assert service._session is None or service._session.closed


class TestTelegramService:
    """Test cases for TelegramService class."""
    
    def test_telegram_service_initialization(self) -> None:
        """Test TelegramService initialization."""
        service = TelegramService(
            token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            timeout=30
        )
        
        assert service.token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert service.timeout == 30
    
    def test_telegram_service_initialization_validation(self) -> None:
        """Test TelegramService initialization validation."""
        # Test empty token
        with pytest.raises(ValueError, match="Token cannot be empty"):
            TelegramService(token="")
        
        # Test invalid timeout
        with pytest.raises(ValueError, match="Timeout must be positive"):
            TelegramService(token="valid_token", timeout=-1)
    
    @pytest.mark.asyncio
    async def test_send_message(self, mock_telegram_service) -> None:
        """Test sending a message via Telegram."""
        chat_id = 123456789
        text = "Test message"
        
        result = await mock_telegram_service.send_message(
            chat_id=chat_id,
            text=text
        )
        
        assert result is not None
        mock_telegram_service.send_message.assert_called_once_with(
            chat_id=chat_id,
            text=text
        )
    
    @pytest.mark.asyncio
    async def test_send_message_with_markup(self, mock_telegram_service) -> None:
        """Test sending a message with inline keyboard markup."""
        chat_id = 123456789
        text = "Test message with buttons"
        reply_markup = {
            "inline_keyboard": [
                [{"text": "Button 1", "callback_data": "btn1"}],
                [{"text": "Button 2", "callback_data": "btn2"}]
            ]
        }
        
        result = await mock_telegram_service.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )
        
        assert result is not None
        mock_telegram_service.send_message.assert_called_once_with(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )
    
    @pytest.mark.asyncio
    async def test_edit_message(self, mock_telegram_service) -> None:
        """Test editing a message."""
        chat_id = 123456789
        message_id = 1
        text = "Edited message"
        
        result = await mock_telegram_service.edit_message(
            chat_id=chat_id,
            message_id=message_id,
            text=text
        )
        
        assert result is not None
        mock_telegram_service.edit_message.assert_called_once_with(
            chat_id=chat_id,
            message_id=message_id,
            text=text
        )
    
    @pytest.mark.asyncio
    async def test_delete_message(self, mock_telegram_service) -> None:
        """Test deleting a message."""
        chat_id = 123456789
        message_id = 1
        
        result = await mock_telegram_service.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
        
        assert result is True
        mock_telegram_service.delete_message.assert_called_once_with(
            chat_id=chat_id,
            message_id=message_id
        )
    
    @pytest.mark.asyncio
    async def test_send_photo(self, mock_telegram_service) -> None:
        """Test sending a photo."""
        chat_id = 123456789
        photo_data = b"fake_photo_data"
        caption = "Test photo"
        
        result = await mock_telegram_service.send_photo(
            chat_id=chat_id,
            photo=photo_data,
            caption=caption
        )
        
        assert result is not None
        mock_telegram_service.send_photo.assert_called_once_with(
            chat_id=chat_id,
            photo=photo_data,
            caption=caption
        )


class TestServiceIntegration:
    """Test cases for service integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_database_jira_sync(
        self, 
        database: DatabaseManager, 
        mock_jira_service
    ) -> None:
        """Test synchronization between database and Jira service."""
        # Create a project in database
        project_id = await database.create_project(
            key='TEST',
            name='Test Project',
            jira_id='10001',
            is_active=True
        )
        
        # Mock Jira project data  
        mock_jira_service.get_project.return_value = {
            'id': '10001',
            'key': 'TEST',
            'name': 'Updated Test Project',
            'description': 'Updated from Jira'
        }
        
        # Simulate sync operation
        jira_project = await mock_jira_service.get_project('TEST')
        
        # Update database with Jira data
        await database.update_project(
            project_id=project_id,
            name=jira_project['name'],
            description=jira_project.get('description')
        )
        
        # Verify sync
        updated_project = await database.get_project_by_id(project_id)
        assert updated_project is not None
        assert updated_project.name == 'Updated Test Project'
        assert updated_project.description == 'Updated from Jira'
    
    @pytest.mark.asyncio
    async def test_error_propagation(
        self, 
        database: DatabaseManager,
        mock_jira_service
    ) -> None:
        """Test error propagation between services."""
        # Mock Jira service to raise an error
        mock_jira_service.create_issue.side_effect = JiraAPIError(
            "Failed to create issue",
            status_code=400
        )
        
        # Create user and project first
        user_id = await database.create_user(
            user_id='123456789',
            first_name='Test',
            role=UserRole.USER.value,
            is_active=True
        )
        
        project_id = await database.create_project(
            key='TEST',
            name='Test Project',
            jira_id='10001',
            is_active=True
        )
        
        # Try to create issue - should handle Jira error gracefully
        with pytest.raises(JiraAPIError):
            await mock_jira_service.create_issue(
                project_key='TEST',
                summary='Test Issue',
                issue_type='Task'
            )
        
        # Database should remain consistent
        user = await database.get_user_by_id(user_id)
        project = await database.get_project_by_id(project_id)
        assert user is not None
        assert project is not None


class AsyncContextManagerMock:
    """Helper class for mocking async context managers."""
    
    def __init__(self, return_value):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass