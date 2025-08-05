#!/usr/bin/env python3
"""
Jira service for the Telegram-Jira bot.

Handles all interactions with the Jira REST API and converts responses to our models.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from urllib.parse import quote

import aiohttp
from aiohttp import ClientTimeout, ClientError

from ..models.project import Project, ProjectStats
from ..models.issue import JiraIssue, IssueComment, IssueSearchResult
from ..models.enums import IssuePriority, IssueType, IssueStatus


class JiraAPIError(Exception):
    """Custom exception for Jira API operations."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class JiraService:
    """Service for Jira API operations with proper model integration."""

    def __init__(
        self, 
        domain: str, 
        email: str, 
        api_token: str,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        page_size: int = 50
    ) -> None:
        """Initialize Jira service.
        
        Args:
            domain: Jira domain (without protocol)
            email: Jira user email
            api_token: Jira API token
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            page_size: Default page size for paginated requests
            
        Raises:
            ValueError: If arguments are invalid
            TypeError: If arguments have wrong types
        """
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("domain must be a non-empty string")
        if not isinstance(email, str) or not email.strip():
            raise ValueError("email must be a non-empty string")
        if not isinstance(api_token, str) or not api_token.strip():
            raise ValueError("api_token must be a non-empty string")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if not isinstance(retry_delay, (int, float)) or retry_delay < 0:
            raise ValueError("retry_delay must be a non-negative number")
        if not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("page_size must be a positive integer")

        # Clean domain (remove protocol if present)
        if domain.startswith(('http://', 'https://')):
            domain = domain.split('://', 1)[1]
        
        self.domain = domain
        self.base_url = f"https://{domain}"
        self.api_url = f"{self.base_url}/rest/api/3"
        self.auth = aiohttp.BasicAuth(email, api_token)
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.page_size = page_size
        self._session = None
        
        self.logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def _get_session(self):
        """Get aiohttp session with proper configuration."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                auth=self.auth,
                timeout=timeout,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            )
        yield self._session

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make HTTP request to Jira API with retry logic."""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self._get_session() as session:
                if method.upper() == 'GET':
                    response = await session.get(url, params=params)
                elif method.upper() == 'POST':
                    response = await session.post(url, json=data, params=params)
                elif method.upper() == 'PUT':
                    response = await session.put(url, json=data, params=params)
                elif method.upper() == 'DELETE':
                    response = await session.delete(url, params=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                if response.status == 200 or response.status == 201:
                    try:
                        return await response.json()
                    except Exception:
                        # Some endpoints return empty responses
                        return {}
                elif response.status == 204:
                    return {}
                else:
                    error_data = {}
                    try:
                        error_data = await response.json()
                    except Exception:
                        pass
                    
                    raise JiraAPIError(
                        f"Jira API error: {response.status} - {error_data.get('message', 'Unknown error')}",
                        status_code=response.status,
                        response_data=error_data
                    )

        except (ClientError, asyncio.TimeoutError) as e:
            if retry_count < self.max_retries:
                self.logger.warning(f"Request failed, retrying in {self.retry_delay}s: {e}")
                await asyncio.sleep(self.retry_delay)
                return await self._make_request(method, endpoint, params, data, retry_count + 1)
            else:
                raise JiraAPIError(f"Request failed after {self.max_retries} retries: {e}")

    # =============================================================================
    # USER OPERATIONS
    # =============================================================================

    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user information."""
        return await self._make_request('GET', 'myself')

    async def test_connection(self) -> bool:
        """Test Jira API connection and permissions."""
        try:
            await self.get_current_user()
            return True
        except JiraAPIError:
            return False

    # =============================================================================
    # PROJECT OPERATIONS - FIXED WITH MODEL INTEGRATION
    # =============================================================================

    async def get_projects(self, max_results: int = 50) -> List[Project]:
        """Get all accessible projects as Project models.
        
        Args:
            max_results: Maximum number of projects to return
            
        Returns:
            List of Project model instances
            
        Raises:
            JiraAPIError: If API request fails
        """
        params = {
            'maxResults': max_results,
            'expand': 'description,lead,url,projectKeys,permissions,insight',
            'status': 'live'
        }
        
        response = await self._make_request('GET', 'project/search', params=params)
        projects = []
        
        for project_data in response.get('values', []):
            try:
                project = self._convert_jira_project_to_model(project_data)
                projects.append(project)
            except (ValueError, TypeError, KeyError) as e:
                self.logger.warning(f"Skipping invalid project {project_data.get('key', 'unknown')}: {e}")
                continue
        
        return projects

    async def get_project(self, project_key: str) -> Optional[Project]:
        """Get a specific project by key as Project model.
        
        Args:
            project_key: Project key (e.g., 'TEST')
            
        Returns:
            Project model instance or None if not found
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")

        try:
            params = {
                'expand': 'description,lead,url,projectKeys,permissions,insight'
            }
            response = await self._make_request('GET', f'project/{project_key}', params=params)
            return self._convert_jira_project_to_model(response)
        except JiraAPIError as e:
            if e.status_code == 404:
                return None
            raise

    def _convert_jira_project_to_model(self, jira_data: Dict[str, Any]) -> Project:
        """Convert Jira API project response to Project model.
        
        Args:
            jira_data: Raw Jira API response data
            
        Returns:
            Project model instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            return Project(
                key=jira_data['key'],
                name=jira_data['name'],
                description=jira_data.get('description', ''),
                jira_id=jira_data['id'],
                created_at=datetime.now(timezone.utc),  # Jira doesn't always provide this
                updated_at=None,
                is_active=True,  # Only active projects are returned by API
                project_type=jira_data.get('projectTypeKey', 'software'),
                lead=jira_data.get('lead', {}).get('displayName'),
                url=jira_data.get('self'),
                avatar_url=jira_data.get('avatarUrls', {}).get('48x48'),
                category=jira_data.get('projectCategory', {}).get('name'),
                issue_count=0,  # We'd need a separate call to get this
                default_priority=IssuePriority.MEDIUM,  # Default value
                default_issue_type=IssueType.TASK  # Default value
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in Jira project data: {e}")

    # =============================================================================
    # ISSUE OPERATIONS - FIXED WITH MODEL INTEGRATION
    # =============================================================================

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str = "",
        issue_type: Union[IssueType, str] = IssueType.TASK,
        priority: Union[IssuePriority, str] = IssuePriority.MEDIUM,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None
    ) -> JiraIssue:
        """Create a new issue and return JiraIssue model.
        
        Args:
            project_key: Project key
            summary: Issue summary
            description: Issue description
            issue_type: Issue type (enum or string)
            priority: Issue priority (enum or string)
            assignee: Assignee account ID or display name
            labels: List of labels
            components: List of component names
            
        Returns:
            JiraIssue model instance
            
        Raises:
            JiraAPIError: If issue creation fails
        """
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary must be a non-empty string")

        # Convert enums to strings
        issue_type_str = issue_type.value if isinstance(issue_type, IssueType) else str(issue_type)
        priority_str = priority.value if isinstance(priority, IssuePriority) else str(priority)

        # Build issue data
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                } if description else None,
                "issuetype": {"name": issue_type_str},
                "priority": {"name": priority_str}
            }
        }

        # Add optional fields
        if assignee:
            issue_data["fields"]["assignee"] = {"accountId": assignee}
        if labels:
            issue_data["fields"]["labels"] = [{"name": label} for label in labels]
        if components:
            issue_data["fields"]["components"] = [{"name": comp} for comp in components]

        response = await self._make_request('POST', 'issue', data=issue_data)
        
        # Get the full issue data
        issue_key = response.get('key')
        if not issue_key:
            raise JiraAPIError("Issue created but key not returned")
        
        return await self.get_issue(issue_key)

    async def get_issue(self, issue_key: str, expand: Optional[List[str]] = None) -> Optional[JiraIssue]:
        """Get an issue by key as JiraIssue model.
        
        Args:
            issue_key: Issue key (e.g., 'TEST-123')
            expand: Fields to expand
            
        Returns:
            JiraIssue model instance or None if not found
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        try:
            params = {}
            if expand:
                params['expand'] = ','.join(expand)
                
            response = await self._make_request('GET', f'issue/{issue_key}', params=params)
            return self._convert_jira_issue_to_model(response)
        except JiraAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        expand: Optional[List[str]] = None
    ) -> IssueSearchResult:
        """Search issues using JQL and return IssueSearchResult model.
        
        Args:
            jql: JQL query string
            max_results: Maximum results to return
            start_at: Starting index for pagination
            expand: Fields to expand
            
        Returns:
            IssueSearchResult model instance
            
        Raises:
            JiraAPIError: If search fails
        """
        if not isinstance(jql, str) or not jql.strip():
            raise ValueError("jql must be a non-empty string")

        params = {
            'jql': jql,
            'maxResults': max_results,
            'startAt': start_at
        }
        
        if expand:
            params['expand'] = ','.join(expand)

        response = await self._make_request('GET', 'search', params=params)
        
        # Convert issues to models
        issues = []
        for issue_data in response.get('issues', []):
            try:
                issue = self._convert_jira_issue_to_model(issue_data)
                issues.append(issue)
            except (ValueError, TypeError, KeyError) as e:
                self.logger.warning(f"Skipping invalid issue {issue_data.get('key', 'unknown')}: {e}")
                continue

        return IssueSearchResult(
            issues=issues,
            total=response.get('total', 0),
            start_at=response.get('startAt', 0),
            max_results=response.get('maxResults', max_results),
            jql_query=jql
        )

    async def update_issue(
        self,
        issue_key: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        issue_type: Optional[Union[IssueType, str]] = None,
        priority: Optional[Union[IssuePriority, str]] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> bool:
        """Update an issue.
        
        Args:
            issue_key: Issue key to update
            summary: New summary
            description: New description
            issue_type: New issue type
            priority: New priority
            assignee: New assignee
            labels: New labels
            
        Returns:
            True if successful
            
        Raises:
            JiraAPIError: If update fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        fields = {}
        
        if summary is not None:
            fields["summary"] = summary
        if description is not None:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            }
        if issue_type is not None:
            type_str = issue_type.value if isinstance(issue_type, IssueType) else str(issue_type)
            fields["issuetype"] = {"name": type_str}
        if priority is not None:
            priority_str = priority.value if isinstance(priority, IssuePriority) else str(priority)
            fields["priority"] = {"name": priority_str}
        if assignee is not None:
            fields["assignee"] = {"accountId": assignee} if assignee else None
        if labels is not None:
            fields["labels"] = [{"name": label} for label in labels]

        if not fields:
            return True  # Nothing to update

        update_data = {"fields": fields}
        await self._make_request('PUT', f'issue/{issue_key}', data=update_data)
        return True

    async def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: Optional[str] = None
    ) -> bool:
        """Transition an issue to a new status.
        
        Args:
            issue_key: Issue key
            transition_id: Transition ID
            comment: Optional comment
            
        Returns:
            True if successful
            
        Raises:
            JiraAPIError: If transition fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        if not isinstance(transition_id, str) or not transition_id.strip():
            raise ValueError("transition_id must be a non-empty string")

        transition_data = {
            "transition": {"id": transition_id}
        }
        
        if comment:
            transition_data["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": comment
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                ]
            }

        await self._make_request('POST', f'issue/{issue_key}/transitions', data=transition_data)
        return True

    async def delete_issue(self, issue_key: str) -> bool:
        """Delete an issue.
        
        Args:
            issue_key: Issue key to delete
            
        Returns:
            True if successful
            
        Raises:
            JiraAPIError: If deletion fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        await self._make_request('DELETE', f'issue/{issue_key}')
        return True

    def _convert_jira_issue_to_model(self, jira_data: Dict[str, Any]) -> JiraIssue:
        """Convert Jira API issue response to JiraIssue model.
        
        Args:
            jira_data: Raw Jira API response data
            
        Returns:
            JiraIssue model instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            fields = jira_data['fields']
            
            # Extract dates
            created_at = self._parse_jira_datetime(fields.get('created'))
            updated_at = self._parse_jira_datetime(fields.get('updated'))
            due_date = self._parse_jira_datetime(fields.get('duedate')) if fields.get('duedate') else None
            resolved_at = self._parse_jira_datetime(fields.get('resolutiondate')) if fields.get('resolutiondate') else None
            
            # Extract description
            description = ""
            if fields.get('description'):
                description = self._extract_description_text(fields['description'])
            
            return JiraIssue(
                key=jira_data['key'],
                jira_id=jira_data['id'],
                project_key=fields['project']['key'],
                summary=fields['summary'],
                description=description,
                issue_type=IssueType.from_string(fields['issuetype']['name']),
                status=self._map_jira_status_to_enum(fields['status']['name']),
                priority=IssuePriority.from_string(fields['priority']['name']),
                assignee=fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None,
                reporter=fields.get('reporter', {}).get('displayName') if fields.get('reporter') else None,
                created_at=created_at,
                updated_at=updated_at,
                due_date=due_date,
                resolved_at=resolved_at,
                labels=self._extract_labels(fields.get('labels', [])),
                components=self._extract_components(fields.get('components', []))
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in Jira issue data: {e}")

    # =============================================================================
    # COMMENT OPERATIONS
    # =============================================================================

    async def add_comment(self, issue_key: str, comment_text: str) -> IssueComment:
        """Add a comment to an issue.
        
        Args:
            issue_key: Issue key
            comment_text: Comment text
            
        Returns:
            IssueComment model instance
            
        Raises:
            JiraAPIError: If comment creation fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        if not isinstance(comment_text, str) or not comment_text.strip():
            raise ValueError("comment_text must be a non-empty string")

        comment_data = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment_text
                            }
                        ]
                    }
                ]
            }
        }

        response = await self._make_request('POST', f'issue/{issue_key}/comment', data=comment_data)
        return self._convert_jira_comment_to_model(response, issue_key)

    async def get_comments(self, issue_key: str) -> List[IssueComment]:
        """Get all comments for an issue.
        
        Args:
            issue_key: Issue key
            
        Returns:
            List of IssueComment model instances
            
        Raises:
            JiraAPIError: If getting comments fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        response = await self._make_request('GET', f'issue/{issue_key}/comment')
        comments = []
        
        for comment_data in response.get('comments', []):
            try:
                comment = self._convert_jira_comment_to_model(comment_data, issue_key)
                comments.append(comment)
            except (ValueError, TypeError, KeyError) as e:
                self.logger.warning(f"Skipping invalid comment {comment_data.get('id', 'unknown')}: {e}")
                continue
        
        return comments

    def _convert_jira_comment_to_model(self, jira_data: Dict[str, Any], issue_key: str) -> IssueComment:
        """Convert Jira API comment response to IssueComment model.
        
        Args:
            jira_data: Raw Jira API comment data
            issue_key: Issue key the comment belongs to
            
        Returns:
            IssueComment model instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            # Extract comment text
            body = ""
            if jira_data.get('body'):
                body = self._extract_description_text(jira_data['body'])
            
            return IssueComment(
                jira_comment_id=jira_data['id'],
                jira_key=issue_key,
                author=jira_data['author']['displayName'],
                body=body,
                created_at=self._parse_jira_datetime(jira_data['created']),
                updated_at=self._parse_jira_datetime(jira_data['updated'])
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in Jira comment data: {e}")

    # =============================================================================
    # UTILITY METHODS - FIXED FOR MODEL CONVERSION
    # =============================================================================

    def _parse_jira_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse Jira datetime string to datetime object.
        
        Args:
            date_str: Jira datetime string
            
        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None
        
        try:
            # Jira typically returns ISO format with timezone
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            elif '+' in date_str[-6:] or '-' in date_str[-6:]:
                # Already has timezone
                pass
            else:
                # Add UTC timezone
                date_str += '+00:00'
            
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Failed to parse Jira datetime '{date_str}': {e}")
            return datetime.now(timezone.utc)

    def _extract_description_text(self, adf_content: Dict[str, Any]) -> str:
        """Extract plain text from Atlassian Document Format (ADF).
        
        Args:
            adf_content: ADF document structure
            
        Returns:
            Plain text string
        """
        if not isinstance(adf_content, dict):
            return str(adf_content)
        
        def extract_text(node: Dict[str, Any]) -> str:
            if node.get('type') == 'text':
                return node.get('text', '')
            elif node.get('content'):
                return ' '.join(extract_text(child) for child in node['content'])
            return ''
        
        return extract_text(adf_content).strip()

    def _map_jira_status_to_enum(self, status_name: str) -> IssueStatus:
        """Map Jira status name to IssueStatus enum.
        
        Args:
            status_name: Jira status name
            
        Returns:
            IssueStatus enum value
        """
        status_mapping = {
            'to do': IssueStatus.TODO,
            'todo': IssueStatus.TODO,
            'open': IssueStatus.TODO,
            'new': IssueStatus.TODO,
            'in progress': IssueStatus.IN_PROGRESS,
            'in-progress': IssueStatus.IN_PROGRESS,
            'progress': IssueStatus.IN_PROGRESS,
            'working': IssueStatus.IN_PROGRESS,
            'done': IssueStatus.DONE,
            'closed': IssueStatus.DONE,
            'resolved': IssueStatus.DONE,
            'complete': IssueStatus.DONE,
            'blocked': IssueStatus.BLOCKED,
            'blocked/waiting': IssueStatus.BLOCKED,
            'waiting': IssueStatus.BLOCKED,
            'in review': IssueStatus.REVIEW,
            'review': IssueStatus.REVIEW,
            'under review': IssueStatus.REVIEW,
            'pending review': IssueStatus.REVIEW
        }
        
        normalized_status = status_name.lower().strip()
        return status_mapping.get(normalized_status, IssueStatus.TODO)

    def _extract_labels(self, labels_data: List[Dict[str, Any]]) -> List[str]:
        """Extract label names from Jira labels data.
        
        Args:
            labels_data: List of Jira label objects
            
        Returns:
            List of label names
        """
        if not isinstance(labels_data, list):
            return []
        
        return [label.get('name', '') for label in labels_data if label.get('name')]

    def _extract_components(self, components_data: List[Dict[str, Any]]) -> List[str]:
        """Extract component names from Jira components data.
        
        Args:
            components_data: List of Jira component objects
            
        Returns:
            List of component names
        """
        if not isinstance(components_data, list):
            return []
        
        return [comp.get('name', '') for comp in components_data if comp.get('name')]

    # =============================================================================
    # HIGH-LEVEL CONVENIENCE METHODS
    # =============================================================================

    async def get_user_assigned_issues(
        self,
        user_account_id: str,
        max_results: int = 50
    ) -> List[JiraIssue]:
        """Get issues assigned to a specific user.
        
        Args:
            user_account_id: User's account ID
            max_results: Maximum results to return
            
        Returns:
            List of JiraIssue model instances
        """
        jql = f"assignee = '{user_account_id}' ORDER BY updated DESC"
        result = await self.search_issues(jql, max_results=max_results)
        return result.issues

    async def get_project_issues(
        self,
        project_key: str,
        status: Optional[Union[IssueStatus, str]] = None,
        max_results: int = 50
    ) -> List[JiraIssue]:
        """Get all issues for a project, optionally filtered by status.
        
        Args:
            project_key: Project key
            status: Optional status filter
            max_results: Maximum results to return
            
        Returns:
            List of JiraIssue model instances
        """
        jql = f"project = {project_key}"
        
        if status:
            status_str = status.value if isinstance(status, IssueStatus) else str(status)
            jql += f" AND status = '{status_str}'"
        
        jql += " ORDER BY created DESC"
        
        result = await self.search_issues(jql, max_results=max_results)
        return result.issues

    async def get_recently_updated_issues(
        self,
        days: int = 7,
        max_results: int = 50
    ) -> List[JiraIssue]:
        """Get recently updated issues.
        
        Args:
            days: Number of days to look back
            max_results: Maximum results to return
            
        Returns:
            List of JiraIssue model instances
        """
        jql = f"updated >= -{days}d ORDER BY updated DESC"
        result = await self.search_issues(jql, max_results=max_results)
        return result.issues