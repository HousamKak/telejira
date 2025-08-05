# =============================================================================
# telegram_jira_bot/config/__init__.py
# =============================================================================
#!/usr/bin/env python3
"""
Configuration package for the Telegram-Jira bot.

Contains configuration management, validation, and environment handling.
"""

from typing import Optional, Dict, Any, List

from .settings import (
    BotConfig,
    load_config_from_env,
    validate_config,
    setup_logging
)

__all__ = [
    "BotConfig",
    "load_config_from_env",
    "validate_config", 
    "setup_logging",
    "DEFAULT_CONFIG",
    "get_default_config",
    "load_config",
    "get_config_warnings"
]

# Configuration defaults
DEFAULT_CONFIG: Dict[str, Any] = {
    "database_path": "bot_data.db",
    "log_level": "INFO",
    "log_file": "telegram_jira_bot.log", 
    "max_summary_length": 100,
    "rate_limit_per_minute": 30,
    "enable_wizards": True,
    "enable_shortcuts": True,
    "compact_mode": False,
    "use_emoji": True
}

def get_default_config() -> Dict[str, Any]:
    """Get default configuration values.
    
    Returns:
        Dictionary of default configuration values
    """
    return DEFAULT_CONFIG.copy()

def load_config(env_file: Optional[str] = None) -> BotConfig:
    """Load configuration from environment variables (alias for load_config_from_env).
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        Loaded and validated bot configuration
    """
    return load_config_from_env(env_file)

def get_config_warnings(config: BotConfig) -> List[str]:
    """Get configuration warnings (alias for validate_config).
    
    Args:
        config: Configuration to validate
        
    Returns:
        List of warning messages
    """
    return validate_config(config)