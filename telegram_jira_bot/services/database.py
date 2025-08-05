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
from ..models.issue import JiraIssue, IssueComment, IssueSearchResult
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
        self._initialized = False
        
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
                self._initialized = True
                self.logger.info("Database initialized successfully")
                
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}")

    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._initialized

    @asynccontextmanager
    async def _get_connection(self):
        """Get database connection with proper timeout and error handling."""
        try:
            conn = await aiosqlite.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False
            )
            conn.row_factory = aiosqlite.Row  # Enable column access by name
            yield conn
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}")
        finally:
            if 'conn' in locals():
                await conn.close()

    async def _create_tables(self, conn: aiosqlite.Connection) -> None:
        """Create database tables."""
        
        # Users table - FIXED: user_id as TEXT to match Telegram IDs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL CHECK (length(user_id) > 0),
                username TEXT,
                first_name TEXT NOT NULL CHECK (length(first_name) > 0),
                last_name TEXT,
                role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin', 'super_admin')),
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                issues_created INTEGER DEFAULT 0 CHECK (issues_created >= 0),
                preferred_language TEXT DEFAULT 'en',
                timezone TEXT DEFAULT 'UTC'
            )
        """)
        
        # User preferences table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY CHECK (length(user_id) > 0),
                default_project_key TEXT,
                default_priority TEXT DEFAULT 'medium' CHECK (default_priority IN ('lowest', 'low', 'medium', 'high', 'critical')),
                default_issue_type TEXT DEFAULT 'task' CHECK (default_issue_type IN ('task', 'story', 'bug', 'epic', 'subtask')),
                auto_assign_to_self BOOLEAN DEFAULT 0,
                notifications_enabled BOOLEAN DEFAULT 1,
                include_description_in_summary BOOLEAN DEFAULT 1,
                max_issues_per_page INTEGER DEFAULT 10 CHECK (max_issues_per_page > 0),
                date_format TEXT DEFAULT 'YYYY-MM-DD',
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
                user_id TEXT PRIMARY KEY CHECK (length(user_id) > 0),
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
                jira_id TEXT,
                project_type TEXT DEFAULT 'software',
                lead TEXT,
                url TEXT,
                avatar_url TEXT,
                category TEXT,
                issue_count INTEGER DEFAULT 0 CHECK (issue_count >= 0),
                default_priority TEXT DEFAULT 'medium' CHECK (default_priority IN ('lowest', 'low', 'medium', 'high', 'critical')),
                default_issue_type TEXT DEFAULT 'task' CHECK (default_issue_type IN ('task', 'story', 'bug', 'epic', 'subtask'))
            )
        """)
        
        # Issues table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jira_key TEXT UNIQUE NOT NULL CHECK (length(jira_key) > 0),
                jira_id TEXT NOT NULL,
                project_key TEXT NOT NULL,
                summary TEXT NOT NULL CHECK (length(summary) > 0),
                description TEXT DEFAULT '',
                issue_type TEXT NOT NULL CHECK (issue_type IN ('task', 'story', 'bug', 'epic', 'subtask')),
                status TEXT NOT NULL CHECK (status IN ('todo', 'in_progress', 'done', 'blocked', 'review')),
                priority TEXT NOT NULL CHECK (priority IN ('lowest', 'low', 'medium', 'high', 'critical')),
                assignee TEXT,
                reporter TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_date TIMESTAMP,
                resolved_at TIMESTAMP,
                telegram_user_id TEXT,
                telegram_message_id INTEGER,
                FOREIGN KEY(project_key) REFERENCES projects(key) ON DELETE CASCADE,
                FOREIGN KEY(telegram_user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
        """)
        
        # Issue comments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS issue_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jira_comment_id TEXT UNIQUE NOT NULL,
                jira_key TEXT NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(jira_key) REFERENCES issues(jira_key) ON DELETE CASCADE
            )
        """)

    async def _create_indexes(self, conn: aiosqlite.Connection) -> None:
        """Create database indexes for performance."""
        indexes = [
            # User indexes
            "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)",
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
        ]
        
        for index_sql in indexes:
            await conn.execute(index_sql)

    # =============================================================================
    # USER OPERATIONS - FIXED METHOD SIGNATURES
    # =============================================================================

    async def create_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        first_name: str = "",
        last_name: Optional[str] = None,
        role: Union[UserRole, str] = UserRole.USER,
        is_active: bool = True,
        preferred_language: str = "en",
        timezone: str = "UTC"
    ) -> int:
        """Create a new user and return the database ID.
        
        Args:
            user_id: Telegram user ID (string)
            username: Telegram username
            first_name: User's first name
            last_name: User's last name
            role: User role (enum or string)
            is_active: Whether user is active
            preferred_language: User's preferred language
            timezone: User's timezone
            
        Returns:
            Database ID of created user
            
        Raises:
            DatabaseError: If user creation fails
            ValueError: If arguments are invalid
        """
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        if not isinstance(first_name, str) or not first_name.strip():
            raise ValueError("first_name must be a non-empty string")
        
        # Convert role to string if needed
        role_str = role.value if isinstance(role, UserRole) else str(role)
        
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("""
                    INSERT INTO users 
                    (user_id, username, first_name, last_name, role, is_active, 
                     preferred_language, timezone, created_at, last_activity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, username, first_name, last_name, role_str, is_active,
                    preferred_language, timezone, 
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))
                await conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            self.logger.error(f"Failed to create user {user_id}: {e}")
            raise DatabaseError(f"Failed to create user: {e}")

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

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by Telegram user ID (string).
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            User object or None if not found
            
        Raises:
            DatabaseError: If database operation fails
        """
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")

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
                        role=UserRole.from_string(row['role']),
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

    async def get_user_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        """Alias for get_user for backward compatibility."""
        return await self.get_user(telegram_id)

    async def get_user_by_id(self, db_id: int) -> Optional[User]:
        """Get a user by database ID (integer).
        
        Args:
            db_id: Database ID (integer primary key)
            
        Returns:
            User object or None if not found
        """
        if not isinstance(db_id, int) or db_id <= 0:
            raise ValueError("db_id must be a positive integer")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE id = ?", (db_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return User(
                        user_id=row['user_id'],
                        username=row['username'],
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        role=UserRole.from_string(row['role']),
                        is_active=bool(row['is_active']),
                        created_at=datetime.fromisoformat(row['created_at']),
                        last_activity=datetime.fromisoformat(row['last_activity']),
                        issues_created=row['issues_created'],
                        preferred_language=row['preferred_language'],
                        timezone=row['timezone']
                    )
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user by ID {db_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user: {e}")

    async def update_user_activity(self, user_id: str) -> None:
        """Update user's last activity timestamp.
        
        Args:
            user_id: Telegram user ID
            
        Raises:
            DatabaseError: If update fails
        """
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "UPDATE users SET last_activity = ? WHERE user_id = ?",
                    (datetime.now(timezone.utc).isoformat(), user_id)
                )
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to update user activity {user_id}: {e}")
            raise DatabaseError(f"Failed to update user activity: {e}")

    async def update_user(
        self,
        user_id: Union[str, int],
        **kwargs
    ) -> None:
        """Update user fields.
        
        Args:
            user_id: User ID (string for telegram_id, int for db_id)
            **kwargs: Fields to update
            
        Raises:
            DatabaseError: If update fails
        """
        if not kwargs:
            return

        # Determine if we're using telegram user_id or database id
        if isinstance(user_id, str):
            where_clause = "user_id = ?"
        elif isinstance(user_id, int):
            where_clause = "id = ?"
        else:
            raise ValueError("user_id must be string or int")

        # Build SET clause
        set_clauses = []
        values = []
        
        for field, value in kwargs.items():
            if field == 'role' and isinstance(value, UserRole):
                value = value.value
            set_clauses.append(f"{field} = ?")
            values.append(value)
        
        if not set_clauses:
            return

        values.append(user_id)

        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    f"UPDATE users SET {', '.join(set_clauses)} WHERE {where_clause}",
                    values
                )
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to update user {user_id}: {e}")
            raise DatabaseError(f"Failed to update user: {e}")

    async def delete_user(self, user_id: Union[str, int]) -> None:
        """Delete a user.
        
        Args:
            user_id: User ID (string for telegram_id, int for db_id)
        """
        if isinstance(user_id, str):
            where_clause = "user_id = ?"
        elif isinstance(user_id, int):
            where_clause = "id = ?"
        else:
            raise ValueError("user_id must be string or int")

        try:
            async with self._get_connection() as conn:
                await conn.execute(f"DELETE FROM users WHERE {where_clause}", (user_id,))
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to delete user {user_id}: {e}")
            raise DatabaseError(f"Failed to delete user: {e}")

    async def get_all_users(self, active_only: bool = True) -> List[User]:
        """Get all users from the database."""
        try:
            async with self._get_connection() as conn:
                if active_only:
                    cursor = await conn.execute(
                        "SELECT * FROM users WHERE is_active = 1 ORDER BY created_at"
                    )
                else:
                    cursor = await conn.execute(
                        "SELECT * FROM users ORDER BY created_at"
                    )
                
                rows = await cursor.fetchall()
                users = []
                
                for row in rows:
                    try:
                        user = User(
                            user_id=row['user_id'],
                            username=row['username'],
                            first_name=row['first_name'],
                            last_name=row['last_name'],
                            role=UserRole.from_string(row['role']),
                            is_active=bool(row['is_active']),
                            created_at=datetime.fromisoformat(row['created_at']),
                            last_activity=datetime.fromisoformat(row['last_activity']),
                            issues_created=row['issues_created'],
                            preferred_language=row['preferred_language'],
                            timezone=row['timezone']
                        )
                        users.append(user)
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Skipping invalid user data for {row['user_id']}: {e}")
                        continue
                
                return users
        except Exception as e:
            self.logger.error(f"Failed to get all users: {e}")
            raise DatabaseError(f"Failed to retrieve users: {e}")

    # =============================================================================
    # PROJECT OPERATIONS - FIXED METHOD SIGNATURES
    # =============================================================================

    async def create_project(
        self,
        key: str,
        name: str,
        description: str = "",
        jira_id: Optional[str] = None,
        is_active: bool = True,
        project_type: str = "software",
        lead: Optional[str] = None,
        url: Optional[str] = None,
        avatar_url: Optional[str] = None,
        category: Optional[str] = None,
        default_priority: Union[IssuePriority, str] = IssuePriority.MEDIUM,
        default_issue_type: Union[IssueType, str] = IssueType.TASK
    ) -> int:
        """Create a new project and return database ID."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        
        # Convert enums to strings
        priority_str = default_priority.value if isinstance(default_priority, IssuePriority) else str(default_priority)
        type_str = default_issue_type.value if isinstance(default_issue_type, IssueType) else str(default_issue_type)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("""
                    INSERT INTO projects 
                    (key, name, description, jira_id, is_active, project_type, lead, url, 
                     avatar_url, category, default_priority, default_issue_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    key, name, description, jira_id, is_active, project_type, lead, url,
                    avatar_url, category, priority_str, type_str,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))
                await conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            self.logger.error(f"Failed to create project {key}: {e}")
            raise DatabaseError(f"Failed to create project: {e}")

    async def get_project_by_key(self, key: str) -> Optional[Project]:
        """Get project by key."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM projects WHERE key = ?", (key,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return self._row_to_project(row)
                return None
        except Exception as e:
            self.logger.error(f"Failed to get project {key}: {e}")
            raise DatabaseError(f"Failed to retrieve project: {e}")

    async def get_project_by_id(self, project_id: int) -> Optional[Project]:
        """Get project by database ID."""
        if not isinstance(project_id, int) or project_id <= 0:
            raise ValueError("project_id must be a positive integer")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM projects WHERE id = ?", (project_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return self._row_to_project(row)
                return None
        except Exception as e:
            self.logger.error(f"Failed to get project by ID {project_id}: {e}")
            raise DatabaseError(f"Failed to retrieve project: {e}")

    async def update_project(
        self,
        project_id: int,
        **kwargs
    ) -> None:
        """Update project fields."""
        if not kwargs:
            return

        # Build SET clause
        set_clauses = []
        values = []
        
        for field, value in kwargs.items():
            if field == 'default_priority' and isinstance(value, IssuePriority):
                value = value.value
            elif field == 'default_issue_type' and isinstance(value, IssueType):
                value = value.value
            set_clauses.append(f"{field} = ?")
            values.append(value)
        
        # Add updated_at
        set_clauses.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(project_id)

        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = ?",
                    values
                )
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to update project {project_id}: {e}")
            raise DatabaseError(f"Failed to update project: {e}")

    async def delete_project(self, project_id: int) -> None:
        """Delete a project."""
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                await conn.commit()
        except Exception as e:
            self.logger.error(f"Failed to delete project {project_id}: {e}")
            raise DatabaseError(f"Failed to delete project: {e}")

    async def get_all_projects(self, active_only: bool = True) -> List[Project]:
        """Get all projects."""
        try:
            async with self._get_connection() as conn:
                if active_only:
                    cursor = await conn.execute(
                        "SELECT * FROM projects WHERE is_active = 1 ORDER BY name"
                    )
                else:
                    cursor = await conn.execute(
                        "SELECT * FROM projects ORDER BY name"
                    )
                
                rows = await cursor.fetchall()
                projects = []
                
                for row in rows:
                    try:
                        project = self._row_to_project(row)
                        projects.append(project)
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Skipping invalid project data for {row['key']}: {e}")
                        continue
                
                return projects
        except Exception as e:
            self.logger.error(f"Failed to get all projects: {e}")
            raise DatabaseError(f"Failed to retrieve projects: {e}")

    def _row_to_project(self, row) -> Project:
        """Convert database row to Project model."""
        return Project(
            key=row['key'],
            name=row['name'],
            description=row['description'] or "",
            jira_id=row['jira_id'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
            is_active=bool(row['is_active']),
            project_type=row['project_type'] or "software",
            lead=row['lead'],
            url=row['url'],
            avatar_url=row['avatar_url'],
            category=row['category'],
            issue_count=row['issue_count'] or 0,
            default_priority=IssuePriority.from_string(row['default_priority']),
            default_issue_type=IssueType.from_string(row['default_issue_type'])
        )

    # =============================================================================
    # USER PREFERENCES OPERATIONS
    # =============================================================================

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

    async def get_user_preferences(self, user_id: str) -> Optional[UserPreferences]:
        """Get user preferences."""
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")

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

    # =============================================================================
    # USER SESSION OPERATIONS
    # =============================================================================

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

    async def get_user_session(self, user_id: str) -> Optional[UserSession]:
        """Get user session."""
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM user_sessions WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return UserSession(
                        user_id=row['user_id'],
                        wizard_state=WizardState.from_string(row['wizard_state']),
                        wizard_data=json.loads(row['wizard_data']) if row['wizard_data'] else {},
                        last_command=row['last_command'],
                        last_message_id=row['last_message_id'],
                        created_at=datetime.fromisoformat(row['created_at']),
                        expires_at=datetime.fromisoformat(row['expires_at'])
                    )
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user session {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user session: {e}")

    # =============================================================================
    # ISSUE OPERATIONS - PLACEHOLDER IMPLEMENTATIONS
    # =============================================================================

    async def create_issue(
        self,
        jira_key: str,
        jira_id: str,
        project_key: str,
        summary: str,
        description: str = "",
        issue_type: Union[IssueType, str] = IssueType.TASK,
        status: Union[IssueStatus, str] = IssueStatus.TODO,
        priority: Union[IssuePriority, str] = IssuePriority.MEDIUM,
        assignee: Optional[str] = None,
        reporter: Optional[str] = None,
        telegram_user_id: Optional[str] = None,
        telegram_message_id: Optional[int] = None,
        due_date: Optional[datetime] = None
    ) -> int:
        """Create a new issue and return database ID."""
        # Convert enums to strings
        type_str = issue_type.value if isinstance(issue_type, IssueType) else str(issue_type)
        status_str = status.value if isinstance(status, IssueStatus) else str(status)
        priority_str = priority.value if isinstance(priority, IssuePriority) else str(priority)

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("""
                    INSERT INTO issues 
                    (jira_key, jira_id, project_key, summary, description, issue_type, 
                     status, priority, assignee, reporter, telegram_user_id, telegram_message_id,
                     due_date, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    jira_key, jira_id, project_key, summary, description, type_str,
                    status_str, priority_str, assignee, reporter, telegram_user_id,
                    telegram_message_id, due_date.isoformat() if due_date else None,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))
                await conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            self.logger.error(f"Failed to create issue {jira_key}: {e}")
            raise DatabaseError(f"Failed to create issue: {e}")

    async def get_issue_by_key(self, jira_key: str) -> Optional[JiraIssue]:
        """Get issue by Jira key."""
        if not isinstance(jira_key, str) or not jira_key.strip():
            raise ValueError("jira_key must be a non-empty string")

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM issues WHERE jira_key = ?", (jira_key,)
                )
                row = await cursor.fetchone()
                
                if row:
                    return self._row_to_issue(row)
                return None
        except Exception as e:
            self.logger.error(f"Failed to get issue {jira_key}: {e}")
            raise DatabaseError(f"Failed to retrieve issue: {e}")

    def _row_to_issue(self, row) -> JiraIssue:
        """Convert database row to JiraIssue model."""
        return JiraIssue(
            key=row['jira_key'],
            jira_id=row['jira_id'],
            project_key=row['project_key'],
            summary=row['summary'],
            description=row['description'] or "",
            issue_type=IssueType.from_string(row['issue_type']),
            status=IssueStatus.from_string(row['status']),
            priority=IssuePriority.from_string(row['priority']),
            assignee=row['assignee'],
            reporter=row['reporter'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            due_date=datetime.fromisoformat(row['due_date']) if row['due_date'] else None,
            resolved_at=datetime.fromisoformat(row['resolved_at']) if row['resolved_at'] else None
        )

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired user sessions."""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM user_sessions WHERE expires_at < ?",
                    (datetime.now(timezone.utc).isoformat(),)
                )
                await conn.commit()
                return cursor.rowcount
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired sessions: {e}")
            raise DatabaseError(f"Failed to cleanup sessions: {e}")

    async def vacuum(self) -> None:
        """Vacuum the database to reclaim space."""
        try:
            async with self._get_connection() as conn:
                await conn.execute("VACUUM")
                self.logger.info("Database vacuumed successfully")
        except Exception as e:
            self.logger.error(f"Failed to vacuum database: {e}")
            raise DatabaseError(f"Failed to vacuum database: {e}")

    async def close(self) -> None:
        """Close database connections (placeholder for connection pool)."""
        self.logger.info("Database connections closed")