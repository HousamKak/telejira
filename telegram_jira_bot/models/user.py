#!/usr/bin/env python3
"""
User model for the Telegram-Jira bot.

Contains user-related data models including User, UserPreferences, and UserSession
with comprehensive validation and business logic.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Union
from .enums import IssuePriority, IssueType, UserRole, WizardState


def parse_iso_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string with tolerant handling.
    
    Args:
        date_str: ISO datetime string
        
    Returns:
        Parsed datetime object or None if parsing fails
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # Handle various ISO formats
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        elif date_str.endswith('+0000'):
            date_str = date_str[:-5] + '+00:00'
        elif date_str.endswith('-0000'):
            date_str = date_str[:-5] + '+00:00'
        
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError, TypeError):
        return None


@dataclass
class User:
    """Telegram user data model with comprehensive validation."""
    user_id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    issues_created: int = 0
    preferred_language: str = "en"
    timezone: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Validate user data after initialization."""
        self._validate_user_id()
        self._validate_strings()
        self._validate_enums()
        self._validate_datetime_fields()
        self._validate_numeric_fields()

    def _validate_user_id(self) -> None:
        """Validate user ID."""
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-empty string")

    def _validate_strings(self) -> None:
        """Validate string fields."""
        optional_string_fields = [self.username, self.first_name, self.last_name, self.timezone]
        for field in optional_string_fields:
            if field is not None and not isinstance(field, str):
                raise TypeError("string fields must be strings or None")
        
        if not isinstance(self.preferred_language, str) or not self.preferred_language.strip():
            raise ValueError("preferred_language must be a non-empty string")

    def _validate_enums(self) -> None:
        """Validate enum fields."""
        if not isinstance(self.role, UserRole):
            raise TypeError("role must be a UserRole instance")

    def _validate_datetime_fields(self) -> None:
        """Validate datetime fields."""
        datetime_fields = [self.created_at, self.last_activity]
        for dt_field in datetime_fields:
            if not isinstance(dt_field, datetime):
                raise TypeError("datetime fields must be datetime instances")
        
        # Ensure last_activity is not before created_at
        if self.last_activity < self.created_at:
            raise ValueError("last_activity cannot be before created_at")

    def _validate_numeric_fields(self) -> None:
        """Validate numeric fields."""
        if not isinstance(self.issues_created, int) or self.issues_created < 0:
            raise ValueError("issues_created must be a non-negative integer")
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active must be a boolean")

    @classmethod
    def from_telegram_user(cls, telegram_user: Any) -> 'User':
        """Create User from Telegram user object.
        
        Args:
            telegram_user: Telegram user object
            
        Returns:
            User instance
        """
        return cls(
            user_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name
        )

    def get_display_name(self) -> str:
        """Get user's display name.
        
        Returns:
            Formatted display name
        """
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.user_id}"

    def get_full_name(self) -> str:
        """Get user's full name with username.
        
        Returns:
            Full name including username if available
        """
        display_name = self.get_display_name()
        if self.username and not display_name.startswith('@'):
            return f"{display_name} (@{self.username})"
        return display_name

    def update_activity(self) -> None:
        """Update last activity timestamp to now."""
        self.last_activity = datetime.now(timezone.utc)

    def increment_issues_created(self) -> None:
        """Increment the count of issues created by user."""
        self.issues_created += 1

    def has_permission(self, required_role: UserRole) -> bool:
        """Check if user has required permission level.
        
        Args:
            required_role: Minimum role required
            
        Returns:
            True if user has sufficient permissions
        """
        return self.role.has_permission(required_role)

    def is_admin(self) -> bool:
        """Check if user is an admin.
        
        Returns:
            True if user has admin privileges
        """
        return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

    def is_super_admin(self) -> bool:
        """Check if user is a super admin.
        
        Returns:
            True if user is a super admin
        """
        return self.role == UserRole.SUPER_ADMIN

    def get_activity_summary(self) -> str:
        """Get formatted activity summary.
        
        Returns:
            Formatted activity information
        """
        now = datetime.now(timezone.utc)
        days_since_created = (now - self.created_at).days
        days_since_activity = (now - self.last_activity).days
        
        summary = f"**{self.get_display_name()}**\n"
        summary += f"🆔 ID: `{self.user_id}`\n"
        summary += f"👤 Role: {self.role.get_display_name()}\n"
        summary += f"📊 Issues Created: {self.issues_created}\n"
        summary += f"📅 Member Since: {days_since_created} days ago\n"
        summary += f"⏰ Last Active: {days_since_activity} days ago\n"
        
        if self.timezone:
            summary += f"🌍 Timezone: {self.timezone}\n"
        
        status = "🟢 Active" if self.is_active else "🔴 Inactive"
        summary += f"📈 Status: {status}"
        
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for serialization.
        
        Returns:
            Dictionary representation of the user
        """
        return {
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'role': self.role.value,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'issues_created': self.issues_created,
            'preferred_language': self.preferred_language,
            'timezone': self.timezone
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create User from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            User instance
            
        Raises:
            TypeError: If data is not a dictionary
            ValueError: If required fields are missing
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse role enum
        role = UserRole.USER
        if data.get('role'):
            try:
                role = UserRole.from_string(data['role'])
            except (ValueError, TypeError):
                role = UserRole.USER

        # Parse datetime fields
        created_at = parse_iso_datetime(data.get('created_at')) or datetime.now(timezone.utc)
        last_activity = parse_iso_datetime(data.get('last_activity')) or created_at

        return cls(
            user_id=data['user_id'],
            username=data.get('username'),
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            role=role,
            is_active=data.get('is_active', True),
            created_at=created_at,
            last_activity=last_activity,
            issues_created=data.get('issues_created', 0),
            preferred_language=data.get('preferred_language', 'en'),
            timezone=data.get('timezone')
        )

    def __str__(self) -> str:
        """String representation of the user."""
        return f"User({self.user_id}: {self.get_display_name()})"

    def __repr__(self) -> str:
        """Developer representation of the user."""
        return (f"User(user_id={self.user_id}, role={self.role.value}, "
                f"is_active={self.is_active}, issues_created={self.issues_created})")


@dataclass
class UserPreferences:
    """User preferences for the bot with validation."""
    user_id: str
    default_project_key: Optional[str] = None
    default_priority: IssuePriority = IssuePriority.MEDIUM
    default_issue_type: IssueType = IssueType.TASK
    auto_assign_to_self: bool = False
    notifications_enabled: bool = True
    include_description_in_summary: bool = True
    max_issues_per_page: int = 5
    date_format: str = "%Y-%m-%d %H:%M"
    show_issue_details: bool = True
    quick_create_mode: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Validate preferences after initialization."""
        self._validate_user_id()
        self._validate_enums()
        self._validate_numeric_fields()
        self._validate_strings()
        self._validate_boolean_fields()
        self._validate_datetime_fields()

    def _validate_user_id(self) -> None:
        """Validate user ID."""
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-empty string")

    def _validate_enums(self) -> None:
        """Validate enum fields with proper defaults."""
        if not isinstance(self.default_priority, IssuePriority):
            try:
                if isinstance(self.default_priority, str):
                    self.default_priority = IssuePriority.from_string(self.default_priority)
                else:
                    raise TypeError("default_priority must be an IssuePriority instance")
            except (ValueError, TypeError):
                self.default_priority = IssuePriority.MEDIUM
        
        if not isinstance(self.default_issue_type, IssueType):
            try:
                if isinstance(self.default_issue_type, str):
                    self.default_issue_type = IssueType.from_string(self.default_issue_type)
                else:
                    raise TypeError("default_issue_type must be an IssueType instance")
            except (ValueError, TypeError):
                self.default_issue_type = IssueType.TASK

    def _validate_numeric_fields(self) -> None:
        """Validate numeric fields."""
        if not isinstance(self.max_issues_per_page, int) or self.max_issues_per_page <= 0:
            raise ValueError("max_issues_per_page must be a positive integer")
        if self.max_issues_per_page > 50:  # Reasonable upper limit
            raise ValueError("max_issues_per_page cannot exceed 50")

    def _validate_strings(self) -> None:
        """Validate string fields."""
        if self.default_project_key is not None:
            if not isinstance(self.default_project_key, str):
                raise TypeError("default_project_key must be a string or None")
            if not self.default_project_key.strip():
                self.default_project_key = None
        
        if not isinstance(self.date_format, str) or not self.date_format.strip():
            raise ValueError("date_format must be a non-empty string")
        
        # Test date format validity
        try:
            datetime.now().strftime(self.date_format)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid date_format: {self.date_format}")

    def _validate_boolean_fields(self) -> None:
        """Validate boolean fields."""
        boolean_fields = [
            self.auto_assign_to_self,
            self.notifications_enabled,
            self.include_description_in_summary,
            self.show_issue_details,
            self.quick_create_mode
        ]
        for field in boolean_fields:
            if not isinstance(field, bool):
                raise TypeError("boolean fields must be boolean values")

    def _validate_datetime_fields(self) -> None:
        """Validate datetime fields."""
        datetime_fields = [self.created_at, self.updated_at]
        for dt_field in datetime_fields:
            if not isinstance(dt_field, datetime):
                raise TypeError("datetime fields must be datetime instances")
        
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert preferences to dictionary for serialization.
        
        Returns:
            Dictionary representation of preferences
        """
        return {
            'user_id': self.user_id,
            'default_project_key': self.default_project_key,
            'default_priority': self.default_priority.value,
            'default_issue_type': self.default_issue_type.value,
            'auto_assign_to_self': self.auto_assign_to_self,
            'notifications_enabled': self.notifications_enabled,
            'include_description_in_summary': self.include_description_in_summary,
            'max_issues_per_page': self.max_issues_per_page,
            'date_format': self.date_format,
            'show_issue_details': self.show_issue_details,
            'quick_create_mode': self.quick_create_mode,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreferences':
        """Create UserPreferences from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            UserPreferences instance
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse enums
        try:
            default_priority = IssuePriority.from_string(data.get('default_priority', 'Medium'))
        except (ValueError, TypeError):
            default_priority = IssuePriority.MEDIUM

        try:
            default_issue_type = IssueType.from_string(data.get('default_issue_type', 'Task'))
        except (ValueError, TypeError):
            default_issue_type = IssueType.TASK

        # Parse datetime fields
        created_at = parse_iso_datetime(data.get('created_at')) or datetime.now(timezone.utc)
        updated_at = parse_iso_datetime(data.get('updated_at')) or created_at

        return cls(
            user_id=data['user_id'],
            default_project_key=data.get('default_project_key'),
            default_priority=default_priority,
            default_issue_type=default_issue_type,
            auto_assign_to_self=data.get('auto_assign_to_self', False),
            notifications_enabled=data.get('notifications_enabled', True),
            include_description_in_summary=data.get('include_description_in_summary', True),
            max_issues_per_page=data.get('max_issues_per_page', 5),
            date_format=data.get('date_format', "%Y-%m-%d %H:%M"),
            show_issue_details=data.get('show_issue_details', True),
            quick_create_mode=data.get('quick_create_mode', False),
            created_at=created_at,
            updated_at=updated_at
        )

    def __str__(self) -> str:
        """String representation of preferences."""
        return f"UserPreferences(user_id={self.user_id}, project={self.default_project_key})"

    def __repr__(self) -> str:
        """Developer representation of preferences."""
        return (f"UserPreferences(user_id={self.user_id}, "
                f"project='{self.default_project_key}', "
                f"priority={self.default_priority.value})")


@dataclass
class UserSession:
    """User session data for wizards and state management.
    
    FIXED: timezone.timedelta -> timedelta import issue resolved.
    """
    user_id: str
    wizard_state: WizardState = WizardState.IDLE
    wizard_data: Dict[str, Any] = field(default_factory=dict)
    last_command: Optional[str] = None
    last_message_id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(hour=23, minute=59, second=59))

    def __post_init__(self) -> None:
        """Validate session data after initialization."""
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        if not isinstance(self.wizard_state, WizardState):
            raise TypeError("wizard_state must be a WizardState instance")
        if not isinstance(self.wizard_data, dict):
            raise TypeError("wizard_data must be a dictionary")
        if self.last_command is not None and not isinstance(self.last_command, str):
            raise TypeError("last_command must be a string or None")
        if self.last_message_id is not None and not isinstance(self.last_message_id, int):
            raise TypeError("last_message_id must be an integer or None")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime object")
        if not isinstance(self.expires_at, datetime):
            raise TypeError("expires_at must be a datetime object")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")

    def is_expired(self) -> bool:
        """Check if session is expired.
        
        Returns:
            True if session has expired
        """
        return datetime.now(timezone.utc) > self.expires_at

    def extend_expiry(self, hours: int = 24) -> None:
        """Extend session expiry.
        
        FIXED: Now correctly imports and uses timedelta instead of timezone.timedelta
        
        Args:
            hours: Number of hours to extend (must be positive)
            
        Raises:
            ValueError: If hours is not a positive integer
        """
        if not isinstance(hours, int) or hours <= 0:
            raise ValueError("hours must be a positive integer")
        
        # FIXED: Use timedelta directly, not timezone.timedelta
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    def start_wizard(self, wizard_state: WizardState, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Start a new wizard session.
        
        Args:
            wizard_state: New wizard state
            initial_data: Initial wizard data
            
        Raises:
            TypeError: If wizard_state is not a WizardState instance
        """
        if not isinstance(wizard_state, WizardState):
            raise TypeError("wizard_state must be a WizardState instance")
        
        self.wizard_state = wizard_state
        self.wizard_data = initial_data or {}
        self.extend_expiry()

    def update_wizard_data(self, key: str, value: Any) -> None:
        """Update wizard data.
        
        Args:
            key: Data key
            value: Data value
            
        Raises:
            TypeError: If key is not a string
        """
        if not isinstance(key, str):
            raise TypeError("key must be a string")
        
        self.wizard_data[key] = value

    def get_wizard_data(self, key: str, default: Any = None) -> Any:
        """Get wizard data value.
        
        Args:
            key: Data key
            default: Default value if key not found
            
        Returns:
            Wizard data value or default
        """
        return self.wizard_data.get(key, default)

    def clear_wizard(self) -> None:
        """Clear wizard state and data."""
        self.wizard_state = WizardState.IDLE
        self.wizard_data.clear()

    def is_in_wizard(self) -> bool:
        """Check if user is currently in a wizard.
        
        Returns:
            True if wizard is active
        """
        return self.wizard_state.is_active()

    def get_wizard_progress(self) -> str:
        """Get formatted wizard progress information.
        
        Returns:
            Formatted progress string
        """
        if not self.is_in_wizard():
            return "No active wizard"
        
        state_name = self.wizard_state.value.replace('_', ' ').title()
        data_count = len(self.wizard_data)
        
        return f"Wizard: {state_name} ({data_count} data items)"

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization.
        
        Returns:
            Dictionary representation of session
        """
        return {
            'user_id': self.user_id,
            'wizard_state': self.wizard_state.value,
            'wizard_data': self.wizard_data.copy(),
            'last_command': self.last_command,
            'last_message_id': self.last_message_id,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserSession':
        """Create UserSession from dictionary.
        
        Args:
            data: Dictionary data
            
        Returns:
            UserSession instance
            
        Raises:
            TypeError: If data is not a dictionary
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse enum
        wizard_state = WizardState.IDLE
        if data.get('wizard_state'):
            try:
                wizard_state = WizardState.from_string(data['wizard_state'])
            except (ValueError, TypeError):
                wizard_state = WizardState.IDLE

        # Parse datetime fields with defaults
        created_at = parse_iso_datetime(data.get('created_at')) or datetime.now(timezone.utc)
        expires_at = parse_iso_datetime(data.get('expires_at'))
        
        # Default expiry to end of day if not specified
        if not expires_at:
            expires_at = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)

        return cls(
            user_id=data['user_id'],
            wizard_state=wizard_state,
            wizard_data=data.get('wizard_data', {}),
            last_command=data.get('last_command'),
            last_message_id=data.get('last_message_id'),
            created_at=created_at,
            expires_at=expires_at
        )

    def __str__(self) -> str:
        """String representation of session."""
        return f"UserSession(user_id={self.user_id}, state={self.wizard_state.value})"

    def __repr__(self) -> str:
        """Developer representation of session."""
        return (f"UserSession(user_id={self.user_id}, "
                f"state={self.wizard_state.value}, "
                f"expired={self.is_expired()})")