#!/usr/bin/env python3
"""
User model for the Telegram-Jira bot.

Contains user-related data models and preferences.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from .enums import IssuePriority, IssueType, UserRole, WizardState


@dataclass
class User:
    """Telegram user data model."""
    user_id: int
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

    def _validate_user_id(self) -> None:
        """Validate user ID."""
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")

    def _validate_strings(self) -> None:
        """Validate string fields."""
        string_fields = [self.username, self.first_name, self.last_name, self.timezone]
        for field in string_fields:
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for serialization."""
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
        """Create User from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse enum
        role = UserRole.USER
        if data.get('role'):
            try:
                role = UserRole(data['role'])
            except ValueError:
                role = UserRole.USER

        # Parse datetime fields
        created_at = datetime.now(timezone.utc)
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        last_activity = datetime.now(timezone.utc)
        if data.get('last_activity'):
            last_activity = datetime.fromisoformat(data['last_activity'])

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

    @classmethod
    def from_telegram_user(cls, telegram_user) -> 'User':
        """Create User from telegram.User object."""
        return cls(
            user_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name
        )

    def get_display_name(self) -> str:
        """Get user's display name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.user_id}"

    def get_full_name(self) -> str:
        """Get user's full name with username."""
        display_name = self.get_display_name()
        if self.username and not display_name.startswith('@'):
            return f"{display_name} (@{self.username})"
        return display_name

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(timezone.utc)

    def increment_issues_created(self) -> None:
        """Increment the count of issues created."""
        self.issues_created += 1

    def has_permission(self, required_role: UserRole) -> bool:
        """Check if user has required permission level."""
        return self.role.has_permission(required_role)

    def is_admin(self) -> bool:
        """Check if user is an admin."""
        return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

    def is_super_admin(self) -> bool:
        """Check if user is a super admin."""
        return self.role == UserRole.SUPER_ADMIN

    def get_activity_summary(self) -> str:
        """Get formatted activity summary."""
        days_since_created = (datetime.now(timezone.utc) - self.created_at).days
        days_since_activity = (datetime.now(timezone.utc) - self.last_activity).days
        
        summary = f"**{self.get_display_name()}**\n"
        summary += f"🆔 ID: `{self.user_id}`\n"
        summary += f"👤 Role: {self.role.value.title()}\n"
        summary += f"📊 Issues Created: {self.issues_created}\n"
        summary += f"📅 Member Since: {days_since_created} days ago\n"
        summary += f"⏰ Last Active: {days_since_activity} days ago\n"
        
        if self.timezone:
            summary += f"🌍 Timezone: {self.timezone}\n"
        
        status = "🟢 Active" if self.is_active else "🔴 Inactive"
        summary += f"📈 Status: {status}"
        
        return summary

    def __str__(self) -> str:
        """String representation of the user."""
        return f"User({self.user_id}: {self.get_display_name()})"

    def __repr__(self) -> str:
        """Developer representation of the user."""
        return (f"User(user_id={self.user_id}, role={self.role.value}, "
                f"is_active={self.is_active}, issues_created={self.issues_created})")


@dataclass
class UserPreferences:
    """User preferences for the bot."""
    user_id: int
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

    def _validate_user_id(self) -> None:
        """Validate user ID."""
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")

    def _validate_enums(self) -> None:
        """Validate enum fields."""
        if not isinstance(self.default_priority, IssuePriority):
            raise TypeError("default_priority must be an IssuePriority instance")
        if not isinstance(self.default_issue_type, IssueType):
            raise TypeError("default_issue_type must be an IssueType instance")

    def _validate_numeric_fields(self) -> None:
        """Validate numeric fields."""
        if not isinstance(self.max_issues_per_page, int) or self.max_issues_per_page <= 0:
            raise ValueError("max_issues_per_page must be a positive integer")

    def _validate_strings(self) -> None:
        """Validate string fields."""
        if self.default_project_key is not None and not isinstance(self.default_project_key, str):
            raise TypeError("default_project_key must be a string or None")
        if not isinstance(self.date_format, str) or not self.date_format.strip():
            raise ValueError("date_format must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Convert preferences to dictionary for serialization."""
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
        """Create UserPreferences from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse enums
        default_priority = IssuePriority.MEDIUM
        if data.get('default_priority'):
            try:
                default_priority = IssuePriority.from_string(data['default_priority'])
            except (ValueError, TypeError):
                pass

        default_issue_type = IssueType.TASK
        if data.get('default_issue_type'):
            try:
                default_issue_type = IssueType.from_string(data['default_issue_type'])
            except (ValueError, TypeError):
                pass

        # Parse datetime fields
        created_at = datetime.now(timezone.utc)
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        updated_at = datetime.now(timezone.utc)
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])

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

    def update_preference(self, key: str, value: Any) -> bool:
        """Update a specific preference."""
        if not hasattr(self, key):
            return False
        
        # Validate the value based on the field type
        current_value = getattr(self, key)
        
        if isinstance(current_value, bool) and not isinstance(value, bool):
            return False
        elif isinstance(current_value, int) and not isinstance(value, int):
            return False
        elif isinstance(current_value, str) and not isinstance(value, str):
            return False
        elif isinstance(current_value, IssuePriority):
            if isinstance(value, str):
                try:
                    value = IssuePriority.from_string(value)
                except ValueError:
                    return False
            elif not isinstance(value, IssuePriority):
                return False
        elif isinstance(current_value, IssueType):
            if isinstance(value, str):
                try:
                    value = IssueType.from_string(value)
                except ValueError:
                    return False
            elif not isinstance(value, IssueType):
                return False
        
        setattr(self, key, value)
        self.updated_at = datetime.now(timezone.utc)
        return True

    def get_formatted_preferences(self) -> str:
        """Get formatted preferences for display."""
        prefs = f"⚙️ **User Preferences**\n\n"
        prefs += f"🎯 Default Project: {self.default_project_key or 'None'}\n"
        prefs += f"🔸 Default Priority: {self.default_priority.get_emoji()} {self.default_priority.value}\n"
        prefs += f"📋 Default Issue Type: {self.default_issue_type.get_emoji()} {self.default_issue_type.value}\n"
        prefs += f"👤 Auto-assign to self: {'✅' if self.auto_assign_to_self else '❌'}\n"
        prefs += f"🔔 Notifications: {'✅' if self.notifications_enabled else '❌'}\n"
        prefs += f"📄 Include descriptions: {'✅' if self.include_description_in_summary else '❌'}\n"
        prefs += f"📊 Issues per page: {self.max_issues_per_page}\n"
        prefs += f"📅 Date format: {self.date_format}\n"
        prefs += f"🔍 Show issue details: {'✅' if self.show_issue_details else '❌'}\n"
        prefs += f"⚡ Quick create mode: {'✅' if self.quick_create_mode else '❌'}\n"
        
        return prefs

    def __str__(self) -> str:
        """String representation of preferences."""
        return f"UserPreferences(user_id={self.user_id}, project={self.default_project_key})"


@dataclass
class UserSession:
    """User session data for wizards and state management."""
    user_id: int
    wizard_state: WizardState = WizardState.IDLE
    wizard_data: Dict[str, Any] = field(default_factory=dict)
    last_command: Optional[str] = None
    last_message_id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(hour=23, minute=59, second=59))

    def __post_init__(self) -> None:
        """Validate session data after initialization."""
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not isinstance(self.wizard_state, WizardState):
            raise TypeError("wizard_state must be a WizardState instance")

    def is_expired(self) -> bool:
        """Check if session is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def extend_expiry(self, hours: int = 24) -> None:
        """Extend session expiry."""
        if not isinstance(hours, int) or hours <= 0:
            raise ValueError("hours must be a positive integer")
        
        self.expires_at = datetime.now(timezone.utc) + timezone.timedelta(hours=hours)

    def start_wizard(self, wizard_state: WizardState, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Start a new wizard session."""
        if not isinstance(wizard_state, WizardState):
            raise TypeError("wizard_state must be a WizardState instance")
        
        self.wizard_state = wizard_state
        self.wizard_data = initial_data or {}
        self.extend_expiry()

    def update_wizard_data(self, key: str, value: Any) -> None:
        """Update wizard data."""
        if not isinstance(key, str):
            raise TypeError("key must be a string")
        
        self.wizard_data[key] = value

    def get_wizard_data(self, key: str, default: Any = None) -> Any:
        """Get wizard data value."""
        return self.wizard_data.get(key, default)

    def clear_wizard(self) -> None:
        """Clear wizard state and data."""
        self.wizard_state = WizardState.IDLE
        self.wizard_data.clear()

    def is_in_wizard(self) -> bool:
        """Check if user is currently in a wizard."""
        return self.wizard_state != WizardState.IDLE

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            'user_id': self.user_id,
            'wizard_state': self.wizard_state.value,
            'wizard_data': self.wizard_data,
            'last_command': self.last_command,
            'last_message_id': self.last_message_id,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserSession':
        """Create UserSession from dictionary."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        # Parse enum
        wizard_state = WizardState.IDLE
        if data.get('wizard_state'):
            try:
                wizard_state = WizardState(data['wizard_state'])
            except ValueError:
                wizard_state = WizardState.IDLE

        # Parse datetime fields
        created_at = datetime.now(timezone.utc)
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        expires_at = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)
        if data.get('expires_at'):
            expires_at = datetime.fromisoformat(data['expires_at'])

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