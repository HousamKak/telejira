#!/usr/bin/env python3
"""
Telegram service for the Telegram-Jira bot.

Handles Telegram-specific operations, message formatting, and bot interactions.
"""

import logging
import re
import time
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timezone

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError, BadRequest, NetworkError, TimedOut, RetryAfter
from telegram.constants import ParseMode, MessageLimit

from ..models.project import Project
from ..models.issue import JiraIssue
from ..models.user import User
from ..models.enums import IssuePriority, IssueType, IssueStatus


class TelegramServiceError(Exception):
    """Custom exception for Telegram service operations."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class TelegramService:
    """Enhanced Telegram service with comprehensive fixes."""

    def __init__(
        self,
        token: str,
        timeout: int = 30,
        use_inline_keyboards: bool = True,
        compact_mode: bool = False,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> None:
        """Initialize Telegram service with enhanced configuration."""
        if not token or not isinstance(token, str):
            raise ValueError("Bot token must be a non-empty string")
        
        self.token = token
        self.timeout = max(5, min(timeout, 120))  # Clamp between 5-120 seconds
        self.use_inline_keyboards = use_inline_keyboards
        self.compact_mode = compact_mode
        self.max_retries = max(1, min(max_retries, 5))
        self.retry_delay = max(0.1, min(retry_delay, 5.0))
        
        # Initialize bot instance
        try:
            self.bot = Bot(token=token, request=None)
        except Exception as e:
            raise TelegramServiceError(f"Failed to initialize bot: {e}", e)
        
        # Statistics and monitoring
        self._message_count = 0
        self._error_count = 0
        self._last_message_time: Optional[float] = None
        
        # Rate limiting for outgoing messages
        self._message_timestamps: List[float] = []
        self._rate_limit_lock = asyncio.Lock()
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("🤖 Telegram service initialized successfully")

    async def _check_message_rate_limit(self) -> None:
        """Implement client-side rate limiting for message sending."""
        async with self._rate_limit_lock:
            now = time.time()
            
            # Remove timestamps older than 1 minute
            self._message_timestamps = [
                ts for ts in self._message_timestamps 
                if now - ts < 60
            ]
            
            # Telegram allows 30 messages per second to different chats
            if len(self._message_timestamps) >= 30:
                # Wait for the oldest message to be outside the 1-second window
                oldest_timestamp = min(self._message_timestamps)
                wait_time = 1.0 - (now - oldest_timestamp)
                
                if wait_time > 0:
                    self.logger.debug(f"⏱️ Rate limiting: waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
            
            # Add current message timestamp
            self._message_timestamps.append(now)

    def _split_message(self, text: str, max_length: int = MessageLimit.MAX_TEXT_LENGTH) -> List[str]:
        """Split message intelligently while preserving formatting and structure."""
        if not text:
            return [""]
        
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Try to split by double newlines (paragraphs) first
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # Check if adding this paragraph would exceed the limit
            test_chunk = current_chunk + ('\n\n' if current_chunk else '') + paragraph
            
            if len(test_chunk) <= max_length:
                current_chunk = test_chunk
            else:
                # Save current chunk if it has content
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # Handle large paragraphs
                if len(paragraph) > max_length:
                    # Split by single newlines
                    lines = paragraph.split('\n')
                    temp_chunk = ""
                    
                    for line in lines:
                        test_line_chunk = temp_chunk + ('\n' if temp_chunk else '') + line
                        
                        if len(test_line_chunk) <= max_length:
                            temp_chunk = test_line_chunk
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                            
                            # Handle very long lines
                            if len(line) > max_length:
                                # Split by sentences
                                sentences = re.split(r'(?<=[.!?])\s+', line)
                                sentence_chunk = ""
                                
                                for sentence in sentences:
                                    test_sentence_chunk = sentence_chunk + (' ' if sentence_chunk else '') + sentence
                                    
                                    if len(test_sentence_chunk) <= max_length:
                                        sentence_chunk = test_sentence_chunk
                                    else:
                                        if sentence_chunk:
                                            chunks.append(sentence_chunk.strip())
                                        
                                        # Handle extremely long sentences
                                        if len(sentence) > max_length:
                                            # Split by words as last resort
                                            words = sentence.split()
                                            word_chunk = ""
                                            
                                            for word in words:
                                                test_word_chunk = word_chunk + (' ' if word_chunk else '') + word
                                                
                                                if len(test_word_chunk) <= max_length:
                                                    word_chunk = test_word_chunk
                                                else:
                                                    if word_chunk:
                                                        chunks.append(word_chunk.strip())
                                                    
                                                    # If single word is too long, truncate it
                                                    if len(word) > max_length:
                                                        chunks.append(word[:max_length-3] + "...")
                                                        word_chunk = ""
                                                    else:
                                                        word_chunk = word
                                            
                                            if word_chunk:
                                                sentence_chunk = word_chunk
                                        else:
                                            sentence_chunk = sentence
                                
                                if sentence_chunk:
                                    temp_chunk = sentence_chunk
                            else:
                                temp_chunk = line
                    
                    if temp_chunk:
                        current_chunk = temp_chunk
                else:
                    current_chunk = paragraph
        
        # Add any remaining content
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Ensure we don't have empty chunks
        chunks = [chunk for chunk in chunks if chunk.strip()]
        
        # If no chunks were created, return the original text truncated
        if not chunks:
            chunks = [text[:max_length-3] + "..."]
        
        return chunks

    def _escape_markdown_v2(self, text: str) -> str:
        """Escape special characters for MarkdownV2 parse mode."""
        if not text:
            return ""
        
        # Characters that need escaping in MarkdownV2
        special_chars = [
            '_', '*', '[', ']', '(', ')', '~', '`', 
            '>', '#', '+', '-', '=', '|', '{', '}', 
            '.', '!', '\\'
        ]
        
        escaped_text = text
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        
        return escaped_text

    def _validate_parse_mode(self, parse_mode: Optional[str]) -> Optional[str]:
        """Validate and normalize parse mode."""
        if parse_mode is None:
            return None
        
        valid_modes = {
            'markdown': ParseMode.MARKDOWN,
            'markdownv2': ParseMode.MARKDOWN_V2,
            'html': ParseMode.HTML
        }
        
        normalized = parse_mode.lower().replace('_', '').replace('-', '')
        
        if normalized in valid_modes:
            return valid_modes[normalized]
        else:
            self.logger.warning(f"Invalid parse_mode '{parse_mode}', using None")
            return None

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[str] = ParseMode.MARKDOWN_V2,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message_id: Optional[int] = None,
        disable_notification: bool = False,
        disable_web_page_preview: bool = True
    ) -> List[int]:
        """Send message with automatic chunking and comprehensive error handling."""
        if not text or not text.strip():
            raise ValueError("Message text cannot be empty")
        
        # Validate and normalize parse mode
        parse_mode = self._validate_parse_mode(parse_mode)
        
        # Apply rate limiting
        await self._check_message_rate_limit()
        
        # Escape text if using MarkdownV2
        if parse_mode == ParseMode.MARKDOWN_V2:
            text = self._escape_markdown_v2(text)
        
        # Split message if too long
        message_chunks = self._split_message(text.strip())
        sent_message_ids = []
        
        for i, chunk in enumerate(message_chunks):
            retry_count = 0
            last_error = None
            
            while retry_count <= self.max_retries:
                try:
                    # Only add reply markup and reply_to for the first message
                    current_markup = reply_markup if i == 0 else None
                    current_reply_to = reply_to_message_id if i == 0 else None
                    
                    # Send the message
                    message = await self.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=parse_mode,
                        reply_markup=current_markup,
                        reply_to_message_id=current_reply_to,
                        disable_notification=disable_notification,
                        disable_web_page_preview=disable_web_page_preview
                    )
                    
                    sent_message_ids.append(message.message_id)
                    self._message_count += 1
                    self._last_message_time = time.time()
                    
                    # Add small delay between chunks to avoid rate limiting
                    if i < len(message_chunks) - 1:
                        await asyncio.sleep(0.1)
                    
                    break  # Success, exit retry loop
                    
                except RetryAfter as e:
                    # Telegram API rate limit - wait as instructed
                    wait_time = e.retry_after + 0.1
                    self.logger.warning(f"🚫 Telegram rate limit: waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                
                except BadRequest as e:
                    error_msg = str(e).lower()
                    
                    if "message is too long" in error_msg:
                        # Message still too long, split further
                        if len(chunk) > 100:
                            # Split the chunk in half and add continuation indicator
                            mid_point = len(chunk) // 2
                            # Find a good break point (space, newline, punctuation)
                            break_point = mid_point
                            for offset in range(0, min(50, mid_point)):
                                if chunk[mid_point - offset] in ' \n.!?':
                                    break_point = mid_point - offset
                                    break
                            
                            chunk = chunk[:break_point] + "..."
                            # The rest will be handled in the next iteration
                            message_chunks.insert(i + 1, "..." + chunk[break_point:])
                        else:
                            # Very short message that's somehow too long - truncate
                            chunk = chunk[:MessageLimit.MAX_TEXT_LENGTH - 3] + "..."
                        
                        retry_count += 1
                        continue
                    
                    elif "chat not found" in error_msg or "bot was blocked" in error_msg:
                        raise TelegramServiceError(
                            f"Cannot send message to chat {chat_id}: {e}",
                            e
                        )
                    
                    elif "can't parse" in error_msg or "parse_mode" in error_msg:
                        # Parse mode error - try without formatting
                        self.logger.warning(f"Parse mode error, retrying without formatting: {e}")
                        parse_mode = None
                        chunk = text  # Use original unescaped text
                        retry_count += 1
                        continue
                    
                    else:
                        # Other bad request errors are not retryable
                        self._error_count += 1
                        raise TelegramServiceError(f"Bad request: {e}", e)
                
                except (NetworkError, TimedOut) as e:
                    # Network errors are retryable
                    last_error = e
                    retry_count += 1
                    
                    if retry_count <= self.max_retries:
                        wait_time = self.retry_delay * (2 ** (retry_count - 1))
                        wait_time = min(wait_time, 10)  # Cap at 10 seconds
                        self.logger.warning(f"🌐 Network error, retrying in {wait_time:.1f}s: {e}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self._error_count += 1
                        raise TelegramServiceError(
                            f"Network error after {self.max_retries} retries: {last_error}",
                            last_error
                        )
                
                except TelegramError as e:
                    # Other Telegram errors
                    self._error_count += 1
                    last_error = e
                    retry_count += 1
                    
                    if retry_count <= self.max_retries:
                        wait_time = self.retry_delay * retry_count
                        self.logger.warning(f"🤖 Telegram error, retrying in {wait_time:.1f}s: {e}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise TelegramServiceError(
                            f"Telegram error after {self.max_retries} retries: {last_error}",
                            last_error
                        )
                
                except Exception as e:
                    # Unexpected errors are not retryable
                    self._error_count += 1
                    self.logger.error(f"❌ Unexpected error sending message: {e}")
                    raise TelegramServiceError(f"Unexpected error: {e}", e)
        
        self.logger.debug(f"✅ Sent {len(sent_message_ids)} message chunks to chat {chat_id}")
        return sent_message_ids

    async def edit_message(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = ParseMode.MARKDOWN_V2,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> bool:
        """Edit an existing message with error handling."""
        if not text or not text.strip():
            raise ValueError("Message text cannot be empty")
        
        # Validate and normalize parse mode
        parse_mode = self._validate_parse_mode(parse_mode)
        
        # Escape text if using MarkdownV2
        if parse_mode == ParseMode.MARKDOWN_V2:
            text = self._escape_markdown_v2(text.strip())
        
        # Truncate if too long (edited messages can't be chunked)
        if len(text) > MessageLimit.MAX_TEXT_LENGTH:
            text = text[:MessageLimit.MAX_TEXT_LENGTH - 3] + "..."
        
        retry_count = 0
        last_error = None
        
        while retry_count <= self.max_retries:
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                
                return True
                
            except BadRequest as e:
                error_msg = str(e).lower()
                
                if "message is not modified" in error_msg:
                    # Message content is the same - not an error
                    return True
                
                elif "message to edit not found" in error_msg:
                    raise TelegramServiceError(
                        f"Message {message_id} not found in chat {chat_id}",
                        e
                    )
                
                elif "can't parse" in error_msg:
                    # Parse mode error - try without formatting
                    self.logger.warning(f"Parse mode error in edit, retrying without formatting: {e}")
                    parse_mode = None
                    retry_count += 1
                    continue
                
                else:
                    self._error_count += 1
                    raise TelegramServiceError(f"Cannot edit message: {e}", e)
            
            except (NetworkError, TimedOut, RetryAfter) as e:
                last_error = e
                retry_count += 1
                
                if retry_count <= self.max_retries:
                    wait_time = self.retry_delay * retry_count
                    if isinstance(e, RetryAfter):
                        wait_time = e.retry_after + 0.1
                    
                    self.logger.warning(f"🔄 Retrying message edit in {wait_time:.1f}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    self._error_count += 1
                    raise TelegramServiceError(
                        f"Failed to edit message after {self.max_retries} retries: {last_error}",
                        last_error
                    )
            
            except Exception as e:
                self._error_count += 1
                raise TelegramServiceError(f"Unexpected error editing message: {e}", e)
        
        return False

    def create_inline_keyboard(
        self,
        buttons: List[List[Tuple[str, str]]],
        max_buttons_per_row: int = 3,
        validate_callbacks: bool = True
    ) -> InlineKeyboardMarkup:
        """Create inline keyboard with validation and optimization."""
        if not buttons:
            raise ValueError("Buttons list cannot be empty")
        
        if not self.use_inline_keyboards:
            self.logger.warning("Inline keyboards are disabled, returning empty keyboard")
            return InlineKeyboardMarkup([])
        
        keyboard_rows = []
        
        for row_index, row in enumerate(buttons):
            if not isinstance(row, list):
                raise ValueError(f"Button row {row_index} must be a list")
            
            if len(row) > max_buttons_per_row:
                self.logger.warning(
                    f"Row {row_index} has {len(row)} buttons, "
                    f"max recommended is {max_buttons_per_row}"
                )
            
            keyboard_row = []
            
            for button_index, button in enumerate(row):
                if not isinstance(button, tuple) or len(button) != 2:
                    raise ValueError(
                        f"Button {row_index},{button_index} must be a tuple of (text, callback_data)"
                    )
                
                text, callback_data = button
                
                # Validate button text
                if not text or not isinstance(text, str):
                    raise ValueError(f"Button text at {row_index},{button_index} must be a non-empty string")
                
                # Validate callback data
                if not callback_data or not isinstance(callback_data, str):
                    raise ValueError(f"Callback data at {row_index},{button_index} must be a non-empty string")
                
                # Check callback data length (Telegram limit is 64 bytes)
                if validate_callbacks and len(callback_data.encode('utf-8')) > 64:
                    raise ValueError(
                        f"Callback data at {row_index},{button_index} is too long "
                        f"({len(callback_data.encode('utf-8'))} bytes), max 64 bytes"
                    )
                
                # Truncate text if too long for display
                display_text = text
                if len(text) > 30:
                    display_text = text[:27] + "..."
                    self.logger.debug(f"Truncated button text: '{text}' -> '{display_text}'")
                
                keyboard_row.append(
                    InlineKeyboardButton(
                        text=display_text,
                        callback_data=callback_data
                    )
                )
            
            if keyboard_row:  # Only add non-empty rows
                keyboard_rows.append(keyboard_row)
        
        if not keyboard_rows:
            self.logger.warning("No valid keyboard rows created")
            return InlineKeyboardMarkup([])
        
        return InlineKeyboardMarkup(keyboard_rows)

    def format_project_message(
        self,
        project: Project,
        include_stats: bool = True,
        include_details: bool = True
    ) -> str:
        """Format project information for display."""
        if not project:
            return "❌ Project information unavailable"
        
        # Basic project info
        message_parts = [
            f"📁 **{project.name}** \\({project.key}\\)"
        ]
        
        if project.description:
            # Escape and truncate description
            desc = self._escape_markdown_v2(project.description[:200])
            if len(project.description) > 200:
                desc += "\\.\\.\\."
            message_parts.append(f"_{desc}_")
        
        if include_details:
            details = []
            
            if project.project_type:
                type_emoji = {"software": "💻", "service_desk": "🎧", "business": "💼"}.get(
                    project.project_type, "📋"
                )
                details.append(f"{type_emoji} Type: {project.project_type}")
            
            if project.lead:
                details.append(f"👤 Lead: {self._escape_markdown_v2(project.lead)}")
            
            if project.category:
                details.append(f"🏷️ Category: {self._escape_markdown_v2(project.category)}")
            
            if details:
                message_parts.append("\n".join(details))
        
        if include_stats:
            stats = [
                f"📊 Issues: {project.issue_count}",
                f"✅ Active: {'Yes' if project.is_active else 'No'}"
            ]
            
            message_parts.append("\n".join(stats))
        
        if project.url:
            message_parts.append(f"🔗 [View in Jira]({project.url})")
        
        return "\n\n".join(message_parts)

    def format_issue_message(
        self,
        issue: JiraIssue,
        include_description: bool = True,
        include_details: bool = True
    ) -> str:
        """Format issue information for display."""
        if not issue:
            return "❌ Issue information unavailable"
        
        # Issue header
        type_emoji = issue.issue_type.get_emoji() if hasattr(issue.issue_type, 'get_emoji') else "📋"
        priority_emoji = issue.priority.get_emoji() if hasattr(issue.priority, 'get_emoji') else "📊"
        status_emoji = issue.status.get_emoji() if hasattr(issue.status, 'get_emoji') else "📝"
        
        message_parts = [
            f"{type_emoji} **{self._escape_markdown_v2(issue.key)}**: {self._escape_markdown_v2(issue.summary)}"
        ]
        
        # Status and priority
        status_line = f"{status_emoji} {issue.status.value} | {priority_emoji} {issue.priority.value}"
        message_parts.append(status_line)
        
        # Description
        if include_description and issue.description:
            desc = self._escape_markdown_v2(issue.description[:300])
            if len(issue.description) > 300:
                desc += "\\.\\.\\."
            message_parts.append(f"_{desc}_")
        
        if include_details:
            details = []
            
            if hasattr(issue, 'assignee_name') and issue.assignee_name:
                details.append(f"👤 Assignee: {self._escape_markdown_v2(issue.assignee_name)}")
            
            if hasattr(issue, 'creator_name') and issue.creator_name:
                details.append(f"✍️ Reporter: {self._escape_markdown_v2(issue.creator_name)}")
            
            if hasattr(issue, 'labels') and issue.labels:
                labels_text = ", ".join(issue.labels[:3])  # Show max 3 labels
                if len(issue.labels) > 3:
                    labels_text += f" \\+{len(issue.labels) - 3} more"
                details.append(f"🏷️ Labels: {self._escape_markdown_v2(labels_text)}")
            
            if details:
                message_parts.append("\n".join(details))
        
        # Timestamps
        if issue.created_at:
            created_date = issue.created_at.strftime("%Y\\-%m\\-%d")
            message_parts.append(f"📅 Created: {created_date}")
        
        return "\n\n".join(message_parts)

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check of the Telegram service."""
        start_time = time.time()
        
        try:
            # Test bot connectivity
            me = await self.bot.get_me()
            
            response_time = time.time() - start_time
            
            return {
                'status': 'healthy',
                'response_time_ms': round(response_time * 1000, 2),
                'bot_info': {
                    'username': me.username,
                    'first_name': me.first_name,
                    'can_join_groups': me.can_join_groups,
                    'can_read_all_group_messages': me.can_read_all_group_messages,
                    'supports_inline_queries': me.supports_inline_queries
                },
                'statistics': {
                    'messages_sent': self._message_count,
                    'errors': self._error_count,
                    'error_rate': round(self._error_count / max(self._message_count, 1) * 100, 2),
                    'last_message_time': self._last_message_time
                },
                'configuration': {
                    'inline_keyboards_enabled': self.use_inline_keyboards,
                    'compact_mode': self.compact_mode,
                    'timeout': self.timeout,
                    'max_retries': self.max_retries
                }
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            
            return {
                'status': 'unhealthy',
                'error': str(e),
                'response_time_ms': round(response_time * 1000, 2),
                'statistics': {
                    'messages_sent': self._message_count,
                    'errors': self._error_count
                }
            }

    async def close(self) -> None:
        """Close the Telegram service and cleanup resources."""
        try:
            # Close the bot session if it exists
            if hasattr(self.bot, '_request') and self.bot._request:
                await self.bot._request.shutdown()
            
            self.logger.info("✅ Telegram service closed")
            
        except Exception as e:
            self.logger.error(f"❌ Error closing Telegram service: {e}")

    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, 'bot') and hasattr(self.bot, '_request') and self.bot._request:
            self.logger.warning("⚠️ Telegram service not properly closed")