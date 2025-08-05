# =============================================================================
# telegram_jira_bot/config/__init__.py
# =============================================================================
#!/usr/bin/env python3
"""
Configuration package for the Telegram-Jira bot.

Contains configuration management, validation, and environment handling.
"""

from typing import Optional, Dict, Any

try:
    from .settings import (
        load_config_from_env,
        load_config,
        validate_config,
        get_config_warnings
    )
    
    __all__ = [
        "BotConfig",
        "load_config", 
        "validate_config",
        "get_config_warnings",
        "load_config_from_env",
        "DEFAULT_CONFIG",
        "get_default_config"
        
    ]
    
except ImportError as e:
    import warnings
    warnings.warn(f"Configuration imports failed: {e}", ImportWarning)
    __all__ = []

# Configuration defaults
DEFAULT_CONFIG: Dict[str, Any] = {
    "database_path": "bot_data.db",
    "log_level": "INFO",
    "log_file": "telegram_jira_bot.log",
    "max_summary_length": 100,
    "rate_limit_per_minute": 30,
    "enable_wizards": True,
    "enable_shortcuts": True,
    "compact_messages": False,
    "use_emoji": True
}

def get_default_config() -> Dict[str, Any]:
    """Get default configuration values.
    
    Returns:
        Dictionary of default configuration values
    """
    return DEFAULT_CONFIG.copy()
