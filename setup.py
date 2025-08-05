#!/usr/bin/env python3
"""
Setup script for Telegram-Jira Bot.

A comprehensive Telegram bot for seamless Jira integration.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

from setuptools import setup, find_packages


def read_file(filepath: str) -> str:
    """Read file contents safely."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""


def get_version() -> str:
    """Get version from the constants file."""
    version_file = Path(__file__).parent / "telegram_jira_bot" / "utils" / "constants.py"
    if version_file.exists():
        content = read_file(str(version_file))
        for line in content.split('\n'):
            if "'VERSION':" in line and "BOT_INFO" in content:
                # Extract version from BOT_INFO dict
                version = line.split("'")[3]  # Get the version string
                return version
    return "2.1.0"  # Fallback version


def get_requirements() -> List[str]:
    """Get requirements from requirements.txt."""
    requirements_file = Path(__file__).parent / "requirements.txt"
    if requirements_file.exists():
        with open(requirements_file, 'r', encoding='utf-8') as f:
            return [
                line.strip() 
                for line in f 
                if line.strip() and not line.startswith('#')
            ]
    
    # Fallback requirements based on the project structure
    return [
        "python-telegram-bot>=20.0,<21.0",
        "aiohttp>=3.8.0,<4.0.0",
        "aiosqlite>=0.17.0,<1.0.0",
        "python-dotenv>=0.19.0,<2.0.0",
        "pydantic>=1.10.0,<3.0.0",
        "httpx>=0.24.0,<1.0.0",
        "pytz>=2023.3",
        "typing-extensions>=4.5.0",
    ]


def get_dev_requirements() -> List[str]:
    """Get development requirements."""
    dev_requirements_file = Path(__file__).parent / "requirements-dev.txt"
    if dev_requirements_file.exists():
        with open(dev_requirements_file, 'r', encoding='utf-8') as f:
            return [
                line.strip() 
                for line in f 
                if line.strip() and not line.startswith('#')
            ]
    
    # Fallback dev requirements
    return [
        "pytest>=7.0.0,<8.0.0",
        "pytest-asyncio>=0.21.0,<1.0.0",
        "pytest-cov>=4.0.0,<5.0.0",
        "pytest-mock>=3.10.0,<4.0.0",
        "black>=23.0.0,<24.0.0",
        "flake8>=6.0.0,<7.0.0",
        "mypy>=1.0.0,<2.0.0",
        "isort>=5.12.0,<6.0.0",
        "pre-commit>=3.3.0,<4.0.0",
        "coverage>=7.2.0,<8.0.0",
    ]


def validate_python_version() -> None:
    """Validate Python version compatibility."""
    if sys.version_info < (3, 9):
        raise RuntimeError(
            "This package requires Python 3.9 or higher. "
            f"You are using Python {sys.version_info.major}.{sys.version_info.minor}."
        )


def get_long_description() -> str:
    """Get long description from README."""
    readme_file = Path(__file__).parent / "README.md"
    return read_file(str(readme_file))


def get_project_urls() -> Dict[str, str]:
    """Get project URLs for metadata."""
    return {
        "Homepage": "https://github.com/yourusername/telegram-jira-bot",
        "Bug Reports": "https://github.com/yourusername/telegram-jira-bot/issues",
        "Source": "https://github.com/yourusername/telegram-jira-bot",
        "Documentation": "https://github.com/yourusername/telegram-jira-bot/wiki",
        "Release Notes": "https://github.com/yourusername/telegram-jira-bot/releases",
    }


def get_classifiers() -> List[str]:
    """Get package classifiers."""
    return [
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Communications :: Chat",
        "Topic :: Office/Business :: Groupware",
        "Topic :: Software Development :: Bug Tracking",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3 :: Only",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Framework :: AsyncIO",
        "Natural Language :: English",
        "Typing :: Typed",
    ]


def get_keywords() -> List[str]:
    """Get package keywords."""
    return [
        "telegram", "bot", "jira", "atlassian", "issue-tracking",
        "project-management", "automation", "productivity", "team-collaboration",
        "api", "webhook", "async", "sqlite", "chat-bot"
    ]


def get_entry_points() -> Dict[str, List[str]]:
    """Get entry points for console scripts."""
    return {
        "console_scripts": [
            "telegram-jira-bot=telegram_jira_bot.main:main",
            "tg-jira=telegram_jira_bot.main:main",
        ],
    }


# Validate Python version before proceeding
validate_python_version()

# Setup configuration
setup_config: Dict[str, Any] = {
    "name": "telegram-jira-bot",
    "version": get_version(),
    "author": "AI Assistant",
    "author_email": "ai-assistant@example.com",
    "description": "A comprehensive Telegram bot for seamless Jira integration",
    "long_description": get_long_description(),
    "long_description_content_type": "text/markdown",
    "url": "https://github.com/yourusername/telegram-jira-bot",
    "project_urls": get_project_urls(),
    "packages": find_packages(exclude=['tests*', 'docs*', 'examples*']),
    "classifiers": get_classifiers(),
    "keywords": " ".join(get_keywords()),
    "license": "MIT",
    "python_requires": ">=3.9",
    "install_requires": get_requirements(),
    "extras_require": {
        "dev": get_dev_requirements(),
        "testing": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
        ],
        "linting": [
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "isort>=5.12.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
            "myst-parser>=1.0.0",
        ],
    },
    "entry_points": get_entry_points(),
    "include_package_data": True,
    "package_data": {
        "telegram_jira_bot": [
            "py.typed",
            "*.sql",
            "*.json",
            "config/*.json",
            "config/*.yaml",
            "config/*.yml",
        ],
    },
    "zip_safe": False,
    "platforms": ["any"],
    "maintainer": "AI Assistant",
    "maintainer_email": "ai-assistant@example.com",
}

# Additional metadata for better package discovery
setup_config.update({
    "download_url": f"https://github.com/yourusername/telegram-jira-bot/archive/v{get_version()}.tar.gz",
    "bugtrack_url": "https://github.com/yourusername/telegram-jira-bot/issues",
    "home_page": "https://github.com/yourusername/telegram-jira-bot",
})

if __name__ == "__main__":
    try:
        setup(**setup_config)
        print(f"✅ Setup completed successfully for telegram-jira-bot v{get_version()}")
    except Exception as e:
        print(f"❌ Setup failed: {e}", file=sys.stderr)
        sys.exit(1)