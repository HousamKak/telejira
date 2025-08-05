#!/usr/bin/env python3
"""
Wizard handlers for the Telegram-Jira bot.

Handles interactive wizard functionality for guided setup and operations.
"""

from typing import Optional, List, Dict, Any, Union

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .base_handler import BaseHandler
from ..models.project import Project
from ..models.user import User, UserPreferences, UserSession
from ..models.enums import IssuePriority, IssueType, WizardState, UserRole, ErrorType
from ..services.database import DatabaseError
from ..services.jira_service import JiraAPIError
from ..utils.constants import EMOJI, WIZARD_FLOWS
from ..utils.validators import ValidationResult


class WizardHandler(BaseHandler):
    """Handles interactive wizard functionality."""

    def get_handler_name(self) -> str:
        """Get handler name."""
        return "WizardHandler"

    async def handle_error(self, update: Update, error: Exception, context: str = "") -> None:
        """Handle errors specific to wizard operations."""
        if isinstance(error, DatabaseError):
            await self.handle_database_error(update, error, context)
        elif isinstance(error, JiraAPIError):
            await self.handle_jira_error(update, error, context)
        else:
            await self.send_error_message(update, f"Unexpected error: {str(error)}")

    # Command handlers
    async def wizard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /wizard command - start setup wizard."""
        self.log_handler_start(update, "wizard_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Show wizard welcome screen
            await self._show_wizard_welcome(update, user)
            self.log_handler_end(update, "wizard_command")

        except Exception as e:
            await self.handle_error(update, e, "wizard_command")
            self.log_handler_end(update, "wizard_command", success=False)

    async def quick_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /quick command - quick setup wizard."""
        self.log_handler_start(update, "quick_command")
        
        user = await self.enforce_user_access(update)
        if not user:
            return

        try:
            # Start quick setup wizard
            await self._start_quick_setup(update, user)
            self.log_handler_end(update, "quick_command")

        except Exception as e:
            await self.handle_error(update, e, "quick_command")
            self.log_handler_end(update, "quick_command", success=False)

    # Message handlers for wizard state
    async def handle_wizard_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle messages when user is in wizard state."""
        if not update.effective_user or not update.message:
            return

        user = await self.get_or_create_user(update)
        if not user:
            return

        session = await self.get_user_session(user.user_id)
        if not session or not session.is_in_wizard():
            return

        message_text = update.message.text.strip()

        try:
            # Route to appropriate wizard handler based on state
            if session.wizard_state == WizardState.PROJECT_ENTERING_KEY:
                await self._handle_project_key_input(update, user, session, message_text)
            elif session.wizard_state == WizardState.PROJECT_ENTERING_NAME:
                await self._handle_project_name_input(update, user, session, message_text)
            elif session.wizard_state == WizardState.PROJECT_ENTERING_DESCRIPTION:
                await self._handle_project_description_input(update, user, session, message_text)
            elif session.wizard_state == WizardState.ISSUE_ENTERING_SUMMARY:
                await self._handle_issue_summary_input(update, user, session, message_text)
            elif session.wizard_state == WizardState.ISSUE_ENTERING_DESCRIPTION:
                await self._handle_issue_description_input(update, user, session, message_text)
            else:
                # Unknown state, reset wizard
                await self._reset_wizard(update, user, session)

        except Exception as e:
            await self.handle_error(update, e, "handle_wizard_message")
            await self._reset_wizard(update, user, session)

    # Callback handlers
    async def handle_wizard_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle wizard-related callbacks."""
        callback_data = self.extract_callback_data(update)
        if not callback_data:
            return

        parts = self.parse_callback_data(callback_data)
        if len(parts) < 2:
            return

        action = parts[1]  # wizard_<action>

        user = await self.get_or_create_user(update)
        if not user:
            return

        try:
            if action == "start":
                await self._show_wizard_welcome(update, user)
            elif action == "project":
                await self._start_project_wizard(update, user, parts[2:])
            elif action == "issue":
                await self._start_issue_wizard(update, user, parts[2:])
            elif action == "preferences":
                await self._start_preferences_wizard(update, user, parts[2:])
            elif action == "quick":
                await self._start_quick_setup(update, user)
            elif action == "cancel":
                await self._cancel_wizard(update, user)
            elif action == "back":
                await self._wizard_go_back(update, user, parts[2:])
            elif action == "next":
                await self._wizard_go_next(update, user, parts[2:])
            elif action.startswith("select_"):
                await self._handle_wizard_selection(update, user, action, parts[2:])

        except Exception as e:
            await self.handle_error(update, e, "handle_wizard_callback")

    # Private wizard flow methods
    async def _show_wizard_welcome(self, update: Update, user: User) -> None:
        """Show wizard welcome screen."""
        text = self.telegram.formatter.format_wizard_welcome()

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['PROJECT']} Project Setup",
                    callback_data="wizard_project_start"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['ISSUE']} Create Issue",
                    callback_data="wizard_issue_start"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['SETTINGS']} Preferences",
                    callback_data="wizard_preferences_start"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['MAGIC']} Quick Setup",
                    callback_data="wizard_quick"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Exit Wizard",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await self.edit_message(update, text, reply_markup)
        else:
            await self.send_message(update, text, reply_markup)

    async def _start_project_wizard(self, update: Update, user: User, action_parts: List[str]) -> None:
        """Start project setup wizard."""
        if not self.is_admin(user):
            await self.send_error_message(
                update,
                "Only administrators can create projects.",
                ErrorType.PERMISSION_ERROR
            )
            return

        # Initialize wizard session
        session = UserSession(user_id=user.user_id)
        session.start_wizard(WizardState.PROJECT_SELECTING_ACTION)
        await self.save_user_session(session)

        text = f"{EMOJI['WIZARD']} **Project Setup Wizard**\n\n"
        text += "**Step 1 of 5**\n\n"
        text += "What would you like to do with projects?\n\n"
        text += f"{EMOJI['CREATE']} **Add New Project** - Create a new project\n"
        text += f"{EMOJI['EDIT']} **Edit Project** - Modify existing project\n"
        text += f"{EMOJI['SYNC']} **Sync Projects** - Sync with Jira"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['CREATE']} Add New Project",
                    callback_data="wizard_project_add"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['EDIT']} Edit Project",
                    callback_data="wizard_project_edit"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['SYNC']} Sync Projects",
                    callback_data="wizard_project_sync"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_start"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.edit_message(update, text, reply_markup)

    async def _start_issue_wizard(self, update: Update, user: User, action_parts: List[str]) -> None:
        """Start issue creation wizard."""
        # Initialize wizard session
        session = UserSession(user_id=user.user_id)
        session.start_wizard(WizardState.ISSUE_SELECTING_PROJECT)
        await self.save_user_session(session)

        # Get available projects
        try:
            projects = await self.db.get_projects(active_only=True)
            if not projects:
                await self.send_info_message(
                    update,
                    f"{EMOJI['INFO']} No projects available. Ask an admin to add projects first."
                )
                await self._reset_wizard(update, user, session)
                return

            text = f"{EMOJI['WIZARD']} **Issue Creation Wizard**\n\n"
            text += "**Step 1 of 6**\n\n"
            text += "Select the project for your new issue:"

            # Store projects in session for reference
            session.update_wizard_data('projects', [p.to_dict() for p in projects])
            await self.save_user_session(session)

            keyboard = self.telegram.create_project_selection_keyboard(
                projects,
                callback_prefix="wizard_select_project",
                show_cancel=True
            )

            await self.edit_message(update, text, keyboard)

        except DatabaseError as e:
            await self.handle_database_error(update, e, "start_issue_wizard")
            await self._reset_wizard(update, user, session)

    async def _start_preferences_wizard(self, update: Update, user: User, action_parts: List[str]) -> None:
        """Start preferences setup wizard."""
        # Get current preferences
        preferences = await self.get_user_preferences(user.user_id)

        text = f"{EMOJI['WIZARD']} **Preferences Setup Wizard**\n\n"
        text += "Let's configure your bot preferences.\n\n"

        if preferences:
            text += "**Current Settings:**\n"
            text += f"└ Default Project: {preferences.default_project_key or 'None'}\n"
            text += f"└ Default Priority: {preferences.default_priority.get_emoji()} {preferences.default_priority.value}\n"
            text += f"└ Default Type: {preferences.default_issue_type.get_emoji()} {preferences.default_issue_type.value}\n\n"

        text += "What would you like to configure?"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['PROJECT']} Default Project",
                    callback_data="wizard_preferences_project"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['PRIORITY_MEDIUM']} Default Priority",
                    callback_data="wizard_preferences_priority"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['TASK']} Default Type",
                    callback_data="wizard_preferences_type"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['SETTINGS']} All Settings",
                    callback_data="wizard_preferences_all"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_start"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.edit_message(update, text, reply_markup)

    async def _start_quick_setup(self, update: Update, user: User) -> None:
        """Start quick setup wizard."""
        # Initialize wizard session
        session = UserSession(user_id=user.user_id)
        session.start_wizard(WizardState.ISSUE_SELECTING_PROJECT)
        session.update_wizard_data('quick_setup', True)
        await self.save_user_session(session)

        text = f"{EMOJI['MAGIC']} **Quick Setup**\n\n"
        text += "Let's get you started quickly!\n\n"
        text += "First, I'll help you set a default project so you can create issues easily.\n\n"

        # Check if user already has a default project
        preferences = await self.get_user_preferences(user.user_id)
        if preferences and preferences.default_project_key:
            text += f"**Current Default:** {preferences.default_project_key}\n\n"
            text += "Would you like to change it or keep the current one?"

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{EMOJI['SUCCESS']} Keep Current",
                        callback_data="wizard_quick_keep_default"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{EMOJI['EDIT']} Change Default",
                        callback_data="wizard_quick_change_default"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{EMOJI['CANCEL']} Cancel",
                        callback_data="wizard_cancel"
                    )
                ]
            ]
        else:
            text += "Let's choose your default project:"

            try:
                projects = await self.db.get_projects(active_only=True)
                if not projects:
                    text = f"{EMOJI['INFO']} No projects available yet.\n\n"
                    text += "Ask an administrator to add projects first, then run `/wizard` again."
                    await self.edit_message(update, text)
                    await self._reset_wizard(update, user, session)
                    return

                session.update_wizard_data('projects', [p.to_dict() for p in projects])
                await self.save_user_session(session)

                keyboard = self.telegram.create_project_selection_keyboard(
                    projects,
                    callback_prefix="wizard_quick_select_project",
                    show_cancel=True
                )

            except DatabaseError as e:
                await self.handle_database_error(update, e, "start_quick_setup")
                await self._reset_wizard(update, user, session)
                return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.edit_message(update, text, reply_markup)

    # Input handling methods
    async def _handle_project_key_input(
        self,
        update: Update,
        user: User,
        session: UserSession,
        message_text: str
    ) -> None:
        """Handle project key input."""
        project_key = message_text.upper().strip()

        # Validate project key
        validation = self.validate_project_key(project_key)
        if not validation.is_valid:
            await self.handle_validation_error(update, validation, "project key")
            await self._show_project_key_prompt(update, session, validation.errors)
            return

        # Check if project already exists
        existing_project = await self.db.get_project_by_key(project_key)
        if existing_project:
            await self.send_error_message(
                update,
                f"Project `{project_key}` already exists.",
                ErrorType.VALIDATION_ERROR
            )
            await self._show_project_key_prompt(update, session)
            return

        # Store project key and move to next step
        session.update_wizard_data('project_key', project_key)
        session.wizard_state = WizardState.PROJECT_ENTERING_NAME
        await self.save_user_session(session)

        await self._show_project_name_prompt(update, session)

    async def _handle_project_name_input(
        self,
        update: Update,
        user: User,
        session: UserSession,
        message_text: str
    ) -> None:
        """Handle project name input."""
        project_name = message_text.strip()

        # Validate project name
        validation = self.validate_project_name(project_name)
        if not validation.is_valid:
            await self.handle_validation_error(update, validation, "project name")
            await self._show_project_name_prompt(update, session, validation.errors)
            return

        # Store project name and move to next step
        session.update_wizard_data('project_name', project_name)
        session.wizard_state = WizardState.PROJECT_ENTERING_DESCRIPTION
        await self.save_user_session(session)

        await self._show_project_description_prompt(update, session)

    async def _handle_project_description_input(
        self,
        update: Update,
        user: User,
        session: UserSession,
        message_text: str
    ) -> None:
        """Handle project description input."""
        project_description = message_text.strip()

        # Validate description
        validation = self.validate_project_description(project_description)
        if not validation.is_valid:
            await self.handle_validation_error(update, validation, "project description")
            await self._show_project_description_prompt(update, session, validation.errors)
            return

        # Store description and move to confirmation
        session.update_wizard_data('project_description', project_description)
        session.wizard_state = WizardState.PROJECT_CONFIRMING
        await self.save_user_session(session)

        await self._show_project_confirmation(update, session)

    async def _handle_issue_summary_input(
        self,
        update: Update,
        user: User,
        session: UserSession,
        message_text: str
    ) -> None:
        """Handle issue summary input."""
        summary = message_text.strip()

        # Validate summary
        validation = self.validate_issue_summary(summary)
        if not validation.is_valid:
            await self.handle_validation_error(update, validation, "issue summary")
            await self._show_issue_summary_prompt(update, session, validation.errors)
            return

        # Store summary and move to description
        session.update_wizard_data('issue_summary', summary)
        session.wizard_state = WizardState.ISSUE_ENTERING_DESCRIPTION
        await self.save_user_session(session)

        await self._show_issue_description_prompt(update, session)

    async def _handle_issue_description_input(
        self,
        update: Update,
        user: User,
        session: UserSession,
        message_text: str
    ) -> None:
        """Handle issue description input."""
        description = message_text.strip()

        # Validate description
        validation = self.validate_issue_description(description)
        if not validation.is_valid:
            await self.handle_validation_error(update, validation, "issue description")
            await self._show_issue_description_prompt(update, session, validation.errors)
            return

        # Store description and move to confirmation
        session.update_wizard_data('issue_description', description)
        session.wizard_state = WizardState.ISSUE_CONFIRMING
        await self.save_user_session(session)

        await self._show_issue_confirmation(update, session)

    # Prompt display methods
    async def _show_project_key_prompt(
        self,
        update: Update,
        session: UserSession,
        errors: Optional[List[str]] = None
    ) -> None:
        """Show project key input prompt."""
        text = self.telegram.formatter.format_wizard_step(
            step_title="Enter Project Key",
            step_description="Please enter a unique project key (2-10 uppercase characters):",
            step_number=2,
            total_steps=5,
            current_data=session.wizard_data
        )

        if errors:
            text += f"\n{EMOJI['ERROR']} **Errors:**\n"
            text += "\n".join([f"• {error}" for error in errors])
            text += "\n"

        text += f"\n**Examples:** WEBAPP, API, MOBILE\n"
        text += f"**Note:** Project key must match your Jira project key."

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _show_project_name_prompt(
        self,
        update: Update,
        session: UserSession,
        errors: Optional[List[str]] = None
    ) -> None:
        """Show project name input prompt."""
        text = self.telegram.formatter.format_wizard_step(
            step_title="Enter Project Name",
            step_description="Please enter a descriptive name for your project:",
            step_number=3,
            total_steps=5,
            current_data=session.wizard_data
        )

        if errors:
            text += f"\n{EMOJI['ERROR']} **Errors:**\n"
            text += "\n".join([f"• {error}" for error in errors])
            text += "\n"

        text += f"\n**Examples:** Web Application, REST API, Mobile App"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_back_project_key"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _show_project_description_prompt(
        self,
        update: Update,
        session: UserSession,
        errors: Optional[List[str]] = None
    ) -> None:
        """Show project description input prompt."""
        text = self.telegram.formatter.format_wizard_step(
            step_title="Enter Project Description",
            step_description="Please enter a description for your project (optional - send 'skip' to skip):",
            step_number=4,
            total_steps=5,
            current_data=session.wizard_data
        )

        if errors:
            text += f"\n{EMOJI['ERROR']} **Errors:**\n"
            text += "\n".join([f"• {error}" for error in errors])
            text += "\n"

        text += f"\n**Example:** Main web application for customer portal"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['SKIP']} Skip Description",
                    callback_data="wizard_skip_description"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_back_project_name"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _show_project_confirmation(self, update: Update, session: UserSession) -> None:
        """Show project creation confirmation."""
        project_key = session.get_wizard_data('project_key')
        project_name = session.get_wizard_data('project_name')
        project_description = session.get_wizard_data('project_description', '')

        text = f"{EMOJI['WIZARD']} **Project Creation Confirmation**\n\n"
        text += "**Step 5 of 5**\n\n"
        text += "Please review your project details:\n\n"
        text += f"**Key:** `{project_key}`\n"
        text += f"**Name:** {project_name}\n"
        text += f"**Description:** {project_description or 'None'}\n\n"
        text += f"{EMOJI['INFO']} The project will be verified with Jira before creation."

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['SUCCESS']} Create Project",
                    callback_data="wizard_project_create_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_back_project_description"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _show_issue_summary_prompt(
        self,
        update: Update,
        session: UserSession,
        errors: Optional[List[str]] = None
    ) -> None:
        """Show issue summary input prompt."""
        current_data = session.wizard_data.copy()
        project_key = current_data.get('selected_project_key', 'Unknown')

        text = self.telegram.formatter.format_wizard_step(
            step_title="Enter Issue Summary",
            step_description=f"Please enter a brief summary for your issue in project `{project_key}`:",
            step_number=4,
            total_steps=6,
            current_data=current_data
        )

        if errors:
            text += f"\n{EMOJI['ERROR']} **Errors:**\n"
            text += "\n".join([f"• {error}" for error in errors])
            text += "\n"

        text += f"\n**Examples:**\n"
        text += f"• Login button not responding\n"
        text += f"• Add export functionality\n"
        text += f"• Fix mobile layout issues"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_back_issue_priority"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _show_issue_description_prompt(
        self,
        update: Update,
        session: UserSession,
        errors: Optional[List[str]] = None
    ) -> None:
        """Show issue description input prompt."""
        text = self.telegram.formatter.format_wizard_step(
            step_title="Enter Issue Description",
            step_description="Please provide a detailed description (optional - send 'skip' to skip):",
            step_number=5,
            total_steps=6,
            current_data=session.wizard_data
        )

        if errors:
            text += f"\n{EMOJI['ERROR']} **Errors:**\n"
            text += "\n".join([f"• {error}" for error in errors])
            text += "\n"

        text += f"\n**Tips:**\n"
        text += f"• Include steps to reproduce\n"
        text += f"• Mention expected vs actual behavior\n"
        text += f"• Add any relevant details"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['SKIP']} Skip Description",
                    callback_data="wizard_skip_issue_description"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_back_issue_summary"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    async def _show_issue_confirmation(self, update: Update, session: UserSession) -> None:
        """Show issue creation confirmation."""
        project_key = session.get_wizard_data('selected_project_key')
        issue_type = session.get_wizard_data('selected_issue_type', 'Task')
        priority = session.get_wizard_data('selected_priority', 'Medium')
        summary = session.get_wizard_data('issue_summary')
        description = session.get_wizard_data('issue_description', '')

        text = f"{EMOJI['WIZARD']} **Issue Creation Confirmation**\n\n"
        text += "**Step 6 of 6**\n\n"
        text += "Please review your issue details:\n\n"
        text += f"**Project:** `{project_key}`\n"
        text += f"**Type:** {IssueType.from_string(issue_type).get_emoji()} {issue_type}\n"
        text += f"**Priority:** {IssuePriority.from_string(priority).get_emoji()} {priority}\n"
        text += f"**Summary:** {summary}\n"
        
        if description:
            desc_preview = description[:100] + "..." if len(description) > 100 else description
            text += f"**Description:** {desc_preview}\n"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{EMOJI['SUCCESS']} Create Issue",
                    callback_data="wizard_issue_create_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{EMOJI['BACK']} Back",
                    callback_data="wizard_back_issue_description"
                ),
                InlineKeyboardButton(
                    f"{EMOJI['CANCEL']} Cancel",
                    callback_data="wizard_cancel"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(update, text, reply_markup)

    # Selection handling
    async def _handle_wizard_selection(
        self,
        update: Update,
        user: User,
        action: str,
        action_parts: List[str]
    ) -> None:
        """Handle wizard selections."""
        session = await self.get_user_session(user.user_id)
        if not session or not session.is_in_wizard():
            return

        if action == "select_project" and action_parts:
            project_key = action_parts[0]
            await self._handle_project_selection(update, user, session, project_key)
        elif action == "select_priority" and action_parts:
            priority = action_parts[0]
            await self._handle_priority_selection(update, user, session, priority)
        elif action == "select_type" and action_parts:
            issue_type = action_parts[0]
            await self._handle_type_selection(update, user, session, issue_type)

    async def _handle_project_selection(
        self,
        update: Update,
        user: User,
        session: UserSession,
        project_key: str
    ) -> None:
        """Handle project selection in wizard."""
        session.update_wizard_data('selected_project_key', project_key)
        
        if session.get_wizard_data('quick_setup'):
            # Quick setup flow - set as default and finish
            await self._complete_quick_setup(update, user, session, project_key)
        else:
            # Regular issue creation flow - move to type selection
            session.wizard_state = WizardState.ISSUE_SELECTING_TYPE
            await self.save_user_session(session)
            await self._show_issue_type_selection(update, session)

    async def _handle_priority_selection(
        self,
        update: Update,
        user: User,
        session: UserSession,
        priority: str
    ) -> None:
        """Handle priority selection in wizard."""
        session.update_wizard_data('selected_priority', priority)
        session.wizard_state = WizardState.ISSUE_ENTERING_SUMMARY
        await self.save_user_session(session)
        
        await self._show_issue_summary_prompt(update, session)

    async def _handle_type_selection(
        self,
        update: Update,
        user: User,
        session: UserSession,
        issue_type: str
    ) -> None:
        """Handle issue type selection in wizard."""
        session.update_wizard_data('selected_issue_type', issue_type)
        session.wizard_state = WizardState.ISSUE_SELECTING_PRIORITY
        await self.save_user_session(session)
        
        await self._show_issue_priority_selection(update, session)

    async def _show_issue_type_selection(self, update: Update, session: UserSession) -> None:
        """Show issue type selection."""
        project_key = session.get_wizard_data('selected_project_key')
        
        text = f"{EMOJI['WIZARD']} **Issue Creation Wizard**\n\n"
        text += "**Step 2 of 6**\n\n"
        text += f"**Project:** `{project_key}`\n\n"
        text += "Select the type of issue you want to create:"

        keyboard = self.telegram.create_issue_type_selection_keyboard(
            callback_prefix="wizard_select_type"
        )

        await self.edit_message(update, text, keyboard)

    async def _show_issue_priority_selection(self, update: Update, session: UserSession) -> None:
        """Show issue priority selection."""
        project_key = session.get_wizard_data('selected_project_key')
        issue_type = session.get_wizard_data('selected_issue_type')
        
        text = f"{EMOJI['WIZARD']} **Issue Creation Wizard**\n\n"
        text += "**Step 3 of 6**\n\n"
        text += f"**Project:** `{project_key}`\n"
        text += f"**Type:** {IssueType.from_string(issue_type).get_emoji()} {issue_type}\n\n"
        text += "Select the priority level:"

        keyboard = self.telegram.create_priority_selection_keyboard(
            callback_prefix="wizard_select_priority"
        )

        await self.edit_message(update, text, keyboard)

    # Wizard completion methods
    async def _complete_quick_setup(
        self,
        update: Update,
        user: User,
        session: UserSession,
        project_key: str
    ) -> None:
        """Complete quick setup by setting default project."""
        try:
            # Verify project exists
            project = await self.db.get_project_by_key(project_key)
            if not project:
                await self.send_error_message(update, f"Project `{project_key}` not found.")
                await self._reset_wizard(update, user, session)
                return

            # Get or create user preferences
            preferences = await self.get_user_preferences(user.user_id)
            if not preferences:
                preferences = UserPreferences(user_id=user.user_id)

            # Set default project
            preferences.default_project_key = project_key
            await self.db.save_user_preferences(preferences)

            # Complete wizard
            session.clear_wizard()
            await self.save_user_session(session)

            text = f"{EMOJI['SUCCESS']} **Quick Setup Complete!**\n\n"
            text += f"**Default Project Set:** `{project.key}` - {project.name}\n\n"
            text += "🎉 You're all set! Now you can:\n\n"
            text += f"• Send any message to create an issue\n"
            text += f"• Use `/create` for guided issue creation\n"
            text += f"• Use `/myissues` to see your issues\n"
            text += f"• Use `/help` for more commands\n\n"
            text += "Try sending a message now to create your first issue!"

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{EMOJI['ISSUE']} Create Issue",
                        callback_data="issue_create_start"
                    ),
                    InlineKeyboardButton(
                        f"{EMOJI['HELP']} Help",
                        callback_data="help_show"
                    )
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await self.edit_message(update, text, reply_markup)

            self.log_user_action(
                user,
                "complete_quick_setup",
                {"default_project": project_key}
            )

        except DatabaseError as e:
            await self.handle_database_error(update, e, "complete_quick_setup")
            await self._reset_wizard(update, user, session)

    # Utility methods
    async def _cancel_wizard(self, update: Update, user: User) -> None:
        """Cancel the current wizard."""
        session = await self.get_user_session(user.user_id)
        if session:
            session.clear_wizard()
            await self.save_user_session(session)

        text = f"{EMOJI['CANCEL']} Wizard cancelled.\n\n"
        text += "You can start the wizard again anytime with `/wizard`."

        await self.edit_message(update, text)

    async def _reset_wizard(self, update: Update, user: User, session: UserSession) -> None:
        """Reset wizard state due to error."""
        session.clear_wizard()
        await self.save_user_session(session)

        text = f"{EMOJI['ERROR']} Wizard reset due to an error.\n\n"
        text += "Please try starting the wizard again with `/wizard`."

        await self.send_message(update, text)

    async def _wizard_go_back(self, update: Update, user: User, action_parts: List[str]) -> None:
        """Handle wizard back navigation."""
        session = await self.get_user_session(user.user_id)
        if not session or not session.is_in_wizard():
            return

        # Implement back navigation based on current state
        # This is a simplified version - full implementation would handle all states
        if session.wizard_state == WizardState.PROJECT_ENTERING_NAME:
            session.wizard_state = WizardState.PROJECT_ENTERING_KEY
            await self.save_user_session(session)
            await self._show_project_key_prompt(update, session)
        elif session.wizard_state == WizardState.PROJECT_ENTERING_DESCRIPTION:
            session.wizard_state = WizardState.PROJECT_ENTERING_NAME
            await self.save_user_session(session)
            await self._show_project_name_prompt(update, session)
        # Add more back navigation cases as needed

    async def _wizard_go_next(self, update: Update, user: User, action_parts: List[str]) -> None:
        """Handle wizard next navigation."""
        # This would handle explicit next button presses
        # Most navigation happens through selections and input handling
        pass