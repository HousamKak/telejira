#!/usr/bin/env python3
"""
Jira service for the Telegram-Jira bot.

Handles all interactions with the Jira REST API and converts responses to our models.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from urllib.parse import quote, urljoin
import json

import aiohttp
from aiohttp import ClientTimeout, ClientError, ClientSession


class JiraAPIError(Exception):
    """Enhanced exception for Jira API operations."""
    
    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None, 
        response_data: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}
        self.retry_after = retry_after

    def is_retryable(self) -> bool:
        """Check if this error indicates a retryable condition."""
        if self.status_code is None:
            return True  # Network errors are retryable
        
        # Retryable HTTP status codes
        retryable_codes = {408, 429, 500, 502, 503, 504}
        return self.status_code in retryable_codes

    def is_rate_limit(self) -> bool:
        """Check if this is a rate limit error."""
        return self.status_code == 429


class JiraService:
    """Enhanced Jira service with comprehensive fixes."""

    def __init__(
        self, 
        domain: str, 
        email: str, 
        api_token: str,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        page_size: int = 50,
        rate_limit_requests: int = 100,
        rate_limit_window: int = 60,
        connection_pool_size: int = 10
    ) -> None:
        """Initialize Jira service with enhanced configuration."""
        # Input validation
        if not all([domain, email, api_token]):
            raise ValueError("Domain, email, and API token are required")
        
        if domain.startswith(('http://', 'https://')):
            raise ValueError("Domain should not include protocol (use 'company.atlassian.net')")
        
        if not domain.endswith('.atlassian.net'):
            self.logger = logging.getLogger(self.__class__.__name__)
            self.logger.warning("Domain doesn't end with '.atlassian.net', this might cause issues")
        
        # Configuration
        self.domain = domain.rstrip('/')
        self.email = email.strip()
        self.api_token = api_token
        self.base_url = f"https://{self.domain}/rest/api/2"
        
        # Timeout and retry configuration
        self.timeout = max(5, min(timeout, 120))  # Clamp between 5-120 seconds
        self.max_retries = max(1, min(max_retries, 10))
        self.retry_delay = max(0.1, min(retry_delay, 10.0))
        self.page_size = max(10, min(page_size, 100))
        
        # Rate limiting configuration
        self.rate_limit_requests = max(10, min(rate_limit_requests, 1000))
        self.rate_limit_window = max(10, min(rate_limit_window, 3600))
        self._request_timestamps: List[float] = []
        self._rate_limit_lock = asyncio.Lock()
        
        # Session management
        self._session: Optional[ClientSession] = None
        self._session_lock = asyncio.Lock()
        self.connection_pool_size = max(5, min(connection_pool_size, 50))
        
        # Statistics and monitoring
        self._request_count = 0
        self._error_count = 0
        self._last_request_time: Optional[float] = None
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"🔧 Jira service initialized for domain: {self.domain}")

    async def _get_session(self) -> ClientSession:
        """Get or create HTTP session with optimized configuration."""
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    await self._create_session()
        
        return self._session

    async def _create_session(self) -> None:
        """Create new HTTP session with optimized settings."""
        try:
            # Create timeout configuration
            timeout = ClientTimeout(
                total=self.timeout,
                connect=min(10, self.timeout // 3),
                sock_read=self.timeout - 5
            )
            
            # Create connector with connection pooling
            connector = aiohttp.TCPConnector(
                limit=self.connection_pool_size,
                limit_per_host=max(2, self.connection_pool_size // 2),
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                force_close=False,
                auto_decompress=True
            )
            
            # Default headers
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'User-Agent': 'telegram-jira-bot/2.0 (aiohttp)',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            
            # Create session
            self._session = ClientSession(
                timeout=timeout,
                connector=connector,
                auth=aiohttp.BasicAuth(self.email, self.api_token),
                headers=headers,
                raise_for_status=False,  # Handle status codes manually
                skip_auto_headers={'User-Agent'}  # Use our custom user agent
            )
            
            self.logger.debug("✅ HTTP session created successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to create HTTP session: {e}")
            raise JiraAPIError(f"Session creation failed: {e}")

    async def _check_rate_limit(self) -> None:
        """Check and enforce client-side rate limiting."""
        async with self._rate_limit_lock:
            now = time.time()
            
            # Remove timestamps outside the window
            self._request_timestamps = [
                ts for ts in self._request_timestamps 
                if now - ts < self.rate_limit_window
            ]
            
            # Check if we're at the limit
            if len(self._request_timestamps) >= self.rate_limit_requests:
                # Calculate wait time
                oldest_timestamp = min(self._request_timestamps)
                wait_time = self.rate_limit_window - (now - oldest_timestamp) + 0.1
                
                if wait_time > 0:
                    self.logger.warning(f"⏱️ Rate limit reached, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                    
                    # Refresh timestamp after waiting
                    now = time.time()
            
            # Add current request timestamp
            self._request_timestamps.append(now)

    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout_override: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with comprehensive error handling and retries."""
        # Apply rate limiting
        await self._check_rate_limit()
        
        # Prepare URL
        url = urljoin(self.base_url + '/', endpoint.lstrip('/'))
        session = await self._get_session()
        
        # Prepare request parameters
        request_kwargs = {
            'method': method,
            'url': url,
            'params': params,
            'headers': headers or {}
        }
        
        # Add data for non-GET requests
        if method != 'GET' and data is not None:
            request_kwargs['json'] = data
        
        # Apply timeout override
        if timeout_override:
            timeout = ClientTimeout(total=timeout_override)
            request_kwargs['timeout'] = timeout
        
        # Retry logic with exponential backoff
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                self._request_count += 1
                self._last_request_time = time.time()
                
                self.logger.debug(f"🌐 {method} {endpoint} (attempt {attempt + 1}/{self.max_retries + 1})")
                
                async with session.request(**request_kwargs) as response:
                    # Log response details
                    self.logger.debug(f"📥 Response: {response.status} for {method} {endpoint}")
                    
                    # Handle successful responses
                    if response.status in (200, 201):
                        if response.content_type == 'application/json':
                            result = await response.json()
                            self.logger.debug(f"✅ Request successful: {method} {endpoint}")
                            return result
                        else:
                            # Handle non-JSON responses
                            text = await response.text()
                            return {'text': text}
                    
                    elif response.status == 204:
                        # No content response (successful)
                        return {}
                    
                    elif response.status == 400:
                        # Bad request - not retryable
                        error_data = {}
                        try:
                            if response.content_type == 'application/json':
                                error_data = await response.json()
                        except:
                            error_data = {'text': await response.text()}
                        
                        error_messages = error_data.get('errorMessages', [])
                        error_details = error_data.get('errors', {})
                        
                        if error_messages:
                            error_msg = '; '.join(error_messages)
                        elif error_details:
                            error_msg = '; '.join([f"{k}: {v}" for k, v in error_details.items()])
                        else:
                            error_msg = error_data.get('text', 'Bad request')
                        
                        raise JiraAPIError(
                            f"Bad request: {error_msg}",
                            status_code=400,
                            response_data=error_data
                        )
                    
                    elif response.status == 401:
                        # Authentication failed - not retryable
                        raise JiraAPIError(
                            "Authentication failed. Please check your email and API token.",
                            status_code=401
                        )
                    
                    elif response.status == 403:
                        # Access denied - not retryable
                        raise JiraAPIError(
                            "Access denied. Please check your account permissions.",
                            status_code=403
                        )
                    
                    elif response.status == 404:
                        # Not found - not retryable
                        raise JiraAPIError(
                            f"Resource not found: {endpoint}",
                            status_code=404
                        )
                    
                    elif response.status == 429:
                        # Rate limited by Jira - retryable
                        retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                        self.logger.warning(f"🚫 Rate limited by Jira, waiting {retry_after}s")
                        
                        if attempt < self.max_retries:
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            raise JiraAPIError(
                                f"Rate limited by Jira after {self.max_retries} retries",
                                status_code=429,
                                retry_after=retry_after
                            )
                    
                    elif 500 <= response.status < 600:
                        # Server error - retryable
                        error_text = await response.text()
                        last_exception = JiraAPIError(
                            f"Server error {response.status}: {error_text[:200]}",
                            status_code=response.status
                        )
                        
                        if attempt < self.max_retries:
                            wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                            wait_time = min(wait_time, 60)  # Cap at 60 seconds
                            self.logger.warning(f"🔄 Server error, retrying in {wait_time:.1f}s")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise last_exception
                    
                    else:
                        # Unexpected status code
                        error_text = await response.text()
                        raise JiraAPIError(
                            f"Unexpected status {response.status}: {error_text[:200]}",
                            status_code=response.status
                        )
            
            except JiraAPIError:
                # Re-raise our custom exceptions
                raise
            
            except asyncio.TimeoutError:
                last_exception = JiraAPIError(f"Request timeout after {self.timeout}s")
                self._error_count += 1
                
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2 ** attempt)
                    self.logger.warning(f"⏰ Timeout, retrying in {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise last_exception
            
            except ClientError as e:
                last_exception = JiraAPIError(f"Network error: {e}")
                self._error_count += 1
                
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2 ** attempt)
                    self.logger.warning(f"🌐 Network error, retrying in {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise last_exception
            
            except Exception as e:
                # Unexpected error - not retryable
                self._error_count += 1
                self.logger.error(f"❌ Unexpected error in request: {e}")
                raise JiraAPIError(f"Unexpected error: {e}")
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception
        else:
            raise JiraAPIError("All retry attempts failed")

    # API Methods with enhanced error handling
    
    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user information with validation."""
        try:
            result = await self._make_request('GET', 'myself')
            
            # Validate required fields
            required_fields = ['accountId', 'displayName']
            for field in required_fields:
                if field not in result:
                    self.logger.warning(f"Missing field '{field}' in user response")
            
            return result
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get current user: {e}")

    async def get_projects(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """Get accessible projects with enhanced filtering."""
        try:
            max_results = max(1, min(max_results, 100))  # Clamp between 1-100
            
            params = {
                'maxResults': max_results,
                'expand': 'description,lead,issueTypes,url,projectKeys'
            }
            
            result = await self._make_request('GET', 'project', params=params)
            
            if not isinstance(result, list):
                self.logger.warning("Expected list of projects, got different format")
                return []
            
            # Filter and validate projects
            valid_projects = []
            for project in result:
                if isinstance(project, dict) and 'key' in project and 'name' in project:
                    valid_projects.append(project)
                else:
                    self.logger.warning(f"Invalid project data: {project}")
            
            self.logger.info(f"📁 Retrieved {len(valid_projects)} valid projects")
            return valid_projects
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get projects: {e}")

    async def get_project(self, project_key: str) -> Dict[str, Any]:
        """Get specific project details."""
        if not project_key or not isinstance(project_key, str):
            raise ValueError("project_key must be a non-empty string")
        
        try:
            project_key = project_key.strip().upper()
            endpoint = f'project/{quote(project_key)}'
            
            params = {
                'expand': 'description,lead,issueTypes,url,projectKeys,roles'
            }
            
            result = await self._make_request('GET', endpoint, params=params)
            
            # Validate project data
            required_fields = ['key', 'name', 'id']
            for field in required_fields:
                if field not in result:
                    raise JiraAPIError(f"Missing required field '{field}' in project response")
            
            return result
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get project {project_key}: {e}")

    async def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search for issues using JQL with enhanced validation."""
        if not jql or not isinstance(jql, str):
            raise ValueError("jql must be a non-empty string")
        
        try:
            # Clamp parameters
            max_results = max(1, min(max_results, 100))
            start_at = max(0, start_at)
            
            # Default fields if not specified
            if fields is None:
                fields = [
                    'summary', 'description', 'status', 'priority', 'issuetype',
                    'assignee', 'reporter', 'created', 'updated', 'resolution',
                    'labels', 'components', 'fixVersions', 'parent'
                ]
            
            data = {
                'jql': jql.strip(),
                'maxResults': max_results,
                'startAt': start_at,
                'fields': fields,
                'expand': ['changelog']
            }
            
            result = await self._make_request('POST', 'search', data=data)
            
            # Validate search result structure
            if not isinstance(result, dict):
                raise JiraAPIError("Invalid search result format")
            
            if 'issues' not in result:
                raise JiraAPIError("Missing 'issues' field in search result")
            
            # Log search statistics
            total = result.get('total', 0)
            returned = len(result.get('issues', []))
            self.logger.info(f"🔍 JQL search returned {returned}/{total} issues")
            
            return result
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Issue search failed: {e}")

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description: str = "",
        priority: str = "Medium",
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new issue with comprehensive validation."""
        # Input validation
        if not all([project_key, summary, issue_type]):
            raise ValueError("project_key, summary, and issue_type are required")
        
        if len(summary.strip()) < 5:
            raise ValueError("Summary must be at least 5 characters long")
        
        if len(summary) > 255:
            raise ValueError("Summary must be 255 characters or less")
        
        try:
            # Prepare issue data
            issue_data = {
                'fields': {
                    'project': {'key': project_key.strip().upper()},
                    'summary': summary.strip(),
                    'description': description.strip() if description else "",
                    'issuetype': {'name': issue_type.strip()},
                    'priority': {'name': priority.strip()}
                }
            }
            
            # Add optional fields
            if assignee:
                issue_data['fields']['assignee'] = {'accountId': assignee}
            
            if labels:
                issue_data['fields']['labels'] = [label.strip() for label in labels if label.strip()]
            
            if components:
                issue_data['fields']['components'] = [
                    {'name': comp.strip()} for comp in components if comp.strip()
                ]
            
            result = await self._make_request('POST', 'issue', data=issue_data)
            
            # Validate creation result
            if not isinstance(result, dict) or 'key' not in result:
                raise JiraAPIError("Invalid issue creation response")
            
            self.logger.info(f"✅ Issue created: {result.get('key')}")
            return result
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to create issue: {e}")

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Get specific issue details."""
        if not issue_key or not isinstance(issue_key, str):
            raise ValueError("issue_key must be a non-empty string")
        
        try:
            issue_key = issue_key.strip().upper()
            endpoint = f'issue/{quote(issue_key)}'
            
            params = {
                'expand': 'changelog,transitions,operations,versionedRepresentations'
            }
            
            result = await self._make_request('GET', endpoint, params=params)
            
            # Validate issue data
            if not isinstance(result, dict) or 'key' not in result:
                raise JiraAPIError(f"Invalid issue data for {issue_key}")
            
            return result
            
        except JiraAPIError:
            raise
        except Exception as e:
            raise JiraAPIError(f"Failed to get issue {issue_key}: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        start_time = time.time()
        
        try:
            # Test basic connectivity
            user_info = await self.get_current_user()
            
            # Test project access
            projects = await self.get_projects(max_results=1)
            
            response_time = time.time() - start_time
            
            return {
                'status': 'healthy',
                'response_time_ms': round(response_time * 1000, 2),
                'user': user_info.get('displayName', 'Unknown'),
                'domain': self.domain,
                'projects_accessible': len(projects),
                'statistics': {
                    'total_requests': self._request_count,
                    'total_errors': self._error_count,
                    'error_rate': round(self._error_count / max(self._request_count, 1) * 100, 2),
                    'last_request': self._last_request_time
                }
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time_ms': round(response_time * 1000, 2),
                'domain': self.domain,
                'statistics': {
                    'total_requests': self._request_count,
                    'total_errors': self._error_count
                }
            }

    async def close(self) -> None:
        """Close HTTP session and cleanup resources."""
        try:
            async with self._session_lock:
                if self._session and not self._session.closed:
                    await self._session.close()
                    self._session = None
            
            self.logger.info("✅ Jira service connections closed")
            
        except Exception as e:
            self.logger.error(f"❌ Error closing Jira service: {e}")

    def __del__(self):
        """Cleanup on deletion."""
        if self._session and not self._session.closed:
            self.logger.warning("⚠️ Jira service not properly closed, session may leak")