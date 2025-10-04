#!/usr/bin/env python3
"""
Validators for the Telegram-Jira bot.

Contains validation functions for user input, data integrity, and business logic.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple, Union
from urllib.parse import urlparse

from models import IssuePriority, IssueType, IssueStatus, UserRole
from .constants import PATTERNS, MAX_PROJECT_KEY_LENGTH, MAX_PROJECT_NAME_LENGTH


class ValidationError(Exception):
    """Custom exception for validation errors."""
    
    def __init__(self, message: str, field: Optional[str] = None, code: Optional[str] = None):
        super().__init__(message)
        self.field = field
        self.code = code


class ValidationResult:
    """Result of a validation operation."""
    
    def __init__(self, is_valid: bool = True, errors: Optional[List[str]] = None, warnings: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
    
    def add_error(self, error: str) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the result."""
        self.warnings.append(warning)
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0


class InputValidator:
    """Validates user input and data integrity."""

    @staticmethod
    def validate_project_key(key: str, allow_empty: bool = False) -> ValidationResult:
        """Validate project key format and constraints.
        
        Args:
            key: Project key to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not key or not key.strip():
            if allow_empty:
                return result
            result.add_error("Project key cannot be empty")
            return result
        
        key = key.strip().upper()
        
        # Length validation
        if len(key) > MAX_PROJECT_KEY_LENGTH:
            result.add_error(f"Project key must be {MAX_PROJECT_KEY_LENGTH} characters or less")
        
        if len(key) < 2:
            result.add_error("Project key must be at least 2 characters long")
        
        # Format validation
        if not re.match(PATTERNS['PROJECT_KEY'], key):
            result.add_error("Project key must start with a letter and contain only uppercase letters, numbers, and underscores")
        
        # Reserved words check
        reserved_words = ['NULL', 'NONE', 'ADMIN', 'ROOT', 'SYSTEM', 'TEST', 'TEMP']
        if key in reserved_words:
            result.add_error(f"'{key}' is a reserved word and cannot be used as a project key")
        
        # Warnings for potentially problematic keys
        if key.startswith('_') or key.endswith('_'):
            result.add_warning("Project keys starting or ending with underscores may cause issues")
        
        if len(key) < 3:
            result.add_warning("Very short project keys may be confusing")
        
        return result

    @staticmethod
    def validate_project_name(name: str, allow_empty: bool = False) -> ValidationResult:
        """Validate project name.
        
        Args:
            name: Project name to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not name or not name.strip():
            if allow_empty:
                return result
            result.add_error("Project name cannot be empty")
            return result
        
        name = name.strip()
        
        # Length validation
        if len(name) > MAX_PROJECT_NAME_LENGTH:
            result.add_error(f"Project name must be {MAX_PROJECT_NAME_LENGTH} characters or less")
        
        if len(name) < 3:
            result.add_error("Project name must be at least 3 characters long")
        
        # Content validation
        if name.isdigit():
            result.add_error("Project name cannot be only numbers")
        
        # Check for potentially problematic characters
        problematic_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\t']
        for char in problematic_chars:
            if char in name:
                result.add_error(f"Project name contains invalid character: '{char}'")
        
        # Warnings
        if name.lower() in ['test', 'demo', 'sample', 'example']:
            result.add_warning("Consider using a more specific project name")
        
        if len(name) > 50:
            result.add_warning("Long project names may be truncated in some displays")
        
        return result

    @staticmethod
    def validate_project_description(description: str, max_length: int = 1000) -> ValidationResult:
        """Validate project description.
        
        Args:
            description: Description to validate
            max_length: Maximum allowed length
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if description is None:
            description = ""
        
        description = description.strip()
        
        # Length validation
        if len(description) > max_length:
            result.add_error(f"Description must be {max_length} characters or less")
        
        # Content validation - check for potentially problematic content
        script_tags = re.findall(r'<script.*?</script>', description, re.IGNORECASE | re.DOTALL)
        if script_tags:
            result.add_error("Description cannot contain script tags")
        
        # Warnings
        if len(description) > 500:
            result.add_warning("Long descriptions may be truncated in some displays")
        
        return result

    @staticmethod
    def validate_issue_summary(summary: str, max_length: int = 200) -> ValidationResult:
        """Validate issue summary.
        
        Args:
            summary: Issue summary to validate
            max_length: Maximum allowed length
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not summary or not summary.strip():
            result.add_error("Issue summary cannot be empty")
            return result
        
        summary = summary.strip()
        
        # Length validation
        if len(summary) > max_length:
            result.add_error(f"Summary must be {max_length} characters or less")
        
        if len(summary) < 5:
            result.add_error("Summary must be at least 5 characters long")
        
        # Content validation
        if summary.lower() in ['test', 'testing', 'todo', 'fix this']:
            result.add_warning("Consider using a more descriptive summary")
        
        if summary.isupper():
            result.add_warning("Consider using proper capitalization instead of ALL CAPS")
        
        if re.search(r'^(bug|task|story|epic|improvement):', summary, re.IGNORECASE):
            result.add_warning("Issue type is already specified separately, no need to include it in the summary")
        
        return result

    @staticmethod
    def validate_summary(summary: str, max_length: int = 200) -> ValidationResult:
        """Alias for validate_issue_summary for convenience."""
        return InputValidator.validate_issue_summary(summary, max_length)

    @staticmethod
    def validate_issue_description(description: str, max_length: int = 5000) -> ValidationResult:
        """Validate issue description.
        
        Args:
            description: Description to validate
            max_length: Maximum allowed length
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if description is None:
            description = ""
        
        description = description.strip()
        
        # Length validation
        if len(description) > max_length:
            result.add_error(f"Description must be {max_length} characters or less")
        
        # Content validation
        script_tags = re.findall(r'<script.*?</script>', description, re.IGNORECASE | re.DOTALL)
        if script_tags:
            result.add_error("Description cannot contain script tags")
        
        # Warnings for quality
        if len(description) < 10 and description:
            result.add_warning("Consider providing a more detailed description")
        
        return result

    @staticmethod
    def validate_description(description: str, max_length: int = 5000) -> ValidationResult:
        """Alias for validate_issue_description for convenience."""
        return InputValidator.validate_issue_description(description, max_length)

    @staticmethod
    def validate_priority(priority: Union[str, IssuePriority], allow_empty: bool = False) -> ValidationResult:
        """Validate issue priority.
        
        Args:
            priority: Priority to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if priority is None or priority == "":
            if allow_empty:
                return result
            result.add_error("Priority cannot be empty")
            return result
        
        if isinstance(priority, IssuePriority):
            return result  # Already valid
        
        if isinstance(priority, str):
            try:
                IssuePriority.from_string(priority)
                return result  # Valid priority string
            except ValueError:
                valid_priorities = [p.value for p in IssuePriority]
                result.add_error(f"Invalid priority '{priority}'. Valid options: {', '.join(valid_priorities)}")
        else:
            result.add_error("Priority must be a string or IssuePriority enum")
        
        return result

    @staticmethod
    def validate_issue_type(issue_type: Union[str, IssueType], allow_empty: bool = False) -> ValidationResult:
        """Validate issue type.
        
        Args:
            issue_type: Issue type to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if issue_type is None or issue_type == "":
            if allow_empty:
                return result
            result.add_error("Issue type cannot be empty")
            return result
        
        if isinstance(issue_type, IssueType):
            return result  # Already valid
        
        if isinstance(issue_type, str):
            try:
                IssueType.from_string(issue_type)
                return result  # Valid issue type string
            except ValueError:
                valid_types = [t.value for t in IssueType]
                result.add_error(f"Invalid issue type '{issue_type}'. Valid options: {', '.join(valid_types)}")
        else:
            result.add_error("Issue type must be a string or IssueType enum")
        
        return result

    @staticmethod
    def validate_issue_status(status: Union[str, IssueStatus], allow_empty: bool = True) -> ValidationResult:
        """Validate issue status.
        
        Args:
            status: Status to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if status is None or status == "":
            if allow_empty:
                return result
            result.add_error("Status cannot be empty")
            return result
        
        if isinstance(status, IssueStatus):
            return result  # Already valid
        
        if isinstance(status, str):
            try:
                IssueStatus.from_string(status)
                return result  # Valid status string
            except ValueError:
                valid_statuses = [s.value for s in IssueStatus]
                result.add_error(f"Invalid status '{status}'. Valid options: {', '.join(valid_statuses)}")
        else:
            result.add_error("Status must be a string or IssueStatus enum")
        
        return result

    @staticmethod
    def validate_user_id(user_id: Union[int, str]) -> ValidationResult:
        """Validate Telegram user ID.
        
        Args:
            user_id: User ID to validate
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if user_id is None:
            result.add_error("User ID cannot be empty")
            return result
        
        # Convert to int if string
        if isinstance(user_id, str):
            if not user_id.isdigit():
                result.add_error("User ID must be a number")
                return result
            user_id = int(user_id)
        
        if not isinstance(user_id, int):
            result.add_error("User ID must be an integer")
            return result
        
        if user_id <= 0:
            result.add_error("User ID must be positive")
        
        # Telegram user IDs are typically in specific ranges
        if user_id > 2147483647:  # 32-bit signed integer max
            result.add_error("Invalid Telegram user ID format")
        
        return result

    @staticmethod
    def validate_email(email: str, allow_empty: bool = False) -> ValidationResult:
        """Validate email address.
        
        Args:
            email: Email to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not email or not email.strip():
            if allow_empty:
                return result
            result.add_error("Email cannot be empty")
            return result
        
        email = email.strip().lower()
        
        # Basic format validation
        if not re.match(PATTERNS['EMAIL'], email):
            result.add_error("Invalid email format")
            return result
        
        # Length validation
        if len(email) > 254:  # RFC 5321 limit
            result.add_error("Email address is too long")
        
        # Domain validation
        domain = email.split('@')[1]
        if len(domain) > 253:
            result.add_error("Email domain is too long")
        
        # Basic domain checks
        if domain.startswith('.') or domain.endswith('.') or '..' in domain:
            result.add_error("Invalid email domain format")
        
        return result

    @staticmethod
    def validate_jira_domain(domain: str) -> ValidationResult:
        """Validate Jira domain.
        
        Args:
            domain: Domain to validate
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not domain or not domain.strip():
            result.add_error("Jira domain cannot be empty")
            return result
        
        domain = domain.strip().lower()
        
        # Remove protocol if present
        if domain.startswith(('http://', 'https://')):
            domain = domain.split('://', 1)[1]
        
        # Remove trailing slash
        domain = domain.rstrip('/')
        
        # Basic format validation
        if not re.match(PATTERNS['JIRA_DOMAIN'], domain):
            result.add_error("Invalid domain format")
            return result
        
        # Length validation
        if len(domain) > 253:
            result.add_error("Domain name is too long")
        
        # Check for common issues
        if domain.count('.') == 0:
            result.add_warning("Domain should typically include a top-level domain (e.g., .com)")
        
        if domain.endswith('.local'):
            result.add_warning("Local domains may not be accessible from all locations")
        
        return result

    @staticmethod
    def validate_jira_api_token(token: str) -> ValidationResult:
        """Validate Jira API token format.
        
        Args:
            token: API token to validate
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not token or not token.strip():
            result.add_error("API token cannot be empty")
            return result
        
        token = token.strip()
        
        # Length validation - Jira API tokens are typically 24 characters
        if len(token) < 10:
            result.add_error("API token appears to be too short")
        
        if len(token) > 100:
            result.add_error("API token appears to be too long")
        
        # Format validation - should be alphanumeric
        if not re.match(r'^[A-Za-z0-9]+$', token):
            result.add_warning("API token contains unexpected characters")
        
        return result

    @staticmethod
    def validate_telegram_token(token: str) -> ValidationResult:
        """Validate Telegram bot token format.
        
        Args:
            token: Bot token to validate
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not token or not token.strip():
            result.add_error("Telegram token cannot be empty")
            return result
        
        token = token.strip()
        
        # Telegram bot token format: <bot_id>:<auth_token>
        # bot_id is digits, auth_token is 35 characters
        pattern = r'^\d+:[A-Za-z0-9_-]{35}$'
        
        if not re.match(pattern, token):
            result.add_error("Invalid Telegram bot token format")
            return result
        
        return result

    @staticmethod
    def validate_labels(labels: List[str], max_labels: int = 10, max_label_length: int = 50) -> ValidationResult:
        """Validate issue labels.
        
        Args:
            labels: List of labels to validate
            max_labels: Maximum number of labels allowed
            max_label_length: Maximum length per label
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not isinstance(labels, list):
            result.add_error("Labels must be a list")
            return result
        
        if len(labels) > max_labels:
            result.add_error(f"Maximum {max_labels} labels allowed")
        
        seen_labels = set()
        for i, label in enumerate(labels):
            if not isinstance(label, str):
                result.add_error(f"Label {i+1} must be a string")
                continue
            
            label = label.strip()
            
            if not label:
                result.add_error(f"Label {i+1} cannot be empty")
                continue
            
            if len(label) > max_label_length:
                result.add_error(f"Label {i+1} is too long (max {max_label_length} characters)")
            
            if label.lower() in seen_labels:
                result.add_error(f"Duplicate label: '{label}'")
            else:
                seen_labels.add(label.lower())
            
            # Check for problematic characters
            if re.search(r'[<>"\'\&\n\r\t]', label):
                result.add_error(f"Label '{label}' contains invalid characters")
        
        return result

    @staticmethod
    def validate_story_points(points: Union[int, float, str, None], allow_empty: bool = True) -> ValidationResult:
        """Validate story points value.
        
        Args:
            points: Story points to validate
            allow_empty: Whether to allow empty values
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if points is None or points == "":
            if allow_empty:
                return result
            result.add_error("Story points cannot be empty")
            return result
        
        # Convert to number if string
        if isinstance(points, str):
            try:
                points = float(points)
            except ValueError:
                result.add_error("Story points must be a number")
                return result
        
        if not isinstance(points, (int, float)):
            result.add_error("Story points must be a number")
            return result
        
        if points < 0:
            result.add_error("Story points cannot be negative")
        
        if points > 1000:
            result.add_error("Story points value is too large")
        
        # Warnings for unusual values
        if points == 0:
            result.add_warning("Zero story points may indicate the issue needs estimation")
        
        if points > 100:
            result.add_warning("Very high story points may indicate the issue should be broken down")
        
        return result

    @staticmethod
    def validate_due_date(due_date: Union[datetime, str, None], allow_past: bool = False) -> ValidationResult:
        """Validate due date.
        
        Args:
            due_date: Due date to validate
            allow_past: Whether to allow past dates
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if due_date is None:
            return result  # Empty is allowed for due dates
        
        # Convert string to datetime if needed
        if isinstance(due_date, str):
            try:
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S']:
                    try:
                        if isinstance(due_date, str):
                            due_date = datetime.strptime(due_date, fmt)
                        if due_date.tzinfo is None:
                            due_date = due_date.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                else:
                    result.add_error("Invalid date format. Use YYYY-MM-DD")
                    return result
            except Exception:
                result.add_error("Invalid date format")
                return result
        
        if not isinstance(due_date, datetime):
            result.add_error("Due date must be a valid date")
            return result
        
        # Ensure timezone awareness
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        
        # Check if date is in the past
        if not allow_past and due_date < now:
            result.add_error("Due date cannot be in the past")
        
        # Check if date is too far in the future
        max_future = now.replace(year=now.year + 10)  # 10 years
        if due_date > max_future:
            result.add_error("Due date is too far in the future")
        
        # Warnings
        if due_date < now + timedelta(hours=1):
            result.add_warning("Due date is very soon")
        
        if due_date > now + timedelta(days=365):
            result.add_warning("Due date is more than a year away")
        
        return result

    @staticmethod
    def validate_search_query(query: str, min_length: int = 3, max_length: int = 200) -> ValidationResult:
        """Validate search query.
        
        Args:
            query: Search query to validate
            min_length: Minimum query length
            max_length: Maximum query length
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not query or not query.strip():
            result.add_error("Search query cannot be empty")
            return result
        
        query = query.strip()
        
        if len(query) < min_length:
            result.add_error(f"Search query must be at least {min_length} characters")
        
        if len(query) > max_length:
            result.add_error(f"Search query must be {max_length} characters or less")
        
        # Check for potentially problematic queries
        if query.count('%') > 10:
            result.add_warning("Query contains many wildcards, results may be slow")
        
        if re.search(r'[<>"\'\&\n\r\t]', query):
            result.add_warning("Query contains special characters that may affect results")
        
        return result

    @staticmethod
    def validate_command_args(args: List[str], expected_count: Union[int, Tuple[int, int]]) -> ValidationResult:
        """Validate command arguments count.
        
        Args:
            args: List of command arguments
            expected_count: Expected number of arguments (int) or range (tuple)
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not isinstance(args, list):
            result.add_error("Arguments must be a list")
            return result
        
        actual_count = len(args)
        
        if isinstance(expected_count, int):
            if actual_count != expected_count:
                result.add_error(f"Expected {expected_count} arguments, got {actual_count}")
        elif isinstance(expected_count, tuple) and len(expected_count) == 2:
            min_count, max_count = expected_count
            if actual_count < min_count:
                result.add_error(f"Expected at least {min_count} arguments, got {actual_count}")
            elif actual_count > max_count:
                result.add_error(f"Expected at most {max_count} arguments, got {actual_count}")
        else:
            result.add_error("Invalid expected_count parameter")
        
        return result

    @staticmethod
    def validate_callback_data(data: str, max_length: int = 64) -> ValidationResult:
        """Validate Telegram callback data.
        
        Args:
            data: Callback data to validate
            max_length: Maximum allowed length
            
        Returns:
            ValidationResult with validation status and messages
        """
        result = ValidationResult()
        
        if not data:
            result.add_error("Callback data cannot be empty")
            return result
        
        if len(data) > max_length:
            result.add_error(f"Callback data must be {max_length} characters or less")
        
        # Check for problematic characters
        if '\n' in data or '\r' in data:
            result.add_error("Callback data cannot contain newlines")
        
        return result

    @staticmethod
    def sanitize_input(text: str, max_length: Optional[int] = None, strip_html: bool = True) -> str:
        """Sanitize user input by removing/escaping problematic content.
        
        Args:
            text: Text to sanitize
            max_length: Maximum length to truncate to
            strip_html: Whether to remove HTML tags
            
        Returns:
            Sanitized text
        """
        if not isinstance(text, str):
            return ""
        
        # Basic cleanup
        text = text.strip()
        
        # Remove HTML tags if requested
        if strip_html:
            text = re.sub(r'<[^>]+>', '', text)
        
        # Remove control characters
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Truncate if necessary
        if max_length and len(text) > max_length:
            text = text[:max_length].rstrip()
        
        return text

    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Check if URL is safe (basic validation).
        
        Args:
            url: URL to check
            
        Returns:
            True if URL appears safe, False otherwise
        """
        if not url:
            return False
        
        try:
            parsed = urlparse(url)
            
            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Only allow HTTP/HTTPS
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Block localhost and private IPs (basic check)
            if 'localhost' in parsed.netloc.lower():
                return False
            
            if parsed.netloc.startswith('127.') or parsed.netloc.startswith('192.168.'):
                return False
            
            return True
            
        except Exception:
            return False