"""
Jira Service for interacting with Jira Cloud API.

This service provides a clean interface for all Jira operations, handling API calls,
response parsing, and error handling. All methods return domain model instances.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from models import (
    IssueComment,
    IssuePriority,
    IssueSearchResult,
    IssueType,
    JiraIssue,
    Project,
)

logger = logging.getLogger(__name__)


class JiraAPIError(Exception):
    """Exception raised for Jira API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        """Initialize Jira API error.
        
        Args:
            message: Error message
            status_code: HTTP status code if available
            response_data: Raw response data if available
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class JiraAuthenticationError(JiraAPIError):
    """Exception raised for Jira authentication errors."""
    pass


class JiraNotFoundError(JiraAPIError):
    """Exception raised when Jira resource is not found."""
    pass


class JiraService:
    """
    Service for interacting with Jira Cloud API.
    
    Provides methods for project management, issue operations, and comments.
    All methods return domain model instances and handle API errors appropriately.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        *,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """
        Initialize Jira service.
        
        Args:
            base_url: Jira instance base URL (e.g., 'https://company.atlassian.net')
            username: Jira username/email
            api_token: Jira API token
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Raises:
            TypeError: If parameters have incorrect types
            ValueError: If parameters have invalid values
        """
        if not isinstance(base_url, str) or not base_url:
            raise TypeError("base_url must be non-empty string")
        if not isinstance(username, str) or not username:
            raise TypeError("username must be non-empty string")
        if not isinstance(api_token, str) or not api_token:
            raise TypeError("api_token must be non-empty string")
        if not isinstance(timeout, int) or timeout <= 0:
            raise TypeError("timeout must be positive integer")
        if not isinstance(max_retries, int) or max_retries < 0:
            raise TypeError("max_retries must be non-negative integer")
        if not isinstance(retry_delay, (int, float)) or retry_delay < 0:
            raise TypeError("retry_delay must be non-negative number")

        self.base_url = base_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._session: Optional[ClientSession] = None
        self._closed = False

    async def _get_session(self) -> ClientSession:
        """Get or create HTTP session with proper configuration."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.timeout)
            auth = aiohttp.BasicAuth(self.username, self.api_token)
            
            self._session = ClientSession(
                timeout=timeout,
                auth=auth,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                }
            )
        
        return self._session

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Jira API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (relative to base_url)
            params: Query parameters
            json_data: JSON request body
            
        Returns:
            Parsed JSON response
            
        Raises:
            JiraAuthenticationError: For authentication failures
            JiraNotFoundError: For 404 errors
            JiraAPIError: For other API errors
        """
        if not isinstance(method, str) or method not in ('GET', 'POST', 'PUT', 'DELETE'):
            raise TypeError(f"method must be valid HTTP method, got {method}")
        if not isinstance(endpoint, str):
            raise TypeError(f"endpoint must be string, got {type(endpoint)}")

        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"
        session = await self._get_session()
        
        for attempt in range(self.max_retries + 1):
            try:
                async with session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                ) as response:
                    
                    if response.status == 401:
                        raise JiraAuthenticationError(
                            "Authentication failed. Check username and API token.",
                            status_code=response.status
                        )
                    
                    if response.status == 404:
                        raise JiraNotFoundError(
                            f"Resource not found: {endpoint}",
                            status_code=response.status
                        )
                    
                    if response.status >= 400:
                        try:
                            error_data = await response.json()
                        except Exception:
                            error_data = {"message": await response.text()}
                        
                        error_msg = error_data.get('errorMessages', [])
                        if isinstance(error_msg, list) and error_msg:
                            error_msg = '; '.join(error_msg)
                        elif not error_msg:
                            error_msg = error_data.get('message', f'HTTP {response.status}')
                            
                        raise JiraAPIError(
                            f"Jira API error: {error_msg}",
                            status_code=response.status,
                            response_data=error_data
                        )
                    
                    # Success case
                    if response.status == 204:  # No content
                        return {}
                    
                    return await response.json()
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == self.max_retries:
                    raise JiraAPIError(f"Network error after {self.max_retries} retries: {e}")
                
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                await asyncio.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff

    # ---- Meta ----

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Jira service health and connectivity.
        
        Returns:
            Dict containing health status and service info
            
        Raises:
            JiraAPIError: If health check fails
        """
        try:
            response = await self._make_request('GET', 'serverInfo')
            
            return {
                'status': 'healthy',
                'server_version': response.get('version'),
                'server_title': response.get('serverTitle'),
                'base_url': self.base_url,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'base_url': self.base_url,
            }

    async def close(self) -> None:
        """Close HTTP session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._closed = True

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if not self._closed and self._session:
            # Log warning as we can't await in __del__
            logger.warning("JiraService was not properly closed. Call close() explicitly.")

    # ---- Projects ----

    async def list_projects(self, *, limit: int = 100, page: int = 0) -> List[Project]:
        """
        List all accessible Jira projects.
        
        Args:
            limit: Maximum number of projects to return
            page: Page number (0-based)
            
        Returns:
            List of Project instances
            
        Raises:
            TypeError: If parameters have incorrect types
            JiraAPIError: If API request fails
        """
        if not isinstance(limit, int) or limit <= 0:
            raise TypeError("limit must be positive integer")
        if not isinstance(page, int) or page < 0:
            raise TypeError("page must be non-negative integer")

        params = {
            'maxResults': min(limit, 100),  # Jira API limit
            'startAt': page * limit,
            'expand': 'description,lead,url,projectKeys,projectCategory',
        }
        
        response = await self._make_request('GET', 'project/search', params=params)
        projects = []
        
        for project_data in response.get('values', []):
            try:
                project = Project.from_jira_response(project_data)
                projects.append(project)
            except Exception as e:
                logger.warning(f"Failed to parse project {project_data.get('key', 'unknown')}: {e}")
        
        return projects

    async def get_project(self, project_key: str) -> Project:
        """
        Get detailed information about a specific project.
        
        Args:
            project_key: Jira project key
            
        Returns:
            Project instance
            
        Raises:
            TypeError: If project_key is not string
            JiraNotFoundError: If project doesn't exist
            JiraAPIError: If API request fails
        """
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")

        params = {
            'expand': 'description,lead,url,projectKeys,projectCategory',
        }
        
        response = await self._make_request('GET', f'project/{project_key}', params=params)
        return Project.from_jira_response(response)

    # ---- Issues ----

    async def get_issue(self, issue_key: str) -> JiraIssue:
        """
        Get detailed information about a specific issue.
        
        Args:
            issue_key: Jira issue key (e.g., 'PROJ-123')
            
        Returns:
            JiraIssue instance
            
        Raises:
            TypeError: If issue_key is not string
            JiraNotFoundError: If issue doesn't exist
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key:
            raise TypeError("issue_key must be non-empty string")

        params = {
            'expand': 'names,schema,operations,editmeta,changelog,renderedFields',
        }
        
        response = await self._make_request('GET', f'issue/{issue_key}', params=params)
        return JiraIssue.from_jira_response(response)

    async def search_issues(
        self,
        jql: str,
        *,
        max_results: int = 20,
        start_at: int = 0,
        fields: Optional[List[str]] = None,
    ) -> IssueSearchResult:
        """
        Search for issues using JQL (Jira Query Language).
        
        Args:
            jql: JQL query string
            max_results: Maximum number of results to return
            start_at: Starting index for pagination
            fields: List of fields to include in response
            
        Returns:
            IssueSearchResult containing matching issues
            
        Raises:
            TypeError: If parameters have incorrect types
            JiraAPIError: If search fails or JQL is invalid
        """
        if not isinstance(jql, str) or not jql:
            raise TypeError("jql must be non-empty string")
        if not isinstance(max_results, int) or max_results <= 0:
            raise TypeError("max_results must be positive integer")
        if not isinstance(start_at, int) or start_at < 0:
            raise TypeError("start_at must be non-negative integer")
        if fields is not None and not isinstance(fields, list):
            raise TypeError("fields must be list or None")

        json_data = {
            'jql': jql,
            'maxResults': min(max_results, 100),  # Jira API limit
            'startAt': start_at,
            'expand': ['names', 'schema', 'operations'],
        }
        
        if fields:
            json_data['fields'] = fields
        else:
            # Default fields for comprehensive issue data
            json_data['fields'] = [
                'summary', 'description', 'issuetype', 'status', 'priority',
                'assignee', 'reporter', 'project', 'labels', 'components',
                'created', 'updated'
            ]

        response = await self._make_request('POST', 'search', json_data=json_data)
        
        issues = []
        for issue_data in response.get('issues', []):
            try:
                issue = JiraIssue.from_jira_response(issue_data)
                issues.append(issue)
            except Exception as e:
                logger.warning(f"Failed to parse issue {issue_data.get('key', 'unknown')}: {e}")

        return IssueSearchResult(
            issues=issues,
            total_count=response.get('total', 0),
            search_query=jql,
            start_at=start_at,
            max_results=max_results,
        )

    async def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        issue_type: IssueType,
        description: str = "",
        priority: IssuePriority = IssuePriority.MEDIUM,
        assignee_account_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None,
    ) -> JiraIssue:
        """
        Create a new Jira issue.
        
        Args:
            project_key: Project key where issue will be created
            summary: Issue summary/title
            issue_type: Type of issue to create
            description: Detailed description
            priority: Issue priority level
            assignee_account_id: Account ID of assignee (optional)
            labels: List of labels to apply
            components: List of component names
            
        Returns:
            Created JiraIssue instance
            
        Raises:
            TypeError: If parameters have incorrect types
            JiraAPIError: If issue creation fails
        """
        # Parameter validation
        if not isinstance(project_key, str) or not project_key:
            raise TypeError("project_key must be non-empty string")
        if not isinstance(summary, str) or not summary:
            raise TypeError("summary must be non-empty string")
        if not isinstance(issue_type, IssueType):
            raise TypeError(f"issue_type must be IssueType, got {type(issue_type)}")
        if not isinstance(description, str):
            raise TypeError(f"description must be string, got {type(description)}")
        if not isinstance(priority, IssuePriority):
            raise TypeError(f"priority must be IssuePriority, got {type(priority)}")
        if assignee_account_id is not None and not isinstance(assignee_account_id, str):
            raise TypeError("assignee_account_id must be string or None")
        if labels is not None and not isinstance(labels, list):
            raise TypeError("labels must be list or None")
        if components is not None and not isinstance(components, list):
            raise TypeError("components must be list or None")

        fields = {
            'project': {'key': project_key},
            'summary': summary,
            'description': description,
            'issuetype': {'name': issue_type.value},
            'priority': {'name': priority.value},
        }
        
        if assignee_account_id:
            fields['assignee'] = {'accountId': assignee_account_id}
            
        if labels:
            fields['labels'] = labels
            
        if components:
            fields['components'] = [{'name': comp} for comp in components]

        json_data = {'fields': fields}
        
        response = await self._make_request('POST', 'issue', json_data=json_data)
        
        # Fetch the created issue with full details
        issue_key = response['key']
        return await self.get_issue(issue_key)

    async def assign_issue(self, issue_key: str, assignee_account_id: str) -> None:
        """
        Assign an issue to a user.
        
        Args:
            issue_key: Jira issue key
            assignee_account_id: Account ID of the assignee
            
        Raises:
            TypeError: If parameters have incorrect types
            JiraNotFoundError: If issue or user doesn't exist
            JiraAPIError: If assignment fails
        """
        if not isinstance(issue_key, str) or not issue_key:
            raise TypeError("issue_key must be non-empty string")
        if not isinstance(assignee_account_id, str) or not assignee_account_id:
            raise TypeError("assignee_account_id must be non-empty string")

        json_data = {
            'accountId': assignee_account_id
        }
        
        await self._make_request('PUT', f'issue/{issue_key}/assignee', json_data=json_data)

    # ---- Comments ----

    async def add_comment(self, issue_key: str, body: str) -> IssueComment:
        """
        Add a comment to an issue.
        
        Args:
            issue_key: Jira issue key
            body: Comment text content
            
        Returns:
            Created IssueComment instance
            
        Raises:
            TypeError: If parameters have incorrect types
            JiraNotFoundError: If issue doesn't exist
            JiraAPIError: If comment creation fails
        """
        if not isinstance(issue_key, str) or not issue_key:
            raise TypeError("issue_key must be non-empty string")
        if not isinstance(body, str) or not body:
            raise TypeError("body must be non-empty string")

        json_data = {
            'body': body
        }
        
        response = await self._make_request('POST', f'issue/{issue_key}/comment', json_data=json_data)
        return IssueComment.from_jira_response(response)

    async def list_comments(self, issue_key: str) -> List[IssueComment]:
        """
        Get all comments for an issue.
        
        Args:
            issue_key: Jira issue key
            
        Returns:
            List of IssueComment instances
            
        Raises:
            TypeError: If issue_key is not string
            JiraNotFoundError: If issue doesn't exist
            JiraAPIError: If request fails
        """
        if not isinstance(issue_key, str) or not issue_key:
            raise TypeError("issue_key must be non-empty string")

        response = await self._make_request('GET', f'issue/{issue_key}/comment')
        
        comments = []
        for comment_data in response.get('comments', []):
            try:
                comment = IssueComment.from_jira_response(comment_data)
                comments.append(comment)
            except Exception as e:
                logger.warning(f"Failed to parse comment {comment_data.get('id', 'unknown')}: {e}")
        
        return comments

    # ---- Transitions ----

    async def list_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Get available transitions for an issue.
        
        Args:
            issue_key: Jira issue key
            
        Returns:
            List of transition dictionaries with 'id' and 'name' keys
            
        Raises:
            TypeError: If issue_key is not string
            JiraNotFoundError: If issue doesn't exist
            JiraAPIError: If request fails
        """
        if not isinstance(issue_key, str) or not issue_key:
            raise TypeError("issue_key must be non-empty string")

        response = await self._make_request('GET', f'issue/{issue_key}/transitions')
        
        transitions = []
        for transition_data in response.get('transitions', []):
            transitions.append({
                'id': transition_data['id'],
                'name': transition_data['name'],
            })
        
        return transitions

    async def transition_issue(self, issue_key: str, transition_id: str) -> None:
        """
        Transition an issue to a new status.
        
        Args:
            issue_key: Jira issue key
            transition_id: ID of the transition to perform
            
        Raises:
            TypeError: If parameters have incorrect types
            JiraNotFoundError: If issue doesn't exist
            JiraAPIError: If transition fails
        """
        if not isinstance(issue_key, str) or not issue_key:
            raise TypeError("issue_key must be non-empty string")
        if not isinstance(transition_id, str) or not transition_id:
            raise TypeError("transition_id must be non-empty string")

        json_data = {
            'transition': {'id': transition_id}
        }
        
        await self._make_request('POST', f'issue/{issue_key}/transitions', json_data=json_data)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        

    async def get_current_user(self) -> Dict[str, Any]:
        """
        Return the current Jira user (the account tied to the API token).
        Docs: GET /rest/api/3/myself
        """
        return await self._make_request('GET', 'myself')
