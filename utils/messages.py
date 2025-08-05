#!/usr/bin/env python3
"""
Message templates for the Telegram-Jira bot wizard flows.

Centralizes all message formatting with consistent HTML styling and proper escaping.
"""

from typing import Optional
from models.project import Project
from models.user import User
from models.issue import JiraIssue
from utils.formatters import truncate_text


def html_escape(text: str) -> str:
    """Escape text for safe HTML rendering in Telegram."""
    if not text:
        return ""
    
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))


def setup_welcome_message(user: User, default_project: Optional[Project] = None) -> str:
    """Generate setup welcome message."""
    project_info = f"<b>{html_escape(default_project.name)}</b> ({default_project.key})" if default_project else "Not set"
    
    return f"""
🧙‍♂️ <b>Welcome to the Wizard, {html_escape(user.username)}!</b>

<b>Your Configuration:</b>
• Default Project: {project_info}
• Role: {html_escape(user.role.value.replace('_', ' ').title())}

<b>What would you like to do?</b>

⚡ <b>Quick Issue</b> - Create an issue fast
🔧 <b>Setup</b> - Configure your default project

Choose an option below to get started!
    """.strip()


def confirm_project_message(project: Project) -> str:
    """Generate project confirmation message."""
    return f"""
📁 <b>Confirm Project Selection</b>

<b>Project:</b> {html_escape(project.name)}
<b>Key:</b> <code>{project.key}</code>
<b>Type:</b> {html_escape(project.project_type or 'Unknown')}

{html_escape(truncate_text(project.description or 'No description available', 150))}

Would you like to set this as your default project?
    """.strip()


def quick_issue_summary_message(project_name: str, issue_type: str, priority: str, 
                               summary: str, description: str = "") -> str:
    """Generate issue summary confirmation message."""
    desc_preview = ""
    if description:
        desc_preview = f"\n<b>Description:</b>\n<i>{html_escape(truncate_text(description, 200))}</i>"
    
    return f"""
📋 <b>Issue Summary</b>

<b>Project:</b> {html_escape(project_name)}
<b>Type:</b> {html_escape(issue_type)}
<b>Priority:</b> {html_escape(priority)}
<b>Summary:</b> {html_escape(summary)}{desc_preview}

Ready to create this issue?
    """.strip()


def no_projects_message() -> str:
    """Generate no projects available message."""
    return """
❌ <b>No Projects Available</b>

You don't have access to any projects yet. Please contact your administrator to:

• Add you to existing projects
• Create new projects for your team
• Grant you the necessary permissions

<i>Need help? Use /help to see all available commands.</i>
    """.strip()


def issue_created_success_message(issue: JiraIssue) -> str:
    """Generate issue creation success message."""
    return f"""
✅ <b>Issue Created Successfully!</b>

<b>Issue:</b> <a href="{issue.url}">{issue.key}</a>
<b>Summary:</b> {html_escape(issue.summary)}
<b>Project:</b> {html_escape(issue.project_name)} ({issue.project_key})
<b>Type:</b> {html_escape(issue.issue_type.value)}
<b>Priority:</b> {html_escape(issue.priority.value)}
<b>Status:</b> {html_escape(issue.status)}

🚀 <b>What's next?</b>
• Use <code>/view {issue.key}</code> to see full details
• Use <code>/edit {issue.key}</code> to modify the issue
• Use <code>/comment {issue.key}</code> to add comments

Great job! 🎉
    """.strip()


def project_selection_message(wizard_type: str, project_count: int) -> str:
    """Generate project selection message."""
    return f"""
📁 <b>Select Project</b>

Choose a project for your {wizard_type}:

<i>Showing {project_count} available projects</i>
    """.strip()


def issue_type_selection_message(project_name: str) -> str:
    """Generate issue type selection message."""
    return f"""
🎯 <b>Issue Type</b>

Project: <b>{html_escape(project_name)}</b>

Select the type of issue you want to create:
    """.strip()


def issue_priority_selection_message(project_name: str, issue_type: str) -> str:
    """Generate issue priority selection message."""
    return f"""
⚡ <b>Priority Level</b>

Project: <b>{html_escape(project_name)}</b>
Type: <b>{html_escape(issue_type)}</b>

Select the priority level for this issue:
    """.strip()


def summary_input_message(project_name: str, issue_type: str, priority: str) -> str:
    """Generate summary input request message."""
    return f"""
📝 <b>Issue Summary</b>

Project: <b>{html_escape(project_name)}</b>
Type: <b>{html_escape(issue_type)}</b>
Priority: <b>{html_escape(priority)}</b>

Please enter a brief, descriptive summary for your issue:

<i>Examples:</i>
• "Login button not working on mobile devices"
• "Add user profile picture upload feature"
• "Database connection timeout errors"

<b>Tip:</b> Keep it concise but descriptive!
    """.strip()


def description_input_message(summary: str) -> str:
    """Generate description input request message."""
    return f"""
📄 <b>Issue Description</b>

Summary: <i>{html_escape(truncate_text(summary, 80))}</i>

Please provide a detailed description of the issue:

<i>Consider including:</i>
• Steps to reproduce (for bugs)
• Expected vs actual behavior
• Screenshots or error messages
• Acceptance criteria (for features)

You can also send <b>/skip</b> to create the issue without a description.
    """.strip()


def validation_error_message(field: str, error: str) -> str:
    """Generate validation error message."""
    return f"""
❌ <b>Invalid {field.title()}</b>

{html_escape(error)}

Please try again with a valid {field.lower()}.
    """.strip()


def wizard_error_message(error_type: str, details: str = "") -> str:
    """Generate wizard error message."""
    base_message = f"❌ <b>Wizard Error</b>\n\n"
    
    if error_type == "database":
        base_message += "Database operation failed. Please try again later."
    elif error_type == "jira":
        base_message += "Jira API error. Please check your permissions and try again."
    elif error_type == "validation":
        base_message += f"Invalid input: {html_escape(details)}"
    elif error_type == "permission":
        base_message += "You don't have permission to perform this action."
    else:
        base_message += "An unexpected error occurred. Please try again."
    
    base_message += "\n\n<i>If the problem persists, contact your administrator.</i>"
    
    return base_message


def setup_complete_message(project_name: str, project_key: str) -> str:
    """Generate setup completion message."""
    return f"""
✅ <b>Setup Complete!</b>

<b>{html_escape(project_name)}</b> is now your default project.

🚀 <b>Ready to go! Try these:</b>
• Use <code>/quick</code> for fast issue creation
• Type: <code>HIGH BUG Something is broken</code>
• Use <code>/help</code> to see all commands

<b>Need help?</b> Use <code>/help</code> anytime!
    """.strip()


def wizard_cancelled_message() -> str:
    """Generate wizard cancelled message."""
    return """
❌ <b>Wizard Cancelled</b>

No worries! You can start again anytime.

<b>Quick commands:</b>
• <code>/wizard</code> - Start the wizard again
• <code>/quick</code> - Quick issue creation
• <code>/help</code> - See all commands

See you soon! 👋
    """.strip()


def loading_message(action: str) -> str:
    """Generate loading message."""
    return f"⏳ <b>{action}...</b>\n\nPlease wait a moment."


def pagination_info(current_page: int, total_pages: int, total_items: int) -> str:
    """Generate pagination information."""
    return f"<i>Page {current_page + 1} of {total_pages} ({total_items} total)</i>"


def back_navigation_message(current_step: str, previous_step: str) -> str:
    """Generate back navigation helper message."""
    return f"""
🔙 <b>Going Back</b>

From: {current_step}
To: {previous_step}

Your progress has been saved.
    """.strip()