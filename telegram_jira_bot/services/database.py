#!/usr/bin/env python3
"""
Database service for the Telegram-Jira bot.

Manages all database operations using SQLite with async support.
"""

import aiosqlite
import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple

from ..models.project import Project, ProjectStats
from ..models.issue import JiraIssue, IssueSearchResult
from ..models.user import User, UserPreferences, UserSession
from ..models.enums import IssuePriority, IssueType, IssueStatus, UserRole, WizardState


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class DatabaseManager:
    """Manages SQLite database operations for the bot."""

    def __init__(self, db_path: str, pool_size: int = 10, timeout: int = 30) -> None:
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
            pool_size: Maximum number of connections (not used in SQLite)
            timeout: Database operation timeout in seconds
            
        Raises:
            TypeError: If arguments have wrong types
            ValueError: If arguments are invalid
            DatabaseError: If database initialization fails
        """
        if not isinstance(db_path, str):
            raise TypeError("db_path must be a string")
        if not db_path.strip():
            raise ValueError("db_path cannot be empty")
        if not isinstance(pool_size, int) or pool_size <= 0:
            raise ValueError("pool_size must be a positive integer")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
            
        self.db_path = Path(db_path)
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Initialize database schema.
        
        Raises:
            DatabaseError: If database initialization fails
        """
        try:
            async with self._get_connection() as conn:
                await self._create_tables(conn)
                await self._create_indexes(conn)
                await conn.commit()
                self.logger.info("Database initialized successfully")
                
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}")

    @asynccontextmanager
    async def _get_connection(self):
        """Get database connection with proper timeout and error handling."""
        conn = None
        try:
            conn = await aiosqlite.connect(
                self.db_path,
                timeout=self.timeout,
                isolation_level=None  # Use autocommit mode
            )
            # Enable foreign key support and set pragmas
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA temp_store = MEMORY")
            await conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
            
            # Set row factory for easier data access
            conn.row_factory = aiosqlite.Row
            
            yield conn
        except Exception as e:
            self.logger.error(f"Database connection error: {e}")
            raise DatabaseError(f"Database connection failed: {e}")
        finally:
            if conn:
                await conn.close()

    async def _create_tables(self, conn: aiosqlite.Connection) -> None:
        """Create database tables."""
        
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY CHECK (user_id > 0),
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin', 'super_admin')),
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                issues_created INTEGER DEFAULT 0 CHECK (issues_created >= 0),
                preferred_language TEXT DEFAULT 'en' CHECK (length(preferred_language) > 0),
                timezone TEXT
            )
        """)
        
        # User preferences table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY CHECK (user_id > 0),
                default_project_key TEXT,
                default_priority TEXT DEFAULT 'Medium' CHECK (length(default_priority) > 0),
                default_issue_type TEXT DEFAULT 'Task' CHECK (length(default_issue_type) > 0),
                auto_assign_to_self BOOLEAN DEFAULT 0,
                notifications_enabled BOOLEAN DEFAULT 1,
                include_description_in_summary BOOLEAN DEFAULT 1,
                max_issues_per_page INTEGER DEFAULT 5 CHECK (max_issues_per_page > 0),
                date_format TEXT DEFAULT '%Y-%m-%d %H:%M',
                show_issue_details BOOLEAN DEFAULT 1,
                quick_create_mode BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(default_project_key) REFERENCES projects(key) ON DELETE SET NULL
            )
        """)
        
        # User sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY CHECK (user_id > 0),
                wizard_state TEXT DEFAULT 'idle' CHECK (length(wizard_state) > 0),
                wizard_data TEXT DEFAULT '{}',
                last_command TEXT,
                last_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP DEFAULT (datetime('now', '+1 day')),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Projects table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL CHECK (length(key) > 0),
                name TEXT NOT NULL CHECK (length(name) > 0),
                description TEXT NOT NULL DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                jira_project_id TEXT,
                project_type TEXT,
                lead TEXT,
                url TEXT,
                avatar_url TEXT,
                category TEXT,
                issue_count INTEGER DEFAULT 0 CHECK (issue_count >= 0)
            )
        """)
        
        # Issues table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL CHECK (telegram_user_id > 0),
                telegram_message_id INTEGER NOT NULL CHECK (telegram_message_id > 0),
                jira_key TEXT NOT NULL CHECK (length(jira_key) > 0),
                project_key TEXT NOT NULL CHECK (length(project_key) > 0),
                summary TEXT NOT NULL CHECK (length(summary) > 0),
                description TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL CHECK (length(priority) > 0),
                issue_type TEXT NOT NULL CHECK (length(issue_type) > 0),
                status TEXT,
                assignee TEXT,
                reporter TEXT,
                labels TEXT DEFAULT '[]',
                components TEXT DEFAULT '[]',
                fix_versions TEXT DEFAULT '[]',
                story_points INTEGER CHECK (story_points >= 0),
                original_estimate INTEGER CHECK (original_estimate >= 0),
                remaining_estimate INTEGER CHECK (remaining_estimate >= 0),
                time_spent INTEGER CHECK (time_spent >= 0),
                parent_key TEXT,
                epic_link TEXT,
                resolution TEXT,
                resolution_date TIMESTAMP,
                due_date TIMESTAMP,
                url TEXT NOT NULL CHECK (length(url) > 0),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(telegram_user_id, telegram_message_id),
                FOREIGN KEY(project_key) REFERENCES projects(key) ON DELETE CASCADE,
                FOREIGN KEY(telegram_user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Issue comments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS issue_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jira_comment_id TEXT NOT NULL,
                jira_key TEXT NOT NULL CHECK (length(jira_key) > 0),
                author TEXT NOT NULL CHECK (length(author) > 0),
                body TEXT NOT NULL,
                visibility TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(jira_comment_id, jira_key),
                FOREIGN KEY(jira_key) REFERENCES issues(jira_key) ON DELETE CASCADE
            )
        """)
        
        # Rate limiting table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                user_id INTEGER NOT NULL CHECK (user_id > 0),
                action TEXT NOT NULL CHECK (length(action) > 0),
                count INTEGER DEFAULT 1 CHECK (count > 0),
                window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, action),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

    async def _create_indexes(self, conn: aiosqlite.Connection) -> None:
        """Create database indexes for performance."""
        indexes = [
            # User indexes
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
            "CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity)",
            
            # Project indexes
            "CREATE INDEX IF NOT EXISTS idx_projects_key ON projects(key)",
            "CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)",
            "CREATE INDEX IF NOT EXISTS idx_projects_category ON projects(category)",
            
            # Issue indexes
            "CREATE INDEX IF NOT EXISTS idx_issues_user_message ON issues(telegram_user_id, telegram_message_id)",
            "CREATE INDEX IF NOT EXISTS idx_issues_jira_key ON issues(jira_key)",
            "CREATE INDEX IF NOT EXISTS idx_issues_project_key ON issues(project_key)",
            "CREATE INDEX IF NOT EXISTS idx_issues_created_at ON issues(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_issues_priority ON issues(priority)",
            "CREATE INDEX IF NOT EXISTS idx_issues_type ON issues(issue_type)",
            "CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status)",
            "CREATE INDEX IF NOT EXISTS idx_issues_assignee ON issues(assignee)",
            "CREATE INDEX IF NOT EXISTS idx_issues_due_date ON issues(due_date)",
            
            # Comment indexes
            "CREATE INDEX IF NOT EXISTS idx_comments_jira_key ON issue_comments(jira_key)",
            "CREATE INDEX IF NOT EXISTS idx_comments_author ON issue_comments(author)",
            "CREATE INDEX IF NOT EXISTS idx_comments_created_at ON issue_comments(created_at)",
            
            # Session indexes
            "CREATE INDEX IF NOT EXISTS idx_sessions_state ON user_sessions(wizard_state)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at)",
            
            # Rate limit indexes
            "CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON rate_limits(window_start)",
        ]
        
        for index_sql in indexes:
            await conn.execute(index_sql)

    # User operations
    async def save_user(self, user: User) -> None:
        """Save or update a user in the database."""
        if not isinstance(user, User):
            raise TypeError("user must be a User instance")

        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name, role, is_active,
                     created_at, last_activity, issues_created, preferred_language, timezone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user.user_id, user.username, user.first_name, user.last_name,
                    user.role.value, user.is_active, user.created_at.isoformat(),
                    user.last_activity.isoformat(), user.issues_created,
                    user.preferred_language, user.timezone
                ))
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to save user {user.user_id}: {e}")
            raise DatabaseError(f"Failed to save user: {e}")

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return User(
                        user_id=row['user_id'],
                        username=row['username'],
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        role=UserRole(row['role']),
                        is_active=bool(row['is_active']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        last_activity=datetime.fromisoformat(row['last_activity']),
                        issues_created=row['issues_created'],
                        preferred_language=row['preferred_language'],
                        timezone=row['timezone']
                    )
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user: {e}")

    async def get_all_users(self, active_only: bool = True) -> List[User]:
        """Get all users from the database."""
        try:
            async with self._get_connection() as conn:
                query = "SELECT * FROM users"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY last_activity DESC"
                
                cursor = await conn.execute(query)
                rows = await cursor.fetchall()
                
                users = []
                for row in rows:
                    users.append(User(
                        user_id=row['user_id'],
                        username=row['username'],
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        role=UserRole(row['role']),
                        is_active=bool(row['is_active']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        last_activity=datetime.fromisoformat(row['last_activity']),
                        issues_created=row['issues_created'],
                        preferred_language=row['preferred_language'],
                        timezone=row['timezone']
                    ))
                return users
        except Exception as e:
            self.logger.error(f"Failed to get all users: {e}")
            raise DatabaseError(f"Failed to retrieve users: {e}")

    async def update_user_activity(self, user_id: int) -> None:
        """Update user's last activity timestamp."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (user_id,)
                )
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to update user activity {user_id}: {e}")
            raise DatabaseError(f"Failed to update user activity: {e}")

    # User preferences operations
    async def save_user_preferences(self, preferences: UserPreferences) -> None:
        """Save user preferences."""
        if not isinstance(preferences, UserPreferences):
            raise TypeError("preferences must be a UserPreferences instance")

        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO user_preferences 
                    (user_id, default_project_key, default_priority, default_issue_type,
                     auto_assign_to_self, notifications_enabled, include_description_in_summary,
                     max_issues_per_page, date_format, show_issue_details, quick_create_mode,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    preferences.user_id, preferences.default_project_key,
                    preferences.default_priority.value, preferences.default_issue_type.value,
                    preferences.auto_assign_to_self, preferences.notifications_enabled,
                    preferences.include_description_in_summary, preferences.max_issues_per_page,
                    preferences.date_format, preferences.show_issue_details,
                    preferences.quick_create_mode, preferences.created_at.isoformat(),
                    preferences.updated_at.isoformat()
                ))
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to save user preferences {preferences.user_id}: {e}")
            raise DatabaseError(f"Failed to save user preferences: {e}")

    async def get_user_preferences(self, user_id: int) -> Optional[UserPreferences]:
        """Get user preferences."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return UserPreferences(
                        user_id=row['user_id'],
                        default_project_key=row['default_project_key'],
                        default_priority=IssuePriority.from_string(row['default_priority']),
                        default_issue_type=IssueType.from_string(row['default_issue_type']),
                        auto_assign_to_self=bool(row['auto_assign_to_self']),
                        notifications_enabled=bool(row['notifications_enabled']),
                        include_description_in_summary=bool(row['include_description_in_summary']),
                        max_issues_per_page=row['max_issues_per_page'],
                        date_format=row['date_format'],
                        show_issue_details=bool(row['show_issue_details']),
                        quick_create_mode=bool(row['quick_create_mode']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        updated_at=datetime.fromisoformat(row['updated_at'])
                    )
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user preferences {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user preferences: {e}")

    # Project operations
    async def add_project(self, project: Project) -> None:
        """Add a new project to the database."""
        if not isinstance(project, Project):
            raise TypeError("project must be a Project instance")

        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT INTO projects 
                    (key, name, description, is_active, created_at, updated_at,
                     jira_project_id, project_type, lead, url, avatar_url, category, issue_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    project.key, project.name, project.description, project.is_active,
                    project.created_at.isoformat(), project.updated_at.isoformat(),
                    project.jira_project_id, project.project_type, project.lead,
                    project.url, project.avatar_url, project.category, project.issue_count
                ))
                await conn.commit()
        except aiosqlite.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise DatabaseError(f"Project with key '{project.key}' already exists")
            raise DatabaseError(f"Database integrity error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to add project {project.key}: {e}")
            raise DatabaseError(f"Failed to add project: {e}")

    async def get_projects(self, active_only: bool = True) -> List[Project]:
        """Get all projects from the database."""
        try:
            async with self._get_connection() as conn:
                query = "SELECT * FROM projects"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY name"
                
                cursor = await conn.execute(query)
                rows = await cursor.fetchall()
                
                projects = []
                for row in rows:
                    projects.append(Project(
                        key=row['key'],
                        name=row['name'],
                        description=row['description'] or "",
                        is_active=bool(row['is_active']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        updated_at=datetime.fromisoformat(row['updated_at']),
                        jira_project_id=row['jira_project_id'],
                        project_type=row['project_type'],
                        lead=row['lead'],
                        url=row['url'],
                        avatar_url=row['avatar_url'],
                        category=row['category'],
                        issue_count=row['issue_count']
                    ))
                return projects
        except Exception as e:
            self.logger.error(f"Failed to get projects: {e}")
            raise DatabaseError(f"Failed to retrieve projects: {e}")

    async def get_project_by_key(self, key: str) -> Optional[Project]:
        """Get a project by its key."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("SELECT * FROM projects WHERE key = ?", (key,))
                row = await cursor.fetchone()
                
                if row:
                    return Project(
                        key=row['key'],
                        name=row['name'],
                        description=row['description'] or "",
                        is_active=bool(row['is_active']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        updated_at=datetime.fromisoformat(row['updated_at']),
                        jira_project_id=row['jira_project_id'],
                        project_type=row['project_type'],
                        lead=row['lead'],
                        url=row['url'],
                        avatar_url=row['avatar_url'],
                        category=row['category'],
                        issue_count=row['issue_count']
                    )
                return None
        except Exception as e:
            self.logger.error(f"Failed to get project {key}: {e}")
            raise DatabaseError(f"Failed to retrieve project: {e}")

    async def update_project(self, key: str, **kwargs) -> bool:
        """Update a project in the database."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")

        if not kwargs:
            return False

        updatable_fields = {
            'name', 'description', 'is_active', 'jira_project_id', 
            'project_type', 'lead', 'url', 'avatar_url', 'category', 'issue_count'
        }
        
        updates = []
        params = []
        
        for field, value in kwargs.items():
            if field in updatable_fields:
                updates.append(f"{field} = ?")
                params.append(value)
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(key)
        
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    f"UPDATE projects SET {', '.join(updates)} WHERE key = ?",
                    params
                )
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Failed to update project {key}: {e}")
            raise DatabaseError(f"Failed to update project: {e}")

    async def delete_project(self, key: str, force: bool = False) -> bool:
        """Delete a project from the database."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                # Check if project has issues
                if not force:
                    cursor = await conn.execute(
                        "SELECT COUNT(*) as count FROM issues WHERE project_key = ?", (key,)
                    )
                    row = await cursor.fetchone()
                    if row and row['count'] > 0:
                        raise DatabaseError(f"Project '{key}' has {row['count']} issues. Use force=True to delete anyway.")
                
                cursor = await conn.execute("DELETE FROM projects WHERE key = ?", (key,))
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Failed to delete project {key}: {e}")
            raise DatabaseError(f"Failed to delete project: {e}")

    async def get_project_stats(self, project_key: str) -> ProjectStats:
        """Get statistics for a project."""
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                # Get total issues
                cursor = await conn.execute(
                    "SELECT COUNT(*) as total FROM issues WHERE project_key = ?",
                    (project_key,)
                )
                row = await cursor.fetchone()
                total_issues = row['total'] if row else 0
                
                # Get issues by type
                cursor = await conn.execute("""
                    SELECT issue_type, COUNT(*) as count 
                    FROM issues WHERE project_key = ? 
                    GROUP BY issue_type
                """, (project_key,))
                issues_by_type = {row['issue_type']: row['count'] for row in await cursor.fetchall()}
                
                # Get issues by priority
                cursor = await conn.execute("""
                    SELECT priority, COUNT(*) as count 
                    FROM issues WHERE project_key = ? 
                    GROUP BY priority
                """, (project_key,))
                issues_by_priority = {row['priority']: row['count'] for row in await cursor.fetchall()}
                
                # Get issues by status
                cursor = await conn.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM issues WHERE project_key = ? AND status IS NOT NULL
                    GROUP BY status
                """, (project_key,))
                issues_by_status = {row['status']: row['count'] for row in await cursor.fetchall()}
                
                # Get activity statistics
                now = datetime.now(timezone.utc)
                month_ago = now - timedelta(days=30)
                week_ago = now - timedelta(days=7)
                
                cursor = await conn.execute("""
                    SELECT COUNT(*) as count FROM issues 
                    WHERE project_key = ? AND created_at >= ?
                """, (project_key, month_ago.isoformat()))
                row = await cursor.fetchone()
                created_this_month = row['count'] if row else 0
                
                cursor = await conn.execute("""
                    SELECT COUNT(*) as count FROM issues 
                    WHERE project_key = ? AND created_at >= ?
                """, (project_key, week_ago.isoformat()))
                row = await cursor.fetchone()
                created_this_week = row['count'] if row else 0
                
                # Get last activity
                cursor = await conn.execute("""
                    SELECT MAX(created_at) as last_activity FROM issues WHERE project_key = ?
                """, (project_key,))
                row = await cursor.fetchone()
                last_activity = None
                if row and row['last_activity']:
                    last_activity = datetime.fromisoformat(row['last_activity'])
                
                return ProjectStats(
                    project_key=project_key,
                    total_issues=total_issues,
                    issues_by_type=issues_by_type,
                    issues_by_priority=issues_by_priority,
                    issues_by_status=issues_by_status,
                    created_this_month=created_this_month,
                    created_this_week=created_this_week,
                    last_activity=last_activity
                )
                
        except Exception as e:
            self.logger.error(f"Failed to get project stats {project_key}: {e}")
            raise DatabaseError(f"Failed to retrieve project statistics: {e}")

    # Issue operations
    async def save_issue(self, user_id: int, message_id: int, issue: JiraIssue) -> None:
        """Save issue to database."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not isinstance(message_id, int) or message_id <= 0:
            raise ValueError("message_id must be a positive integer")
        if not isinstance(issue, JiraIssue):
            raise TypeError("issue must be a JiraIssue instance")

        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO issues 
                    (telegram_user_id, telegram_message_id, jira_key, project_key,
                     summary, description, priority, issue_type, status, assignee, reporter,
                     labels, components, fix_versions, story_points, original_estimate,
                     remaining_estimate, time_spent, parent_key, epic_link, resolution,
                     resolution_date, due_date, url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, message_id, issue.key, issue.project_key,
                    issue.summary, issue.description, issue.priority.value, 
                    issue.issue_type.value, issue.status.value if issue.status else None,
                    issue.assignee, issue.reporter,
                    json.dumps(issue.labels), json.dumps(issue.components),
                    json.dumps(issue.fix_versions), issue.story_points,
                    issue.original_estimate, issue.remaining_estimate, issue.time_spent,
                    issue.parent_key, issue.epic_link, issue.resolution,
                    issue.resolution_date.isoformat() if issue.resolution_date else None,
                    issue.due_date.isoformat() if issue.due_date else None,
                    issue.url, issue.created_at.isoformat(),
                    issue.updated_at.isoformat() if issue.updated_at else None
                ))
                
                # Update project issue count
                await conn.execute("""
                    UPDATE projects SET issue_count = (
                        SELECT COUNT(*) FROM issues WHERE project_key = ?
                    ) WHERE key = ?
                """, (issue.project_key, issue.project_key))
                
                # Update user issue count
                await conn.execute("""
                    UPDATE users SET issues_created = (
                        SELECT COUNT(*) FROM issues WHERE telegram_user_id = ?
                    ) WHERE user_id = ?
                """, (user_id, user_id))
                
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to save issue {issue.key}: {e}")
            raise DatabaseError(f"Failed to save issue: {e}")

    async def get_user_issues(self, user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get recent issues for a user."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("""
                    SELECT i.*, p.name as project_name 
                    FROM issues i
                    LEFT JOIN projects p ON i.project_key = p.key
                    WHERE i.telegram_user_id = ? 
                    ORDER BY i.created_at DESC 
                    LIMIT ? OFFSET ?
                """, (user_id, limit, offset))
                
                issues = []
                async for row in cursor:
                    issue_data = dict(row)
                    # Parse JSON fields
                    issue_data['labels'] = json.loads(issue_data['labels'] or '[]')
                    issue_data['components'] = json.loads(issue_data['components'] or '[]')
                    issue_data['fix_versions'] = json.loads(issue_data['fix_versions'] or '[]')
                    issues.append(issue_data)
                
                return issues
        except Exception as e:
            self.logger.error(f"Failed to get user issues {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user issues: {e}")

    async def search_issues(
        self, 
        query: Optional[str] = None,
        project_key: Optional[str] = None,
        issue_type: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = 10,
        offset: int = 0
    ) -> IssueSearchResult:
        """Search issues with filters."""
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        if offset < 0:
            raise ValueError("offset must be a non-negative integer")

        try:
            async with self._get_connection() as conn:
                # Build WHERE clause
                where_conditions = []
                params = []
                
                if query:
                    where_conditions.append("(summary LIKE ? OR description LIKE ?)")
                    params.extend([f"%{query}%", f"%{query}%"])
                
                if project_key:
                    where_conditions.append("project_key = ?")
                    params.append(project_key)
                
                if issue_type:
                    where_conditions.append("issue_type = ?")
                    params.append(issue_type)
                
                if priority:
                    where_conditions.append("priority = ?")
                    params.append(priority)
                
                if status:
                    where_conditions.append("status = ?")
                    params.append(status)
                
                if assignee:
                    where_conditions.append("assignee LIKE ?")
                    params.append(f"%{assignee}%")
                
                if user_id:
                    where_conditions.append("telegram_user_id = ?")
                    params.append(user_id)
                
                where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
                
                # Get total count
                cursor = await conn.execute(
                    f"SELECT COUNT(*) as total FROM issues WHERE {where_clause}",
                    params
                )
                row = await cursor.fetchone()
                total_count = row['total'] if row else 0
                
                # Get issues
                cursor = await conn.execute(f"""
                    SELECT i.*, p.name as project_name 
                    FROM issues i
                    LEFT JOIN projects p ON i.project_key = p.key
                    WHERE {where_clause}
                    ORDER BY i.created_at DESC 
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])
                
                issues = []
                async for row in cursor:
                    # Convert row to JiraIssue
                    issue_data = dict(row)
                    
                    # Parse enum fields
                    priority_enum = IssuePriority.from_string(issue_data['priority'])
                    issue_type_enum = IssueType.from_string(issue_data['issue_type'])
                    status_enum = None
                    if issue_data['status']:
                        try:
                            status_enum = IssueStatus.from_string(issue_data['status'])
                        except ValueError:
                            pass
                    
                    # Parse datetime fields
                    created_at = datetime.fromisoformat(issue_data['created_at'])
                    updated_at = None
                    if issue_data['updated_at']:
                        updated_at = datetime.fromisoformat(issue_data['updated_at'])
                    
                    resolution_date = None
                    if issue_data['resolution_date']:
                        resolution_date = datetime.fromisoformat(issue_data['resolution_date'])
                    
                    due_date = None
                    if issue_data['due_date']:
                        due_date = datetime.fromisoformat(issue_data['due_date'])
                    
                    # Parse JSON fields
                    labels = json.loads(issue_data['labels'] or '[]')
                    components = json.loads(issue_data['components'] or '[]')
                    fix_versions = json.loads(issue_data['fix_versions'] or '[]')
                    
                    issue = JiraIssue(
                        key=issue_data['jira_key'],
                        summary=issue_data['summary'],
                        description=issue_data['description'],
                        priority=priority_enum,
                        issue_type=issue_type_enum,
                        project_key=issue_data['project_key'],
                        url=issue_data['url'],
                        created_at=created_at,
                        updated_at=updated_at,
                        status=status_enum,
                        assignee=issue_data['assignee'],
                        reporter=issue_data['reporter'],
                        labels=labels,
                        components=components,
                        fix_versions=fix_versions,
                        story_points=issue_data['story_points'],
                        original_estimate=issue_data['original_estimate'],
                        remaining_estimate=issue_data['remaining_estimate'],
                        time_spent=issue_data['time_spent'],
                        parent_key=issue_data['parent_key'],
                        epic_link=issue_data['epic_link'],
                        resolution=issue_data['resolution'],
                        resolution_date=resolution_date,
                        due_date=due_date,
                        telegram_user_id=issue_data['telegram_user_id'],
                        telegram_message_id=issue_data['telegram_message_id']
                    )
                    issues.append(issue)
                
                # Build filters dict
                filters_applied = {}
                if project_key:
                    filters_applied['project'] = project_key
                if issue_type:
                    filters_applied['type'] = issue_type
                if priority:
                    filters_applied['priority'] = priority
                if status:
                    filters_applied['status'] = status
                if assignee:
                    filters_applied['assignee'] = assignee
                if user_id:
                    filters_applied['user'] = user_id
                
                return IssueSearchResult(
                    issues=issues,
                    total_count=total_count,
                    search_query=query,
                    filters_applied=filters_applied
                )
                
        except Exception as e:
            self.logger.error(f"Failed to search issues: {e}")
            raise DatabaseError(f"Failed to search issues: {e}")

    # Session operations
    async def save_user_session(self, session: UserSession) -> None:
        """Save user session."""
        if not isinstance(session, UserSession):
            raise TypeError("session must be a UserSession instance")

        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT OR REPLACE INTO user_sessions 
                    (user_id, wizard_state, wizard_data, last_command, last_message_id,
                     created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.user_id, session.wizard_state.value,
                    json.dumps(session.wizard_data), session.last_command,
                    session.last_message_id, session.created_at.isoformat(),
                    session.expires_at.isoformat()
                ))
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to save user session {session.user_id}: {e}")
            raise DatabaseError(f"Failed to save user session: {e}")

    async def get_user_session(self, user_id: int) -> Optional[UserSession]:
        """Get user session."""
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM user_sessions WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return UserSession(
                        user_id=row['user_id'],
                        wizard_state=WizardState(row['wizard_state']),
                        wizard_data=json.loads(row['wizard_data']),
                        last_command=row['last_command'],
                        last_message_id=row['last_message_id'],
                        created_at=datetime.fromisoformat(row['created_at']),
                        expires_at=datetime.fromisoformat(row['expires_at'])
                    )
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user session {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user session: {e}")

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP"
                )
                await conn.commit()
                return cursor.rowcount
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired sessions: {e}")
            raise DatabaseError(f"Failed to cleanup expired sessions: {e}")

    # Utility operations
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            async with self._get_connection() as conn:
                stats = {}
                
                # Count records in each table
                tables = ['users', 'projects', 'issues', 'user_preferences', 'user_sessions', 'issue_comments']
                for table in tables:
                    cursor = await conn.execute(f"SELECT COUNT(*) as count FROM {table}")
                    row = await cursor.fetchone()
                    stats[f"{table}_count"] = row['count'] if row else 0
                
                # Database size
                cursor = await conn.execute("PRAGMA page_count")
                page_count = (await cursor.fetchone())[0]
                cursor = await conn.execute("PRAGMA page_size")
                page_size = (await cursor.fetchone())[0]
                stats['database_size_bytes'] = page_count * page_size
                
                # Active users (active in last 30 days)
                thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
                cursor = await conn.execute(
                    "SELECT COUNT(*) as count FROM users WHERE last_activity >= ?", 
                    (thirty_days_ago,)
                )
                row = await cursor.fetchone()
                stats['active_users_30_days'] = row['count'] if row else 0
                
                return stats
        except Exception as e:
            self.logger.error(f"Failed to get database stats: {e}")
            raise DatabaseError(f"Failed to retrieve database statistics: {e}")

    async def vacuum_database(self) -> None:
        """Vacuum the database to reclaim space."""
        try:
            async with self._get_connection() as conn:
                await conn.execute("VACUUM")
                self.logger.info("Database vacuumed successfully")
        except Exception as e:
            self.logger.error(f"Failed to vacuum database: {e}")
            raise DatabaseError(f"Failed to vacuum database: {e}")