#!/usr/bin/env python3
"""
Configuration settings for the Telegram-Jira bot.

Handles environment variables, validation, and configuration management.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..models.enums import IssuePriority, IssueType


@dataclass(frozen=True)
class BotConfig:
    """Configuration for the Telegram-Jira bot."""
    # Required fields
    telegram_token: str
    jira_domain: str
    jira_email: str
    jira_api_token: str
    
    # Database configuration
    database_path: str = "bot_data.db"
    database_pool_size: int = 10
    database_timeout: int = 30
    
    # Bot behavior settings
    max_summary_length: int = 100
    max_description_length: int = 2000
    max_issues_per_page: int = 10
    max_projects_per_page: int = 15
    session_timeout_hours: int = 24
    
    # Default values
    default_priority: IssuePriority = IssuePriority.MEDIUM
    default_issue_type: IssueType = IssueType.TASK
    
    # Security settings
    allowed_users: List[str] = field(default_factory=list)
    admin_users: List[str] = field(default_factory=list)
    super_admin_users: List[str] = field(default_factory=list)
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    
    # Logging settings
    log_level: str = "INFO"
    log_file: str = "telegram_jira_bot.log"
    log_max_size: int = 10 * 1024 * 1024  # 10MB
    log_backup_count: int = 5
    
    # Jira API settings
    jira_timeout: int = 30
    jira_max_retries: int = 3
    jira_retry_delay: float = 1.0
    jira_page_size: int = 50
    
    # Telegram settings
    telegram_timeout: int = 30
    telegram_pool_timeout: int = 1
    telegram_connection_pool_size: int = 8
    
    # Feature flags
    enable_wizards: bool = True
    enable_shortcuts: bool = True
    enable_auto_sync: bool = False
    enable_notifications: bool = True
    enable_issue_comments: bool = True
    enable_time_tracking: bool = True
    
    # Cache settings
    cache_projects_minutes: int = 30
    cache_user_preferences_minutes: int = 60
    cache_jira_metadata_minutes: int = 120
    
    # UI settings
    use_inline_keyboards: bool = True
    show_issue_previews: bool = True
    show_user_avatars: bool = False
    compact_mode: bool = False

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate_required_fields()
        self._validate_domain_format()
        self._validate_numeric_fields()
        self._validate_log_level()
        self._validate_paths()
        self._validate_user_lists()

    def _validate_required_fields(self) -> None:
        """Validate required string fields are non-empty."""
        required_fields = {
            'telegram_token': self.telegram_token,
            'jira_domain': self.jira_domain,
            'jira_email': self.jira_email,
            'jira_api_token': self.jira_api_token,
        }
        
        for field_name, field_value in required_fields.items():
            if not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    def _validate_domain_format(self) -> None:
        """Validate Jira domain format."""
        # Remove protocol if present
        domain = self.jira_domain
        if domain.startswith(('http://', 'https://')):
            domain = domain.split('://', 1)[1]
        
        # Validate domain format
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$', domain):
            raise ValueError("jira_domain must be a valid domain name")

    def _validate_numeric_fields(self) -> None:
        """Validate numeric configuration fields."""
        numeric_fields = {
            'max_summary_length': (self.max_summary_length, 10, 500),
            'max_description_length': (self.max_description_length, 100, 10000),
            'max_issues_per_page': (self.max_issues_per_page, 1, 100),
            'max_projects_per_page': (self.max_projects_per_page, 1, 50),
            'session_timeout_hours': (self.session_timeout_hours, 1, 168),  # 1 hour to 1 week
            'database_pool_size': (self.database_pool_size, 1, 100),
            'database_timeout': (self.database_timeout, 5, 300),
            'rate_limit_per_minute': (self.rate_limit_per_minute, 1, 1000),
            'rate_limit_per_hour': (self.rate_limit_per_hour, 10, 10000),
            'jira_timeout': (self.jira_timeout, 5, 300),
            'jira_max_retries': (self.jira_max_retries, 0, 10),
            'jira_page_size': (self.jira_page_size, 10, 1000),
            'telegram_timeout': (self.telegram_timeout, 5, 300),
            'telegram_connection_pool_size': (self.telegram_connection_pool_size, 1, 100),
            'log_max_size': (self.log_max_size, 1024 * 1024, 100 * 1024 * 1024),  # 1MB to 100MB
            'log_backup_count': (self.log_backup_count, 1, 20),
        }
        
        for field_name, (value, min_val, max_val) in numeric_fields.items():
            if not isinstance(value, int) or not (min_val <= value <= max_val):
                raise ValueError(f"{field_name} must be an integer between {min_val} and {max_val}")
        
        # Validate float fields
        if not isinstance(self.jira_retry_delay, (int, float)) or self.jira_retry_delay < 0:
            raise ValueError("jira_retry_delay must be a non-negative number")
        
        if not isinstance(self.telegram_pool_timeout, (int, float)) or self.telegram_pool_timeout < 0:
            raise ValueError("telegram_pool_timeout must be a non-negative number")

    def _validate_log_level(self) -> None:
        """Validate log level is supported."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of: {valid_levels}")

    def _validate_paths(self) -> None:
        """Validate file paths."""
        if not isinstance(self.database_path, str) or not self.database_path.strip():
            raise ValueError("database_path must be a non-empty string")
        
        if not isinstance(self.log_file, str) or not self.log_file.strip():
            raise ValueError("log_file must be a non-empty string")

    def _validate_user_lists(self) -> None:
        """Validate user ID lists."""
        user_lists = [self.allowed_users, self.admin_users, self.super_admin_users]
        for user_list in user_lists:
            if not isinstance(user_list, list):
                raise TypeError("user lists must be lists")
            for user_id in user_list:
                if not isinstance(user_id, str) or not user_id.strip():
                    raise ValueError("user IDs must be non-empty strings")

    def get_jira_base_url(self) -> str:
        """Get the full Jira base URL."""
        domain = self.jira_domain
        if not domain.startswith(('http://', 'https://')):
            domain = f"https://{domain}"
        return domain

    def get_jira_api_url(self) -> str:
        """Get the Jira REST API base URL."""
        return f"{self.get_jira_base_url()}/rest/api/3"

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user ID is allowed to use the bot."""
        if not self.allowed_users:
            return True  # Allow all users if no restrictions
        return str(user_id) in self.allowed_users

    def is_user_admin(self, user_id: int) -> bool:
        """Check if a user ID is an admin."""
        return str(user_id) in self.admin_users

    def is_user_super_admin(self, user_id: int) -> bool:
        """Check if a user ID is a super admin."""
        return str(user_id) in self.super_admin_users

    def get_user_role_name(self, user_id: int) -> str:
        """Get the role name for a user."""
        if self.is_user_super_admin(user_id):
            return "Super Admin"
        elif self.is_user_admin(user_id):
            return "Admin"
        else:
            return "User"

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'telegram_token': '***HIDDEN***',  # Don't expose token
            'jira_domain': self.jira_domain,
            'jira_email': self.jira_email,
            'jira_api_token': '***HIDDEN***',  # Don't expose token
            'database_path': self.database_path,
            'log_level': self.log_level,
            'max_summary_length': self.max_summary_length,
            'default_priority': self.default_priority.value,
            'default_issue_type': self.default_issue_type.value,
            'rate_limit_per_minute': self.rate_limit_per_minute,
            'enable_wizards': self.enable_wizards,
            'enable_shortcuts': self.enable_shortcuts,
            'use_inline_keyboards': self.use_inline_keyboards,
        }

    def get_summary(self) -> str:
        """Get formatted configuration summary."""
        summary = "🔧 **Bot Configuration**\n\n"
        summary += f"**Jira:** {self.jira_domain}\n"
        summary += f"**Database:** {self.database_path}\n"
        summary += f"**Log Level:** {self.log_level}\n"
        summary += f"**Max Summary Length:** {self.max_summary_length}\n"
        summary += f"**Default Priority:** {self.default_priority.value}\n"
        summary += f"**Default Issue Type:** {self.default_issue_type.value}\n"
        summary += f"**Rate Limit:** {self.rate_limit_per_minute}/min\n"
        
        features = []
        if self.enable_wizards:
            features.append("Wizards")
        if self.enable_shortcuts:
            features.append("Shortcuts")
        if self.enable_auto_sync:
            features.append("Auto-sync")
        if self.enable_notifications:
            features.append("Notifications")
        
        if features:
            summary += f"**Features:** {', '.join(features)}\n"
        
        if self.allowed_users:
            summary += f"**User Restrictions:** {len(self.allowed_users)} allowed\n"
        if self.admin_users:
            summary += f"**Admins:** {len(self.admin_users)}\n"
        if self.super_admin_users:
            summary += f"**Super Admins:** {len(self.super_admin_users)}\n"
        
        return summary


def load_config_from_env(env_file: Optional[str] = None) -> BotConfig:
    """Load configuration from environment variables.
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        Loaded and validated bot configuration
        
    Raises:
        ValueError: If required environment variables are missing or invalid
        FileNotFoundError: If specified env_file doesn't exist
    """
    if env_file:
        env_path = Path(env_file)
        if not env_path.exists():
            raise FileNotFoundError(f"Environment file not found: {env_file}")
        
        from dotenv import load_dotenv
        load_dotenv(env_path)
    
    # Check required environment variables
    required_vars = [
        'TELEGRAM_TOKEN', 'JIRA_DOMAIN', 'JIRA_EMAIL', 'JIRA_API_TOKEN'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Parse user lists from comma-separated strings
    def parse_user_list(env_var: str) -> List[str]:
        value = os.getenv(env_var, '')
        if not value.strip():
            return []
        return [u.strip() for u in value.split(',') if u.strip()]

    allowed_users = parse_user_list('ALLOWED_USERS')
    admin_users = parse_user_list('ADMIN_USERS')
    super_admin_users = parse_user_list('SUPER_ADMIN_USERS')

    # Parse default priority with error handling
    default_priority = IssuePriority.MEDIUM
    if os.getenv('DEFAULT_PRIORITY'):
        try:
            default_priority = IssuePriority.from_string(os.getenv('DEFAULT_PRIORITY', ''))
        except (ValueError, TypeError):
            logging.warning(f"Invalid DEFAULT_PRIORITY value, using {IssuePriority.MEDIUM.value}")

    # Parse default issue type with error handling
    default_issue_type = IssueType.TASK
    if os.getenv('DEFAULT_ISSUE_TYPE'):
        try:
            default_issue_type = IssueType.from_string(os.getenv('DEFAULT_ISSUE_TYPE', ''))
        except (ValueError, TypeError):
            logging.warning(f"Invalid DEFAULT_ISSUE_TYPE value, using {IssueType.TASK.value}")

    # Parse numeric values with validation
    def parse_int(env_var: str, default: int, min_val: int, max_val: int) -> int:
        try:
            value = int(os.getenv(env_var, str(default)))
            if min_val <= value <= max_val:
                return value
            else:
                logging.warning(f"Invalid {env_var} value {value}, using default {default}")
                return default
        except (ValueError, TypeError):
            logging.warning(f"Invalid {env_var} value, using default {default}")
            return default

    def parse_float(env_var: str, default: float, min_val: float) -> float:
        try:
            value = float(os.getenv(env_var, str(default)))
            if value >= min_val:
                return value
            else:
                logging.warning(f"Invalid {env_var} value {value}, using default {default}")
                return default
        except (ValueError, TypeError):
            logging.warning(f"Invalid {env_var} value, using default {default}")
            return default

    def parse_bool(env_var: str, default: bool) -> bool:
        value = os.getenv(env_var, '').lower()
        if value in ('true', '1', 'yes', 'on'):
            return True
        elif value in ('false', '0', 'no', 'off'):
            return False
        else:
            return default

    return BotConfig(
        # Required fields
        telegram_token=os.getenv('TELEGRAM_TOKEN', ''),
        jira_domain=os.getenv('JIRA_DOMAIN', ''),
        jira_email=os.getenv('JIRA_EMAIL', ''),
        jira_api_token=os.getenv('JIRA_API_TOKEN', ''),
        
        # Database configuration
        database_path=os.getenv('DATABASE_PATH', 'bot_data.db'),
        database_pool_size=parse_int('DATABASE_POOL_SIZE', 10, 1, 100),
        database_timeout=parse_int('DATABASE_TIMEOUT', 30, 5, 300),
        
        # Bot behavior settings
        max_summary_length=parse_int('MAX_SUMMARY_LENGTH', 100, 10, 500),
        max_description_length=parse_int('MAX_DESCRIPTION_LENGTH', 2000, 100, 10000),
        max_issues_per_page=parse_int('MAX_ISSUES_PER_PAGE', 10, 1, 100),
        max_projects_per_page=parse_int('MAX_PROJECTS_PER_PAGE', 15, 1, 50),
        session_timeout_hours=parse_int('SESSION_TIMEOUT_HOURS', 24, 1, 168),
        
        # Default values
        default_priority=default_priority,
        default_issue_type=default_issue_type,
        
        # Security settings
        allowed_users=allowed_users,
        admin_users=admin_users,
        super_admin_users=super_admin_users,
        rate_limit_per_minute=parse_int('RATE_LIMIT_PER_MINUTE', 60, 1, 1000),
        rate_limit_per_hour=parse_int('RATE_LIMIT_PER_HOUR', 1000, 10, 10000),
        
        # Logging settings
        log_level=os.getenv('LOG_LEVEL', 'INFO').upper(),
        log_file=os.getenv('LOG_FILE', 'telegram_jira_bot.log'),
        log_max_size=parse_int('LOG_MAX_SIZE', 10 * 1024 * 1024, 1024 * 1024, 100 * 1024 * 1024),
        log_backup_count=parse_int('LOG_BACKUP_COUNT', 5, 1, 20),
        
        # Jira API settings
        jira_timeout=parse_int('JIRA_TIMEOUT', 30, 5, 300),
        jira_max_retries=parse_int('JIRA_MAX_RETRIES', 3, 0, 10),
        jira_retry_delay=parse_float('JIRA_RETRY_DELAY', 1.0, 0.0),
        jira_page_size=parse_int('JIRA_PAGE_SIZE', 50, 10, 1000),
        
        # Telegram settings
        telegram_timeout=parse_int('TELEGRAM_TIMEOUT', 30, 5, 300),
        telegram_pool_timeout=parse_float('TELEGRAM_POOL_TIMEOUT', 1.0, 0.0),
        telegram_connection_pool_size=parse_int('TELEGRAM_CONNECTION_POOL_SIZE', 8, 1, 100),
        
        # Feature flags
        enable_wizards=parse_bool('ENABLE_WIZARDS', True),
        enable_shortcuts=parse_bool('ENABLE_SHORTCUTS', True),
        enable_auto_sync=parse_bool('ENABLE_AUTO_SYNC', False),
        enable_notifications=parse_bool('ENABLE_NOTIFICATIONS', True),
        enable_issue_comments=parse_bool('ENABLE_ISSUE_COMMENTS', True),
        enable_time_tracking=parse_bool('ENABLE_TIME_TRACKING', True),
        
        # Cache settings
        cache_projects_minutes=parse_int('CACHE_PROJECTS_MINUTES', 30, 1, 1440),
        cache_user_preferences_minutes=parse_int('CACHE_USER_PREFERENCES_MINUTES', 60, 1, 1440),
        cache_jira_metadata_minutes=parse_int('CACHE_JIRA_METADATA_MINUTES', 120, 1, 1440),
        
        # UI settings
        use_inline_keyboards=parse_bool('USE_INLINE_KEYBOARDS', True),
        show_issue_previews=parse_bool('SHOW_ISSUE_PREVIEWS', True),
        show_user_avatars=parse_bool('SHOW_USER_AVATARS', False),
        compact_mode=parse_bool('COMPACT_MODE', False)
    )


def setup_logging(config: BotConfig) -> None:
    """Set up logging configuration.
    
    Args:
        config: Bot configuration containing logging settings
    """
    from logging.handlers import RotatingFileHandler
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        config.log_file,
        maxBytes=config.log_max_size,
        backupCount=config.log_backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Set specific loggers to appropriate levels
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)


def validate_config(config: BotConfig) -> List[str]:
    """Validate configuration and return list of warnings.
    
    Args:
        config: Configuration to validate
        
    Returns:
        List of warning messages
    """
    warnings = []
    
    # Check for common issues
    if not config.allowed_users and not config.admin_users:
        warnings.append("No user restrictions configured - bot will accept all users")
    
    if not config.admin_users and not config.super_admin_users:
        warnings.append("No admin users configured - administrative functions will be unavailable")
    
    if config.jira_domain.startswith('http'):
        warnings.append("JIRA_DOMAIN should not include protocol (http/https)")
    
    if config.max_summary_length < 50:
        warnings.append("MAX_SUMMARY_LENGTH is very short, may truncate issue titles heavily")
    
    if config.rate_limit_per_minute > 100:
        warnings.append("Rate limit is quite high, consider lowering for production use")
    
    if not config.enable_wizards and not config.enable_shortcuts:
        warnings.append("Both wizards and shortcuts are disabled - user experience may be poor")
    
    # Check file paths
    db_path = Path(config.database_path)
    if not db_path.parent.exists():
        warnings.append(f"Database directory does not exist: {db_path.parent}")
    
    log_path = Path(config.log_file)
    if not log_path.parent.exists():
        warnings.append(f"Log directory does not exist: {log_path.parent}")
    
    return warnings