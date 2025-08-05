#!/usr/bin/env python3
"""
Jira service for the Telegram-Jira bot.

Handles all interactions with the Jira REST API.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from urllib.parse import quote

import aiohttp
from aiohttp import ClientTimeout, ClientError

from ..models.project import Project
from ..models.issue import JiraIssue, IssueComment
from ..models.enums import IssuePriority, IssueType, IssueStatus


class JiraAPIError(Exception):
    """Custom exception for Jira API operations."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class JiraService:
    """Service for Jira API operations."""

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
        
        self.logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def _get_session(self):
        """Get aiohttp session with proper configuration."""
        timeout = ClientTimeout(total=self.timeout, connect=10)
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            enable_cleanup_closed=True
        )
        
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        ) as session:
            yield session

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make HTTP request to Jira API with retries.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (relative to api_url)
            data: Request body data
            params: Query parameters
            retry_count: Current retry attempt
            
        Returns:
            Response data as dictionary
            
        Raises:
            JiraAPIError: If request fails after all retries
        """
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self._get_session() as session:
                async with session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    auth=self.auth
                ) as response:
                    
                    response_text = await response.text()
                    
                    # Handle different response codes
                    if response.status == 200 or response.status == 201:
                        try:
                            return await response.json() if response_text else {}
                        except ValueError:
                            return {'message': response_text}
                    
                    elif response.status == 204:  # No Content
                        return {}
                    
                    elif response.status == 404:
                        raise JiraAPIError(
                            f"Resource not found: {endpoint}",
                            status_code=response.status
                        )
                    
                    elif response.status == 401:
                        raise JiraAPIError(
                            "Authentication failed. Check your email and API token.",
                            status_code=response.status
                        )
                    
                    elif response.status == 403:
                        raise JiraAPIError(
                            "Permission denied. Check your Jira permissions.",
                            status_code=response.status
                        )
                    
                    elif response.status >= 400:
                        # Try to parse error response
                        error_data = {}
                        try:
                            error_data = await response.json()
                        except ValueError:
                            error_data = {'message': response_text}
                        
                        error_message = self._extract_error_message(error_data, response.status)
                        raise JiraAPIError(
                            error_message,
                            status_code=response.status,
                            response_data=error_data
                        )
                    
                    else:
                        raise JiraAPIError(
                            f"Unexpected response code: {response.status}",
                            status_code=response.status
                        )
                        
        except (ClientError, asyncio.TimeoutError) as e:
            if retry_count < self.max_retries:
                self.logger.warning(f"Request failed, retrying in {self.retry_delay}s: {e}")
                await asyncio.sleep(self.retry_delay * (retry_count + 1))  # Exponential backoff
                return await self._make_request(method, endpoint, data, params, retry_count + 1)
            else:
                self.logger.error(f"Request failed after {self.max_retries} retries: {e}")
                raise JiraAPIError(f"Network error after {self.max_retries} retries: {e}")
        
        except JiraAPIError:
            # Re-raise JiraAPIError without modification
            raise
        
        except Exception as e:
            self.logger.error(f"Unexpected error in request: {e}")
            raise JiraAPIError(f"Unexpected error: {e}")

    def _extract_error_message(self, error_data: Dict[str, Any], status_code: int) -> str:
        """Extract meaningful error message from Jira error response."""
        if isinstance(error_data, dict):
            # Check for standard error message
            if 'errorMessages' in error_data and error_data['errorMessages']:
                return '; '.join(error_data['errorMessages'])
            
            if 'message' in error_data:
                return error_data['message']
            
            # Check for field errors
            if 'errors' in error_data and error_data['errors']:
                error_parts = []
                for field, message in error_data['errors'].items():
                    error_parts.append(f"{field}: {message}")
                return '; '.join(error_parts)
        
        return f"HTTP {status_code} error"

    async def test_connection(self) -> bool:
        """Test Jira API connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = await self._make_request('GET', 'myself')
            return bool(response.get('accountId'))
        except Exception as e:
            self.logger.error(f"Jira connection test failed: {e}")
            return False

    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user information.
        
        Returns:
            User information dictionary
            
        Raises:
            JiraAPIError: If request fails
        """
        return await self._make_request('GET', 'myself')

    # Project operations
    async def get_projects(self, include_archived: bool = False) -> List[Project]:
        """Get all accessible projects.
        
        Args:
            include_archived: Whether to include archived projects
            
        Returns:
            List of Project objects
            
        Raises:
            JiraAPIError: If request fails
        """
        params = {
            'expand': 'description,lead,url,projectKeys,permissions,insight',
            'recent': 50
        }
        
        if not include_archived:
            params['status'] = 'live'
        
        try:
            response = await self._make_request('GET', 'project/search', params=params)
            projects = []
            
            for project_data in response.get('values', []):
                try:
                    project = Project.from_jira_data(project_data)
                    projects.append(project)
                except Exception as e:
                    self.logger.warning(f"Failed to parse project {project_data.get('key', 'unknown')}: {e}")
                    continue
            
            return projects
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to retrieve projects: {e}")

    async def get_project(self, project_key: str) -> Optional[Project]:
        """Get a specific project by key.
        
        Args:
            project_key: Project key to retrieve
            
        Returns:
            Project object if found, None otherwise
            
        Raises:
            ValueError: If project_key is invalid
            JiraAPIError: If request fails
        """
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")

        try:
            response = await self._make_request(
                'GET', 
                f'project/{project_key}',
                params={'expand': 'description,lead,url,projectKeys,permissions,insight'}
            )
            return Project.from_jira_data(response)
            
        except JiraAPIError as e:
            if e.status_code == 404:
                return None
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to retrieve project {project_key}: {e}")

    async def verify_project(self, project_key: str) -> bool:
        """Verify if a project exists and is accessible.
        
        Args:
            project_key: Project key to verify
            
        Returns:
            True if project exists and is accessible, False otherwise
            
        Raises:
            ValueError: If project_key is invalid
        """
        try:
            project = await self.get_project(project_key)
            return project is not None
        except JiraAPIError:
            return False

    # Issue operations
    async def create_issue(
        self, 
        project_key: str, 
        summary: str,
        description: str,
        priority: IssuePriority = IssuePriority.MEDIUM,
        issue_type: IssueType = IssueType.TASK,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        parent_key: Optional[str] = None,
        epic_link: Optional[str] = None,
        due_date: Optional[datetime] = None,
        story_points: Optional[int] = None
    ) -> JiraIssue:
        """Create a Jira issue.
        
        Args:
            project_key: Jira project key
            summary: Issue summary
            description: Issue description  
            priority: Issue priority
            issue_type: Issue type
            assignee: Issue assignee (email or account ID)
            labels: Issue labels
            parent_key: Parent issue key (for subtasks)
            epic_link: Epic link
            due_date: Due date
            story_points: Story points
            
        Returns:
            Created Jira issue
            
        Raises:
            ValueError: If arguments are invalid
            JiraAPIError: If API request fails
        """
        # Input validation
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary must be a non-empty string")
        if not isinstance(description, str):
            raise ValueError("description must be a string")
        if not isinstance(priority, IssuePriority):
            raise ValueError("priority must be an IssuePriority instance")
        if not isinstance(issue_type, IssueType):
            raise ValueError("issue_type must be an IssueType instance")

        # Build issue payload
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type.value},
            "priority": {"name": priority.value}
        }
        
        # Add description in Atlassian Document Format
        if description:
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
        
        # Add optional fields
        if assignee:
            # Try to find user by email or account ID
            try:
                user_response = await self._make_request('GET', f'user/search', params={'query': assignee})
                if user_response and len(user_response) > 0:
                    fields["assignee"] = {"accountId": user_response[0]["accountId"]}
            except JiraAPIError:
                self.logger.warning(f"Could not find assignee: {assignee}")
        
        if labels:
            fields["labels"] = labels
        
        if parent_key:
            fields["parent"] = {"key": parent_key}
        
        if due_date:
            fields["duedate"] = due_date.strftime('%Y-%m-%d')
        
        # Handle custom fields (these field IDs may vary by Jira instance)
        if epic_link:
            # Common epic link field ID - may need to be configured per instance
            fields["customfield_10014"] = epic_link
        
        if story_points:
            # Common story points field ID - may need to be configured per instance  
            fields["customfield_10016"] = story_points

        payload = {"fields": fields}

        try:
            response = await self._make_request('POST', 'issue', data=payload)
            issue_key = response["key"]
            
            # Fetch the created issue to get complete data
            return await self.get_issue(issue_key)
                    
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to create issue: {e}")

    async def get_issue(self, issue_key: str) -> JiraIssue:
        """Get a specific issue by key.
        
        Args:
            issue_key: Issue key to retrieve
            
        Returns:
            JiraIssue object
            
        Raises:
            ValueError: If issue_key is invalid
            JiraAPIError: If request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        try:
            response = await self._make_request(
                'GET', 
                f'issue/{issue_key}',
                params={
                    'expand': 'fields,changelog,operations,versionedRepresentations',
                    'fields': '*all'
                }
            )
            
            # Extract project key from the issue
            project_key = response['fields']['project']['key']
            
            return JiraIssue.from_jira_data(response, project_key, self.base_url)
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to retrieve issue {issue_key}: {e}")

    async def update_issue(
        self,
        issue_key: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[IssuePriority] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        status: Optional[str] = None,
        due_date: Optional[datetime] = None,
        story_points: Optional[int] = None
    ) -> JiraIssue:
        """Update a Jira issue.
        
        Args:
            issue_key: Issue key to update
            summary: New summary
            description: New description
            priority: New priority
            assignee: New assignee
            labels: New labels
            status: New status (will attempt transition)
            due_date: New due date
            story_points: New story points
            
        Returns:
            Updated JiraIssue object
            
        Raises:
            ValueError: If issue_key is invalid
            JiraAPIError: If request fails
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
        
        if priority is not None:
            fields["priority"] = {"name": priority.value}
        
        if assignee is not None:
            if assignee == "":
                fields["assignee"] = None  # Unassign
            else:
                try:
                    user_response = await self._make_request('GET', f'user/search', params={'query': assignee})
                    if user_response and len(user_response) > 0:
                        fields["assignee"] = {"accountId": user_response[0]["accountId"]}
                except JiraAPIError:
                    self.logger.warning(f"Could not find assignee: {assignee}")
        
        if labels is not None:
            fields["labels"] = labels
        
        if due_date is not None:
            fields["duedate"] = due_date.strftime('%Y-%m-%d')
        
        if story_points is not None:
            fields["customfield_10016"] = story_points

        if fields:
            payload = {"fields": fields}
            try:
                await self._make_request('PUT', f'issue/{issue_key}', data=payload)
            except JiraAPIError:
                raise
        
        # Handle status transition separately
        if status is not None:
            try:
                await self.transition_issue(issue_key, status)
            except JiraAPIError as e:
                self.logger.warning(f"Failed to transition issue {issue_key} to {status}: {e}")
        
        # Return updated issue
        return await self.get_issue(issue_key)

    async def transition_issue(self, issue_key: str, status: str) -> None:
        """Transition an issue to a new status.
        
        Args:
            issue_key: Issue key to transition
            status: Target status name
            
        Raises:
            ValueError: If arguments are invalid
            JiraAPIError: If request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")

        try:
            # Get available transitions
            transitions_response = await self._make_request('GET', f'issue/{issue_key}/transitions')
            transitions = transitions_response.get('transitions', [])
            
            # Find matching transition
            transition_id = None
            for transition in transitions:
                if transition['to']['name'].lower() == status.lower():
                    transition_id = transition['id']
                    break
            
            if transition_id is None:
                available_statuses = [t['to']['name'] for t in transitions]
                raise JiraAPIError(
                    f"Cannot transition to '{status}'. Available transitions: {', '.join(available_statuses)}"
                )
            
            # Perform transition
            payload = {
                "transition": {"id": transition_id}
            }
            
            await self._make_request('POST', f'issue/{issue_key}/transitions', data=payload)
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to transition issue {issue_key}: {e}")

    async def search_issues(
        self,
        jql: Optional[str] = None,
        project_key: Optional[str] = None,
        issue_type: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        text_query: Optional[str] = None,
        start_at: int = 0,
        max_results: int = 50
    ) -> Dict[str, Any]:
        """Search for issues using JQL or filters.
        
        Args:
            jql: Custom JQL query
            project_key: Filter by project
            issue_type: Filter by issue type
            status: Filter by status
            assignee: Filter by assignee
            text_query: Text search in summary/description
            start_at: Starting index for pagination
            max_results: Maximum results to return
            
        Returns:
            Search results dictionary with issues and metadata
            
        Raises:
            JiraAPIError: If request fails
        """
        if jql:
            query = jql
        else:
            # Build JQL from filters
            conditions = []
            
            if project_key:
                conditions.append(f'project = "{project_key}"')
            
            if issue_type:
                conditions.append(f'issuetype = "{issue_type}"')
            
            if status:
                conditions.append(f'status = "{status}"')
            
            if assignee:
                if assignee.lower() == 'unassigned':
                    conditions.append('assignee is EMPTY')
                elif assignee.lower() == 'currentuser()':
                    conditions.append('assignee = currentUser()')
                else:
                    conditions.append(f'assignee = "{assignee}"')
            
            if text_query:
                conditions.append(f'(summary ~ "{text_query}" OR description ~ "{text_query}")')
            
            query = ' AND '.join(conditions) if conditions else 'project is not EMPTY'
        
        # Add ordering
        query += ' ORDER BY created DESC'
        
        params = {
            'jql': query,
            'startAt': start_at,
            'maxResults': min(max_results, 100),  # Jira API limit
            'expand': 'fields',
            'fields': '*all'
        }

        try:
            response = await self._make_request('GET', 'search', params=params)
            
            # Parse issues
            issues = []
            for issue_data in response.get('issues', []):
                try:
                    project_key = issue_data['fields']['project']['key']
                    issue = JiraIssue.from_jira_data(issue_data, project_key, self.base_url)
                    issues.append(issue)
                except Exception as e:
                    self.logger.warning(f"Failed to parse issue {issue_data.get('key', 'unknown')}: {e}")
                    continue
            
            return {
                'issues': issues,
                'total': response.get('total', 0),
                'start_at': response.get('startAt', 0),
                'max_results': response.get('maxResults', 0),
                'jql': query
            }
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to search issues: {e}")

    # Comment operations
    async def add_comment(self, issue_key: str, comment_body: str, visibility: Optional[str] = None) -> IssueComment:
        """Add a comment to an issue.
        
        Args:
            issue_key: Issue key to comment on
            comment_body: Comment text
            visibility: Comment visibility restriction
            
        Returns:
            Created comment
            
        Raises:
            ValueError: If arguments are invalid
            JiraAPIError: If request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        if not isinstance(comment_body, str) or not comment_body.strip():
            raise ValueError("comment_body must be a non-empty string")

        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment_body
                            }
                        ]
                    }
                ]
            }
        }
        
        if visibility:
            payload["visibility"] = {"type": "role", "value": visibility}

        try:
            response = await self._make_request('POST', f'issue/{issue_key}/comment', data=payload)
            
            return IssueComment(
                id=response['id'],
                author=response['author']['displayName'],
                body=comment_body,
                created_at=datetime.fromisoformat(response['created'].replace('Z', '+00:00')),
                updated_at=datetime.fromisoformat(response['updated'].replace('Z', '+00:00')) if response.get('updated') else None,
                visibility=visibility
            )
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to add comment to {issue_key}: {e}")

    async def get_comments(self, issue_key: str) -> List[IssueComment]:
        """Get all comments for an issue.
        
        Args:
            issue_key: Issue key to get comments for
            
        Returns:
            List of comments
            
        Raises:
            ValueError: If issue_key is invalid
            JiraAPIError: If request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        try:
            response = await self._make_request('GET', f'issue/{issue_key}/comment')
            
            comments = []
            for comment_data in response.get('comments', []):
                try:
                    # Extract text from comment body (ADF format)
                    body_text = self._extract_text_from_adf(comment_data.get('body', {}))
                    
                    comment = IssueComment(
                        id=comment_data['id'],
                        author=comment_data['author']['displayName'],
                        body=body_text,
                        created_at=datetime.fromisoformat(comment_data['created'].replace('Z', '+00:00')),
                        updated_at=datetime.fromisoformat(comment_data['updated'].replace('Z', '+00:00')) if comment_data.get('updated') else None,
                        visibility=comment_data.get('visibility', {}).get('value')
                    )
                    comments.append(comment)
                except Exception as e:
                    self.logger.warning(f"Failed to parse comment {comment_data.get('id', 'unknown')}: {e}")
                    continue
            
            return comments
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get comments for {issue_key}: {e}")

    def _extract_text_from_adf(self, adf_content: Dict[str, Any]) -> str:
        """Extract plain text from Atlassian Document Format."""
        if not isinstance(adf_content, dict):
            return str(adf_content)
        
        content = adf_content.get('content', [])
        if not isinstance(content, list):
            return ""
        
        text_parts = []
        
        for item in content:
            if not isinstance(item, dict):
                continue
                
            item_type = item.get('type', '')
            
            if item_type == 'paragraph':
                paragraph_content = item.get('content', [])
                paragraph_text = []
                for text_item in paragraph_content:
                    if isinstance(text_item, dict) and text_item.get('type') == 'text':
                        paragraph_text.append(text_item.get('text', ''))
                text_parts.append(' '.join(paragraph_text))
            elif item_type == 'text':
                text_parts.append(item.get('text', ''))
        
        return '\n'.join(text_parts).strip()

    # Utility methods
    async def get_issue_types(self, project_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get available issue types.
        
        Args:
            project_key: Optional project key to filter by
            
        Returns:
            List of issue type dictionaries
            
        Raises:
            JiraAPIError: If request fails
        """
        endpoint = 'issuetype'
        if project_key:
            endpoint = f'project/{project_key}/issuetype'

        try:
            response = await self._make_request('GET', endpoint)
            return response if isinstance(response, list) else []
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get issue types: {e}")

    async def get_priorities(self) -> List[Dict[str, Any]]:
        """Get available priorities.
        
        Returns:
            List of priority dictionaries
            
        Raises:
            JiraAPIError: If request fails
        """
        try:
            response = await self._make_request('GET', 'priority')
            return response if isinstance(response, list) else []
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get priorities: {e}")

    async def get_statuses(self) -> List[Dict[str, Any]]:
        """Get available statuses.
        
        Returns:
            List of status dictionaries
            
        Raises:
            JiraAPIError: If request fails
        """
        try:
            response = await self._make_request('GET', 'status')
            return response if isinstance(response, list) else []
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get statuses: {e}")

    async def get_users(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Search for users.
        
        Args:
            query: Search query (name, email, etc.)
            max_results: Maximum results to return
            
        Returns:
            List of user dictionaries
            
        Raises:
            ValueError: If query is invalid
            JiraAPIError: If request fails
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        try:
            params = {
                'query': query,
                'maxResults': min(max_results, 1000)
            }
            response = await self._make_request('GET', 'user/search', params=params)
            return response if isinstance(response, list) else []
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to search users: {e}")

    async def get_server_info(self) -> Dict[str, Any]:
        """Get Jira server information.
        
        Returns:
            Server information dictionary
            
        Raises:
            JiraAPIError: If request fails
        """
        try:
            return await self._make_request('GET', 'serverInfo')
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get server info: {e}")
        
    class JiraServiceExtensions:
    """Extension methods for JiraService class."""
    
    async def get_project_by_key(self, project_key: str) -> Optional[Project]:
        """Get project information by key.
        
        Args:
            project_key: Project key to lookup
            
        Returns:
            Project object if found, None otherwise
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/project/{quote(project_key)}"
                
                async with session.get(url, auth=self.auth) as response:
                    if response.status == 404:
                        return None
                    
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    return Project.from_jira_response(data)
                    
        except ClientError as e:
            self.logger.error(f"Network error getting project {project_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting project {project_key}: {e}")
            raise JiraAPIError(f"Failed to get project: {e}")

    async def get_all_projects(self, include_archived: bool = False) -> List[Project]:
        """Get all accessible projects.
        
        Args:
            include_archived: Whether to include archived projects
            
        Returns:
            List of Project objects
            
        Raises:
            JiraAPIError: If API request fails
        """
        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/project"
                params = {}
                
                if not include_archived:
                    params['expand'] = 'description,lead,issueTypes,url,projectKeys'
                
                if params:
                    url += f"?{urlencode(params)}"
                
                async with session.get(url, auth=self.auth) as response:
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    projects = []
                    for project_data in data:
                        try:
                            if not include_archived and project_data.get('archived', False):
                                continue
                            
                            project = Project.from_jira_response(project_data)
                            projects.append(project)
                        except (KeyError, ValueError) as e:
                            self.logger.warning(f"Skipping invalid project data: {e}")
                            continue
                    
                    return projects
                    
        except ClientError as e:
            self.logger.error(f"Network error getting projects: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting projects: {e}")
            raise JiraAPIError(f"Failed to get projects: {e}")

    async def search_issues(
        self, 
        jql_query: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: Optional[List[str]] = None
    ) -> List[JiraIssue]:
        """Search for issues using JQL.
        
        Args:
            jql_query: JQL query string
            max_results: Maximum number of results to return
            start_at: Index to start results from
            fields: Specific fields to retrieve
            
        Returns:
            List of JiraIssue objects
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(jql_query, str) or not jql_query.strip():
            raise ValueError("jql_query must be a non-empty string")
        
        if not isinstance(max_results, int) or max_results <= 0:
            raise ValueError("max_results must be a positive integer")
        
        if not isinstance(start_at, int) or start_at < 0:
            raise ValueError("start_at must be a non-negative integer")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/search"
                
                payload = {
                    'jql': jql_query,
                    'maxResults': min(max_results, 100),  # Jira API limit
                    'startAt': start_at,
                    'fields': fields or [
                        'summary', 'description', 'status', 'priority', 
                        'issuetype', 'assignee', 'reporter', 'created', 
                        'updated', 'labels', 'components', 'fixVersions',
                        'resolution', 'resolutiondate', 'duedate'
                    ]
                }
                
                async with session.post(
                    url, 
                    json=payload, 
                    auth=self.auth,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    issues = []
                    for issue_data in data.get('issues', []):
                        try:
                            issue = JiraIssue.from_jira_response(issue_data)
                            issues.append(issue)
                        except (KeyError, ValueError) as e:
                            self.logger.warning(f"Skipping invalid issue data: {e}")
                            continue
                    
                    return issues
                    
        except ClientError as e:
            self.logger.error(f"Network error searching issues: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error searching issues: {e}")
            raise JiraAPIError(f"Failed to search issues: {e}")

    async def get_issue_by_key(self, issue_key: str) -> Optional[JiraIssue]:
        """Get issue by key.
        
        Args:
            issue_key: Issue key (e.g., 'PROJ-123')
            
        Returns:
            JiraIssue object if found, None otherwise
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/issue/{quote(issue_key)}"
                
                async with session.get(url, auth=self.auth) as response:
                    if response.status == 404:
                        return None
                    
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    return JiraIssue.from_jira_response(data)
                    
        except ClientError as e:
            self.logger.error(f"Network error getting issue {issue_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting issue {issue_key}: {e}")
            raise JiraAPIError(f"Failed to get issue: {e}")

    async def update_issue(
        self,
        issue_key: str,
        fields: Dict[str, Any],
        update_history: bool = True
    ) -> bool:
        """Update issue fields.
        
        Args:
            issue_key: Issue key to update
            fields: Dictionary of fields to update
            update_history: Whether to add to issue history
            
        Returns:
            True if successful
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        
        if not isinstance(fields, dict) or not fields:
            raise ValueError("fields must be a non-empty dictionary")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/issue/{quote(issue_key)}"
                
                payload = {'fields': {}}
                
                # Convert common field updates
                if 'summary' in fields:
                    payload['fields']['summary'] = fields['summary']
                
                if 'description' in fields:
                    payload['fields']['description'] = fields['description']
                
                if 'priority' in fields:
                    if isinstance(fields['priority'], IssuePriority):
                        payload['fields']['priority'] = {'name': fields['priority'].value}
                    else:
                        payload['fields']['priority'] = {'name': str(fields['priority'])}
                
                if 'assignee' in fields:
                    if fields['assignee'] is None:
                        payload['fields']['assignee'] = None
                    else:
                        payload['fields']['assignee'] = {'name': fields['assignee']}
                
                if 'labels' in fields:
                    payload['fields']['labels'] = fields['labels']
                
                # Add any other custom fields
                for key, value in fields.items():
                    if key not in ['summary', 'description', 'priority', 'assignee', 'labels']:
                        payload['fields'][key] = value
                
                async with session.put(
                    url,
                    json=payload,
                    auth=self.auth,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    await self._handle_response_errors(response)
                    return True
                    
        except ClientError as e:
            self.logger.error(f"Network error updating issue {issue_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error updating issue {issue_key}: {e}")
            raise JiraAPIError(f"Failed to update issue: {e}")

    async def add_comment(self, issue_key: str, comment_text: str) -> Optional[IssueComment]:
        """Add comment to issue.
        
        Args:
            issue_key: Issue key to comment on
            comment_text: Comment text
            
        Returns:
            IssueComment object if successful
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        
        if not isinstance(comment_text, str) or not comment_text.strip():
            raise ValueError("comment_text must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/issue/{quote(issue_key)}/comment"
                
                payload = {'body': comment_text}
                
                async with session.post(
                    url,
                    json=payload,
                    auth=self.auth,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    return IssueComment.from_jira_response(data)
                    
        except ClientError as e:
            self.logger.error(f"Network error adding comment to {issue_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error adding comment to {issue_key}: {e}")
            raise JiraAPIError(f"Failed to add comment: {e}")

    async def get_issue_comments(self, issue_key: str) -> List[IssueComment]:
        """Get comments for an issue.
        
        Args:
            issue_key: Issue key to get comments for
            
        Returns:
            List of IssueComment objects
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/issue/{quote(issue_key)}/comment"
                
                async with session.get(url, auth=self.auth) as response:
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    comments = []
                    for comment_data in data.get('comments', []):
                        try:
                            comment = IssueComment.from_jira_response(comment_data)
                            comments.append(comment)
                        except (KeyError, ValueError) as e:
                            self.logger.warning(f"Skipping invalid comment data: {e}")
                            continue
                    
                    return comments
                    
        except ClientError as e:
            self.logger.error(f"Network error getting comments for {issue_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting comments for {issue_key}: {e}")
            raise JiraAPIError(f"Failed to get comments: {e}")

    async def transition_issue(
        self, 
        issue_key: str, 
        transition_id: str,
        fields: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Transition issue to new status.
        
        Args:
            issue_key: Issue key to transition
            transition_id: ID of transition to execute
            fields: Optional fields to update during transition
            
        Returns:
            True if successful
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")
        
        if not isinstance(transition_id, str) or not transition_id.strip():
            raise ValueError("transition_id must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/issue/{quote(issue_key)}/transitions"
                
                payload = {
                    'transition': {'id': transition_id}
                }
                
                if fields:
                    payload['fields'] = fields
                
                async with session.post(
                    url,
                    json=payload,
                    auth=self.auth,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    await self._handle_response_errors(response)
                    return True
                    
        except ClientError as e:
            self.logger.error(f"Network error transitioning issue {issue_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error transitioning issue {issue_key}: {e}")
            raise JiraAPIError(f"Failed to transition issue: {e}")

    async def get_available_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get available transitions for an issue.
        
        Args:
            issue_key: Issue key to get transitions for
            
        Returns:
            List of transition dictionaries
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(issue_key, str) or not issue_key.strip():
            raise ValueError("issue_key must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/issue/{quote(issue_key)}/transitions"
                
                async with session.get(url, auth=self.auth) as response:
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    return data.get('transitions', [])
                    
        except ClientError as e:
            self.logger.error(f"Network error getting transitions for {issue_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting transitions for {issue_key}: {e}")
            raise JiraAPIError(f"Failed to get transitions: {e}")

    async def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information by username.
        
        Args:
            username: Username to lookup
            
        Returns:
            User information dictionary if found
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(username, str) or not username.strip():
            raise ValueError("username must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/user"
                params = {'username': username}
                
                async with session.get(url, params=params, auth=self.auth) as response:
                    if response.status == 404:
                        return None
                    
                    await self._handle_response_errors(response)
                    return await response.json()
                    
        except ClientError as e:
            self.logger.error(f"Network error getting user {username}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting user {username}: {e}")
            raise JiraAPIError(f"Failed to get user info: {e}")

    async def get_project_components(self, project_key: str) -> List[Dict[str, Any]]:
        """Get components for a project.
        
        Args:
            project_key: Project key
            
        Returns:
            List of component dictionaries
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/project/{quote(project_key)}/components"
                
                async with session.get(url, auth=self.auth) as response:
                    await self._handle_response_errors(response)
                    return await response.json()
                    
        except ClientError as e:
            self.logger.error(f"Network error getting components for {project_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting components for {project_key}: {e}")
            raise JiraAPIError(f"Failed to get components: {e}")

    async def get_project_versions(self, project_key: str) -> List[Dict[str, Any]]:
        """Get versions for a project.
        
        Args:
            project_key: Project key
            
        Returns:
            List of version dictionaries
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(project_key, str) or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/project/{quote(project_key)}/versions"
                
                async with session.get(url, auth=self.auth) as response:
                    await self._handle_response_errors(response)
                    return await response.json()
                    
        except ClientError as e:
            self.logger.error(f"Network error getting versions for {project_key}: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting versions for {project_key}: {e}")
            raise JiraAPIError(f"Failed to get versions: {e}")

    async def _handle_response_errors(self, response: aiohttp.ClientResponse) -> None:
        """Handle HTTP response errors.
        
        Args:
            response: HTTP response object
            
        Raises:
            JiraAPIError: If response indicates an error
        """
        if response.status >= 400:
            try:
                error_data = await response.json()
                error_message = error_data.get('errorMessages', [])
                if error_message:
                    message = '; '.join(error_message)
                else:
                    errors = error_data.get('errors', {})
                    if errors:
                        message = '; '.join([f"{k}: {v}" for k, v in errors.items()])
                    else:
                        message = f"HTTP {response.status}: {response.reason}"
            except (ValueError, KeyError):
                message = f"HTTP {response.status}: {response.reason}"
            
            raise JiraAPIError(message, status_code=response.status)

    async def validate_jql(self, jql_query: str) -> Dict[str, Any]:
        """Validate JQL query syntax.
        
        Args:
            jql_query: JQL query to validate
            
        Returns:
            Validation result dictionary
            
        Raises:
            JiraAPIError: If API request fails
        """
        if not isinstance(jql_query, str):
            raise ValueError("jql_query must be a string")

        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/jql/parse"
                payload = {'queries': [jql_query]}
                
                async with session.post(
                    url,
                    json=payload,
                    auth=self.auth,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    await self._handle_response_errors(response)
                    data = await response.json()
                    
                    if data.get('queries'):
                        return data['queries'][0]
                    
                    return {'valid': False, 'errors': ['Invalid JQL query']}
                    
        except ClientError as e:
            self.logger.error(f"Network error validating JQL: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error validating JQL: {e}")
            raise JiraAPIError(f"Failed to validate JQL: {e}")

    async def get_server_info(self) -> Dict[str, Any]:
        """Get Jira server information.
        
        Returns:
            Server information dictionary
            
        Raises:
            JiraAPIError: If API request fails
        """
        try:
            async with self._get_session() as session:
                url = f"{self.base_url}/serverInfo"
                
                async with session.get(url, auth=self.auth) as response:
                    await self._handle_response_errors(response)
                    return await response.json()
                    
        except ClientError as e:
            self.logger.error(f"Network error getting server info: {e}")
            raise JiraAPIError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Error getting server info: {e}")
            raise JiraAPIError(f"Failed to get server info: {e}")

    async def test_connection(self) -> bool:
        """Test connection to Jira.
        
        Returns:
            True if connection successful
            
        Raises:
            JiraAPIError: If connection fails
        """
        try:
            await self.get_server_info()
            return True
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Connection test failed: {e}")    