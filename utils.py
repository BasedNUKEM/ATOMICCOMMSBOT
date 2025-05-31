"""
Utility functions and classes for the NUKEM Bot.
"""

import time
import random # Added for varied responses
import logging # Added for error_handler
from collections import defaultdict
from datetime import datetime
from functools import wraps
from typing import Optional, Callable, Any, Coroutine

from telegram import Update, ChatMember # Added ChatMember for admin_required
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError # For error_handler

# Local imports
from constants import (
    RATE_LIMIT_MESSAGES, RATE_LIMIT_PERIOD, COMMAND_COOLDOWNS, ADMIN_USER_IDS,
    EMOJI_WARNING, EMOJI_ROCKET, EMOJI_ALIEN, EMOJI_NO_ENTRY, EMOJI_ADMIN,
    EMOJI_TARGET, EMOJI_STOPWATCH, EMOJI_ERROR, EMOJI_INFO, EMOJI_SKULL, EMOJI_SHIELD,
    EMOJI_DATABASE # Added EMOJI_DATABASE
)
from db import DatabaseError # For error_handler

logger = logging.getLogger(__name__) # Logger for utility functions

# --- Helper to escape MarkdownV2 ---
def escape_markdown_v2(text: str) -> str:
    """Helper function to escape telegram MarkdownV2 special characters."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in str(text))

# --- Rate Limiting ---
# RATE_LIMIT_MESSAGES and RATE_LIMIT_PERIOD are now imported from constants

class RateLimiter:
    """Rate limiter with Redis-like sliding window."""

    def __init__(self):
        self._cache = defaultdict(list)

    async def is_rate_limited(self, user_id: int, chat_id: Optional[int] = None) -> bool: # Added chat_id for context
        current_time = time.time()
        # Use constants for period and messages (RATE_LIMIT_PERIOD is timedelta, convert to seconds)
        # RATE_LIMIT_MESSAGES is a dict, we need to use the values from it.
        # For simplicity, the check_rate_limit decorator handles the message.
        # This method just checks if limited.
        
        # Using a combined key for user_id and chat_id if chat_id is provided for chat-specific limits
        # For now, sticking to user-specific global rate limit as per original design.
        # If chat-specific limits are desired, key would be (user_id, chat_id)
        
        key = user_id 
        
        # RATE_LIMIT_PERIOD is a timedelta, get total_seconds()
        # The number of allowed requests is implicitly defined by how many timestamps are kept.
        # Let's assume 5 requests per RATE_LIMIT_PERIOD (e.g. 5 requests per 5 seconds)
        # This needs to be configured or passed. For now, let's use a fixed number.
        MAX_REQUESTS = 5 # Example: 5 requests in RATE_LIMIT_PERIOD seconds

        cutoff_time = current_time - RATE_LIMIT_PERIOD.total_seconds()
        
        timestamps = self._cache[key] = [
            ts for ts in self._cache[key] if ts > cutoff_time
        ]
        
        if len(timestamps) >= MAX_REQUESTS:
            return True
        
        timestamps.append(current_time)
        self._cache[key] = timestamps # Ensure the updated list is stored
        return False

    def cleanup(self):
        current_time = time.time()
        cutoff_time = current_time - RATE_LIMIT_PERIOD.total_seconds() # Use total_seconds()
        for user_id in list(self._cache.keys()): # Iterate over keys safely
            timestamps = self._cache[user_id]
            valid_timestamps = [ts for ts in timestamps if ts > cutoff_time]
            if valid_timestamps:
                self._cache[user_id] = valid_timestamps
            else:
                del self._cache[user_id]

rate_limiter = RateLimiter()

def check_rate_limit(func: Callable[..., Coroutine[Any, Any, Any]]):
    """Decorator to add rate limiting to commands."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Optional[Any]:
        if not update.effective_user:
            return await func(update, context, *args, **kwargs)
            
        user_id = update.effective_user.id
        if user_id in ADMIN_USER_IDS:
            return await func(update, context, *args, **kwargs)

        # Pass chat_id if you want chat-specific rate limits in RateLimiter
        if await rate_limiter.is_rate_limited(user_id): 
            limit_message_key = "user" # Assuming user-specific messages for now
            # Use RATE_LIMIT_MESSAGES from constants.py
            default_message = f"{EMOJI_STOPWATCH} Easy there, slick! Too many commands too fast. Take a breather."
            message = RATE_LIMIT_MESSAGES.get(limit_message_key, default_message)
            
            # Add some variety
            insults = [
                message,
                f"{EMOJI_ROCKET} Woah there, partner! You're burnin' fuel too fast! Try again in a sec.",
                f"{EMOJI_SHIELD} My circuits are smokin' from your requests! Give it a rest, maggot!",
                f"{EMOJI_ALIEN} Even aliens need a coffee break. You're rate limited!"
            ]
            await update.message.reply_text(random.choice(insults))
            return None
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Cooldown Management ---
LAST_COMMAND_USAGE = defaultdict(lambda: defaultdict(float)) # User-specific cooldowns

def command_cooldown(command_name: str, default_cooldown_seconds: Optional[int] = None):
    """Decorator factory to add cooldown to commands. Uses COMMAND_COOLDOWNS and ADMIN_USER_IDS from constants."""
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Optional[Any]:
            if not update.effective_user:
                return await func(update, context, *args, **kwargs)

            user_id = update.effective_user.id
            current_time = datetime.now().timestamp()

            if user_id in ADMIN_USER_IDS: # Admins bypass cooldowns
                return await func(update, context, *args, **kwargs)

            # Get cooldown from COMMAND_COOLDOWNS in constants.py, or use the provided default_cooldown_seconds
            cooldown_seconds = COMMAND_COOLDOWNS.get(command_name, default_cooldown_seconds if default_cooldown_seconds is not None else COMMAND_COOLDOWNS.get("default", 5))
            
            last_usage = LAST_COMMAND_USAGE[command_name].get(user_id, 0.0)

            if current_time - last_usage < cooldown_seconds:
                remaining = int(cooldown_seconds - (current_time - last_usage))
                responses = [
                    f"{EMOJI_STOPWATCH} Hold your horses! `{escape_markdown_v2(command_name)}` is on cooldown. {remaining}s left.",
                    f"{EMOJI_ROCKET} My `{escape_markdown_v2(command_name)}` cannon needs {remaining} more seconds to recharge!",
                    f"{EMOJI_SHIELD} Patience, rookie! {remaining}s cooldown remaining for `{escape_markdown_v2(command_name)}`.",
                    f"{EMOJI_ALIEN} Can't spam `{escape_markdown_v2(command_name)}` like that! {remaining}s before next launch."
                ]
                await safe_markdown_message(update, random.choice(responses), logger, reply_to=True)
                return None

            LAST_COMMAND_USAGE[command_name][user_id] = current_time
            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator

# --- Error Handler Decorator ---
def error_handler(func: Callable[..., Coroutine[Any, Any, Any]]):
    """Decorator to handle errors in commands gracefully."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Optional[Any]:
        try:
            return await func(update, context, *args, **kwargs)
        except DatabaseError as e:
            logger.error(f"{EMOJI_ERROR} Database error in {func.__name__}: {e}", exc_info=True)
            if update and update.message:
                await safe_markdown_message(update, 
                    f"{EMOJI_DATABASE}{EMOJI_ERROR} Database is having a meltdown! Try again later, soldier.", 
                    logger, reply_to=True
                )
        except TelegramError as e: # More specific Telegram errors can be caught if needed
            logger.error(f"{EMOJI_ERROR} Telegram API error in {func.__name__}: {e}", exc_info=True)
            if update and update.message:
                error_message = escape_markdown_v2(str(e))
                await safe_markdown_message(update, 
                    f"{EMOJI_ALIEN}{EMOJI_ERROR} Telegram's acting up! My systems are blinking red. Error: {error_message}", 
                    logger, reply_to=True
                )
        except Exception as e:
            logger.error(f"{EMOJI_ERROR} Unexpected error in {func.__name__}: {e}", exc_info=True)
            if update and update.message:
                await safe_markdown_message(update, 
                    f"{EMOJI_SKULL}{EMOJI_WARNING} Son of a bitch! Something went sideways. But Duke always comes back! Error: {escape_markdown_v2(str(e))}", 
                    logger, reply_to=True
                )
        return None # Explicitly return None on handled error
    return wrapped

# --- Admin Check Decorator ---
def admin_required(_func: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None, *, fetch_chat_admins: bool = False):
    """Decorator to ensure only admins (global or chat) can run the command.
    Can be used as @admin_required or @admin_required(fetch_chat_admins=True).
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Optional[Any]:
            if not update.effective_user:
                logger.warning(f"Command {func.__name__} called without effective_user.")
                return None 
            
            user_id = update.effective_user.id
            
            if user_id in ADMIN_USER_IDS: # Global admins from constants.py
                # If fetch_chat_admins is True, ensure chat_admins is populated in context.chat_data
                if fetch_chat_admins and update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
                    if 'chat_admins' not in context.chat_data:
                        try:
                            chat_administrators = await context.bot.get_chat_administrators(update.effective_chat.id)
                            context.chat_data['chat_admins'] = [admin.user.id for admin in chat_administrators]
                        except TelegramError as e:
                            logger.warning(f"Could not fetch chat admins for {func.__name__}: {e}")
                            context.chat_data['chat_admins'] = [] # Set to empty list on failure
                return await func(update, context, *args, **kwargs)
            
            # Check for chat admin status if in a group/supergroup
            if update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
                chat_id = update.effective_chat.id
                # Use cached chat_admins if available and fetch_chat_admins was true, or fetch fresh
                chat_admin_ids = context.chat_data.get('chat_admins')
                
                if chat_admin_ids is None or not fetch_chat_admins: # If not cached or not asked to pre-fetch, get fresh
                    try:
                        chat_member = await context.bot.get_chat_member(chat_id, user_id)
                        if chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                            # If fetch_chat_admins is True, populate the cache now if it wasn\'t already
                            if fetch_chat_admins and 'chat_admins' not in context.chat_data:
                                chat_administrators = await context.bot.get_chat_administrators(chat_id)
                                context.chat_data['chat_admins'] = [admin.user.id for admin in chat_administrators]
                            return await func(update, context, *args, **kwargs)
                    except TelegramError as e:
                        logger.warning(f"{EMOJI_WARNING} Could not verify chat admin status for user {user_id} in chat {chat_id} due to Telegram API error: {e}")
                    except Exception as e:
                        logger.error(f"{EMOJI_ERROR} Unexpected error verifying chat admin status for user {user_id} in chat {chat_id}: {e}", exc_info=True)
                elif user_id in chat_admin_ids: # User is in the pre-fetched list of admins
                    return await func(update, context, *args, **kwargs)

            # If not a global admin and (not a chat admin or check failed/not applicable)
            insults = [
                f"{EMOJI_NO_ENTRY} Nice try, pencil-neck. This command's for the {EMOJI_ADMIN} big boys.",
                f"{EMOJI_SHIELD} Whoa there, slick. You ain't got the clearance for that. Access denied.",
                f"{EMOJI_TARGET} Access denied. Go cry to your mama. This is restricted airspace!",
                f"{EMOJI_ALIEN} You? Admin? Ha! That's funnier than a pig in a prom dress. {EMOJI_SKULL}"
            ]
            if update.message: # Ensure there's a message to reply to
                await safe_markdown_message(update, random.choice(insults), logger, reply_to=True)
            return None
        return wrapped

    if _func is None: # Called as @admin_required(fetch_chat_admins=True)
        return decorator
    else: # Called as @admin_required
        return decorator(_func)

# --- Chat Type Management ---
def chat_type_allowed(allowed_types: list[str]):
    """Decorator to restrict commands to specific chat types."""
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Optional[Any]:
            if not update.effective_chat:
                logger.warning(f"{EMOJI_WARNING} Command {func.__name__} called without effective_chat.")
                # Attempt to inform user if possible, though update.message might not exist
                if update.message:
                     await safe_markdown_message(update, f"{EMOJI_ERROR} Cannot determine chat type for this command.", logger, reply_to=True)
                return None 

            chat_type = update.effective_chat.type
            if chat_type not in allowed_types:
                allowed_types_str = ', '.join(allowed_types)
                message = (f"{EMOJI_NO_ENTRY} This command, `{escape_markdown_v2(func.__name__)}`, ain't for this kind of rodeo! "
                           f"It only works in {escape_markdown_v2(allowed_types_str)} chats.")
                if update.message: # Ensure there's a message to reply to
                    await safe_markdown_message(update, message, logger, reply_to=True)
                return None
            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator

# --- Safe Message Sending ---
async def safe_markdown_message(
    update: Update, 
    text: str, 
    logger_instance: logging.Logger, # Changed from logger to logger_instance to avoid conflict
    reply_to: bool = False, 
    chat_id_override: Optional[int] = None,
    parse_mode: str = ParseMode.MARKDOWN_V2 # Default to MarkdownV2
) -> None:
    """Sends a message using MarkdownV2, falling back to plain text if issues occur."""
    try:
        target_chat_id = chat_id_override if chat_id_override else update.effective_chat.id
        if not target_chat_id:
            logger_instance.error(f"{EMOJI_ERROR} No target chat ID available for safe_markdown_message.")
            return

        if reply_to and update.message:
            await update.message.reply_text(text, parse_mode=parse_mode)
        else:
            await update.get_bot().send_message(chat_id=target_chat_id, text=text, parse_mode=parse_mode)
            
    except TelegramError as e:
        logger_instance.warning(
            f"{EMOJI_WARNING} Failed to send message with MarkdownV2: {e}. Content: '{text[:100]}...'"
        )
        # Fallback to plain text
        try:
            plain_text = text # Assuming text is already escaped or doesn't need it for plain
            # A more robust fallback would be to strip markdown characters or use a library
            # For now, just send as is, which might show raw markdown.
            if reply_to and update.message:
                await update.message.reply_text(plain_text)
            elif target_chat_id: # Ensure target_chat_id is still valid
                await update.get_bot().send_message(chat_id=target_chat_id, text=plain_text)
        except TelegramError as e_plain:
            logger_instance.error(
                f"{EMOJI_ERROR} Failed to send message even in plain text: {e_plain}. Content: '{text[:100]}...'"
            )
    except Exception as ex: # Catch any other unexpected error
        logger_instance.error(
            f"{EMOJI_ERROR} Unexpected error in safe_markdown_message: {ex}. Content: '{text[:100]}...'", exc_info=True
        )


# --- Message Chunking ---
def chunk_message(message: str, chunk_size: int = 4096) -> list[str]:
    """Chunk a message into smaller parts for sending in multiple messages."""
    if len(message) <= chunk_size:
        return [message]
    
    # Split by Telegram's recommended max length for messages, then further split by newline to avoid cutting words
    parts = message.split('\n')
    chunks = []
    current_chunk = ""

    for part in parts:
        if len(current_chunk) + len(part) + 1 <= chunk_size:
            current_chunk += (part + '\n')
        else:
            chunks.append(current_chunk.strip())
            current_chunk = part + '\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

async def send_message_in_chunks(update: Update, text: str, logger_instance: logging.Logger, **kwargs: Any) -> None:
    """Send a message in chunks, handling MarkdownV2 and plain text."""
    try:
        # First, chunk the message
        message_chunks = chunk_message(text)
        
        # Send each chunk separately
        for i, chunk in enumerate(message_chunks):
            is_last_chunk = (i == len(message_chunks) - 1)
            await safe_markdown_message(update, chunk, logger_instance, reply_to=is_last_chunk, **kwargs)
    except Exception as e:
        logger_instance.error(f"Error in send_message_in_chunks: {e}", exc_info=True)
        await update.message.reply_text(f"Error sending message chunks: {e}")

def parse_duration(duration_str: str) -> Optional[int]:
    """
    Parses a duration string (e.g., "1d", "2h", "30m") into seconds.
    Placeholder implementation.
    """
    logger.info(f"Attempting to parse duration: {duration_str}")
    # TODO: Implement actual duration parsing logic
    # Examples: "1d" -> 86400, "2h" -> 7200, "30m" -> 1800
    # For now, return None or raise an error if it's critical for startup
    if duration_str.endswith('s'):
        return int(duration_str[:-1])
    elif duration_str.endswith('m'):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return int(duration_str[:-1]) * 3600
    elif duration_str.endswith('d'):
        return int(duration_str[:-1]) * 86400
    logger.warning(f"parse_duration: Basic implementation, received {duration_str}")
    return None # Or raise ValueError("Invalid duration string")

async def get_user_id_from_username_or_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> Optional[int]:
    """
    Placeholder for a function that gets user ID from username or reply.
    """
    logger.info(f"Attempting to get user ID from username or reply. Args: {args}")
    # TODO: Implement actual logic to extract user ID
    # This might involve checking update.message.reply_to_message
    # or parsing args for a username and then looking up the user.
    return None
