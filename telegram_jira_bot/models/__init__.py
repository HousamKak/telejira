# =============================================================================
# telegram_jira_bot/models/__init__.py  
# =============================================================================
#!/usr/bin/env python3
"""
Data models for the Telegram-Jira bot.

Contains all data models including User, Project, Issue, and related enums.
"""

try:
    # Import all models
    from .user import User, UserPreferences, UserSession
    from .project import Project, ProjectSummary
    from .issue import JiraIssue, IssueComment
    from .enums import (
        UserRole,
        IssuePriority, 
        IssueType,
        IssueStatus,
        CommandShortcut,
        WizardState,
        ErrorType
    )
    
    __all__ = [
        # User models
        "User",
        "UserPreferences", 
        "UserSession",
        
        # Project models
        "Project",
        "ProjectSummary",
        
        # Issue models
        "JiraIssue",
        "IssueComment",
        
        # Enums
        "UserRole",
        "IssuePriority",
        "IssueType", 
        "IssueStatus",
        "CommandShortcut",
        "WizardState",
        "ErrorType"
    ]
    
except ImportError as e:
    import warnings
    warnings.warn(f"Model imports failed: {e}", ImportWarning)
    __all__ = []