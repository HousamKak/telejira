"""
Database Service for managing persistent data.

This service provides a clean repository interface for all database operations,
handling connections, transactions, and data mapping. All methods return domain model instances.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite
from aiosqlite import Connection

from models import (
    IssuePriority,
    IssueType,
    JiraIssue,
    Project,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Exception raised for database operation errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        """Initialize database error.
        
        Args:
            message: Error message
            original_error: Original exception that caused this error
        """
        super().__init__(message)
        self.original_error = original_error


class DatabaseService:
    """
    Service for managing all database operations.
    
    Provides methods for user management, project management, and statistics.
    All methods return domain model instances and handle database errors appropriately.
    """

    def __init__(self, database_path: str = "bot.db") -> None:
        """
        Initialize database service.
        
        Args:
            database_path: Path to SQLite database file
            
        Raises:
            TypeError: If database_path is not string
        """
        if not isinstance(database_path, str) or not database_path:
            raise TypeError("database_path must be non-empty string")

        self.database_path = database_path
        self._connection: Optional[Connection] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables if needed.
        
        Raises:
            DatabaseError: If initialization fails
        """
        try:
            self._connection = await aiosqlite.connect(self.database_path)
            self._connection.row_factory = aiosqlite.Row
            
            # Create tables
            await self._create_tables()
            self._initialized = True
            
            logger.info(f"Database initialized: {self.database_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise DatabaseError(f"Database initialization failed: {e}", e)

    async def close(self) -> None:
        """Close database connection and cleanup resources."""
        if self._connection:
            await self._connection.close()
            self._connection = None
        self._initialized = False

    def is_initialized(self) -> bool:
        """Check if database is initialized and ready for operations."""
        return self._initialized and self._connection is not None

    async def _ensure_connection(self) -> Connection:
        """Ensure database connection is available."""
        if not self.is_initialized():
            raise DatabaseError("Database not initialized. Call initialize() first.")
        
        if self._connection is None:
            raise DatabaseError("Database connection is None")
            
        return self._connection

    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        connection = await self._ensure_connection()
        
        # Users table
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                preferred_language TEXT DEFAULT 'en',
                timezone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Preauthorized users table
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS preauthorized_users (
                username TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Projects table
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                url TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                project_type TEXT DEFAULT 'software',
                lead TEXT,
                avatar_url TEXT,
                default_priority TEXT DEFAULT 'Medium',
                default_issue_type TEXT DEFAULT 'Task',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # User projects associations
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS user_projects (
                user_id TEXT,
                project_key TEXT,
                is_default INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, project_key),
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (project_key) REFERENCES projects (key)
            )
        """)

        # User activity log
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS user_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        # Optional: Issues table for local tracking (if needed)
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                key TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                project_key TEXT NOT NULL,
                issue_type TEXT,
                status TEXT,
                priority TEXT,
                assignee_account_id TEXT,
                created_by_user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_key) REFERENCES projects (key),
                FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
            )
        """)

        # Create indexes for better performance
        await connection.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users (user_id)")
        await connection.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)")
        await connection.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_user_id ON user_activity_log (user_id)")
        await connection.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_timestamp ON user_activity_log (timestamp)")
        
        await connection.commit()

    # -------- Users --------

    async def list_users(self) -> List[User]:
        """
        Get all users from the database.
        
        Returns:
            List of User instances
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT row_id, user_id, username, first_name, last_name, role, 
                       is_active, preferred_language, timezone, created_at, last_activity
                FROM users 
                ORDER BY created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                
            users = []
            for row in rows:
                user = self._row_to_user(row)
                users.append(user)
                
            return users
            
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            raise DatabaseError(f"Failed to list users: {e}", e)

    async def get_user_by_telegram_id(self, user_id: str) -> Optional[User]:
        """
        Get user by Telegram ID.
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            User instance if found, None otherwise
            
        Raises:
            TypeError: If user_id is not string
            DatabaseError: If query fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT row_id, user_id, username, first_name, last_name, role, 
                       is_active, preferred_language, timezone, created_at, last_activity
                FROM users 
                WHERE user_id = ?
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                
            return self._row_to_user(row) if row else None
            
        except Exception as e:
            logger.error(f"Failed to get user by telegram ID {user_id}: {e}")
            raise DatabaseError(f"Failed to get user by telegram ID: {e}", e)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username to search for
            
        Returns:
            User instance if found, None otherwise
            
        Raises:
            TypeError: If username is not string
            DatabaseError: If query fails
        """
        if not isinstance(username, str) or not username:
            raise TypeError("username must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT row_id, user_id, username, first_name, last_name, role, 
                       is_active, preferred_language, timezone, created_at, last_activity
                FROM users 
                WHERE username = ?
            """, (username,)) as cursor:
                row = await cursor.fetchone()
                
            return self._row_to_user(row) if row else None
            
        except Exception as e:
            logger.error(f"Failed to get user by username {username}: {e}")
            raise DatabaseError(f"Failed to get user by username: {e}", e)

    async def get_user_by_row_id(self, row_id: int) -> Optional[User]:
        """
        Get user by database row ID.
        
        Args:
            row_id: Database row ID
            
        Returns:
            User instance if found, None otherwise
            
        Raises:
            TypeError: If row_id is not integer
            DatabaseError: If query fails
        """
        if not isinstance(row_id, int) or row_id <= 0:
            raise TypeError("row_id must be positive integer")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT row_id, user_id, username, first_name, last_name, role, 
                       is_active, preferred_language, timezone, created_at, last_activity
                FROM users 
                WHERE row_id = ?
            """, (row_id,)) as cursor:
                row = await cursor.fetchone()
                
            return self._row_to_user(row) if row else None
            
        except Exception as e:
            logger.error(f"Failed to get user by row ID {row_id}: {e}")
            raise DatabaseError(f"Failed to get user by row ID: {e}", e)

    async def create_user(
        self,
        *,
        user_id: str,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        role: UserRole,
        is_active: bool = True,
        preferred_language: str = "en",
        timezone: Optional[str] = None,
    ) -> int:
        """
        Create a new user.
        
        Args:
            user_id: Telegram user ID as string
            username: Username (optional)
            first_name: First name (optional)
            last_name: Last name (optional)
            role: User role
            is_active: Whether user is active
            preferred_language: Preferred language code
            timezone: User timezone (optional)
            
        Returns:
            Database row ID of created user
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If user creation fails
        """
        # Parameter validation
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")
        if username is not None and not isinstance(username, str):
            raise TypeError("username must be string or None")
        if first_name is not None and not isinstance(first_name, str):
            raise TypeError("first_name must be string or None")
        if last_name is not None and not isinstance(last_name, str):
            raise TypeError("last_name must be string or None")
        if not isinstance(role, UserRole):
            raise TypeError(f"role must be UserRole, got {type(role)}")
        if not isinstance(is_active, bool):
            raise TypeError("is_active must be boolean")
        if not isinstance(preferred_language, str):
            raise TypeError("preferred_language must be string")
        if timezone is not None and not isinstance(timezone, str):
            raise TypeError("timezone must be string or None")

        try:
            connection = await self._ensure_connection()
            
            cursor = await connection.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, role, 
                                 is_active, preferred_language, timezone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, role.value, 
                  is_active, preferred_language, timezone))
            
            await connection.commit()
            row_id = cursor.lastrowid
            
            logger.info(f"Created user {user_id} with row ID {row_id}")
            return row_id
            
        except Exception as e:
            logger.error(f"Failed to create user {user_id}: {e}")
            raise DatabaseError(f"Failed to create user: {e}", e)

    async def update_user_last_activity(self, user_id: str) -> None:
        """
        Update user's last activity timestamp.
        
        Args:
            user_id: Telegram user ID as string
            
        Raises:
            TypeError: If user_id is not string
            DatabaseError: If update fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            await connection.execute("""
                UPDATE users 
                SET last_activity = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            
            await connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to update last activity for user {user_id}: {e}")
            raise DatabaseError(f"Failed to update user last activity: {e}", e)

    async def update_user_role(self, row_id: int, role: UserRole) -> None:
        """
        Update user's role.
        
        Args:
            row_id: Database row ID
            role: New user role
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If update fails
        """
        if not isinstance(row_id, int) or row_id <= 0:
            raise TypeError("row_id must be positive integer")
        if not isinstance(role, UserRole):
            raise TypeError(f"role must be UserRole, got {type(role)}")

        try:
            connection = await self._ensure_connection()
            
            await connection.execute("""
                UPDATE users 
                SET role = ? 
                WHERE row_id = ?
            """, (role.value, row_id))
            
            await connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to update role for user {row_id}: {e}")
            raise DatabaseError(f"Failed to update user role: {e}", e)

    async def deactivate_user(self, row_id: int) -> None:
        """
        Deactivate a user.
        
        Args:
            row_id: Database row ID
            
        Raises:
            TypeError: If row_id is not integer
            DatabaseError: If deactivation fails
        """
        if not isinstance(row_id, int) or row_id <= 0:
            raise TypeError("row_id must be positive integer")

        try:
            connection = await self._ensure_connection()
            
            await connection.execute("""
                UPDATE users 
                SET is_active = 0 
                WHERE row_id = ?
            """, (row_id,))
            
            await connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to deactivate user {row_id}: {e}")
            raise DatabaseError(f"Failed to deactivate user: {e}", e)

    # Preauthorization methods

    async def add_preauthorized_user(self, username: str, role: UserRole) -> None:
        """
        Add a preauthorized user for initial access.
        
        Args:
            username: Username to preauthorize
            role: Role to assign when user first joins
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If insertion fails
        """
        if not isinstance(username, str) or not username:
            raise TypeError("username must be non-empty string")
        if not isinstance(role, UserRole):
            raise TypeError(f"role must be UserRole, got {type(role)}")

        try:
            connection = await self._ensure_connection()
            
            await connection.execute("""
                INSERT OR REPLACE INTO preauthorized_users (username, role)
                VALUES (?, ?)
            """, (username, role.value))
            
            await connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to add preauthorized user {username}: {e}")
            raise DatabaseError(f"Failed to add preauthorized user: {e}", e)

    async def get_preauthorized_user_role(self, username: str) -> Optional[UserRole]:
        """
        Get role for preauthorized user.
        
        Args:
            username: Username to check
            
        Returns:
            UserRole if user is preauthorized, None otherwise
            
        Raises:
            TypeError: If username is not string
            DatabaseError: If query fails
        """
        if not isinstance(username, str) or not username:
            raise TypeError("username must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT role 
                FROM preauthorized_users 
                WHERE username = ?
            """, (username,)) as cursor:
                row = await cursor.fetchone()
                
            if row:
                try:
                    return UserRole(row['role'])
                except ValueError:
                    logger.warning(f"Invalid role found for preauthorized user {username}: {row['role']}")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get preauthorized user role for {username}: {e}")
            raise DatabaseError(f"Failed to get preauthorized user role: {e}", e)

    # -------- Projects --------

    async def list_projects(self) -> List[Project]:
        """
        Get all projects from the database.
        
        Returns:
            List of Project instances
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT key, name, description, url, is_active, project_type, lead,
                       avatar_url, default_priority, default_issue_type, created_at, updated_at
                FROM projects 
                ORDER BY name
            """) as cursor:
                rows = await cursor.fetchall()
                
            projects = []
            for row in rows:
                project = self._row_to_project(row)
                projects.append(project)
                
            return projects
            
        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            raise DatabaseError(f"Failed to list projects: {e}", e)

    async def get_project_by_key(self, project_key: str) -> Optional[Project]:
        """
        Get project by key.
        
        Args:
            project_key: Project key to search for
            
        Returns:
            Project instance if found, None otherwise
            
        Raises:
            TypeError: If project_key is not string
            DatabaseError: If query fails
        """
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT key, name, description, url, is_active, project_type, lead,
                       avatar_url, default_priority, default_issue_type, created_at, updated_at
                FROM projects 
                WHERE key = ?
            """, (project_key,)) as cursor:
                row = await cursor.fetchone()
                
            return self._row_to_project(row) if row else None
            
        except Exception as e:
            logger.error(f"Failed to get project by key {project_key}: {e}")
            raise DatabaseError(f"Failed to get project by key: {e}", e)

    async def create_project(
        self,
        *,
        key: str,
        name: str,
        description: str = "",
        url: str = "",
        is_active: bool = True,
        project_type: str = "software",
        lead: Optional[str] = None,
        avatar_url: Optional[str] = None,
        default_priority: IssuePriority = IssuePriority.MEDIUM,
        default_issue_type: IssueType = IssueType.TASK,
    ) -> int:
        """
        Create a new project.
        
        Args:
            key: Project key (unique identifier)
            name: Project name
            description: Project description
            url: Project URL
            is_active: Whether project is active
            project_type: Type of project
            lead: Project lead name
            avatar_url: URL to project avatar image
            default_priority: Default priority for new issues
            default_issue_type: Default type for new issues
            
        Returns:
            Number of affected rows (should be 1)
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If project creation fails
        """
        # Parameter validation
        if not isinstance(key, str) or not key:
            raise TypeError("key must be non-empty string")
        if not isinstance(name, str) or not name:
            raise TypeError("name must be non-empty string")
        if not isinstance(description, str):
            raise TypeError("description must be string")
        if not isinstance(url, str):
            raise TypeError("url must be string")
        if not isinstance(is_active, bool):
            raise TypeError("is_active must be boolean")
        if not isinstance(project_type, str):
            raise TypeError("project_type must be string")
        if lead is not None and not isinstance(lead, str):
            raise TypeError("lead must be string or None")
        if avatar_url is not None and not isinstance(avatar_url, str):
            raise TypeError("avatar_url must be string or None")
        if not isinstance(default_priority, IssuePriority):
            raise TypeError(f"default_priority must be IssuePriority, got {type(default_priority)}")
        if not isinstance(default_issue_type, IssueType):
            raise TypeError(f"default_issue_type must be IssueType, got {type(default_issue_type)}")

        try:
            connection = await self._ensure_connection()
            
            cursor = await connection.execute("""
                INSERT INTO projects (key, name, description, url, is_active, project_type,
                                    lead, avatar_url, default_priority, default_issue_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (key, name, description, url, is_active, project_type, lead, avatar_url,
                  default_priority.value, default_issue_type.value))
            
            await connection.commit()
            
            logger.info(f"Created project {key}")
            return cursor.rowcount
            
        except Exception as e:
            logger.error(f"Failed to create project {key}: {e}")
            raise DatabaseError(f"Failed to create project: {e}", e)

    async def update_project(
        self,
        *,
        project_key: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        url: Optional[str] = None,
        is_active: Optional[bool] = None,
        project_type: Optional[str] = None,
        lead: Optional[str] = None,
        avatar_url: Optional[str] = None,
        default_priority: Optional[IssuePriority] = None,
        default_issue_type: Optional[IssueType] = None,
    ) -> None:
        """
        Update an existing project.
        
        Args:
            project_key: Project key to update
            name: New project name (optional)
            description: New description (optional)
            url: New URL (optional)
            is_active: New active status (optional)
            project_type: New project type (optional)
            lead: New project lead (optional)
            avatar_url: New avatar URL (optional)
            default_priority: New default priority (optional)
            default_issue_type: New default issue type (optional)
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If project update fails
        """
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")

        # Build update query dynamically based on provided parameters
        updates = []
        params = []
        
        if name is not None:
            if not isinstance(name, str):
                raise TypeError("name must be string")
            updates.append("name = ?")
            params.append(name)
            
        if description is not None:
            if not isinstance(description, str):
                raise TypeError("description must be string")
            updates.append("description = ?")
            params.append(description)
            
        if url is not None:
            if not isinstance(url, str):
                raise TypeError("url must be string")
            updates.append("url = ?")
            params.append(url)
            
        if is_active is not None:
            if not isinstance(is_active, bool):
                raise TypeError("is_active must be boolean")
            updates.append("is_active = ?")
            params.append(is_active)
            
        if project_type is not None:
            if not isinstance(project_type, str):
                raise TypeError("project_type must be string")
            updates.append("project_type = ?")
            params.append(project_type)
            
        if lead is not None:
            if not isinstance(lead, str):
                raise TypeError("lead must be string")
            updates.append("lead = ?")
            params.append(lead)
            
        if avatar_url is not None:
            if not isinstance(avatar_url, str):
                raise TypeError("avatar_url must be string")
            updates.append("avatar_url = ?")
            params.append(avatar_url)
            
        if default_priority is not None:
            if not isinstance(default_priority, IssuePriority):
                raise TypeError(f"default_priority must be IssuePriority, got {type(default_priority)}")
            updates.append("default_priority = ?")
            params.append(default_priority.value)
            
        if default_issue_type is not None:
            if not isinstance(default_issue_type, IssueType):
                raise TypeError(f"default_issue_type must be IssueType, got {type(default_issue_type)}")
            updates.append("default_issue_type = ?")
            params.append(default_issue_type.value)

        if not updates:
            return  # Nothing to update

        # Add updated_at timestamp
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(project_key)

        try:
            connection = await self._ensure_connection()
            
            query = f"UPDATE projects SET {', '.join(updates)} WHERE key = ?"
            await connection.execute(query, params)
            await connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to update project {project_key}: {e}")
            raise DatabaseError(f"Failed to update project: {e}", e)

    # User → Projects & preferences

    async def list_user_projects(self, user_id: str) -> List[Project]:
        """
        Get all projects associated with a user.
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            List of Project instances
            
        Raises:
            TypeError: If user_id is not string
            DatabaseError: If query fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT p.key, p.name, p.description, p.url, p.is_active, p.project_type, 
                       p.lead, p.avatar_url, p.default_priority, p.default_issue_type, 
                       p.created_at, p.updated_at
                FROM projects p
                JOIN user_projects up ON p.key = up.project_key
                WHERE up.user_id = ? AND p.is_active = 1
                ORDER BY up.is_default DESC, p.name
            """, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                
            projects = []
            for row in rows:
                project = self._row_to_project(row)
                projects.append(project)
                
            return projects
            
        except Exception as e:
            logger.error(f"Failed to list user projects for {user_id}: {e}")
            raise DatabaseError(f"Failed to list user projects: {e}", e)

    async def get_user_default_project(self, user_id: str) -> Optional[Project]:
        """
        Get user's default project.
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            Project instance if found, None otherwise
            
        Raises:
            TypeError: If user_id is not string
            DatabaseError: If query fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT p.key, p.name, p.description, p.url, p.is_active, p.project_type, 
                       p.lead, p.avatar_url, p.default_priority, p.default_issue_type, 
                       p.created_at, p.updated_at
                FROM projects p
                JOIN user_projects up ON p.key = up.project_key
                WHERE up.user_id = ? AND up.is_default = 1 AND p.is_active = 1
            """, (user_id,)) as cursor:
                row = await cursor.fetchone()
                
            return self._row_to_project(row) if row else None
            
        except Exception as e:
            logger.error(f"Failed to get user default project for {user_id}: {e}")
            raise DatabaseError(f"Failed to get user default project: {e}", e)

    async def set_user_default_project(self, user_id: str, project_key: str) -> None:
        """
        Set user's default project.
        
        Args:
            user_id: Telegram user ID as string
            project_key: Project key to set as default
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If operation fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            # Start transaction
            await connection.execute("BEGIN")
            
            # Clear existing default
            await connection.execute("""
                UPDATE user_projects 
                SET is_default = 0 
                WHERE user_id = ?
            """, (user_id,))
            
            # Set new default (insert if not exists)
            await connection.execute("""
                INSERT OR REPLACE INTO user_projects (user_id, project_key, is_default)
                VALUES (?, ?, 1)
            """, (user_id, project_key))
            
            await connection.commit()
            
        except Exception as e:
            await connection.rollback()
            logger.error(f"Failed to set default project for {user_id}: {e}")
            raise DatabaseError(f"Failed to set user default project: {e}", e)

    # -------- Statistics --------

    async def get_user_statistics(self, user_row_id: int) -> Dict[str, Any]:
        """
        Get detailed statistics for a specific user.
        
        Args:
            user_row_id: Database row ID of the user
            
        Returns:
            Dictionary containing user statistics
            
        Raises:
            TypeError: If user_row_id is not integer
            DatabaseError: If query fails
        """
        if not isinstance(user_row_id, int) or user_row_id <= 0:
            raise TypeError("user_row_id must be positive integer")

        try:
            connection = await self._ensure_connection()
            
            # Get user info
            async with connection.execute("""
                SELECT user_id, username, first_name, last_name, role, created_at, last_activity
                FROM users WHERE row_id = ?
            """, (user_row_id,)) as cursor:
                user_row = await cursor.fetchone()
                
            if not user_row:
                return {'error': 'User not found'}
            
            # Get activity count
            async with connection.execute("""
                SELECT COUNT(*) as activity_count
                FROM user_activity_log 
                WHERE user_id = ?
            """, (user_row['user_id'],)) as cursor:
                activity_row = await cursor.fetchone()
            
            # Get project count
            async with connection.execute("""
                SELECT COUNT(*) as project_count
                FROM user_projects 
                WHERE user_id = ?
            """, (user_row['user_id'],)) as cursor:
                project_row = await cursor.fetchone()
            
            # Get created issues count (if tracking locally)
            async with connection.execute("""
                SELECT COUNT(*) as created_issues
                FROM issues 
                WHERE created_by_user_id = ?
            """, (user_row['user_id'],)) as cursor:
                issues_row = await cursor.fetchone()
            
            return {
                'user_id': user_row['user_id'],
                'username': user_row['username'],
                'display_name': f"{user_row['first_name'] or ''} {user_row['last_name'] or ''}".strip(),
                'role': user_row['role'],
                'created_at': user_row['created_at'],
                'last_activity': user_row['last_activity'],
                'activity_count': activity_row['activity_count'] if activity_row else 0,
                'project_count': project_row['project_count'] if project_row else 0,
                'created_issues': issues_row['created_issues'] if issues_row else 0,
            }
            
        except Exception as e:
            logger.error(f"Failed to get user statistics for {user_row_id}: {e}")
            raise DatabaseError(f"Failed to get user statistics: {e}", e)

    async def get_user_statistics_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for all users.
        
        Returns:
            Dictionary containing user statistics summary
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            # Get user counts by role
            async with connection.execute("""
                SELECT role, COUNT(*) as count
                FROM users 
                WHERE is_active = 1
                GROUP BY role
            """) as cursor:
                role_rows = await cursor.fetchall()
            
            # Get activity statistics
            async with connection.execute("""
                SELECT 
                    COUNT(DISTINCT user_id) as active_users_today,
                    COUNT(*) as total_activities_today
                FROM user_activity_log 
                WHERE DATE(timestamp) = DATE('now')
            """) as cursor:
                activity_row = await cursor.fetchone()
            
            # Get recent registrations
            async with connection.execute("""
                SELECT COUNT(*) as new_users_this_week
                FROM users 
                WHERE created_at >= DATE('now', '-7 days')
            """) as cursor:
                new_users_row = await cursor.fetchone()
            
            role_counts = {row['role']: row['count'] for row in role_rows}
            
            return {
                'total_users': sum(role_counts.values()),
                'role_distribution': role_counts,
                'active_today': activity_row['active_users_today'] if activity_row else 0,
                'activities_today': activity_row['total_activities_today'] if activity_row else 0,
                'new_users_this_week': new_users_row['new_users_this_week'] if new_users_row else 0,
            }
            
        except Exception as e:
            logger.error(f"Failed to get user statistics summary: {e}")
            raise DatabaseError(f"Failed to get user statistics summary: {e}", e)

    async def get_project_statistics(self, project_key: str) -> Dict[str, Any]:
        """
        Get detailed statistics for a specific project.
        
        Args:
            project_key: Project key to get statistics for
            
        Returns:
            Dictionary containing project statistics
            
        Raises:
            TypeError: If project_key is not string
            DatabaseError: If query fails
        """
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            # Get project info
            async with connection.execute("""
                SELECT key, name, created_at, updated_at
                FROM projects WHERE key = ?
            """, (project_key,)) as cursor:
                project_row = await cursor.fetchone()
                
            if not project_row:
                return {'error': 'Project not found'}
            
            # Get user count
            async with connection.execute("""
                SELECT COUNT(*) as user_count
                FROM user_projects 
                WHERE project_key = ?
            """, (project_key,)) as cursor:
                user_row = await cursor.fetchone()
            
            # Get issues count (if tracking locally)
            async with connection.execute("""
                SELECT COUNT(*) as issue_count
                FROM issues 
                WHERE project_key = ?
            """, (project_key,)) as cursor:
                issues_row = await cursor.fetchone()
            
            return {
                'project_key': project_row['key'],
                'project_name': project_row['name'],
                'created_at': project_row['created_at'],
                'updated_at': project_row['updated_at'],
                'user_count': user_row['user_count'] if user_row else 0,
                'issue_count': issues_row['issue_count'] if issues_row else 0,
            }
            
        except Exception as e:
            logger.error(f"Failed to get project statistics for {project_key}: {e}")
            raise DatabaseError(f"Failed to get project statistics: {e}", e)

    async def get_project_statistics_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for all projects.
        
        Returns:
            Dictionary containing project statistics summary
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            # Get project counts
            async with connection.execute("""
                SELECT 
                    COUNT(*) as total_projects,
                    SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_projects
                FROM projects
            """) as cursor:
                project_row = await cursor.fetchone()
            
            # Get most popular projects
            async with connection.execute("""
                SELECT p.key, p.name, COUNT(up.user_id) as user_count
                FROM projects p
                LEFT JOIN user_projects up ON p.key = up.project_key
                WHERE p.is_active = 1
                GROUP BY p.key, p.name
                ORDER BY user_count DESC
                LIMIT 5
            """) as cursor:
                popular_rows = await cursor.fetchall()
            
            popular_projects = [
                {
                    'key': row['key'], 
                    'name': row['name'], 
                    'user_count': row['user_count']
                } 
                for row in popular_rows
            ]
            
            return {
                'total_projects': project_row['total_projects'] if project_row else 0,
                'active_projects': project_row['active_projects'] if project_row else 0,
                'popular_projects': popular_projects,
            }
            
        except Exception as e:
            logger.error(f"Failed to get project statistics summary: {e}")
            raise DatabaseError(f"Failed to get project statistics summary: {e}", e)

    async def get_activity_statistics(self, *, days: int) -> Dict[str, Any]:
        """
        Get activity statistics for the specified number of days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary containing activity statistics
            
        Raises:
            TypeError: If days is not integer
            DatabaseError: If query fails
        """
        if not isinstance(days, int) or days <= 0:
            raise TypeError("days must be positive integer")

        try:
            connection = await self._ensure_connection()
            
            # Get daily activity counts
            async with connection.execute("""
                SELECT 
                    DATE(timestamp) as date,
                    COUNT(*) as activity_count,
                    COUNT(DISTINCT user_id) as unique_users
                FROM user_activity_log 
                WHERE timestamp >= DATE('now', '-{} days')
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            """.format(days)) as cursor:
                daily_rows = await cursor.fetchall()
            
            # Get top actions
            async with connection.execute("""
                SELECT 
                    action,
                    COUNT(*) as count
                FROM user_activity_log 
                WHERE timestamp >= DATE('now', '-{} days')
                GROUP BY action
                ORDER BY count DESC
                LIMIT 10
            """.format(days)) as cursor:
                action_rows = await cursor.fetchall()
            
            daily_activity = [
                {
                    'date': row['date'],
                    'activity_count': row['activity_count'],
                    'unique_users': row['unique_users']
                }
                for row in daily_rows
            ]
            
            top_actions = [
                {'action': row['action'], 'count': row['count']}
                for row in action_rows
            ]
            
            return {
                'period_days': days,
                'daily_activity': daily_activity,
                'top_actions': top_actions,
                'total_activities': sum(day['activity_count'] for day in daily_activity),
                'total_unique_users': len(set(day['unique_users'] for day in daily_activity)),
            }
            
        except Exception as e:
            logger.error(f"Failed to get activity statistics for {days} days: {e}")
            raise DatabaseError(f"Failed to get activity statistics: {e}", e)

    # Simple counts

    async def get_user_count(self) -> int:
        """
        Get total number of active users.
        
        Returns:
            Number of active users
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT COUNT(*) as count 
                FROM users 
                WHERE is_active = 1
            """) as cursor:
                row = await cursor.fetchone()
                
            return row['count'] if row else 0
            
        except Exception as e:
            logger.error(f"Failed to get user count: {e}")
            raise DatabaseError(f"Failed to get user count: {e}", e)

    async def get_project_count(self) -> int:
        """
        Get total number of active projects.
        
        Returns:
            Number of active projects
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT COUNT(*) as count 
                FROM projects 
                WHERE is_active = 1
            """) as cursor:
                row = await cursor.fetchone()
                
            return row['count'] if row else 0
            
        except Exception as e:
            logger.error(f"Failed to get project count: {e}")
            raise DatabaseError(f"Failed to get project count: {e}", e)

    async def get_total_issue_count(self) -> int:
        """
        Get total number of issues (if tracking locally).
        
        Returns:
            Number of issues
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT COUNT(*) as count 
                FROM issues
            """) as cursor:
                row = await cursor.fetchone()
                
            return row['count'] if row else 0
            
        except Exception as e:
            logger.error(f"Failed to get total issue count: {e}")
            raise DatabaseError(f"Failed to get total issue count: {e}", e)

    # Optional "local" issue tracking

    async def list_user_issues(self, user_id: str, *, limit: int = 20) -> List[JiraIssue]:
        """
        Get issues created by a specific user (if tracking locally).
        
        Args:
            user_id: Telegram user ID as string
            limit: Maximum number of issues to return
            
        Returns:
            List of JiraIssue instances (empty if not tracking locally)
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If query fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")
        if not isinstance(limit, int) or limit <= 0:
            raise TypeError("limit must be positive integer")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT key, summary, project_key, issue_type, status, priority,
                       assignee_account_id, created_at, updated_at
                FROM issues 
                WHERE created_by_user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
            
            # Convert to JiraIssue instances (simplified)
            issues = []
            for row in rows:
                try:
                    # Create minimal JiraIssue from local data
                    issue = JiraIssue(
                        key=row['key'],
                        summary=row['summary'],
                        description="",  # Not stored locally
                        issue_type=IssueType(row['issue_type']) if row['issue_type'] else IssueType.TASK,
                        status=row['status'] or "Unknown",
                        priority=IssuePriority(row['priority']) if row['priority'] else IssuePriority.MEDIUM,
                        assignee=row['assignee_account_id'],
                        project_key=row['project_key'],
                        created=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                    )
                    issues.append(issue)
                except Exception as e:
                    logger.warning(f"Failed to parse local issue {row['key']}: {e}")
            
            return issues
            
        except Exception as e:
            logger.error(f"Failed to list user issues for {user_id}: {e}")
            raise DatabaseError(f"Failed to list user issues: {e}", e)

    async def get_project_issue_count(self, project_key: str) -> int:
        """
        Get number of issues for a project (if tracking locally).
        
        Args:
            project_key: Project key
            
        Returns:
            Number of issues for the project
            
        Raises:
            TypeError: If project_key is not string
            DatabaseError: If query fails
        """
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")

        try:
            connection = await self._ensure_connection()
            
            async with connection.execute("""
                SELECT COUNT(*) as count 
                FROM issues
                WHERE project_key = ?
            """, (project_key,)) as cursor:
                row = await cursor.fetchone()
                
            return row['count'] if row else 0
            
        except Exception as e:
            logger.error(f"Failed to get project issue count for {project_key}: {e}")
            raise DatabaseError(f"Failed to get project issue count: {e}", e)

    # Audit/log

    async def log_user_action(
        self, 
        user_id: str, 
        action: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a user action for audit purposes.
        
        Args:
            user_id: Telegram user ID as string
            action: Action description
            details: Optional additional details as JSON
            
        Raises:
            TypeError: If parameters have incorrect types
            DatabaseError: If logging fails
        """
        if not isinstance(user_id, str) or not user_id:
            raise TypeError("user_id must be non-empty string")
        if not isinstance(action, str) or not action:
            raise TypeError("action must be non-empty string")
        if details is not None and not isinstance(details, dict):
            raise TypeError("details must be dict or None")

        try:
            connection = await self._ensure_connection()
            
            import json
            details_json = json.dumps(details) if details else None
            
            await connection.execute("""
                INSERT INTO user_activity_log (user_id, action, details)
                VALUES (?, ?, ?)
            """, (user_id, action, details_json))
            
            await connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to log user action {action} for {user_id}: {e}")
            raise DatabaseError(f"Failed to log user action: {e}", e)

    # Helper methods for data conversion

    def _row_to_user(self, row) -> User:
        """Convert database row to User instance."""
        if not row:
            raise ValueError("Cannot convert None row to User")

        try:
            role = UserRole(row['role'])
        except ValueError:
            logger.warning(f"Invalid role in database: {row['role']}, defaulting to USER")
            role = UserRole.USER

        created_at = None
        last_activity = None
        
        if row['created_at']:
            try:
                created_at = datetime.fromisoformat(row['created_at'])
            except ValueError:
                pass
                
        if row['last_activity']:
            try:
                last_activity = datetime.fromisoformat(row['last_activity'])
            except ValueError:
                pass

        return User(
            row_id=row['row_id'],
            user_id=row['user_id'],
            username=row['username'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            role=role,
            is_active=bool(row['is_active']),
            preferred_language=row['preferred_language'] or "en",
            timezone=row['timezone'],
            created_at=created_at,
            last_activity=last_activity,
        )

    def _row_to_project(self, row) -> Project:
        """Convert database row to Project instance."""
        if not row:
            raise ValueError("Cannot convert None row to Project")

        try:
            default_priority = IssuePriority(row['default_priority'])
        except ValueError:
            default_priority = IssuePriority.MEDIUM

        try:
            default_issue_type = IssueType(row['default_issue_type'])
        except ValueError:
            default_issue_type = IssueType.TASK

        created_at = None
        updated_at = None
        
        if row['created_at']:
            try:
                created_at = datetime.fromisoformat(row['created_at'])
            except ValueError:
                pass
                
        if row['updated_at']:
            try:
                updated_at = datetime.fromisoformat(row['updated_at'])
            except ValueError:
                pass

        return Project(
            key=row['key'],
            name=row['name'],
            description=row['description'] or "",
            url=row['url'] or "",
            is_active=bool(row['is_active']),
            project_type=row['project_type'] or "software",
            lead=row['lead'],
            avatar_url=row['avatar_url'],
            default_priority=default_priority,
            default_issue_type=default_issue_type,
            created_at=created_at,
            updated_at=updated_at,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()