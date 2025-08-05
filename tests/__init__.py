#!/usr/bin/env python3
"""
Test package for the Telegram-Jira Bot.

This package contains comprehensive unit tests, integration tests, and utilities
for testing all components of the Telegram-Jira bot including models, services,
handlers, and configuration.

Test Structure:
- test_models.py: Tests for data models (Project, Issue, User, Enums)
- test_services.py: Tests for services (Database, Jira, Telegram)
- test_handlers.py: Tests for command handlers and user interactions
- conftest.py: Pytest configuration, fixtures, and test utilities

Usage:
    Run all tests:
    $ pytest

    Run specific test file:
    $ pytest tests/test_models.py

    Run with coverage:
    $ pytest --cov=telegram_jira_bot

    Run only unit tests:
    $ pytest -m unit

    Run only integration tests:
    $ pytest -m integration
"""

import sys
import warnings
from pathlib import Path

# Add the parent directory to Python path for imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Version info for the test suite
__version__ = "2.1.0"
__author__ = "AI Assistant"
__description__ = "Test suite for Telegram-Jira Bot"

# Test configuration
TEST_CONFIG = {
    "timeout": 30,
    "database_url": ":memory:",
    "mock_external_services": True,
    "log_level": "DEBUG"
}

# Common test constants
TEST_USER_ID = "123456789"
TEST_PROJECT_KEY = "TEST"
TEST_ISSUE_KEY = "TEST-1"
TEST_JIRA_DOMAIN = "test.atlassian.net"
TEST_TELEGRAM_TOKEN = "TEST_TOKEN:123456789"

# Export commonly used test utilities
__all__ = [
    "TEST_CONFIG",
    "TEST_USER_ID", 
    "TEST_PROJECT_KEY",
    "TEST_ISSUE_KEY",
    "TEST_JIRA_DOMAIN",
    "TEST_TELEGRAM_TOKEN"
]

try:
    from .conftest import (
        TestDatabase,
        TestUtils,
        AsyncContextManagerMock
    )
    __all__.extend([
        "TestDatabase",
        "TestUtils", 
        "AsyncContextManagerMock"
    ])
except ImportError as e:
    warnings.warn(f"Test utilities import failed: {e}", ImportWarning)