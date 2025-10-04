#!/usr/bin/env python3
"""
Keyboard utilities for the Telegram-Jira bot.

Contains functions for creating inline keyboards for various bot interactions.
"""

from typing import List, Dict, Any, Optional, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models import IssuePriority, IssueType,Project
from .constants import EMOJI


def cb(scope: str, action: str = "", payload: str = "") -> str:
    """Create callback data string.

    Args:
        scope: Scope/prefix identifier (or full action for backwards compatibility)
        action: Action identifier (optional)
        payload: Additional data (optional)

    Returns:
        Formatted callback data string in format "scope:action:payload" or "scope_action"
    """
    # New format: scope:action:payload
    if action:
        if payload:
            return f"{scope}:{action}:{payload}"
        return f"{scope}:{action}"

    # Legacy format: just scope (backwards compatibility)
    return scope


def parse_cb(callback_data: str) -> Tuple[str, str, str]:
    """Parse callback data string.

    Args:
        callback_data: Callback data to parse in format "scope:action:payload" or "scope_action"

    Returns:
        Tuple of (scope, action, payload)
    """
    # Handle colon-separated format (new wizard format)
    if ':' in callback_data:
        parts = callback_data.split(":", 2)
        scope = parts[0] if len(parts) > 0 else ""
        action = parts[1] if len(parts) > 1 else ""
        payload = parts[2] if len(parts) > 2 else ""
        return scope, action, payload

    # Handle underscore-separated format (legacy format)
    parts = callback_data.split("_", 1)
    scope = parts[0]
    action = parts[1] if len(parts) > 1 else ""
    payload = ""
    return scope, action, payload


def build_project_list_keyboard(
    projects: List[Project], 
    action_prefix: str = "select_project",
    max_per_row: int = 2
) -> InlineKeyboardMarkup:
    """Build keyboard for project selection.
    
    Args:
        projects: List of projects
        action_prefix: Prefix for callback actions
        max_per_row: Maximum buttons per row
        
    Returns:
        InlineKeyboardMarkup for project selection
    """
    keyboard = []
    row = []
    
    for project in projects:
        button_text = f"{project.name} ({project.key})"
        callback_data = cb(action_prefix, project.key)
        button = InlineKeyboardButton(button_text, callback_data=callback_data)
        
        row.append(button)
        if len(row) >= max_per_row:
            keyboard.append(row)
            row = []
    
    # Add remaining buttons
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


def build_issue_type_keyboard(
    issue_types: List[IssueType] = None,
    action_prefix: str = "select_type",
    max_per_row: int = 2
) -> InlineKeyboardMarkup:
    """Build keyboard for issue type selection.

    Args:
        issue_types: List of issue types to include (default: all)
        action_prefix: Prefix for callback actions
        max_per_row: Maximum buttons per row

    Returns:
        InlineKeyboardMarkup for issue type selection
    """
    if issue_types is None:
        issue_types = list(IssueType)

    keyboard = []
    row = []

    for issue_type in issue_types:
        emoji = issue_type.get_emoji() if hasattr(issue_type, 'get_emoji') else ""
        button_text = f"{emoji} {issue_type.value}".strip()
        callback_data = cb(action_prefix, issue_type.name.lower())
        button = InlineKeyboardButton(button_text, callback_data=callback_data)
        
        row.append(button)
        if len(row) >= max_per_row:
            keyboard.append(row)
            row = []
    
    # Add remaining buttons
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


def build_issue_priority_keyboard(
    priorities: List[IssuePriority] = None,
    action_prefix: str = "select_priority",
    max_per_row: int = 2
) -> InlineKeyboardMarkup:
    """Build keyboard for issue priority selection.

    Args:
        priorities: List of priorities to include (default: all)
        action_prefix: Prefix for callback actions
        max_per_row: Maximum buttons per row

    Returns:
        InlineKeyboardMarkup for priority selection
    """
    if priorities is None:
        priorities = list(IssuePriority)

    keyboard = []
    row = []

    for priority in priorities:
        emoji = priority.get_emoji() if hasattr(priority, 'get_emoji') else ""
        button_text = f"{emoji} {priority.value}".strip()
        callback_data = cb(action_prefix, priority.name.lower())
        button = InlineKeyboardButton(button_text, callback_data=callback_data)
        
        row.append(button)
        if len(row) >= max_per_row:
            keyboard.append(row)
            row = []
    
    # Add remaining buttons
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


def build_confirm_keyboard(
    confirm_action: str = "confirm",
    cancel_action: str = "cancel",
    confirm_text: str = "✅ Confirm",
    cancel_text: str = "❌ Cancel"
) -> InlineKeyboardMarkup:
    """Build keyboard for confirmation dialogs.
    
    Args:
        confirm_action: Callback action for confirm button
        cancel_action: Callback action for cancel button
        confirm_text: Text for confirm button
        cancel_text: Text for cancel button
        
    Returns:
        InlineKeyboardMarkup for confirmation
    """
    keyboard = [
        [
            InlineKeyboardButton(confirm_text, callback_data=confirm_action),
            InlineKeyboardButton(cancel_text, callback_data=cancel_action)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_cancel_keyboard(
    back_action: str = "back",
    cancel_action: str = "cancel",
    back_text: str = "⬅️ Back", 
    cancel_text: str = "❌ Cancel"
) -> InlineKeyboardMarkup:
    """Build keyboard with back and cancel options.
    
    Args:
        back_action: Callback action for back button
        cancel_action: Callback action for cancel button
        back_text: Text for back button
        cancel_text: Text for cancel button
        
    Returns:
        InlineKeyboardMarkup with back and cancel buttons
    """
    keyboard = [
        [
            InlineKeyboardButton(back_text, callback_data=back_action),
            InlineKeyboardButton(cancel_text, callback_data=cancel_action)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_pagination_keyboard(
    current_page: int,
    total_pages: int,
    action_prefix: str = "page",
    max_buttons: int = 5
) -> InlineKeyboardMarkup:
    """Build keyboard for pagination.
    
    Args:
        current_page: Current page number (0-based)
        total_pages: Total number of pages
        action_prefix: Prefix for callback actions
        max_buttons: Maximum number of page buttons to show
        
    Returns:
        InlineKeyboardMarkup for pagination
    """
    if total_pages <= 1:
        return InlineKeyboardMarkup([])
    
    keyboard = []
    row = []
    
    # Calculate page range to display
    start_page = max(0, current_page - max_buttons // 2)
    end_page = min(total_pages, start_page + max_buttons)
    
    # Adjust start if we're near the end
    if end_page - start_page < max_buttons:
        start_page = max(0, end_page - max_buttons)
    
    # Previous button
    if current_page > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=cb(action_prefix, str(current_page - 1))))
    
    # Page number buttons
    for page in range(start_page, end_page):
        text = f"[{page + 1}]" if page == current_page else str(page + 1)
        row.append(InlineKeyboardButton(text, callback_data=cb(action_prefix, str(page))))
    
    # Next button
    if current_page < total_pages - 1:
        row.append(InlineKeyboardButton("➡️", callback_data=cb(action_prefix, str(current_page + 1))))
    
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


def build_menu_keyboard(
    options: Dict[str, str],
    columns: int = 2,
    add_back: bool = False,
    add_cancel: bool = False
) -> InlineKeyboardMarkup:
    """Build a generic menu keyboard.
    
    Args:
        options: Dict of {button_text: callback_data}
        columns: Number of columns for buttons
        add_back: Whether to add a back button
        add_cancel: Whether to add a cancel button
        
    Returns:
        InlineKeyboardMarkup for menu
    """
    keyboard = []
    row = []
    
    for text, callback_data in options.items():
        button = InlineKeyboardButton(text, callback_data=callback_data)
        row.append(button)
        
        if len(row) >= columns:
            keyboard.append(row)
            row = []
    
    # Add remaining buttons
    if row:
        keyboard.append(row)
    
    # Add back/cancel row if requested
    if add_back or add_cancel:
        control_row = []
        if add_back:
            control_row.append(InlineKeyboardButton("⬅️ Back", callback_data="back"))
        if add_cancel:
            control_row.append(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
        keyboard.append(control_row)
    
    return InlineKeyboardMarkup(keyboard)


def build_wizard_navigation_keyboard(
    show_back: bool = True,
    show_cancel: bool = True,
    show_skip: bool = False,
    back_data: str = "wizard_back",
    cancel_data: str = "wizard_cancel",
    skip_data: str = "wizard_skip"
) -> InlineKeyboardMarkup:
    """Build navigation keyboard for wizard flows.
    
    Args:
        show_back: Whether to show back button
        show_cancel: Whether to show cancel button
        show_skip: Whether to show skip button
        back_data: Callback data for back button
        cancel_data: Callback data for cancel button
        skip_data: Callback data for skip button
        
    Returns:
        InlineKeyboardMarkup for wizard navigation
    """
    keyboard = []
    row = []
    
    if show_back:
        row.append(InlineKeyboardButton("⬅️ Back", callback_data=back_data))
    
    if show_skip:
        row.append(InlineKeyboardButton("⏭️ Skip", callback_data=skip_data))
    
    if show_cancel:
        row.append(InlineKeyboardButton("❌ Cancel", callback_data=cancel_data))
    
    if row:
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


def build_wizard_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build main menu keyboard for wizard entry point.
    
    Returns:
        InlineKeyboardMarkup for wizard main menu
    """
    keyboard = [
        [
            InlineKeyboardButton("⚡ Quick Issue", callback_data="wizard_quick_issue"),
            InlineKeyboardButton("🔧 Setup", callback_data="wizard_setup")
        ],
        [
            InlineKeyboardButton("📋 My Issues", callback_data="wizard_my_issues"),
            InlineKeyboardButton("📁 Projects", callback_data="wizard_projects")
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="wizard_cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)