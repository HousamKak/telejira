#!/usr/bin/env python3
"""
Mapping utilities for the Telegram-Jira bot.

Handles conversion between different enum ecosystems and data formats
to maintain compatibility across different parts of the application.
"""

import logging
from typing import Dict, Any, Optional, Union

from models.enums import IssueType, IssuePriority, IssueStatus, UserRole

logger = logging.getLogger(__name__)


class EnumMapper:
    """Handles mapping between different enum representations."""
    
    # Mapping from string values to enum instances
    ISSUE_TYPE_MAP = {
        'task': IssueType.TASK,
        'bug': IssueType.BUG, 
        'story': IssueType.STORY,
        'epic': IssueType.EPIC,
        'sub-task': IssueType.SUBTASK,
        'subtask': IssueType.SUBTASK,
        # Case variations
        'Task': IssueType.TASK,
        'Bug': IssueType.BUG,
        'Story': IssueType.STORY,
        'Epic': IssueType.EPIC,
        'Sub-task': IssueType.SUBTASK,
        'TASK': IssueType.TASK,
        'BUG': IssueType.BUG,
        'STORY': IssueType.STORY,
        'EPIC': IssueType.EPIC,
        'SUBTASK': IssueType.SUBTASK,
    }
    
    PRIORITY_MAP = {
        'highest': IssuePriority.HIGHEST,
        'high': IssuePriority.HIGH,
        'medium': IssuePriority.MEDIUM,
        'low': IssuePriority.LOW,
        'lowest': IssuePriority.LOWEST,
        # Case variations
        'Highest': IssuePriority.HIGHEST,
        'High': IssuePriority.HIGH,
        'Medium': IssuePriority.MEDIUM,
        'Low': IssuePriority.LOW,
        'Lowest': IssuePriority.LOWEST,
        'HIGHEST': IssuePriority.HIGHEST,
        'HIGH': IssuePriority.HIGH,
        'MEDIUM': IssuePriority.MEDIUM,
        'LOW': IssuePriority.LOW,
        'LOWEST': IssuePriority.LOWEST,
        # Alternative names
        'critical': IssuePriority.HIGHEST,
        'Critical': IssuePriority.HIGHEST,
        'CRITICAL': IssuePriority.HIGHEST,
    }
    
    STATUS_MAP = {
        'to do': IssueStatus.TODO,
        'todo': IssueStatus.TODO,
        'in progress': IssueStatus.IN_PROGRESS,
        'inprogress': IssueStatus.IN_PROGRESS,
        'done': IssueStatus.DONE,
        'blocked': IssueStatus.BLOCKED,
        'in review': IssueStatus.REVIEW,
        'review': IssueStatus.REVIEW,
        # Case variations
        'To Do': IssueStatus.TODO,
        'In Progress': IssueStatus.IN_PROGRESS,
        'Done': IssueStatus.DONE,
        'Blocked': IssueStatus.BLOCKED,
        'In Review': IssueStatus.REVIEW,
        'TODO': IssueStatus.TODO,
        'IN_PROGRESS': IssueStatus.IN_PROGRESS,
        'DONE': IssueStatus.DONE,
        'BLOCKED': IssueStatus.BLOCKED,
        'REVIEW': IssueStatus.REVIEW,
    }
    
    ROLE_MAP = {
        'guest': UserRole.GUEST,
        'user': UserRole.USER,
        'admin': UserRole.ADMIN,
        'super_admin': UserRole.SUPER_ADMIN,
        'superadmin': UserRole.SUPER_ADMIN,
        # Case variations
        'Guest': UserRole.GUEST,
        'User': UserRole.USER,
        'Admin': UserRole.ADMIN,
        'Super_Admin': UserRole.SUPER_ADMIN,
        'GUEST': UserRole.GUEST,
        'USER': UserRole.USER,
        'ADMIN': UserRole.ADMIN,
        'SUPER_ADMIN': UserRole.SUPER_ADMIN,
    }

    @classmethod
    def string_to_issue_type(cls, value: str) -> Optional[IssueType]:
        """Convert string to IssueType enum.
        
        Args:
            value: String representation of issue type
            
        Returns:
            IssueType enum or None if not found
        """
        if not isinstance(value, str):
            return None
            
        # Try direct lookup first
        result = cls.ISSUE_TYPE_MAP.get(value)
        if result:
            return result
            
        # Try case-insensitive lookup
        result = cls.ISSUE_TYPE_MAP.get(value.lower())
        if result:
            return result
            
        # Try enum name lookup
        try:
            return IssueType[value.upper()]
        except (KeyError, AttributeError):
            pass
            
        logger.warning(f"Could not map string '{value}' to IssueType")
        return None

    @classmethod
    def string_to_priority(cls, value: str) -> Optional[IssuePriority]:
        """Convert string to IssuePriority enum.
        
        Args:
            value: String representation of priority
            
        Returns:
            IssuePriority enum or None if not found
        """
        if not isinstance(value, str):
            return None
            
        # Try direct lookup first
        result = cls.PRIORITY_MAP.get(value)
        if result:
            return result
            
        # Try case-insensitive lookup
        result = cls.PRIORITY_MAP.get(value.lower())
        if result:
            return result
            
        # Try enum name lookup
        try:
            return IssuePriority[value.upper()]
        except (KeyError, AttributeError):
            pass
            
        logger.warning(f"Could not map string '{value}' to IssuePriority")
        return None

    @classmethod
    def string_to_status(cls, value: str) -> Optional[IssueStatus]:
        """Convert string to IssueStatus enum.
        
        Args:
            value: String representation of status
            
        Returns:
            IssueStatus enum or None if not found
        """
        if not isinstance(value, str):
            return None
            
        # Try direct lookup first
        result = cls.STATUS_MAP.get(value)
        if result:
            return result
            
        # Try case-insensitive lookup
        result = cls.STATUS_MAP.get(value.lower())
        if result:
            return result
            
        # Try enum name lookup
        try:
            return IssueStatus[value.upper().replace(' ', '_')]
        except (KeyError, AttributeError):
            pass
            
        logger.warning(f"Could not map string '{value}' to IssueStatus")
        return None

    @classmethod
    def string_to_role(cls, value: str) -> Optional[UserRole]:
        """Convert string to UserRole enum.
        
        Args:
            value: String representation of role
            
        Returns:
            UserRole enum or None if not found
        """
        if not isinstance(value, str):
            return None
            
        # Try direct lookup first
        result = cls.ROLE_MAP.get(value)
        if result:
            return result
            
        # Try case-insensitive lookup
        result = cls.ROLE_MAP.get(value.lower())
        if result:
            return result
            
        # Try enum name lookup
        try:
            return UserRole[value.upper()]
        except (KeyError, AttributeError):
            pass
            
        logger.warning(f"Could not map string '{value}' to UserRole")
        return None


class JiraDataMapper:
    """Handles mapping between Jira API responses and our models."""
    
    @classmethod
    def map_jira_issue_type(cls, jira_type: Dict[str, Any]) -> Optional[IssueType]:
        """Map Jira issue type object to IssueType enum.
        
        Args:
            jira_type: Jira issue type object with 'name' field
            
        Returns:
            IssueType enum or None if mapping fails
        """
        if not isinstance(jira_type, dict) or 'name' not in jira_type:
            return None
            
        type_name = jira_type['name']
        return EnumMapper.string_to_issue_type(type_name)

    @classmethod
    def map_jira_priority(cls, jira_priority: Dict[str, Any]) -> Optional[IssuePriority]:
        """Map Jira priority object to IssuePriority enum.
        
        Args:
            jira_priority: Jira priority object with 'name' field
            
        Returns:
            IssuePriority enum or None if mapping fails
        """
        if not isinstance(jira_priority, dict) or 'name' not in jira_priority:
            return None
            
        priority_name = jira_priority['name']
        return EnumMapper.string_to_priority(priority_name)

    @classmethod
    def map_jira_status(cls, jira_status: Dict[str, Any]) -> Optional[IssueStatus]:
        """Map Jira status object to IssueStatus enum.
        
        Args:
            jira_status: Jira status object with 'name' field
            
        Returns:
            IssueStatus enum or None if mapping fails
        """
        if not isinstance(jira_status, dict) or 'name' not in jira_status:
            return None
            
        status_name = jira_status['name']
        return EnumMapper.string_to_status(status_name)

    @classmethod
    def enum_to_jira_payload(cls, enum_value: Union[IssueType, IssuePriority, IssueStatus]) -> Dict[str, str]:
        """Convert enum to Jira API payload format.
        
        Args:
            enum_value: Enum instance to convert
            
        Returns:
            Dictionary with 'name' field for Jira API
        """
        return {'name': enum_value.value}


class TelegramDataMapper:
    """Handles mapping between Telegram data and our models."""
    
    @classmethod
    def parse_natural_language_issue(cls, text: str) -> Optional[Dict[str, Any]]:
        """Parse natural language issue creation text.
        
        Expected format: "PRIORITY TYPE description"
        Example: "HIGH BUG Login button not working"
        
        Args:
            text: Text to parse
            
        Returns:
            Dictionary with parsed components or None if parsing fails
        """
        if not isinstance(text, str):
            return None
            
        import re
        
        # Pattern: PRIORITY TYPE description
        pattern = r'^(LOW|MEDIUM|HIGH|CRITICAL|HIGHEST)\s+(BUG|TASK|STORY|EPIC|SUBTASK)\s+(.+)$'
        match = re.match(pattern, text.strip().upper())
        
        if not match:
            return None
            
        priority_str, type_str, description = match.groups()
        
        # Map to enums
        priority = EnumMapper.string_to_priority(priority_str)
        issue_type = EnumMapper.string_to_issue_type(type_str)
        
        if not priority or not issue_type:
            return None
            
        return {
            'priority': priority,
            'issue_type': issue_type,
            'summary': description.strip(),
        }

    @classmethod
    def format_issue_for_telegram(cls, issue: 'JiraIssue') -> str:
        """Format issue for Telegram display.
        
        Args:
            issue: JiraIssue instance
            
        Returns:
            Formatted string for Telegram
        """
        from models import get_priority_emoji, get_issue_type_emoji, get_status_emoji
        
        priority_emoji = get_priority_emoji(issue.priority)
        type_emoji = get_issue_type_emoji(issue.issue_type)
        status_emoji = get_status_emoji(issue.status)
        
        formatted = f"{status_emoji} <b>{issue.key}</b> - {issue.summary}\n"
        formatted += f"{priority_emoji} {issue.priority.value} | {type_emoji} {issue.issue_type.value}"
        
        if issue.assignee_display_name:
            formatted += f" | 👤 {issue.assignee_display_name}"
            
        return formatted


class ContextDataMapper:
    """Handles mapping context data for wizards and conversations."""
    
    @classmethod
    def serialize_wizard_data(cls, data: 'IssueWizardData') -> Dict[str, Any]:
        """Serialize wizard data for storage in context.
        
        Args:
            data: IssueWizardData instance
            
        Returns:
            Serializable dictionary
        """
        return {
            'project_key': data.project_key,
            'issue_type': data.issue_type,
            'priority': data.priority,
            'summary': data.summary,
            'description': data.description,
        }

    @classmethod
    def deserialize_wizard_data(cls, data: Dict[str, Any]) -> 'IssueWizardData':
        """Deserialize wizard data from context storage.
        
        Args:
            data: Dictionary from context storage
            
        Returns:
            IssueWizardData instance
        """
        from handlers.wizard_handlers import IssueWizardData
        
        return IssueWizardData(
            project_key=data.get('project_key'),
            issue_type=data.get('issue_type'),
            priority=data.get('priority'),
            summary=data.get('summary'),
            description=data.get('description', ''),
        )


# Convenience functions
def safe_enum_convert(value: str, enum_class, default=None):
    """Safely convert string to enum with fallback.
    
    Args:
        value: String value to convert
        enum_class: Target enum class
        default: Default value if conversion fails
        
    Returns:
        Enum instance or default value
    """
    if enum_class == IssueType:
        result = EnumMapper.string_to_issue_type(value)
    elif enum_class == IssuePriority:
        result = EnumMapper.string_to_priority(value)
    elif enum_class == IssueStatus:
        result = EnumMapper.string_to_status(value)
    elif enum_class == UserRole:
        result = EnumMapper.string_to_role(value)
    else:
        result = None
        
    return result if result is not None else default


def validate_and_convert_enums(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and convert string enum values in a data dictionary.
    
    Args:
        data: Dictionary containing potential enum values
        
    Returns:
        Dictionary with converted enum instances
    """
    result = data.copy()
    
    # Convert issue type
    if 'issue_type' in result and isinstance(result['issue_type'], str):
        converted = EnumMapper.string_to_issue_type(result['issue_type'])
        if converted:
            result['issue_type'] = converted
            
    # Convert priority
    if 'priority' in result and isinstance(result['priority'], str):
        converted = EnumMapper.string_to_priority(result['priority'])
        if converted:
            result['priority'] = converted
            
    # Convert status
    if 'status' in result and isinstance(result['status'], str):
        converted = EnumMapper.string_to_status(result['status'])
        if converted:
            result['status'] = converted
            
    # Convert role
    if 'role' in result and isinstance(result['role'], str):
        converted = EnumMapper.string_to_role(result['role'])
        if converted:
            result['role'] = converted
            
    return result