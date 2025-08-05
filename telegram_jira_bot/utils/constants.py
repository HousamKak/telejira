#!/usr/bin/env python3
"""
Constants for the Telegram-Jira bot.

Contains emoji mappings, limits, and other constant values.
"""

from typing import Dict, List, Final

# Telegram API limits
MAX_MESSAGE_LENGTH: Final[int] = 4096
MAX_CALLBACK_DATA_LENGTH: Final[int] = 64
MAX_INLINE_KEYBOARD_BUTTONS: Final[int] = 100
MAX_REPLY_KEYBOARD_BUTTONS: Final[int] = 300

# Pagination limits
DEFAULT_PAGE_SIZE: Final[int] = 10
MAX_PAGE_SIZE: Final[int] = 50

# Text limits
MAX_SUMMARY_LENGTH: Final[int] = 200
MAX_DESCRIPTION_LENGTH: Final[int] = 5000
MAX_PROJECT_NAME_LENGTH: Final[int] = 255
MAX_PROJECT_KEY_LENGTH: Final[int] = 10

# Rate limiting
DEFAULT_RATE_LIMIT_PER_MINUTE: Final[int] = 60
DEFAULT_RATE_LIMIT_PER_HOUR: Final[int] = 1000

# Cache durations (in seconds)
CACHE_DURATION_SHORT: Final[int] = 300  # 5 minutes
CACHE_DURATION_MEDIUM: Final[int] = 1800  # 30 minutes
CACHE_DURATION_LONG: Final[int] = 3600  # 1 hour

# Emoji mappings for consistent UI
EMOJI: Final[Dict[str, str]] = {
    # Status indicators
    'SUCCESS': '✅',
    'ERROR': '❌',
    'WARNING': '⚠️',
    'INFO': 'ℹ️',
    'LOADING': '⏳',
    'DONE': '✅',
    'PENDING': '⏳',
    'FAILED': '❌',
    
    # Navigation
    'BACK': '◀️',
    'FORWARD': '▶️',
    'PREVIOUS': '⬅️',
    'NEXT': '➡️',
    'UP': '⬆️',
    'DOWN': '⬇️',
    'CANCEL': '❌',
    'CONFIRM': '✅',
    'SELECT': '✅',
    'SELECTED': '☑️',
    'UNSELECTED': '☐',
    
    # Objects and entities
    'PROJECT': '📂',
    'ISSUE': '🎫',
    'USER': '👤',
    'ADMIN': '👑',
    'TEAM': '👥',
    'COMMENT': '💬',
    'LABEL': '🏷️',
    'TAG': '🔖',
    'LINK': '🔗',
    'FILE': '📄',
    'FOLDER': '📁',
    'CALENDAR': '📅',
    'CLOCK': '🕐',
    'DATE': '📆',
    
    # Priority levels
    'PRIORITY_LOWEST': '🔵',
    'PRIORITY_LOW': '🟢',
    'PRIORITY_MEDIUM': '🟡',
    'PRIORITY_HIGH': '🟠',
    'PRIORITY_HIGHEST': '🔴',
    
    # Issue types
    'TASK': '📋',
    'BUG': '🐛',
    'STORY': '📖',
    'EPIC': '🚀',
    'IMPROVEMENT': '⚡',
    'SUBTASK': '📝',
    
    # Issue statuses
    'TO_DO': '📝',
    'IN_PROGRESS': '⏳',
    'RESOLVED': '✅',
    'CLOSED': '🔒',
    'REOPENED': '🔄',
    
    # Actions
    'CREATE': '➕',
    'EDIT': '✏️',
    'DELETE': '🗑️',
    'SAVE': '💾',
    'REFRESH': '🔄',
    'SYNC': '🔄',
    'SEARCH': '🔍',
    'FILTER': '🔽',
    'SORT': '🔢',
    'VIEW': '👁️',
    'SETTINGS': '⚙️',
    'PREFERENCES': '🎛️',
    
    # States
    'ACTIVE': '🟢',
    'INACTIVE': '🔴',
    'ENABLED': '✅',
    'DISABLED': '❌',
    'ONLINE': '🟢',
    'OFFLINE': '🔴',
    'DEFAULT': '🎯',
    'FAVORITE': '⭐',
    'BOOKMARK': '🔖',
    
    # Communication
    'MESSAGE': '💌',
    'NOTIFICATION': '🔔',
    'ALERT': '🚨',
    'BELL': '🔔',
    'MAIL': '📧',
    'CHAT': '💬',
    
    # Special actions
    'MAGIC': '✨',
    'WIZARD': '🧙‍♂️',
    'ROBOT': '🤖',
    'GEAR': '⚙️',
    'WRENCH': '🔧',
    'HAMMER': '🔨',
    'TOOL': '🛠️',
    
    # Data and stats
    'CHART': '📊',
    'GRAPH': '📈',
    'STATS': '📊',
    'REPORT': '📋',
    'DATABASE': '💾',
    'BACKUP': '💾',
    
    # Help and information
    'HELP': '❓',
    'QUESTION': '❓',
    'LIGHT_BULB': '💡',
    'TIP': '💡',
    'GUIDE': '📖',
    'MANUAL': '📘',
    'BOOK': '📚',
    
    # Security and permissions
    'LOCK': '🔒',
    'UNLOCK': '🔓',
    'KEY': '🔑',
    'SHIELD': '🛡️',
    'SECURITY': '🔐',
    'PERMISSION': '🔐',
    
    # Time and scheduling
    'TIMER': '⏲️',
    'STOPWATCH': '⏱️',
    'HOURGLASS': '⏳',
    'OVERDUE': '🚨',
    'DEADLINE': '⏰',
    'SCHEDULE': '📅',
    
    # Quality and testing
    'TEST': '🧪',
    'CHECK': '✅',
    'CROSS': '❌',
    'CHECKMARK': '✔️',
    'QUALITY': '💎',
    'STAR': '⭐',
    'AWARD': '🏆',
    
    # Development
    'CODE': '💻',
    'BRANCH': '🌿',
    'MERGE': '🔀',
    'COMMIT': '📝',
    'DEPLOY': '🚀',
    'BUILD': '🏗️',
    'PACKAGE': '📦',
    
    # Misc
    'FIRE': '🔥',
    'LIGHTNING': '⚡',
    'ROCKET': '🚀',
    'TARGET': '🎯',
    'FLAG': '🚩',
    'PIN': '📌',
    'PAPERCLIP': '📎',
    'ATTACHMENT': '📎',
    'DOWNLOAD': '⬇️',
    'UPLOAD': '⬆️',
    'COPY': '📋',
    'PASTE': '📋',
    
    # Numbers (for pagination, etc.)
    'ONE': '1️⃣',
    'TWO': '2️⃣',
    'THREE': '3️⃣',
    'FOUR': '4️⃣',
    'FIVE': '5️⃣',
    'SIX': '6️⃣',
    'SEVEN': '7️⃣',
    'EIGHT': '8️⃣',
    'NINE': '9️⃣',
    'TEN': '🔟',
}

# Command shortcuts mapping
COMMAND_SHORTCUTS: Final[Dict[str, str]] = {
    'p': 'projects',
    'ap': 'addproject',
    'ep': 'editproject',
    'dp': 'deleteproject',
    'sd': 'setdefault',
    'c': 'create',
    'li': 'listissues',
    'mi': 'myissues',
    'si': 'searchissues',
    'ei': 'editissue',
    's': 'status',
    'u': 'users',
    'sync': 'syncjira',
    'w': 'wizard',
    'q': 'quick',
    'h': 'help',
    'cfg': 'config',
    'pref': 'preferences',
}

# Error messages
ERROR_MESSAGES: Final[Dict[str, str]] = {
    'INVALID_PROJECT_KEY': 'Invalid project key format. Use uppercase letters, numbers, and underscores only.',
    'PROJECT_NOT_FOUND': 'Project not found or not accessible.',
    'PROJECT_EXISTS': 'A project with this key already exists.',
    'PROJECT_HAS_ISSUES': 'Cannot delete project that contains issues.',
    'ISSUE_NOT_FOUND': 'Issue not found or not accessible.',
    'INVALID_PRIORITY': 'Invalid priority. Valid options: Lowest, Low, Medium, High, Highest.',
    'INVALID_ISSUE_TYPE': 'Invalid issue type. Valid options: Task, Bug, Story, Epic, Improvement, Sub-task.',
    'INVALID_STATUS': 'Invalid status.',
    'NO_DEFAULT_PROJECT': 'No default project set. Use /setdefault to choose one.',
    'PERMISSION_DENIED': 'You don\'t have permission to perform this action.',
    'USER_NOT_FOUND': 'User not found.',
    'JIRA_CONNECTION_FAILED': 'Failed to connect to Jira. Check your configuration.',
    'JIRA_AUTH_FAILED': 'Jira authentication failed. Check your credentials.',
    'DATABASE_ERROR': 'Database operation failed. Please try again.',
    'VALIDATION_ERROR': 'Input validation failed.',
    'NETWORK_ERROR': 'Network error occurred. Please try again.',
    'TIMEOUT_ERROR': 'Operation timed out. Please try again.',
    'RATE_LIMIT_EXCEEDED': 'Rate limit exceeded. Please wait before trying again.',
    'SESSION_EXPIRED': 'Your session has expired. Please start over.',
    'INVALID_COMMAND': 'Invalid command or arguments.',
    'MISSING_ARGUMENTS': 'Missing required arguments.',
    'WIZARD_ERROR': 'Wizard state error. Please start over.',
    'UNKNOWN_ERROR': 'An unexpected error occurred.',
}

# Success messages
SUCCESS_MESSAGES: Final[Dict[str, str]] = {
    'PROJECT_CREATED': 'Project created successfully!',
    'PROJECT_UPDATED': 'Project updated successfully!',
    'PROJECT_DELETED': 'Project deleted successfully!',
    'ISSUE_CREATED': 'Issue created successfully!',
    'ISSUE_UPDATED': 'Issue updated successfully!',
    'ISSUE_DELETED': 'Issue deleted successfully!',
    'DEFAULT_PROJECT_SET': 'Default project set successfully!',
    'PREFERENCES_UPDATED': 'Preferences updated successfully!',
    'USER_UPDATED': 'User information updated successfully!',
    'SYNC_COMPLETED': 'Synchronization completed successfully!',
    'WIZARD_COMPLETED': 'Setup completed successfully!',
    'OPERATION_COMPLETED': 'Operation completed successfully!',
}

# Info messages
INFO_MESSAGES: Final[Dict[str, str]] = {
    'WELCOME': 'Welcome to the Telegram-Jira Bot!',
    'SETUP_REQUIRED': 'Initial setup required. Use /wizard to get started.',
    'NO_PROJECTS': 'No projects available. Contact an admin to add projects.',
    'NO_ISSUES': 'No issues found.',
    'NO_USERS': 'No users found.',
    'WIZARD_STARTED': 'Setup wizard started. Follow the prompts to configure the bot.',
    'WIZARD_CANCELLED': 'Setup wizard cancelled.',
    'OPERATION_CANCELLED': 'Operation cancelled.',
    'LOADING_DATA': 'Loading data, please wait...',
    'PROCESSING_REQUEST': 'Processing your request...',
    'SYNCING_DATA': 'Synchronizing data with Jira...',
}

# Default values
DEFAULTS: Final[Dict[str, str]] = {
    'PRIORITY': 'Medium',
    'ISSUE_TYPE': 'Task',
    'PAGE_SIZE': '10',
    'DATE_FORMAT': '%Y-%m-%d %H:%M',
    'TIMEZONE': 'UTC',
    'LANGUAGE': 'en',
}

# Validation patterns
PATTERNS: Final[Dict[str, str]] = {
    'PROJECT_KEY': r'^[A-Z][A-Z0-9_]*$',
    'ISSUE_KEY': r'^[A-Z][A-Z0-9_]+-\d+$',
    'EMAIL': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
    'USERNAME': r'^[a-zA-Z0-9_]{3,30}$',
    'JIRA_DOMAIN': r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$',
}

# Jira field mappings (common custom field IDs)
JIRA_CUSTOM_FIELDS: Final[Dict[str, str]] = {
    'STORY_POINTS': 'customfield_10016',
    'EPIC_LINK': 'customfield_10014',
    'EPIC_NAME': 'customfield_10011',
    'SPRINT': 'customfield_10020',
    'TEAM': 'customfield_10100',
    'BUSINESS_VALUE': 'customfield_10200',
}

# Time tracking constants
TIME_UNITS: Final[Dict[str, int]] = {
    'm': 1,        # minutes
    'h': 60,       # hours in minutes
    'd': 480,      # working day in minutes (8 hours)
    'w': 2400,     # working week in minutes (5 days)
}

# Priority weights for sorting
PRIORITY_WEIGHTS: Final[Dict[str, int]] = {
    'Highest': 5,
    'High': 4,
    'Medium': 3,
    'Low': 2,
    'Lowest': 1,
}

# Status categories
STATUS_CATEGORIES: Final[Dict[str, List[str]]] = {
    'TO_DO': ['To Do', 'Open', 'New', 'Created', 'Backlog'],
    'IN_PROGRESS': ['In Progress', 'In Development', 'In Review', 'Testing'],
    'DONE': ['Done', 'Closed', 'Resolved', 'Completed', 'Released'],
}

# Issue type categories
ISSUE_TYPE_CATEGORIES: Final[Dict[str, List[str]]] = {
    'STANDARD': ['Task', 'Story', 'Bug', 'Improvement'],
    'EPIC': ['Epic'],
    'SUBTASK': ['Sub-task', 'Subtask'],
}

# Keyboard layouts for different contexts
KEYBOARD_LAYOUTS: Final[Dict[str, List[List[str]]]] = {
    'MAIN_MENU': [
        ['📂 Projects', '🎫 Create Issue'],
        ['📊 My Issues', '⚙️ Settings'],
        ['❓ Help', '📈 Status']
    ],
    'ADMIN_MENU': [
        ['📂 Projects', '👥 Users'],
        ['🔄 Sync Jira', '📊 Statistics'],
        ['⚙️ Configuration', '❓ Help']
    ],
    'PROJECT_ACTIONS': [
        ['✏️ Edit', '🗑️ Delete'],
        ['📊 Statistics', '🔄 Refresh'],
        ['◀️ Back', '❌ Cancel']
    ],
    'ISSUE_ACTIONS': [
        ['✏️ Edit', '💬 Comments'],
        ['👤 Assign', '🔄 Refresh'],
        ['🔗 View in Jira', '◀️ Back']
    ],
}

# Wizard flow steps
WIZARD_FLOWS: Final[Dict[str, List[str]]] = {
    'PROJECT_SETUP': [
        'welcome',
        'enter_key',
        'enter_name', 
        'enter_description',
        'verify_jira',
        'confirm',
        'complete'
    ],
    'ISSUE_CREATION': [
        'welcome',
        'select_project',
        'select_type',
        'select_priority',
        'enter_summary',
        'enter_description',
        'confirm',
        'create',
        'complete'
    ],
    'PREFERENCES_SETUP': [
        'welcome',
        'select_default_project',
        'select_default_priority',
        'select_default_type',
        'configure_notifications',
        'configure_ui',
        'confirm',
        'complete'
    ],
}

# Rate limiting windows
RATE_LIMIT_WINDOWS: Final[Dict[str, int]] = {
    'MINUTE': 60,
    'HOUR': 3600,
    'DAY': 86400,
}

# Cache keys
CACHE_KEYS: Final[Dict[str, str]] = {
    'PROJECTS': 'projects:all',
    'PROJECT': 'project:{}',
    'USER_PREFERENCES': 'user_preferences:{}',
    'USER_SESSION': 'user_session:{}',
    'JIRA_METADATA': 'jira:metadata',
    'ISSUE_TYPES': 'jira:issue_types',
    'PRIORITIES': 'jira:priorities',
    'STATUSES': 'jira:statuses',
}

# Feature flags (can be overridden by config)
FEATURES: Final[Dict[str, bool]] = {
    'ENABLE_WIZARDS': True,
    'ENABLE_SHORTCUTS': True,
    'ENABLE_AUTO_SYNC': False,
    'ENABLE_NOTIFICATIONS': True,
    'ENABLE_ISSUE_COMMENTS': True,
    'ENABLE_TIME_TRACKING': True,
    'ENABLE_FILE_ATTACHMENTS': False,
    'ENABLE_BULK_OPERATIONS': False,
    'ENABLE_ADVANCED_SEARCH': True,
    'ENABLE_ISSUE_TEMPLATES': False,
    'ENABLE_CUSTOM_FIELDS': False,
    'ENABLE_WEBHOOKS': False,
}

# Logging configuration
LOG_LEVELS: Final[List[str]] = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

# Date and time formats
DATE_FORMATS: Final[Dict[str, str]] = {
    'SHORT': '%Y-%m-%d',
    'MEDIUM': '%Y-%m-%d %H:%M',
    'LONG': '%Y-%m-%d %H:%M:%S',
    'ISO': '%Y-%m-%dT%H:%M:%S',
    'HUMAN': '%B %d, %Y at %I:%M %p',
}

# File size limits
FILE_SIZE_LIMITS: Final[Dict[str, int]] = {
    'AVATAR': 5 * 1024 * 1024,    # 5MB
    'ATTACHMENT': 20 * 1024 * 1024,  # 20MB
    'LOG': 100 * 1024 * 1024,    # 100MB
    'DATABASE': 1024 * 1024 * 1024,  # 1GB
}

# URL patterns for validation
URL_PATTERNS: Final[Dict[str, str]] = {
    'JIRA_ISSUE': r'^https?://[^/]+/browse/[A-Z][A-Z0-9_]+-\d+$',
    'JIRA_PROJECT': r'^https?://[^/]+/projects/[A-Z][A-Z0-9_]+$',
    'JIRA_BOARD': r'^https?://[^/]+/secure/RapidBoard\.jspa\?rapidView=\d+',
}

# Database constraints
DB_CONSTRAINTS: Final[Dict[str, int]] = {
    'MAX_STRING_LENGTH': 255,
    'MAX_TEXT_LENGTH': 65535,
    'MAX_JSON_LENGTH': 16777215,  # MEDIUMTEXT
    'MAX_SESSIONS': 10000,
    'MAX_USERS': 100000,
    'MAX_PROJECTS': 1000,
    'MAX_ISSUES_PER_USER': 10000,
}

# Performance thresholds
PERFORMANCE_THRESHOLDS: Final[Dict[str, float]] = {
    'SLOW_QUERY_TIME': 1.0,      # seconds
    'SLOW_REQUEST_TIME': 2.0,    # seconds
    'MEMORY_WARNING': 0.8,       # 80% of available memory
    'DISK_WARNING': 0.9,         # 90% of available disk
}

# Notification types
NOTIFICATION_TYPES: Final[List[str]] = [
    'ISSUE_CREATED',
    'ISSUE_UPDATED',
    'ISSUE_ASSIGNED',
    'ISSUE_COMMENTED',
    'ISSUE_RESOLVED',
    'PROJECT_CREATED',
    'PROJECT_UPDATED',
    'SYNC_COMPLETED',
    'ERROR_OCCURRED',
]

# Export formats
EXPORT_FORMATS: Final[List[str]] = [
    'CSV',
    'JSON',
    'XLSX',
    'PDF',
]

# Language codes (for future i18n support)
LANGUAGE_CODES: Final[List[str]] = [
    'en',  # English
    'es',  # Spanish
    'fr',  # French
    'de',  # German
    'it',  # Italian
    'pt',  # Portuguese
    'ru',  # Russian
    'zh',  # Chinese
    'ja',  # Japanese
    'ko',  # Korean
]

# Bot metadata
BOT_INFO: Final[Dict[str, str]] = {
    'NAME': 'Telegram-Jira Bot',
    'VERSION': '2.1.0',
    'DESCRIPTION': 'A comprehensive Telegram bot for Jira integration',
    'AUTHOR': 'AI Assistant',
    'LICENSE': 'MIT',
    'REPOSITORY': 'https://github.com/example/telegram-jira-bot',
    'DOCUMENTATION': 'https://docs.example.com/telegram-jira-bot',
}