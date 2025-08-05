"""
Telegram Service for bot message handling.

This service provides a clean interface for Telegram Bot API operations,
handling message sending, editing, and bot health checks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from telegram import Bot, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.error import TelegramError

from .models import SentMessages

logger = logging.getLogger(__name__)


class TelegramAPIError(Exception):
    """Exception raised for Telegram API errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        """Initialize Telegram API error.
        
        Args:
            message: Error message
            original_error: Original telegram error that caused this error
        """
        super().__init__(message)
        self.original_error = original_error


class TelegramService:
    """
    Service for interacting with Telegram Bot API.
    
    Provides methods for sending and editing messages with proper error handling
    and type safety. All methods return structured data about sent messages.
    """

    def __init__(self, bot_token: str) -> None:
        """
        Initialize Telegram service.
        
        Args:
            bot_token: Telegram bot token
            
        Raises:
            TypeError: If bot_token is not string
            ValueError: If bot_token is empty
        """
        if not isinstance(bot_token, str):
            raise TypeError(f"bot_token must be string, got {type(bot_token)}")
        if not bot_token:
            raise ValueError("bot_token cannot be empty")

        self.bot_token = bot_token
        self._bot: Optional[Bot] = None
        self._closed = False

    def _get_bot(self) -> Bot:
        """Get or create Bot instance."""
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        *,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message_id: Optional[int] = None,
        disable_notification: bool = False,
        disable_web_page_preview: bool = True,
    ) -> SentMessages:
        """
        Send a message to a chat.
        
        Args:
            chat_id: Unique identifier for the target chat or username
            text: Text of the message to be sent
            parse_mode: Parse mode for formatting ('Markdown', 'HTML', or None)
            reply_markup: Inline keyboard markup
            reply_to_message_id: ID of message to reply to
            disable_notification: Send message silently
            disable_web_page_preview: Disable link previews
            
        Returns:
            SentMessages containing message IDs
            
        Raises:
            TypeError: If parameters have incorrect types
            TelegramAPIError: If message sending fails
        """
        # Parameter validation
        if not isinstance(chat_id, (int, str)):
            raise TypeError(f"chat_id must be int or str, got {type(chat_id)}")
        if not isinstance(text, str) or not text:
            raise TypeError("text must be non-empty string")
        if parse_mode is not None and not isinstance(parse_mode, str):
            raise TypeError("parse_mode must be string or None")
        if reply_markup is not None and not isinstance(reply_markup, InlineKeyboardMarkup):
            raise TypeError("reply_markup must be InlineKeyboardMarkup or None")
        if reply_to_message_id is not None and not isinstance(reply_to_message_id, int):
            raise TypeError("reply_to_message_id must be int or None")
        if not isinstance(disable_notification, bool):
            raise TypeError("disable_notification must be boolean")
        if not isinstance(disable_web_page_preview, bool):
            raise TypeError("disable_web_page_preview must be boolean")

        # Convert parse_mode string to ParseMode enum
        telegram_parse_mode = None
        if parse_mode:
            if parse_mode.lower() == "markdown":
                telegram_parse_mode = ParseMode.MARKDOWN_V2
            elif parse_mode.lower() == "html":
                telegram_parse_mode = ParseMode.HTML
            else:
                logger.warning(f"Unknown parse_mode '{parse_mode}', using None")

        try:
            bot = self._get_bot()
            
            # Handle long messages by splitting if necessary
            messages = await self._split_and_send_message(
                bot=bot,
                chat_id=chat_id,
                text=text,
                parse_mode=telegram_parse_mode,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                disable_notification=disable_notification,
                disable_web_page_preview=disable_web_page_preview,
            )
            
            message_ids = [msg.message_id for msg in messages]
            
            return SentMessages(
                message_ids=message_ids,
                first_message_id=message_ids[0] if message_ids else None
            )
            
        except TelegramError as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            raise TelegramAPIError(f"Failed to send message: {e}", e)
        except Exception as e:
            logger.error(f"Unexpected error sending message to {chat_id}: {e}")
            raise TelegramAPIError(f"Unexpected error sending message: {e}", e)

    async def _split_and_send_message(
        self,
        bot: Bot,
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[ParseMode],
        reply_markup: Optional[InlineKeyboardMarkup],
        reply_to_message_id: Optional[int],
        disable_notification: bool,
        disable_web_page_preview: bool,
    ) -> List[Message]:
        """
        Split long message and send multiple messages if needed.
        
        Telegram has a 4096 character limit per message.
        """
        MAX_MESSAGE_LENGTH = 4000  # Leave some buffer for formatting
        
        if len(text) <= MAX_MESSAGE_LENGTH:
            # Single message
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                disable_notification=disable_notification,
                disable_web_page_preview=disable_web_page_preview,
            )
            return [message]
        
        # Split message into chunks
        messages = []
        chunks = self._split_text(text, MAX_MESSAGE_LENGTH)
        
        for i, chunk in enumerate(chunks):
            # Only apply reply_markup to the last message
            current_reply_markup = reply_markup if i == len(chunks) - 1 else None
            # Only reply to original message for the first chunk
            current_reply_to_message_id = reply_to_message_id if i == 0 else None
            
            message = await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
                reply_markup=current_reply_markup,
                reply_to_message_id=current_reply_to_message_id,
                disable_notification=disable_notification,
                disable_web_page_preview=disable_web_page_preview,
            )
            messages.append(message)
        
        return messages

    def _split_text(self, text: str, max_length: int) -> List[str]:
        """
        Split text into chunks while preserving formatting.
        
        Args:
            text: Text to split
            max_length: Maximum length per chunk
            
        Returns:
            List of text chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by lines first to preserve formatting
        lines = text.split('\n')
        
        for line in lines:
            # If single line is too long, we need to split it further
            if len(line) > max_length:
                # If we have content in current_chunk, save it
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                    current_chunk = ""
                
                # Split the long line by words
                words = line.split(' ')
                temp_line = ""
                
                for word in words:
                    if len(temp_line + word + " ") <= max_length:
                        temp_line += word + " "
                    else:
                        if temp_line:
                            chunks.append(temp_line.rstrip())
                        temp_line = word + " "
                
                if temp_line:
                    current_chunk = temp_line.rstrip()
            else:
                # Check if adding this line would exceed limit
                test_chunk = current_chunk + ('\n' if current_chunk else '') + line
                
                if len(test_chunk) <= max_length:
                    current_chunk = test_chunk
                else:
                    # Save current chunk and start new one
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line
        
        # Add remaining content
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    async def edit_message(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        *,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """
        Edit a message.
        
        Args:
            chat_id: Unique identifier for the target chat
            message_id: ID of the message to edit
            text: New text of the message
            parse_mode: Parse mode for formatting ('Markdown', 'HTML', or None)
            reply_markup: Inline keyboard markup
            
        Raises:
            TypeError: If parameters have incorrect types
            TelegramAPIError: If message editing fails
        """
        # Parameter validation
        if not isinstance(chat_id, (int, str)):
            raise TypeError(f"chat_id must be int or str, got {type(chat_id)}")
        if not isinstance(message_id, int):
            raise TypeError(f"message_id must be int, got {type(message_id)}")
        if not isinstance(text, str) or not text:
            raise TypeError("text must be non-empty string")
        if parse_mode is not None and not isinstance(parse_mode, str):
            raise TypeError("parse_mode must be string or None")
        if reply_markup is not None and not isinstance(reply_markup, InlineKeyboardMarkup):
            raise TypeError("reply_markup must be InlineKeyboardMarkup or None")

        # Convert parse_mode string to ParseMode enum
        telegram_parse_mode = None
        if parse_mode:
            if parse_mode.lower() == "markdown":
                telegram_parse_mode = ParseMode.MARKDOWN_V2
            elif parse_mode.lower() == "html":
                telegram_parse_mode = ParseMode.HTML
            else:
                logger.warning(f"Unknown parse_mode '{parse_mode}', using None")

        try:
            bot = self._get_bot()
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=telegram_parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            
        except TelegramError as e:
            logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")
            raise TelegramAPIError(f"Failed to edit message: {e}", e)
        except Exception as e:
            logger.error(f"Unexpected error editing message {message_id} in chat {chat_id}: {e}")
            raise TelegramAPIError(f"Unexpected error editing message: {e}", e)

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Telegram service health and connectivity.
        
        Returns:
            Dict containing health status and bot info
            
        Raises:
            TelegramAPIError: If health check fails
        """
        try:
            bot = self._get_bot()
            bot_info = await bot.get_me()
            
            return {
                'status': 'healthy',
                'bot_id': bot_info.id,
                'bot_username': bot_info.username,
                'bot_first_name': bot_info.first_name,
                'can_join_groups': bot_info.can_join_groups,
                'can_read_all_group_messages': bot_info.can_read_all_group_messages,
                'supports_inline_queries': bot_info.supports_inline_queries,
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
            }

    async def close(self) -> None:
        """Close bot session and cleanup resources."""
        if self._bot:
            # Note: python-telegram-bot doesn't require explicit closing
            # but we mark as closed for consistency
            self._bot = None
        self._closed = True

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if not self._closed:
            logger.warning("TelegramService was not properly closed. Call close() explicitly.")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Utility functions for message formatting

def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2 format.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text safe for MarkdownV2
    """
    if not isinstance(text, str):
        return str(text)
    
    # Characters that need to be escaped in MarkdownV2
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def format_code_block(code: str, language: str = "") -> str:
    """
    Format code block for Telegram.
    
    Args:
        code: Code to format
        language: Programming language for syntax highlighting
        
    Returns:
        Formatted code block
    """
    if not isinstance(code, str):
        code = str(code)
    
    # Escape backticks in code
    code = code.replace('`', '\\`')
    
    if language:
        return f"```{language}\n{code}\n```"
    else:
        return f"```\n{code}\n```"


def format_inline_code(code: str) -> str:
    """
    Format inline code for Telegram.
    
    Args:
        code: Code to format
        
    Returns:
        Formatted inline code
    """
    if not isinstance(code, str):
        code = str(code)
    
    # Escape backticks in code
    code = code.replace('`', '\\`')
    
    return f"`{code}`"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if not isinstance(text, str):
        text = str(text)
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix