#!/usr/bin/env python3
"""
Pytest configuration and fixtures for the Telegram-Jira bot test suite.

Contains shared fixtures, test configuration, and utilities for testing
all components of the bot including services, handlers, and models.
"""

import asyncio
import os
import tempfile
import pytest
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator, Generator
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

import aiohttp
from telegram import Update, Message, User, Chat, CallbackQuery
from telegram.ext import Application, ContextTypes

# Add the parent directory to Python path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import BotConfig
from services.database import DatabaseManager
from services.jira_service import JiraService
from services.telegram_service import TelegramService
from models.project import Project
from models.issue import JiraIssue
from models.user import User as BotUser
from models.enums import IssuePriority, IssueType, IssueStatus, UserRole


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config() -> BotConfig:
    """Create a test configuration with safe defaults.
    
    Returns:
        BotConfig: Test configuration with mock values
    """
    return BotConfig(
        telegram_token="TEST_TOKEN:123456789",
        jira_domain="test.atlassian.net",
        jira_email="test@example.com",
        jira_api_token="test_api_token",
        database_path=":memory:",  # Use in-memory database for tests
        log_level="DEBUG",
        max_summary_length=100,
        max_description_length=2000,
        allowed_users=["123456789", "987654321"],
        admin_users=["123456789"],
        super_admin_users=["123456789"],
        enable_wizards=True,
        enable_shortcuts=True,
    )


@pytest.fixture
async def database(test_config: BotConfig) -> AsyncGenerator[DatabaseManager, None]:
    """Create and initialize a test database.
    
    Args:
        test_config: Test configuration
        
    Yields:
        DatabaseManager: Initialized test database
    """
    db = DatabaseManager(
        db_path=":memory:",
        pool_size=1,
        timeout=30
    )
    
    await db.initialize()
    
    yield db
    
    await db.close()


@pytest.fixture
def mock_jira_service() -> JiraService:
    """Create a mock Jira service for testing.
    
    Returns:
        JiraService: Mock Jira service with predefined responses
    """
    service = MagicMock(spec=JiraService)
    
    # Mock async methods
    service.get_projects = AsyncMock(return_value=[
        {
            "id": "10001",
            "key": "TEST",
            "name": "Test Project",
            "description": "A test project",
            "projectTypeKey": "software",
            "lead": {"displayName": "Test User"}
        },
        {
            "id": "10002", 
            "key": "DEMO",
            "name": "Demo Project",
            "description": "A demo project",
            "projectTypeKey": "business",
            "lead": {"displayName": "Demo User"}
        }
    ])
    
    service.get_project = AsyncMock(return_value={
        "id": "10001",
        "key": "TEST",
        "name": "Test Project",
        "description": "A test project",
        "projectTypeKey": "software",
        "lead": {"displayName": "Test User"}
    })
    
    service.create_issue = AsyncMock(return_value={
        "id": "10001",
        "key": "TEST-1",
        "fields": {
            "summary": "Test Issue",
            "description": "Test description",
            "priority": {"name": "Medium"},
            "issuetype": {"name": "Task"},
            "status": {"name": "To Do"},
            "created": "2023-01-01T00:00:00.000+0000",
            "updated": "2023-01-01T00:00:00.000+0000",
            "assignee": None,
            "reporter": {"displayName": "Test User"}
        }
    })
    
    service.get_issue = AsyncMock(return_value={
        "id": "10001", 
        "key": "TEST-1",
        "fields": {
            "summary": "Test Issue",
            "description": "Test description", 
            "priority": {"name": "Medium"},
            "issuetype": {"name": "Task"},
            "status": {"name": "To Do"},
            "created": "2023-01-01T00:00:00.000+0000",
            "updated": "2023-01-01T00:00:00.000+0000",
            "assignee": None,
            "reporter": {"displayName": "Test User"}
        }
    })
    
    service.search_issues = AsyncMock(return_value={
        "issues": [
            {
                "id": "10001",
                "key": "TEST-1", 
                "fields": {
                    "summary": "Test Issue",
                    "description": "Test description",
                    "priority": {"name": "Medium"},
                    "issuetype": {"name": "Task"},
                    "status": {"name": "To Do"},
                    "created": "2023-01-01T00:00:00.000+0000",
                    "updated": "2023-01-01T00:00:00.000+0000",
                    "assignee": None,
                    "reporter": {"displayName": "Test User"}
                }
            }
        ],
        "total": 1,
        "startAt": 0,
        "maxResults": 50
    })
    
    service.get_current_user = AsyncMock(return_value={
        "displayName": "Test User",
        "emailAddress": "test@example.com",
        "accountId": "test_account_id"
    })
    
    service.update_issue = AsyncMock(return_value=True)
    service.delete_issue = AsyncMock(return_value=True)
    service.transition_issue = AsyncMock(return_value=True)
    service.add_comment = AsyncMock(return_value={
        "id": "10001",
        "body": "Test comment",
        "author": {"displayName": "Test User"},
        "created": "2023-01-01T00:00:00.000+0000"
    })
    
    service.close = AsyncMock()
    
    return service


@pytest.fixture
def mock_telegram_service() -> TelegramService:
    """Create a mock Telegram service for testing.
    
    Returns:
        TelegramService: Mock Telegram service
    """
    service = MagicMock(spec=TelegramService)
    service.send_message = AsyncMock(return_value=MagicMock())
    service.edit_message = AsyncMock(return_value=MagicMock())
    service.delete_message = AsyncMock(return_value=True)
    service.send_photo = AsyncMock(return_value=MagicMock())
    service.send_document = AsyncMock(return_value=MagicMock())
    
    return service


@pytest.fixture
def sample_project() -> Project:
    """Create a sample project for testing.
    
    Returns:
        Project: Sample project instance
    """
    return Project(
        id=1,
        key="TEST",
        name="Test Project",
        description="A test project for unit testing",
        jira_id="10001",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        is_active=True
    )


@pytest.fixture
def sample_projects() -> List[Project]:
    """Create a list of sample projects for testing.
    
    Returns:
        List[Project]: List of sample projects
    """
    return [
        Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="A test project",
            jira_id="10001",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        ),
        Project(
            id=2,
            key="DEMO", 
            name="Demo Project",
            description="A demo project",
            jira_id="10002",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_active=True
        )
    ]


@pytest.fixture
def sample_issue() -> JiraIssue:
    """Create a sample Jira issue for testing.
    
    Returns:
        JiraIssue: Sample Jira issue instance
    """
    return JiraIssue(
        id=1,
        jira_id="10001",
        key="TEST-1",
        summary="Test Issue",
        description="This is a test issue for unit testing",
        priority=IssuePriority.MEDIUM,
        issue_type=IssueType.TASK,
        status=IssueStatus.TODO,
        project_id=1,
        creator_id=1,
        assignee_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        jira_created_at=datetime.now(timezone.utc),
        jira_updated_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_user() -> BotUser:
    """Create a sample bot user for testing.
    
    Returns:
        BotUser: Sample bot user instance
    """
    return BotUser(
        id=1,
        user_id="123456789",
        username="testuser",
        first_name="Test",
        last_name="User",
        role=UserRole.USER,
        default_project_id=1,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc)
    )


@pytest.fixture
def telegram_user() -> User:
    """Create a Telegram User object for testing.
    
    Returns:
        User: Telegram User instance
    """
    return User(
        id=123456789,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="testuser",
        language_code="en"
    )


@pytest.fixture
def telegram_chat() -> Chat:
    """Create a Telegram Chat object for testing.
    
    Returns:
        Chat: Telegram Chat instance
    """
    return Chat(
        id=123456789,
        type=Chat.PRIVATE,
        username="testuser",
        first_name="Test",
        last_name="User"
    )


@pytest.fixture
def telegram_message(telegram_user: User, telegram_chat: Chat) -> Message:
    """Create a Telegram Message object for testing.
    
    Args:
        telegram_user: Telegram user fixture
        telegram_chat: Telegram chat fixture
        
    Returns:
        Message: Telegram Message instance
    """
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=telegram_chat,
        from_user=telegram_user,
        text="/start"
    )


@pytest.fixture
def telegram_update(telegram_message: Message) -> Update:
    """Create a Telegram Update object for testing.
    
    Args:
        telegram_message: Telegram message fixture
        
    Returns:
        Update: Telegram Update instance
    """
    return Update(
        update_id=1,
        message=telegram_message
    )


@pytest.fixture
def telegram_callback_query(telegram_user: User) -> CallbackQuery:
    """Create a Telegram CallbackQuery object for testing.
    
    Args:
        telegram_user: Telegram user fixture
        
    Returns:
        CallbackQuery: Telegram CallbackQuery instance
    """
    return CallbackQuery(
        id="callback_query_1",
        from_user=telegram_user,
        chat_instance="chat_instance_1",
        data="test_callback_data"
    )


@pytest.fixture
def mock_context() -> ContextTypes.DEFAULT_TYPE:
    """Create a mock Telegram context for testing.
    
    Returns:
        ContextTypes.DEFAULT_TYPE: Mock Telegram context
    """
    context = MagicMock()
    context.bot = MagicMock()
    context.user_data = {}
    context.chat_data = {}
    context.bot_data = {}
    context.args = []
    
    # Mock bot methods
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.bot.answer_callback_query = AsyncMock()
    
    return context


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file path for testing.
    
    Yields:
        str: Temporary database file path
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
        temp_path = temp_file.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp session for HTTP testing.
    
    Returns:
        Mock aiohttp session
    """
    session = MagicMock()
    session.get = AsyncMock()
    session.post = AsyncMock()
    session.put = AsyncMock()
    session.delete = AsyncMock()
    session.close = AsyncMock()
    
    return session


class AsyncContextManagerMock:
    """Mock async context manager for testing."""
    
    def __init__(self, return_value: Any):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_http_response():
    """Create a mock HTTP response for testing.
    
    Returns:
        Mock HTTP response with common methods
    """
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "success"})
    response.text = AsyncMock(return_value="Success")
    response.headers = {"Content-Type": "application/json"}
    
    return response


# Test utilities
class TestDatabase:
    """Utility class for database testing."""
    
    @staticmethod
    async def clear_all_tables(db: DatabaseManager) -> None:
        """Clear all tables in the test database.
        
        Args:
            db: Database manager instance
        """
        async with db.get_connection() as conn:
            # Get all table names
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = await cursor.fetchall()
            
            # Clear each table
            for table in tables:
                table_name = table[0]
                if not table_name.startswith('sqlite_'):
                    await conn.execute(f"DELETE FROM {table_name}")
            
            await conn.commit()
    
    @staticmethod
    async def insert_test_data(db: DatabaseManager) -> Dict[str, Any]:
        """Insert test data into the database.
        
        Args:
            db: Database manager instance
            
        Returns:
            Dict containing inserted test data IDs and objects
        """
        # This would contain logic to insert test users, projects, issues
        # Implementation depends on your specific database schema
        return {
            "user_id": 1,
            "project_id": 1,
            "issue_id": 1
        }


class TestUtils:
    """Utility functions for testing."""
    
    @staticmethod
    def assert_dict_contains(actual: Dict[str, Any], expected: Dict[str, Any]) -> None:
        """Assert that actual dict contains all key-value pairs from expected dict.
        
        Args:
            actual: Actual dictionary
            expected: Expected key-value pairs
            
        Raises:
            AssertionError: If any expected key-value pair is missing
        """
        for key, value in expected.items():
            assert key in actual, f"Key '{key}' not found in actual dict"
            assert actual[key] == value, f"Value for key '{key}' mismatch: expected {value}, got {actual[key]}"
    
    @staticmethod
    def create_jira_issue_response(
        key: str = "TEST-1",
        summary: str = "Test Issue",
        description: str = "Test description",
        priority: str = "Medium",
        issue_type: str = "Task",
        status: str = "To Do"
    ) -> Dict[str, Any]:
        """Create a mock Jira issue response.
        
        Args:
            key: Issue key
            summary: Issue summary
            description: Issue description
            priority: Issue priority
            issue_type: Issue type
            status: Issue status
            
        Returns:
            Dict representing a Jira issue response
        """
        return {
            "id": "10001",
            "key": key,
            "fields": {
                "summary": summary,
                "description": description,
                "priority": {"name": priority},
                "issuetype": {"name": issue_type},
                "status": {"name": status},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-01T00:00:00.000+0000",
                "assignee": None,
                "reporter": {"displayName": "Test User"}
            }
        }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest settings."""
    # Add custom markers
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "database: mark test as requiring database"
    )
    config.addinivalue_line(
        "markers", "network: mark test as requiring network access"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Mark database tests
        if "database" in str(item.fspath) or "test_database" in item.name:
            item.add_marker(pytest.mark.database)
        
        # Mark integration tests
        if "integration" in str(item.fspath) or "test_integration" in item.name:
            item.add_marker(pytest.mark.integration)
        
        # Mark network tests
        if "network" in item.name or "jira" in item.name:
            item.add_marker(pytest.mark.network)