#!/usr/bin/env python3
"""
Unit tests for model classes in the Telegram-Jira bot.

Tests all data models including Project, JiraIssue, User, and enum classes
for validation, serialization, and business logic.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from telegram_jira_bot.models.project import Project
from telegram_jira_bot.models.issue import JiraIssue, IssueComment
from telegram_jira_bot.models.user import User as BotUser
from telegram_jira_bot.models.enums import (
    IssuePriority, IssueType, IssueStatus, UserRole
)


class TestIssuePriority:
    """Test cases for IssuePriority enum."""
    
    def test_priority_values(self) -> None:
        """Test that all priority values are correctly defined."""
        assert IssuePriority.CRITICAL.value == "Critical"
        assert IssuePriority.HIGH.value == "High"
        assert IssuePriority.MEDIUM.value == "Medium"
        assert IssuePriority.LOW.value == "Low"
        assert IssuePriority.LOWEST.value == "Lowest"
    
    def test_from_string_valid(self) -> None:
        """Test from_string method with valid inputs."""
        assert IssuePriority.from_string("critical") == IssuePriority.CRITICAL
        assert IssuePriority.from_string("HIGH") == IssuePriority.HIGH
        assert IssuePriority.from_string("Medium") == IssuePriority.MEDIUM
        assert IssuePriority.from_string("low") == IssuePriority.LOW
        assert IssuePriority.from_string("LOWEST") == IssuePriority.LOWEST
    
    def test_from_string_invalid(self) -> None:
        """Test from_string method with invalid inputs."""
        with pytest.raises(ValueError, match="Invalid priority"):
            IssuePriority.from_string("invalid")
        
        with pytest.raises(ValueError, match="Invalid priority"):
            IssuePriority.from_string("")
        
        with pytest.raises(ValueError, match="Invalid priority"):
            IssuePriority.from_string("   ")
    
    def test_from_string_type_validation(self) -> None:
        """Test from_string method with invalid types."""
        with pytest.raises(TypeError):
            IssuePriority.from_string(None)  # type: ignore
        
        with pytest.raises(TypeError):
            IssuePriority.from_string(123)  # type: ignore
    
    def test_priority_ordering(self) -> None:
        """Test priority ordering for sorting."""
        priorities = [
            IssuePriority.LOW,
            IssuePriority.CRITICAL,
            IssuePriority.MEDIUM,
            IssuePriority.HIGH,
            IssuePriority.LOWEST
        ]
        
        # Test that priorities can be compared (implementation-dependent)
        assert IssuePriority.CRITICAL != IssuePriority.LOW
        assert IssuePriority.MEDIUM != IssuePriority.HIGH


class TestIssueType:
    """Test cases for IssueType enum."""
    
    def test_issue_type_values(self) -> None:
        """Test that all issue type values are correctly defined."""
        assert IssueType.TASK.value == "Task"
        assert IssueType.STORY.value == "Story"
        assert IssueType.BUG.value == "Bug"
        assert IssueType.EPIC.value == "Epic"
        assert IssueType.SUBTASK.value == "Sub-task"
    
    def test_from_string_valid(self) -> None:
        """Test from_string method with valid inputs."""
        assert IssueType.from_string("task") == IssueType.TASK
        assert IssueType.from_string("STORY") == IssueType.STORY
        assert IssueType.from_string("Bug") == IssueType.BUG
        assert IssueType.from_string("epic") == IssueType.EPIC
        assert IssueType.from_string("sub-task") == IssueType.SUBTASK
        assert IssueType.from_string("subtask") == IssueType.SUBTASK
    
    def test_from_string_invalid(self) -> None:
        """Test from_string method with invalid inputs."""
        with pytest.raises(ValueError, match="Invalid issue type"):
            IssueType.from_string("invalid")
    
    def test_is_valid_type(self) -> None:
        """Test type validation."""
        valid_types = ["Task", "Story", "Bug", "Epic", "Sub-task"]
        for type_name in valid_types:
            assert any(issue_type.value == type_name for issue_type in IssueType)


class TestIssueStatus:
    """Test cases for IssueStatus enum."""
    
    def test_status_values(self) -> None:
        """Test that all status values are correctly defined."""
        assert IssueStatus.TODO.value == "To Do"
        assert IssueStatus.IN_PROGRESS.value == "In Progress"
        assert IssueStatus.DONE.value == "Done"
        assert IssueStatus.BLOCKED.value == "Blocked"
        assert IssueStatus.REVIEW.value == "In Review"
    
    def test_from_string_valid(self) -> None:
        """Test from_string method with valid inputs."""
        assert IssueStatus.from_string("to do") == IssueStatus.TODO
        assert IssueStatus.from_string("IN PROGRESS") == IssueStatus.IN_PROGRESS
        assert IssueStatus.from_string("Done") == IssueStatus.DONE
        assert IssueStatus.from_string("blocked") == IssueStatus.BLOCKED
        assert IssueStatus.from_string("in review") == IssueStatus.REVIEW


class TestUserRole:
    """Test cases for UserRole enum."""
    
    def test_role_values(self) -> None:
        """Test that all role values are correctly defined."""
        assert UserRole.USER.value == "user"
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.SUPER_ADMIN.value == "super_admin"
    
    def test_role_hierarchy(self) -> None:
        """Test role hierarchy for permissions."""
        # Test that roles have different values
        assert UserRole.USER != UserRole.ADMIN
        assert UserRole.ADMIN != UserRole.SUPER_ADMIN
        assert UserRole.USER != UserRole.SUPER_ADMIN


class TestProject:
    """Test cases for Project model."""
    
    def test_project_initialization(self) -> None:
        """Test Project model initialization with valid data."""
        now = datetime.now(timezone.utc)
        
        project = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="A test project",
            jira_id="10001",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        assert project.id == 1
        assert project.key == "TEST"
        assert project.name == "Test Project"
        assert project.description == "A test project"
        assert project.jira_id == "10001"
        assert project.created_at == now
        assert project.updated_at == now
        assert project.is_active is True
    
    def test_project_key_validation(self) -> None:
        """Test project key validation."""
        now = datetime.now(timezone.utc)
        
        # Valid keys
        valid_keys = ["TEST", "DEMO", "PROJ1", "ABC123"]
        for key in valid_keys:
            project = Project(
                id=1,
                key=key,
                name="Test Project",
                description="Test",
                jira_id="10001",
                created_at=now,
                updated_at=now,
                is_active=True
            )
            assert project.key == key
    
    def test_project_optional_fields(self) -> None:
        """Test Project model with optional fields."""
        now = datetime.now(timezone.utc)
        
        project = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description=None,  # Optional field
            jira_id="10001",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        assert project.description is None
        assert project.key == "TEST"
    
    def test_project_string_representation(self) -> None:
        """Test Project string representation."""
        now = datetime.now(timezone.utc)
        
        project = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="A test project",
            jira_id="10001",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        str_repr = str(project)
        assert "TEST" in str_repr
        assert "Test Project" in str_repr
    
    def test_project_equality(self) -> None:
        """Test Project equality comparison."""
        now = datetime.now(timezone.utc)
        
        project1 = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="A test project",
            jira_id="10001",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        project2 = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="A test project",
            jira_id="10001",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        project3 = Project(
            id=2,
            key="OTHER",
            name="Other Project",
            description="Another project",
            jira_id="10002",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        assert project1 == project2
        assert project1 != project3


class TestJiraIssue:
    """Test cases for JiraIssue model."""
    
    def test_issue_initialization(self) -> None:
        """Test JiraIssue model initialization with valid data."""
        now = datetime.now(timezone.utc)
        
        issue = JiraIssue(
            id=1,
            jira_id="10001",
            key="TEST-1",
            summary="Test Issue",
            description="This is a test issue",
            priority=IssuePriority.MEDIUM,
            issue_type=IssueType.TASK,
            status=IssueStatus.TODO,
            project_id=1,
            creator_id=1,
            assignee_id=None,
            created_at=now,
            updated_at=now,
            jira_created_at=now,
            jira_updated_at=now
        )
        
        assert issue.id == 1
        assert issue.jira_id == "10001"
        assert issue.key == "TEST-1"
        assert issue.summary == "Test Issue"
        assert issue.description == "This is a test issue"
        assert issue.priority == IssuePriority.MEDIUM
        assert issue.issue_type == IssueType.TASK
        assert issue.status == IssueStatus.TODO
        assert issue.project_id == 1
        assert issue.creator_id == 1
        assert issue.assignee_id is None
    
    def test_issue_key_validation(self) -> None:
        """Test issue key format validation."""
        now = datetime.now(timezone.utc)
        
        # Valid keys
        valid_keys = ["TEST-1", "DEMO-123", "PROJ-999", "ABC-1"]
        for key in valid_keys:
            issue = JiraIssue(
                id=1,
                jira_id="10001",
                key=key,
                summary="Test Issue",
                description="Test",
                priority=IssuePriority.MEDIUM,
                issue_type=IssueType.TASK,
                status=IssueStatus.TODO,
                project_id=1,
                creator_id=1,
                assignee_id=None,
                created_at=now,
                updated_at=now,
                jira_created_at=now,
                jira_updated_at=now
            )
            assert issue.key == key
    
    def test_issue_optional_fields(self) -> None:
        """Test JiraIssue model with optional fields."""
        now = datetime.now(timezone.utc)
        
        issue = JiraIssue(
            id=1,
            jira_id="10001",
            key="TEST-1",
            summary="Test Issue",
            description=None,  # Optional
            priority=IssuePriority.MEDIUM,
            issue_type=IssueType.TASK,
            status=IssueStatus.TODO,
            project_id=1,
            creator_id=1,
            assignee_id=None,  # Optional
            created_at=now,
            updated_at=now,
            jira_created_at=now,
            jira_updated_at=now
        )
        
        assert issue.description is None
        assert issue.assignee_id is None
    
    def test_issue_string_representation(self) -> None:
        """Test JiraIssue string representation."""
        now = datetime.now(timezone.utc)
        
        issue = JiraIssue(
            id=1,
            jira_id="10001",
            key="TEST-1",
            summary="Test Issue",
            description="Test description",
            priority=IssuePriority.HIGH,
            issue_type=IssueType.BUG,
            status=IssueStatus.IN_PROGRESS,
            project_id=1,
            creator_id=1,
            assignee_id=2,
            created_at=now,
            updated_at=now,
            jira_created_at=now,
            jira_updated_at=now
        )
        
        str_repr = str(issue)
        assert "TEST-1" in str_repr
        assert "Test Issue" in str_repr
        assert "High" in str_repr
        assert "Bug" in str_repr
    
    def test_issue_priority_change(self) -> None:
        """Test changing issue priority."""
        now = datetime.now(timezone.utc)
        
        issue = JiraIssue(
            id=1,
            jira_id="10001",
            key="TEST-1",
            summary="Test Issue",
            description="Test",
            priority=IssuePriority.LOW,
            issue_type=IssueType.TASK,
            status=IssueStatus.TODO,
            project_id=1,
            creator_id=1,
            assignee_id=None,
            created_at=now,
            updated_at=now,
            jira_created_at=now,
            jira_updated_at=now
        )
        
        assert issue.priority == IssuePriority.LOW
        
        # Change priority
        issue.priority = IssuePriority.CRITICAL
        assert issue.priority == IssuePriority.CRITICAL


class TestIssueComment:
    """Test cases for IssueComment model."""
    
    def test_comment_initialization(self) -> None:
        """Test IssueComment model initialization."""
        now = datetime.now(timezone.utc)
        
        comment = IssueComment(
            id=1,
            jira_id="10001",
            issue_id=1,
            author_user_id=1,
            body="This is a test comment",
            created_at=now,
            updated_at=now
        )
        
        assert comment.id == 1
        assert comment.jira_id == "10001"
        assert comment.issue_id == 1
        assert comment.author_user_id == 1
        assert comment.body == "This is a test comment"
        assert comment.created_at == now
        assert comment.updated_at == now
    
    def test_comment_body_validation(self) -> None:
        """Test comment body validation."""
        now = datetime.now(timezone.utc)
        
        # Test with valid comment body
        comment = IssueComment(
            id=1,
            jira_id="10001",
            issue_id=1,
            author_user_id=1,
            body="Valid comment with multiple words and punctuation.",
            created_at=now,
            updated_at=now
        )
        
        assert "Valid comment" in comment.body


class TestBotUser:
    """Test cases for BotUser model."""
    
    def test_user_initialization(self) -> None:
        """Test BotUser model initialization."""
        now = datetime.now(timezone.utc)
        
        user = BotUser(
            id=1,
            user_id="123456789",
            username="testuser",
            first_name="Test",
            last_name="User",
            role=UserRole.USER,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert user.id == 1
        assert user.user_id == "123456789"
        assert user.username == "testuser"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.role == UserRole.USER
        assert user.default_project_id == 1
        assert user.is_active is True
        assert user.created_at == now
        assert user.last_activity == now
    
    def test_user_optional_fields(self) -> None:
        """Test BotUser model with optional fields."""
        now = datetime.now(timezone.utc)
        
        user = BotUser(
            id=1,
            user_id="123456789",
            username=None,  # Optional
            first_name="Test",
            last_name=None,  # Optional
            role=UserRole.USER,
            default_project_id=None,  # Optional
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert user.username is None
        assert user.last_name is None
        assert user.default_project_id is None
    
    def test_user_display_name(self) -> None:
        """Test get_display_name method."""
        now = datetime.now(timezone.utc)
        
        # User with both first and last name
        user1 = BotUser(
            id=1,
            user_id="123456789",
            username="testuser",
            first_name="Test",
            last_name="User",
            role=UserRole.USER,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert user1.get_display_name() == "Test User"
        
        # User with only first name
        user2 = BotUser(
            id=2,
            user_id="987654321",
            username="testuser2",
            first_name="Test",
            last_name=None,
            role=UserRole.USER,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert user2.get_display_name() == "Test"
        
        # User with only username
        user3 = BotUser(
            id=3,
            user_id="555555555",
            username="testuser3",
            first_name=None,
            last_name=None,
            role=UserRole.USER,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert user3.get_display_name() == "testuser3"
    
    def test_user_role_validation(self) -> None:
        """Test user role validation."""
        now = datetime.now(timezone.utc)
        
        # Test different roles
        roles = [UserRole.USER, UserRole.ADMIN, UserRole.SUPER_ADMIN]
        
        for role in roles:
            user = BotUser(
                id=1,
                user_id="123456789",
                username="testuser",
                first_name="Test",
                last_name="User",
                role=role,
                default_project_id=1,
                is_active=True,
                created_at=now,
                last_activity=now
            )
            
            assert user.role == role
    
    def test_user_permissions(self) -> None:
        """Test user permission checking methods."""
        now = datetime.now(timezone.utc)
        
        # Regular user
        user = BotUser(
            id=1,
            user_id="123456789",
            username="testuser",
            first_name="Test",
            last_name="User",
            role=UserRole.USER,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert user.is_admin() is False
        assert user.is_super_admin() is False
        
        # Admin user
        admin_user = BotUser(
            id=2,
            user_id="987654321",
            username="adminuser",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert admin_user.is_admin() is True
        assert admin_user.is_super_admin() is False
        
        # Super admin user
        super_admin_user = BotUser(
            id=3,
            user_id="111111111",
            username="superadmin",
            first_name="Super",
            last_name="Admin",
            role=UserRole.SUPER_ADMIN,
            default_project_id=1,
            is_active=True,
            created_at=now,
            last_activity=now
        )
        
        assert super_admin_user.is_admin() is True  # Super admin is also admin
        assert super_admin_user.is_super_admin() is True


class TestModelValidation:
    """Test cases for model validation and edge cases."""
    
    def test_datetime_timezone_handling(self) -> None:
        """Test that datetime fields handle timezones correctly."""
        # Test with UTC timezone
        utc_time = datetime.now(timezone.utc)
        
        project = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="Test",
            jira_id="10001",
            created_at=utc_time,
            updated_at=utc_time,
            is_active=True
        )
        
        assert project.created_at.tzinfo == timezone.utc
        assert project.updated_at.tzinfo == timezone.utc
    
    def test_model_serialization(self) -> None:
        """Test model serialization to dict."""
        now = datetime.now(timezone.utc)
        
        project = Project(
            id=1,
            key="TEST",
            name="Test Project",
            description="A test project",
            jira_id="10001",
            created_at=now,
            updated_at=now,
            is_active=True
        )
        
        # Test that model can be converted to dict-like structure
        # (Implementation depends on your specific model design)
        assert hasattr(project, 'key')
        assert hasattr(project, 'name')
        assert hasattr(project, 'description')
    
    def test_model_type_safety(self) -> None:
        """Test model type safety and validation."""
        now = datetime.now(timezone.utc)
        
        # Test that enum fields only accept valid enum values
        issue = JiraIssue(
            id=1,
            jira_id="10001",
            key="TEST-1",
            summary="Test Issue",
            description="Test",
            priority=IssuePriority.HIGH,
            issue_type=IssueType.BUG,
            status=IssueStatus.TODO,
            project_id=1,
            creator_id=1,
            assignee_id=None,
            created_at=now,
            updated_at=now,
            jira_created_at=now,
            jira_updated_at=now
        )
        
        assert isinstance(issue.priority, IssuePriority)
        assert isinstance(issue.issue_type, IssueType)
        assert isinstance(issue.status, IssueStatus)