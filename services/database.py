#!/usr/bin/env python3
"""
Database service for the Telegram-Jira bot.

Manages all database operations using SQLite with async support.
"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Callable
import aiosqlite

from models.user import User, UserPreferences, UserSession
from models.project import Project, ProjectStats
from models.issue import JiraIssue, IssueComment
from models.enums import UserRole, IssuePriority, IssueType, IssueStatus


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class DatabaseManager:
    """Enhanced database manager with comprehensive fixes."""

    def __init__(
        self, 
        db_path: str = "bot_data.db",
        pool_size: int = 5,
        timeout: float = 30.0,
        enable_wal: bool = True,
        enable_foreign_keys: bool = True
    ) -> None:
        """Initialize database manager with enhanced configuration."""
        self.db_path = Path(db_path)
        self.pool_size = max(1, min(pool_size, 20))  # Clamp between 1-20
        self.timeout = max(5.0, min(timeout, 300.0))  # Clamp between 5-300 seconds
        self.enable_wal = enable_wal
        self.enable_foreign_keys = enable_foreign_keys
        
        # Connection management
        self._connection_pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._initialized = False
        
        self.logger = logging.getLogger(self.__class__.__name__)

    async def initialize(self) -> None:
        """Initialize database with enhanced setup."""
        if self._initialized:
            self.logger.warning("Database already initialized")
            return

        try:
            # Ensure directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Test basic connectivity
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("SELECT 1")

            # Temporarily set initialized to True to allow _get_connection()
            old_flag = self._initialized
            self._initialized = True

            try:
                # Create tables and setup
                await self._create_tables()
                await self._setup_database_settings()

                # Leave initialized=True on success
                self.logger.info(f"✅ Database initialized: {self.db_path}")
            except Exception as e:
                # Restore flag if an exception occurs
                self._initialized = old_flag
                raise e

        except Exception as e:
            self.logger.error(f"❌ Database initialization failed: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}")

    @asynccontextmanager
    async def _get_connection(self):
        """Get database connection with proper resource management."""
        if not self._initialized:
            raise DatabaseError("Database not initialized")
        
        conn = None
        try:
            # Create new connection with optimized settings
            conn = await aiosqlite.connect(
                self.db_path,
                timeout=self.timeout,
                isolation_level=None  # Explicit transaction control
            )
            
            # Configure connection
            if self.enable_foreign_keys:
                await conn.execute("PRAGMA foreign_keys = ON")
            
            if self.enable_wal:
                await conn.execute("PRAGMA journal_mode = WAL")
            
            # Performance optimizations
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            await conn.execute("PRAGMA temp_store = MEMORY")
            await conn.execute("PRAGMA mmap_size = 268435456")  # 256MB mmap
            
            # Set row factory for dictionary-like access
            conn.row_factory = aiosqlite.Row
            
            yield conn
            
        except sqlite3.Error as e:
            if conn:
                try:
                    await conn.rollback()
                except:
                    pass
            raise DatabaseError(f"Database operation failed: {e}")
        except Exception as e:
            if conn:
                try:
                    await conn.rollback()
                except:
                    pass
            raise DatabaseError(f"Unexpected database error: {e}")
        finally:
            if conn:
                try:
                    await conn.close()
                except Exception as e:
                    self.logger.warning(f"Error closing connection: {e}")

    async def _execute_transaction(
        self, 
        operations: List[Callable],
        read_only: bool = False
    ) -> List[Any]:
        """Execute multiple operations in a single transaction."""
        async with self._get_connection() as conn:
            try:
                if not read_only:
                    await conn.execute("BEGIN IMMEDIATE TRANSACTION")
                else:
                    await conn.execute("BEGIN TRANSACTION")
                
                results = []
                for operation in operations:
                    if asyncio.iscoroutinefunction(operation):
                        result = await operation(conn)
                    else:
                        result = operation(conn)
                    results.append(result)
                
                if not read_only:
                    await conn.commit()
                
                return results
                
            except Exception as e:
                if not read_only:
                    await conn.rollback()
                self.logger.error(f"Transaction failed: {e}")
                raise DatabaseError(f"Transaction execution failed: {e}")

    async def _create_tables(self) -> None:
        """Create all database tables with enhanced schema."""
        async with self._get_connection() as conn:
            try:
                # Users table with enhanced constraints
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT UNIQUE NOT NULL CHECK (length(user_id) > 0 AND length(user_id) <= 20),
                        username TEXT CHECK (username IS NULL OR (length(username) > 0 AND length(username) <= 32)),
                        first_name TEXT CHECK (first_name IS NULL OR (length(first_name) > 0 AND length(first_name) <= 64)),
                        last_name TEXT CHECK (last_name IS NULL OR (length(last_name) <= 64)),
                        role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin', 'super_admin')),
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        issues_created INTEGER NOT NULL DEFAULT 0 CHECK (issues_created >= 0),
                        preferred_language TEXT NOT NULL DEFAULT 'en' CHECK (length(preferred_language) <= 10),
                        timezone TEXT NOT NULL DEFAULT 'UTC' CHECK (length(timezone) <= 50),
                        default_project_key TEXT CHECK (default_project_key IS NULL OR length(default_project_key) <= 20),
                        FOREIGN KEY(default_project_key) REFERENCES projects(key) ON DELETE SET NULL
                    )
                """)

                # Create indexes for performance
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity)")

                # User sessions table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        user_id TEXT PRIMARY KEY CHECK (length(user_id) > 0),
                        wizard_state TEXT NOT NULL DEFAULT 'idle' CHECK (length(wizard_state) > 0),
                        wizard_data TEXT NOT NULL DEFAULT '{}',
                        last_command TEXT CHECK (last_command IS NULL OR length(last_command) <= 100),
                        last_message_id INTEGER CHECK (last_message_id IS NULL OR last_message_id > 0),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL DEFAULT (datetime('now', '+1 day')),
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                """)

                # Projects table with enhanced validation
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL CHECK (length(key) > 0 AND length(key) <= 20),
                        name TEXT NOT NULL CHECK (length(name) > 0 AND length(name) <= 255),
                        description TEXT NOT NULL DEFAULT '',
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        jira_id TEXT CHECK (jira_id IS NULL OR length(jira_id) <= 50),
                        project_type TEXT NOT NULL DEFAULT 'software' CHECK (
                            project_type IN ('software', 'service_desk', 'business', 'product_discovery')
                        ),
                        lead TEXT CHECK (lead IS NULL OR length(lead) <= 100),
                        url TEXT CHECK (url IS NULL OR length(url) <= 500),
                        avatar_url TEXT CHECK (avatar_url IS NULL OR length(avatar_url) <= 500),
                        category TEXT CHECK (category IS NULL OR length(category) <= 100),
                        issue_count INTEGER NOT NULL DEFAULT 0 CHECK (issue_count >= 0),
                        default_priority TEXT NOT NULL DEFAULT 'medium' CHECK (
                            default_priority IN ('lowest', 'low', 'medium', 'high', 'critical')
                        ),
                        default_issue_type TEXT NOT NULL DEFAULT 'task' CHECK (
                            default_issue_type IN ('task', 'story', 'bug', 'epic', 'improvement', 'subtask')
                        )
                    )
                """)

                # Project indexes
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_key ON projects(key)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_type ON projects(project_type)")

                # Issues table with comprehensive validation
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS issues (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        jira_id TEXT UNIQUE NOT NULL CHECK (length(jira_id) > 0 AND length(jira_id) <= 50),
                        key TEXT UNIQUE NOT NULL CHECK (length(key) > 0 AND length(key) <= 50),
                        summary TEXT NOT NULL CHECK (length(summary) > 0 AND length(summary) <= 500),
                        description TEXT NOT NULL DEFAULT '',
                        priority TEXT NOT NULL DEFAULT 'medium' CHECK (
                            priority IN ('lowest', 'low', 'medium', 'high', 'critical')
                        ),
                        issue_type TEXT NOT NULL DEFAULT 'task' CHECK (
                            issue_type IN ('task', 'story', 'bug', 'epic', 'improvement', 'subtask')
                        ),
                        status TEXT NOT NULL DEFAULT 'todo' CHECK (length(status) > 0 AND length(status) <= 50),
                        project_id INTEGER NOT NULL,
                        creator_id INTEGER NOT NULL,
                        assignee_id INTEGER CHECK (assignee_id IS NULL OR assignee_id > 0),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        jira_created_at TIMESTAMP,
                        jira_updated_at TIMESTAMP,
                        resolution TEXT CHECK (resolution IS NULL OR length(resolution) <= 100),
                        labels TEXT NOT NULL DEFAULT '[]',
                        components TEXT NOT NULL DEFAULT '[]',
                        fix_versions TEXT NOT NULL DEFAULT '[]',
                        story_points INTEGER CHECK (story_points IS NULL OR story_points >= 0),
                        original_estimate INTEGER CHECK (original_estimate IS NULL OR original_estimate >= 0),
                        remaining_estimate INTEGER CHECK (remaining_estimate IS NULL OR remaining_estimate >= 0),
                        time_spent INTEGER CHECK (time_spent IS NULL OR time_spent >= 0),
                        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                        FOREIGN KEY(creator_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY(assignee_id) REFERENCES users(id) ON DELETE SET NULL
                    )
                """)

                # Issue indexes for performance
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_jira_id ON issues(jira_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_key ON issues(key)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_project_id ON issues(project_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_creator_id ON issues(creator_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_assignee_id ON issues(assignee_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_priority ON issues(priority)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_created_at ON issues(created_at)")

                # Issue comments table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS issue_comments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        jira_id TEXT UNIQUE NOT NULL CHECK (length(jira_id) > 0),
                        issue_id INTEGER NOT NULL,
                        author_id INTEGER NOT NULL,
                        body TEXT NOT NULL CHECK (length(body) > 0),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        jira_created_at TIMESTAMP,
                        jira_updated_at TIMESTAMP,
                        visibility TEXT CHECK (visibility IS NULL OR length(visibility) <= 50),
                        FOREIGN KEY(issue_id) REFERENCES issues(id) ON DELETE CASCADE,
                        FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """)

                # Comment indexes
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON issue_comments(issue_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_author_id ON issue_comments(author_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_created_at ON issue_comments(created_at)")

                await conn.commit()
                self.logger.info("✅ Database tables created successfully")

            except Exception as e:
                await conn.rollback()
                self.logger.error(f"❌ Failed to create tables: {e}")
                raise DatabaseError(f"Table creation failed: {e}")

    async def _setup_database_settings(self) -> None:
        """Setup database-wide settings and triggers."""
        async with self._get_connection() as conn:
            try:
                # Create trigger to update project issue count
                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS update_project_issue_count_insert
                    AFTER INSERT ON issues
                    BEGIN
                        UPDATE projects 
                        SET issue_count = issue_count + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = NEW.project_id;
                    END
                """)

                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS update_project_issue_count_delete
                    AFTER DELETE ON issues
                    BEGIN
                        UPDATE projects 
                        SET issue_count = issue_count - 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = OLD.project_id;
                    END
                """)

                # Create trigger to update user issues_created count
                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS update_user_issues_created
                    AFTER INSERT ON issues
                    BEGIN
                        UPDATE users 
                        SET issues_created = issues_created + 1,
                            last_activity = CURRENT_TIMESTAMP
                        WHERE id = NEW.creator_id;
                    END
                """)

                # Create trigger to update timestamps
                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS update_issue_timestamp
                    AFTER UPDATE ON issues
                    BEGIN
                        UPDATE issues 
                        SET updated_at = CURRENT_TIMESTAMP
                        WHERE id = NEW.id;
                    END
                """)

                await conn.commit()
                self.logger.info("✅ Database triggers created successfully")

            except Exception as e:
                await conn.rollback()
                self.logger.error(f"❌ Failed to setup database settings: {e}")
                raise DatabaseError(f"Database setup failed: {e}")

    # Enhanced user operations with comprehensive validation
    async def create_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: Union[UserRole, str] = UserRole.USER,
        is_active: bool = True,
        preferred_language: str = "en",
        user_timezone: str = "UTC"
    ) -> int:
        """Create a new user with comprehensive validation."""
        # Input validation
        if not user_id or not isinstance(user_id, str) or len(user_id.strip()) == 0:
            raise ValueError("user_id must be a non-empty string")
        
        user_id = user_id.strip()
        if len(user_id) > 20:
            raise ValueError("user_id must be 20 characters or less")
        
        if username is not None:
            username = username.strip() if username else None
            if username and len(username) > 32:
                raise ValueError("username must be 32 characters or less")
        
        if first_name is not None:
            first_name = first_name.strip() if first_name else None
            if first_name and len(first_name) > 64:
                raise ValueError("first_name must be 64 characters or less")
        
        if last_name is not None:
            last_name = last_name.strip() if last_name else None
            if last_name and len(last_name) > 64:
                raise ValueError("last_name must be 64 characters or less")
        
        # Role validation and conversion
        if isinstance(role, str):
            try:
                role = UserRole.from_string(role)
            except ValueError as e:
                raise ValueError(f"Invalid role: {e}")
        elif not isinstance(role, UserRole):
            raise TypeError("role must be a UserRole instance or valid string")
        
        # Language and timezone validation
        if not preferred_language or len(preferred_language) > 10:
            preferred_language = "en"
        
        if not user_timezone or len(user_timezone) > 50:
            user_timezone = "UTC"

        try:
            async with self._get_connection() as conn:
                # Check if user already exists
                cursor = await conn.execute(
                    "SELECT id FROM users WHERE user_id = ?", (user_id,)
                )
                existing = await cursor.fetchone()
                if existing:
                    raise ValueError(f"User with ID {user_id} already exists")
                
                # Insert new user
                cursor = await conn.execute("""
                    INSERT INTO users (
                        user_id, username, first_name, last_name, role, 
                        is_active, preferred_language, timezone, created_at, last_activity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, username, first_name, last_name, role.value,
                    is_active, preferred_language, user_timezone,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))
                
                await conn.commit()
                user_db_id = cursor.lastrowid
                
                self.logger.info(f"✅ User created: {user_id} (DB ID: {user_db_id})")
                return user_db_id
                
        except sqlite3.IntegrityError as e:
            self.logger.error(f"❌ User creation integrity error: {e}")
            raise ValueError(f"User creation failed: {e}")
        except Exception as e:
            self.logger.error(f"❌ Failed to create user {user_id}: {e}")
            raise DatabaseError(f"Failed to create user: {e}")

    async def get_user_by_telegram_id(self, user_id: str) -> Optional[User]:
        """Get user by Telegram ID with enhanced error handling."""
        if not user_id or not isinstance(user_id, str):
            raise ValueError("user_id must be a non-empty string")
        
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE user_id = ? AND is_active = 1", 
                    (user_id.strip(),)
                )
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                # Update last activity
                await conn.execute(
                    "UPDATE users SET last_activity = ? WHERE user_id = ?",
                    (datetime.now(timezone.utc).isoformat(), user_id.strip())
                )
                await conn.commit()
                
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
                
        except ValueError:
            raise
        except Exception as e:
            self.logger.error(f"❌ Failed to get user {user_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive database health check."""
        try:
            async with self._get_connection() as conn:
                start_time = asyncio.get_event_loop().time()
                
                # Basic connectivity
                await conn.execute("SELECT 1")
                
                # Check table existence
                cursor = await conn.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name IN ('users', 'projects', 'issues')
                """)
                tables = [row[0] for row in await cursor.fetchall()]
                
                # Check foreign key constraints
                await conn.execute("PRAGMA foreign_key_check")
                
                # Check database integrity
                cursor = await conn.execute("PRAGMA integrity_check")
                integrity_result = await cursor.fetchone()
                
                # Get basic stats
                cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
                active_users = (await cursor.fetchone())[0]
                
                cursor = await conn.execute("SELECT COUNT(*) FROM projects WHERE is_active = 1")
                active_projects = (await cursor.fetchone())[0]
                
                cursor = await conn.execute("SELECT COUNT(*) FROM issues")
                total_issues = (await cursor.fetchone())[0]
                
                response_time = asyncio.get_event_loop().time() - start_time
                
                return {
                    'status': 'healthy',
                    'response_time_ms': round(response_time * 1000, 2),
                    'tables_present': len(tables) == 3,
                    'integrity_check': integrity_result[0] == 'ok',
                    'stats': {
                        'active_users': active_users,
                        'active_projects': active_projects,
                        'total_issues': total_issues
                    },
                    'database_path': str(self.db_path),
                    'database_size_mb': round(self.db_path.stat().st_size / 1024 / 1024, 2)
                }
                
        except Exception as e:
            self.logger.error(f"❌ Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'database_path': str(self.db_path)
            }

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired user sessions."""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("""
                    DELETE FROM user_sessions 
                    WHERE expires_at < datetime('now')
                """)
                await conn.commit()
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    self.logger.info(f"🧹 Cleaned up {deleted_count} expired sessions")
                
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"❌ Failed to cleanup expired sessions: {e}")
            raise DatabaseError(f"Session cleanup failed: {e}")

    async def close(self) -> None:
        """Close database connections and cleanup."""
        try:
            async with self._pool_lock:
                for conn in self._connection_pool:
                    if not conn._connection.is_closed:
                        await conn.close()
                self._connection_pool.clear()
            
            self._initialized = False
            self.logger.info("✅ Database connections closed")
            
        except Exception as e:
            self.logger.error(f"❌ Error closing database: {e}")
            
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._initialized

    @asynccontextmanager
    async def get_connection(self):
        """Public interface for getting database connections."""
        async with self._get_connection() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions."""
        async with self._get_connection() as conn:
            try:
                await conn.execute("BEGIN IMMEDIATE TRANSACTION")
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                self.logger.error(f"Transaction failed: {e}")
                raise DatabaseError(f"Transaction execution failed: {e}")