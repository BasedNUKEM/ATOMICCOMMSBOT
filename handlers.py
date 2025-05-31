# This file will contain the command handlers, message tracker, and other event handlers.
import asyncio
import datetime
import logging
import random
import re
from functools import wraps
from typing import Callable, Coroutine, Any, cast
from datetime import timedelta
from telegram import Update, ChatMember, ChatPermissions, MessageEntity # Changed MessageEntityType to MessageEntity
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Ensure ParseMode is imported
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError

from constants import (
    NUKEM_QUOTES, NUKEM_REACTIONS_POSITIVE, NUKEM_REACTIONS_NEGATIVE,
    NUKEM_RATINGS, ALIEN_SCAN_REPORTS, PROJECT_INFO, DUKE_ARSENAL, KARMA_EMOJI,
    EMOJI_WAVE, EMOJI_SUNGLASSES, EMOJI_ADMIN, EMOJI_ROCKET, EMOJI_BOOK,
    EMOJI_GEAR, EMOJI_BROADCAST, EMOJI_TARGET, EMOJI_TOOLS, EMOJI_INFO,
    EMOJI_BRAIN, EMOJI_STAR, EMOJI_ALIEN, EMOJI_USER, EMOJI_SCROLL,
    EMOJI_QUESTION, EMOJI_CHART_UP, EMOJI_CHART_DOWN, EMOJI_SHIELD,
    EMOJI_WARNING, EMOJI_SUCCESS, EMOJI_NO_ENTRY, EMOJI_CHAT,
    EMOJI_LEADERBOARD, EMOJI_ROBOT, EMOJI_ERROR, EMOJI_DATABASE, EMOJI_THINKING,
    EMOJI_GREEN_CIRCLE, EMOJI_RED_CIRCLE, EMOJI_YELLOW_CIRCLE, EMOJI_PIN, EMOJI_STOPWATCH,
    EMOJI_COMMAND, EMOJI_CYCLE, EMOJI_CHECKMARK, EMOJI_CROSS_MARK, EMOJI_HOURGLASS,
    EMOJI_PAGER, EMOJI_INBOX, EMOJI_OUTBOX, EMOJI_PACKAGE, EMOJI_MEMO, EMOJI_CLIPBOARD,
    EMOJI_PUSHPIN, EMOJI_NOTEPAD, EMOJI_CALENDAR, EMOJI_GRAPH, EMOJI_BAR_CHART,
    EMOJI_SPEECH_BUBBLE, EMOJI_EXPLOSION, EMOJI_BOMB, EMOJI_SKULL, EMOJI_FIRE, EMOJI_NUKE,
    EMOJI_LIGHTBULB, EMOJI_PARTY, EMOJI_EYES, EMOJI_LINK
)
from utils import (
    escape_markdown_v2, check_rate_limit, command_cooldown,
    safe_markdown_message, chunk_message, error_handler,
    admin_required, chat_type_allowed, parse_duration, get_user_id_from_username_or_reply
)
# from db import Database  # Assuming db.py might be refactored or this import is conditional
# Conditional import for Database to avoid circular dependency if db.py imports from handlers

# Define placeholder types/classes that are always valid for type hints and isinstance/except.
class _DatabasePlaceholder:
    """Placeholder for Database type when db.py is not available."""
    pass

class _DatabaseErrorPlaceholder(Exception): # Must be an Exception subclass
    """Placeholder for DatabaseError type when db.py is not available."""
    pass

# These will be the names used throughout the code for type hints and runtime checks.
# They default to placeholders.
Database: type = _DatabasePlaceholder
DatabaseError: type[Exception] = _DatabaseErrorPlaceholder # Ensure it's an exception type

# This flag indicates if the real Database class was successfully imported.
_real_db_imported = False

try:
    # Attempt to import the real Database and DatabaseError classes
    from db import Database as _ImportedDatabase, DatabaseError as _ImportedDatabaseError
    
    # Validate that imported names are actual types/classes suitable for use
    if not isinstance(_ImportedDatabase, type):
        # Use logging module directly as 'logger' instance might not be defined yet
        logging.error("Imported 'Database' from db.py is not a class. Using placeholder.")
    elif not (isinstance(_ImportedDatabaseError, type) and issubclass(_ImportedDatabaseError, Exception)):
        logging.error("Imported 'DatabaseError' from db.py is not an Exception subclass. Using placeholder.")
    else:
        # If validation passes, assign the real classes
        Database = _ImportedDatabase
        DatabaseError = _ImportedDatabaseError
        _real_db_imported = True
        logging.info("Successfully imported and validated Database and DatabaseError from db.py")

except ImportError:
    logging.warning(
        "Failed to import Database or DatabaseError from db.py. "
        "Database features will be unavailable. Using placeholders."
    )
except Exception as e: # Catch other potential errors during import or validation
    logging.error(
        f"An unexpected error occurred during import or validation of Database/DatabaseError: {e}. "
        "Using placeholders."
    )

logger = logging.getLogger(__name__)

# Conversation states for multi-step interactions (if any)
# EXAMPLE_STATE = 1

# --- Helper Functions Specific to Handlers (if any) ---

async def _get_db_instance(context: ContextTypes.DEFAULT_TYPE) -> Database | None:
    """Safely retrieves the database instance from bot_data."""
    if not _real_db_imported: # Check if the real Database class was successfully imported
        logger.error("Real Database class not imported. DB features will not work.")
        return None
    
    db_instance = context.bot_data.get('db')
    # If _real_db_imported is True, 'Database' refers to the actual imported class.
    if not isinstance(db_instance, Database):
        logger.error("Database instance not found or not of correct type in bot_data.")
        return None
    return db_instance

async def _get_target_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Database | None) -> tuple[int | None, str | None, dict | None]:
    """
    Determines the target user ID and username from the command.
    Can be from a replied-to message, a mention, or the command issuer.
    Returns (user_id, username_display, user_doc).
    """
    target_user_id = None
    target_username_display = None
    user_doc = None
    
    # Check for replied-to message first
    if update.message and update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username_display = update.message.reply_to_message.from_user.username or f"User {target_user_id}"
        if db:
            user_doc = await db.get_user(target_user_id)
        return target_user_id, target_username_display, user_doc

    # Check for mentions or username in args
    if context.args:
        raw_target_arg = context.args[0]
        # Attempt to get user_id from argument (could be @username or user_id)
        # This helper function would need to be robust
        resolved_user_id, resolved_username = await get_user_id_from_username_or_reply(update, context, raw_target_arg)

        if resolved_user_id:
            target_user_id = resolved_user_id
            target_username_display = resolved_username or f"User {target_user_id}"
            if db:
                user_doc = await db.get_user(target_user_id)
            return target_user_id, target_username_display, user_doc
        else: # Argument provided but not resolved as a user
            await safe_markdown_message(update, f"{EMOJI_QUESTION} Couldn't find user: {escape_markdown_v2(raw_target_arg)}\\. Try replying to their message or using a valid @username or ID\\.", logger)
            return None, None, None
            
    # If no reply and no args, target is the message sender (for commands like /karma (self))
    if update.effective_user:
        target_user_id = update.effective_user.id
        target_username_display = update.effective_user.username or f"User {target_user_id}"
        if db:
            user_doc = await db.get_user(target_user_id)
        return target_user_id, target_username_display, user_doc
        
    return None, None, None


# --- Command Handlers ---
@chat_type_allowed(['group', 'supergroup', 'private'])
@command_cooldown("start") 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command with Duke's flair."""
    _update_stats = context.bot_data.get('update_stats')
    
    start_message_parts = [
        f"{EMOJI_WAVE} Yo\\! The Duke is in the house\\! {EMOJI_SUNGLASSES}\\n",
        f"Ready to kick ass and chew bubble gum\\.\\.\\. and I\\'m all outta gum\\.\\n",
        f"If you\\'re an {EMOJI_ADMIN} admin, type `{escape_markdown_v2('/help_nukem')}` for the full arsenal\\. ",
        f"Everyone else, try not to get any on ya\\. {EMOJI_ROCKET}"
    ]
    start_message = "".join(start_message_parts)
    
    await safe_markdown_message(update, start_message, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    if callable(_update_stats): _update_stats(command="start", user_id=update.effective_user.id if update.effective_user else None)

@admin_required
@command_cooldown("help_nukem")
async def help_nukem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help_nukem command, displaying available commands with emojis."""
    _update_stats = context.bot_data.get('update_stats')
    
    help_parts = [
        f"{EMOJI_BOOK} {EMOJI_ADMIN} *Alright, maggots, listen up\\! Here\\'s the NUKEM command console:*\\n\\n",
        f"{EMOJI_GEAR} *Basic Operations:*\\n",
        f"`{escape_markdown_v2('/mentionall <message>')}` \\- {EMOJI_BROADCAST} Yell at *everyone*\\. Use sparingly, or I\\'ll use *you* for target practice\\.\\n",
        f"`{escape_markdown_v2('/mention @user1 @user2 <message>')}` \\- {EMOJI_TARGET} Point your finger at specific chumps\\.\\n",
        f"`{escape_markdown_v2('/pin_nukem <message_or_reply>')}` \\- {EMOJI_TOOLS} Make somethin\\' stick\\. Like gum to a boot\\.\\n",
        f"`{escape_markdown_v2('/info [topic]')}` \\- {EMOJI_INFO} Get the damn intel \\(e\\.g\\., roadmap, tokenomics, website\\)\\. Default for general info\\.\\n",
        f"`{escape_markdown_v2('/nukem_quote')}` \\- {EMOJI_BRAIN} Get a dose of pure, unadulterated wisdom from yours truly\\.\\n",
        f"`{escape_markdown_v2('/rate_my_play <description>')}` \\- {EMOJI_STAR} Let the Duke judge your so-called \\'skills\\'\\.\\n",
        f"`{escape_markdown_v2('/arsenal [weapon_name]')}` \\- {EMOJI_TOOLS} Check out my boomsticks\\.\\n",
        f"`{escape_markdown_v2('/alien_scan')}` \\- {EMOJI_ALIEN} Check if any green-blooded freaks are sniffin\\' around\\.\\n\\n",
        
        f"{EMOJI_USER} *User Management & Karma:*\\n",
        f"`{escape_markdown_v2('/list_users')}` \\- {EMOJI_SCROLL} See who\\'s on my list \\(user list with karma/warnings\\)\\.\\n",
        f"`{escape_markdown_v2('/karma @user')}` \\- {EMOJI_QUESTION} Check someone\\'s karma level\\.\\n",
        f"`{escape_markdown_v2('/give_karma @user [reason]')}` \\- {EMOJI_CHART_UP} Award karma to a worthy soldier\\.\\n",
        f"`{escape_markdown_v2('/remove_karma @user [reason]')}` \\- {EMOJI_CHART_DOWN} Take karma from a disappointment\\.\\n\\n",
        
        f"{EMOJI_SHIELD} *Moderation Arsenal:*\\n",
        f"`{escape_markdown_v2('/warn @user [reason]')}` \\- {EMOJI_WARNING} Issue a warning to a troublemaker\\.\\n",
        f"`{escape_markdown_v2('/unwarn @user')}` \\- {EMOJI_SUCCESS} Remove a warning if they\\'ve learned their lesson\\.\\n",
        f"`{escape_markdown_v2('/warnings @user')}` \\- {EMOJI_INFO} Check someone\\'s rap sheet \\(warning history\\)\\.\\n",
        f"`{escape_markdown_v2('/mute @user <duration> [reason]')}` \\- {EMOJI_NO_ENTRY} Shut someone up \\(e\\.g\\., 10m, 1h, 1d\\)\\.\\n",
        f"`{escape_markdown_v2('/unmute @user')}` \\- {EMOJI_CHAT} Let \\'em talk again, if they\\'ve learned their place\\.\\n\\n",
        
        f"{EMOJI_LEADERBOARD} *Stats & Glory:*\\n",
        f"`{escape_markdown_v2('/stats')}` \\- {EMOJI_CHART_UP} See how much ass this bot has kicked \\(bot statistics\\)\\.\\n",
        f"`{escape_markdown_v2('/leaderboard [karma|activity]')}` \\- {EMOJI_LEADERBOARD} See who\\'s top dog\\.\\n\\n",
        
        f"{EMOJI_ROBOT} *Remember, I\\'m always watching\\.\\.\\. and judging\\. So make it good\\.* {EMOJI_SUNGLASSES}"
    ]
    help_text = "".join(help_parts)
    
    await safe_markdown_message(update, help_text, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    if callable(_update_stats): _update_stats(command="help_nukem", user_id=update.effective_user.id if update.effective_user else None)

# ... (other handlers will be moved here)
@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("mentionall")
@admin_required
@error_handler
async def mention_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mentions all users in a chat with a message.""" # Simplified docstring
    chat_id = update.effective_chat.id
    message_text_parts = context.args
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')

    if not message_text_parts:
        await safe_markdown_message(update,
            f"{EMOJI_QUESTION} Spit it out, genius\\! `{escape_markdown_v2('/mentionall <your damn message>')}`",
            logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2
        )
        if callable(_update_stats): _update_stats(command="mentionall", error_occurred="no_message", chat_id=chat_id)
        return

    message_text = " ".join(message_text_parts)
    escaped_custom_message = escape_markdown_v2(message_text)

    try:
        if db is None:
            await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot fetch users\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="mentionall", error_occurred="db_not_connected", chat_id=chat_id)
            return

        user_docs = await db.get_all_users_in_chat(chat_id)
        if not user_docs:
            await safe_markdown_message(update, f"{EMOJI_THINKING} No users found in this chat\\'s records, or they all left\\. Spooky\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="mentionall", error_occurred="no_users_in_db", chat_id=chat_id)
            return

        mentions = []
        for user_doc in user_docs:
            user_id = user_doc.get('user_id')
            # username = user_doc.get('username') # Not used directly for mention if using user_id
            if user_id:
                # For MarkdownV2, user mentions are [inline mention of a user](tg://user?id=USER_ID)
                mentions.append(f"[\\u200B](tg://user?id={user_id})") # \\u200B is a zero-width space

        if not mentions:
            await safe_markdown_message(update, f"{EMOJI_THINKING} Couldn\\'t prepare any mentions\\. Maybe no one wants to be bothered\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="mentionall", error_occurred="no_mentions_prepared", chat_id=chat_id)
            return
            
        # Telegram message length limit is 4096 characters.
        # Each mention like "[\\u200B](tg://user?id=123456789)" is approx 30-35 chars.
        # Max users per message: 4096 / 35 \\u2248 110-115 users.
        # We also need space for the custom message.
        
        # Split users into chunks to avoid exceeding message length limits
        # Max mentions per message to be safe with custom message length
        max_mentions_per_message = 50 
        
        full_message_header = f"{EMOJI_BROADCAST} {EMOJI_ADMIN} *Listen up, you meatbags\\!* {EMOJI_FIRE}\\n\\n{escaped_custom_message}\\n\\n*Tagging:* "

        user_mention_chunks = [mentions[i:i + max_mentions_per_message] for i in range(0, len(mentions), max_mentions_per_message)]

        for i, chunk in enumerate(user_mention_chunks):
            mention_text = "".join(chunk) # Join without spaces for compact mentions
            
            # For subsequent messages, adjust header
            current_header = full_message_header
            if i > 0:
                current_header = f"{EMOJI_PAGER} *Continuing broadcast \\(part {i+1}\\):*\\n\\n{escaped_custom_message}\\n\\n*Tagging:* "

            message_to_send = current_header + mention_text
            
            # Ensure the message (header + mentions) doesn\'t exceed limits.
            # This is a simplified check; precise calculation is harder due to UTF-8.
            if len(message_to_send) > 4000: # Leave some buffer
                 # This part needs more robust chunking of the message_to_send itself if it\'s too long
                await safe_markdown_message(update, f"{EMOJI_ERROR} Message part {i+1} is too long to send with all mentions\\. Try a shorter message or fewer people\\.", logger, parse_mode=ParseMode.MARKDOWN_V2)
                continue


            try:
                await safe_markdown_message(update, message_to_send, logger, parse_mode=ParseMode.MARKDOWN_V2, disable_notification=False)
            except BadRequest as e:
                logger.error(f"BadRequest during mention_all part {i+1} for chat {chat_id}: {e}")
                await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn\\'t send part {i+1} of the mentions\\. Telegram said: {escape_markdown_v2(str(e))}", logger, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e:
                logger.error(f"Unexpected error during mention_all part {i+1} for chat {chat_id}: {e}")
                await safe_markdown_message(update, f"{EMOJI_ERROR} An unexpected error occurred sending part {i+1} of the mentions\\.", logger, parse_mode=ParseMode.MARKDOWN_V2)
        
        if callable(_update_stats): _update_stats(command="mentionall", success=True, chat_id=chat_id, users_mentioned=len(mentions))

    except Exception as e:
        logger.error(f"Failed to execute mention_all for chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_SKULL} Something went sideways trying to yell at everyone\\. Check the logs, admin\\!", logger, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mentionall", error_occurred=str(e), chat_id=chat_id)

@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("mention")
@admin_required
@error_handler
async def mention_specific(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mentions specific users with a message.""" # Simplified docstring
    chat_id = update.effective_chat.id
    args = context.args
    db = await _get_db_instance(context) # Assuming you have this helper
    _update_stats = context.bot_data.get('update_stats')

    if not args or len(args) < 2: # Need at least one user and a message
        await safe_markdown_message(update,
                                    f"{EMOJI_QUESTION} Who am I yelling at, and what am I saying\\? Use: `{escape_markdown_v2('/mention @user1 [@user2...] <message>')}`",
                                    logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mention_specific", error_occurred="not_enough_args", chat_id=chat_id)
        return

    target_usernames_or_ids = []
    message_parts = []
    
    # Separate users from the message
    # Users are expected to be at the beginning, message at the end
    # A simple heuristic: if an arg starts with @ or is a number (potential ID), it\'s a user
    # This can be made more robust.
    
    message_start_index = 0
    for i, arg_val in enumerate(args): # Renamed arg to arg_val to avoid conflict with context.args
        if arg_val.startswith('@') or arg_val.isdigit():
            target_usernames_or_ids.append(arg_val)
            message_start_index = i + 1
        else:
            # First non-@ or non-digit arg, assume message starts here
            break 
    
    if not target_usernames_or_ids:
        await safe_markdown_message(update,
                                    f"{EMOJI_QUESTION} You forgot to tell me *who* to target\\! Use: `{escape_markdown_v2('/mention @user1 <message>')}`",
                                    logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mention_specific", error_occurred="no_targets", chat_id=chat_id)
        return

    if message_start_index >= len(args):
        await safe_markdown_message(update,
                                    f"{EMOJI_QUESTION} And what exactly do you want me to *say* to them\\? Message is missing\\.",
                                    logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mention_specific", error_occurred="no_message", chat_id=chat_id)
        return
        
    message_parts = args[message_start_index:]
    custom_message = escape_markdown_v2(" ".join(message_parts))

    mentions = []
    not_found_users = []

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot resolve users by username\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        # Continue with IDs if any, or just fail if all were usernames
        # For simplicity, we\'ll mostly rely on direct mentions if DB is down.
        # However, resolving User ID from @username is better via DB for persistence.

    for target_arg in target_usernames_or_ids:
        user_id = None
        display_name = target_arg # Default to the argument itself

        if target_arg.startswith('@'):
            username_to_find = target_arg[1:]
            if db:
                user_doc = await db.get_user_by_username(username_to_find)
                if user_doc:
                    user_id = user_doc['user_id']
                    display_name = user_doc.get('first_name', username_to_find) # Or full name
                else:
                    not_found_users.append(target_arg)
                    continue # Skip to next arg if user not found in DB
            else: # DB not available, can\'t resolve @username to ID reliably for tg://user link
                  # We can try to use the @username directly in the message, but it won\'t be a "silent" mention.
                  # For now, let\'s treat as not found if DB is down and it\'s a username.
                not_found_users.append(f"{target_arg} \\(DB unavailable for lookup\\)")
                continue
        elif target_arg.isdigit():
            user_id = int(target_arg)
            # Optionally, try to get a display name from DB if available
            if db:
                user_doc = await db.get_user(user_id)
                if user_doc:
                    display_name = user_doc.get('first_name', f"User {user_id}")

        if user_id:
            mentions.append(f"[{escape_markdown_v2(display_name)}](tg://user?id={user_id})")
        elif not target_arg.startswith('@'): # If it wasn\'t a username and not a digit, it\'s an unknown format
            not_found_users.append(target_arg)


    if not mentions:
        await safe_markdown_message(update,
                                    f"{EMOJI_THINKING} Couldn\\'t find anyone to target from your list: {escape_markdown_v2(', '.join(not_found_users))}",
                                    logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mention_specific", error_occurred="all_targets_not_found", chat_id=chat_id)
        return

    mention_string = ", ".join(mentions)
    full_message = f"{EMOJI_TARGET} {mention_string}, {custom_message} {EMOJI_FIRE}"

    await safe_markdown_message(update, full_message, logger, parse_mode=ParseMode.MARKDOWN_V2)

    if not_found_users:
        await safe_markdown_message(update,
                                    f"{EMOJI_QUESTION} By the way, I couldn\\'t find these chumps: {escape_markdown_v2(', '.join(not_found_users))}",
                                    logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2) # Send as a follow-up
    
    if callable(_update_stats): _update_stats(command="mention_specific", success=True, chat_id=chat_id, users_mentioned=len(mentions))


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("pin_nukem")
@admin_required
@error_handler
async def pin_nukem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pins a message in the chat.""" # Simplified docstring
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    message_id_to_pin = None
    pin_message_text = ""

    if update.message.reply_to_message:
        message_id_to_pin = update.message.reply_to_message.message_id
        pin_message_text = "That\\. Right there\\. That\\'s important\\."
        if context.args: # Custom message for pinning replied-to message
            pin_message_text = " ".join(context.args)
    elif context.args:
        # Pin the command message itself after sending a custom message
        # First, send Duke\'s commentary, then pin that message.
        # This is a bit tricky as we need the ID of the bot\'s *own* message.
        duke_commentary = " ".join(context.args)
        sent_message = await safe_markdown_message(update, f"{EMOJI_PUSHPIN} {escape_markdown_v2(duke_commentary)} {EMOJI_TOOLS}", logger, parse_mode=ParseMode.MARKDOWN_V2)
        if sent_message:
            message_id_to_pin = sent_message.message_id
        pin_message_text = duke_commentary # Already included in the sent message
    else:
        await safe_markdown_message(update, f"{EMOJI_QUESTION} Whatcha want me to pin\\? Reply to a message or give me some text for a new pinned message\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="pin_nukem", error_occurred="no_target_or_text", chat_id=chat_id)
        return

    if message_id_to_pin:
        try:
            await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_id_to_pin, disable_notification=False)
            # Confirmation is tricky if we pinned the bot\'s own message that contained the text.
            # If we pinned a reply, a separate confirmation is good.
            if update.message.reply_to_message: # Only send confirmation if we pinned a reply
                 await safe_markdown_message(update, f"{EMOJI_PIN} Pinned it like a grenade to a grunt\\! {escape_markdown_v2(pin_message_text)}", logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="pin_nukem", success=True, chat_id=chat_id)
        except TelegramError as e:
            logger.error(f"Failed to pin message {message_id_to_pin} in chat {chat_id}: {e}")
            await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn\\'t pin it\\. Telegram said: {escape_markdown_v2(str(e))}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="pin_nukem", error_occurred=str(e), chat_id=chat_id)
    elif not context.args: # This case should ideally be caught earlier if no reply and no args
        await safe_markdown_message(update, f"{EMOJI_THINKING} Still don\\'t know what to pin, slick\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="pin_nukem", error_occurred="pin_target_resolution_failed", chat_id=chat_id)


@chat_type_allowed(['group', 'supergroup', 'private'])
@command_cooldown("info")
@error_handler
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides information about the project.""" # Simplified docstring
    _update_stats = context.bot_data.get('update_stats')
    topic = " ".join(context.args).lower() if context.args else "general"
    user_id = update.effective_user.id if update.effective_user else None

    info_text = PROJECT_INFO.get(topic)

    if info_text:
        # Replace placeholders like {DUKE_QUOTE}
        if "{DUKE_QUOTE}" in info_text:
            info_text = info_text.replace("{DUKE_QUOTE}", random.choice(NUKEM_QUOTES))
        
        # Ensure all parts of info_text are properly escaped if they contain MarkdownV2 special chars
        # Assuming PROJECT_INFO values are pre-escaped or safe. If not, escape them here.
        # Example: info_text = escape_markdown_v2(info_text) if it\'s not pre-formatted.
        # Since PROJECT_INFO can contain markdown, we must be careful.
        # Let\'s assume PROJECT_INFO values are already MarkdownV2 formatted.

        await safe_markdown_message(update, f"{EMOJI_INFO} {info_text}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2) # Assuming info_text is already MarkdownV2 safe
        if callable(_update_stats): _update_stats(command="info", success=True, topic=topic, user_id=user_id)
    else:
        available_topics = [escape_markdown_v2(t) for t in PROJECT_INFO.keys()]
        await safe_markdown_message(update,
                                    f"{EMOJI_QUESTION} Don\\'t have intel on `{escape_markdown_v2(topic)}`\\. Try one of these, maggot: {', '.join(available_topics)}",
                                    logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="info", error_occurred="topic_not_found", topic=topic, user_id=user_id)


@chat_type_allowed(['group', 'supergroup', 'private'])
@command_cooldown("nukem_quote")
@error_handler
async def nukem_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a random Nukem quote.""" # Simplified docstring
    _update_stats = context.bot_data.get('update_stats')
    quote = random.choice(NUKEM_QUOTES)
    # Quotes are assumed to be plain text and need escaping for MarkdownV2
    await safe_markdown_message(update, f"{EMOJI_BRAIN} {escape_markdown_v2(quote)} {EMOJI_SUNGLASSES}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    if callable(_update_stats): _update_stats(command="nukem_quote", success=True, user_id=update.effective_user.id if update.effective_user else None)


@chat_type_allowed(['group', 'supergroup', 'private'])
@command_cooldown("rate_my_play")
@error_handler
async def rate_my_play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rates the user\'s described play.""" # Simplified docstring
    _update_stats = context.bot_data.get('update_stats')
    user_id = update.effective_user.id if update.effective_user else None
    play_description = " ".join(context.args)

    if not play_description:
        await safe_markdown_message(update, f"{EMOJI_QUESTION} Whatcha do\\? Describe your play, hotshot\\! `{escape_markdown_v2('/rate_my_play <your glorious moment>')}`", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="rate_my_play", error_occurred="no_description", user_id=user_id)
        return

    rating = random.choice(NUKEM_RATINGS)
    reaction = random.choice(NUKEM_REACTIONS_POSITIVE) if "Awesome" in rating or "Godlike" in rating else random.choice(NUKEM_REACTIONS_NEGATIVE)
    
    # Escape user-provided description and other parts if they aren\'t already safe
    escaped_description = escape_markdown_v2(play_description)
    
    response_message = (
        f"{EMOJI_STAR} So you think you\\'re a badass, huh\\? Let\\'s see\\.\\.\\.\n"
        f"You said: \\\"_{escaped_description}_\\\"\\n\\n"
        f"{EMOJI_ROBOT} The Duke rates your play: *{escape_markdown_v2(rating)}*\\!\n"
        f"{escape_markdown_v2(reaction)} {EMOJI_SUNGLASSES}"
    )
    await safe_markdown_message(update, response_message, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    if callable(_update_stats): _update_stats(command="rate_my_play", success=True, rating=rating, user_id=user_id)


@chat_type_allowed(['group', 'supergroup', 'private'])
@command_cooldown("alien_scan")
@error_handler
async def alien_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Performs an 'alien scan'.""" # Simplified docstring
    _update_stats = context.bot_data.get('update_stats')
    report = random.choice(ALIEN_SCAN_REPORTS)
    # Reports are assumed plain text and need escaping
    scan_message = f"{EMOJI_ALIEN} *Initiating Alien Scan\\.\\.\\.* {EMOJI_EYES}\\n\\n{escape_markdown_v2(report)}"
    await safe_markdown_message(update, scan_message, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    if callable(_update_stats): _update_stats(command="alien_scan", success=True, user_id=update.effective_user.id if update.effective_user else None)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("arsenal")
@error_handler
async def arsenal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays Duke\'s arsenal or details of a specific weapon."""
    _update_stats = context.bot_data.get('update_stats')
    user_id = update.effective_user.id if update.effective_user else None
    args = context.args

    if not args:
        # Display all weapons
        response_parts = [f"{EMOJI_TOOLS} *DUKE\\'S ARSENAL \\- PICK YOUR POISON:* {EMOJI_NUKE}\\n\\n"]
        for weapon, details in DUKE_ARSENAL.items():
            response_parts.append(f"`{escape_markdown_v2(weapon)}`: {escape_markdown_v2(details['description_short'])}\\n")
        response_parts.append(f"\\nType `{escape_markdown_v2('/arsenal <weapon_name>')}` for more intel on a specific piece of hardware\\.")
        
        full_message = "".join(response_parts)
        message_chunks = chunk_message(full_message, 4096) # Max message length for Telegram

        for i, chunk in enumerate(message_chunks):
            header = f"{EMOJI_PACKAGE} *Arsenal Listing Part {i+1}/{len(message_chunks)}*\\n" if len(message_chunks) > 1 else ""
            await safe_markdown_message(update, header + chunk, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="arsenal", success=True, action="list_all", user_id=user_id)

    else:
        weapon_name_query = " ".join(args).lower()
        found_weapon = None
        # Allow partial matches or case-insensitive search
        for weapon_key in DUKE_ARSENAL:
            if weapon_name_query == weapon_key.lower():
                found_weapon = weapon_key
                break
        
        if found_weapon:
            details = DUKE_ARSENAL[found_weapon]
            response = (
                f"{details.get('emoji', EMOJI_TOOLS)} *{escape_markdown_v2(found_weapon.upper())}* {EMOJI_FIRE}\\n"
                f"*Type:* {escape_markdown_v2(details['type'])}\\n"
                f"*Description:* {escape_markdown_v2(details['description_full'])}\\n"
                f"*Duke\\'s Rating:* {escape_markdown_v2(details['rating_duke'])} {EMOJI_STAR}\\n"
                f"*Sound Off:* \\\"_{escape_markdown_v2(details['quote'])}_\\\" {EMOJI_SPEECH_BUBBLE}"
            )
            await safe_markdown_message(update, response, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="arsenal", success=True, action="show_weapon", weapon=found_weapon, user_id=user_id)
        else:
            await safe_markdown_message(update, f"{EMOJI_QUESTION} Ain\\'t got no weapon called `{escape_markdown_v2(weapon_name_query)}` in my stash\\. Try `{escape_markdown_v2('/arsenal')}` to see what I got\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="arsenal", error_occurred="weapon_not_found", weapon_query=weapon_name_query, user_id=user_id)


# --- User Management & Karma ---
@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("list_users",_bypass_admin=True) # Allow non-admins to use, but might show limited info
@admin_required(fetch_chat_admins=True) # Decorator now fetches admins if not already in context
@error_handler
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists users in the chat with karma and warnings.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    requesting_user_id = update.effective_user.id
    
    # Check if the requesting user is an admin (using context.chat_data.get('chat_admins'))
    # The @admin_required decorator should handle this, but double-checking or specific logic can be here.
    # For now, assume @admin_required grants access.

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot list users\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="list_users", error_occurred="db_not_connected", chat_id=chat_id)
        return

    try:
        user_docs = await db.get_all_users_in_chat(chat_id)
        if not user_docs:
            await safe_markdown_message(update, f"{EMOJI_THINKING} No users found in this chat\\'s records\\. Maybe it\\'s a ghost town\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="list_users", error_occurred="no_users_in_db", chat_id=chat_id)
            return

        response_parts = [f"{EMOJI_SCROLL} *User Roster & Standing for this Chat:* {EMOJI_LEADERBOARD}\\n"]
        active_users = 0
        for user_doc in user_docs:
            user_id = user_doc.get('user_id')
            username = user_doc.get('username', 'N/A')
            first_name = user_doc.get('first_name', 'Unknown Soldier')
            last_name = user_doc.get('last_name', '')
            display_name = first_name + (f" {last_name}" if last_name else "")
            
            karma = user_doc.get('karma', 0)
            warnings_count = len(user_doc.get('warnings', []))
            
            # Check membership status if possible (might require bot to be admin or specific permissions)
            # This is a more advanced feature. For now, list all from DB.
            # try:
            #     chat_member = await context.bot.get_chat_member(chat_id, user_id)
            #     if chat_member.status not in [ChatMember.LEFT, ChatMember.KICKED]:
            #         active_users += 1
            #     else:
            #         continue # Skip users not in chat
            # except TelegramError: # User might have blocked bot or other issue
            #     logger.warning(f"Could not verify membership for user {user_id} in chat {chat_id}")
            #     # Decide whether to show them or not. For now, show if in DB.
            
            active_users +=1 # Simplified: count all in DB for now

            karma_str = f"{KARMA_EMOJI} {karma}"
            warnings_str = f"{EMOJI_WARNING} {warnings_count}" if warnings_count > 0 else f"{EMOJI_SUCCESS} 0 warnings"
            
            user_line = f"\\- `{escape_markdown_v2(display_name)}` \\(@{escape_markdown_v2(username)} \\| ID: `{user_id}`\\): {karma_str}, {warnings_str}\\n"
            response_parts.append(user_line)

        if active_users == 0 :
             await safe_markdown_message(update, f"{EMOJI_THINKING} No active users found in this chat\\'s records that I can see\\. Maybe it\\'s a ghost town\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
             if callable(_update_stats): _update_stats(command="list_users", error_occurred="no_active_users_listed", chat_id=chat_id)
             return

        response_parts.append(f"\\nTotal users on record: {len(user_docs)}") # Total active users shown: {active_users}
        
        full_message_text_users = "".join(response_parts)
        message_chunks_users = chunk_message(full_message_text_users, 4096)

        for i, chunk in enumerate(message_chunks_users):
            header = f"{EMOJI_PAGER} *User List Part {i+1}/{len(message_chunks_users)}*\\n" if len(message_chunks_users) > 1 else ""
            await safe_markdown_message(update, header + chunk, logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2) # reply_to=False for subsequent parts
        
        if callable(_update_stats): _update_stats(command="list_users", success=True, users_listed=len(user_docs), chat_id=chat_id)

    except DatabaseError as e: # type: ignore
        logger.error(f"Database error in list_users for chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while fetching users\\. Try again later, maggot\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="list_users", error_occurred=f"db_error: {str(e)}", chat_id=chat_id)
    except Exception as e:
        logger.error(f"Unexpected error in list_users for chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_SKULL} Something blew up trying to list users\\. The tech grunts are on it \\(maybe\\)\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="list_users", error_occurred=f"unexpected: {str(e)}", chat_id=chat_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("sync_users", 300) # 5 min cooldown
@admin_required(fetch_chat_admins=True)
@error_handler
async def sync_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Synchronizes chat administrators with the database.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    
    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot sync users\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="sync_users", error_occurred="db_not_connected", chat_id=chat_id)
        return

    current_chat_admins = context.chat_data.get('chat_admins', []) # Filled by @admin_required
    if not current_chat_admins:
        # This case should ideally be handled by admin_required or it should attempt to fetch here.
        # For now, assume admin_required populates it or fails the command.
        # If admin_required doesn't populate, we might need to call context.bot.get_chat_administrators
        try:
            admin_members = await context.bot.get_chat_administrators(chat_id)
            current_chat_admins = [admin.user.id for admin in admin_members]
            context.chat_data['chat_admins'] = current_chat_admins # Cache it
        except TelegramError as e:
            logger.error(f"Could not fetch administrators for chat {chat_id} during sync: {e}")
            await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn\\'t fetch admin list to sync\\. Telegram said: {escape_markdown_v2(str(e))}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="sync_users", error_occurred=f"fetch_admin_error: {str(e)}", chat_id=chat_id)
            return
            
    if not current_chat_admins: # Still no admins after trying to fetch
        await safe_markdown_message(update, f"{EMOJI_THINKING} No administrators found for this chat to sync\\. Are there any\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="sync_users", error_occurred="no_admins_found_to_sync", chat_id=chat_id)
        return

    # Also, consider syncing all members if the bot has permissions, not just admins.
    # This is a more complex operation. For now, focusing on admins.
    # A full member sync would involve iterating through all users the bot knows in the chat.
    # This is not directly possible without being an admin and potentially high API usage.
    # A common pattern is to update users when they send a message (see message_tracker).

    # Syncing admins: Ensure they are in the DB and marked as admin.
    # This example focuses on adding/updating admins found via get_chat_administrators.
    # A more complete sync might involve removing admin status from users no longer admin.

    synced_count = 0
    newly_added_admins = []
    already_admin_in_db = []
    failed_to_sync = []

    admin_user_objects = []
    try:
        admin_members_for_details = await context.bot.get_chat_administrators(chat_id)
        admin_user_objects = [admin.user for admin in admin_members_for_details]
    except TelegramError as e:
        logger.error(f"Error fetching admin details for sync in chat {chat_id}: {e}")
        # Proceed with IDs if details fetch fails, but names will be missing for new admins

    for admin_id in current_chat_admins:
        user_obj = next((u for u in admin_user_objects if u.id == admin_id), None)
        username = user_obj.username if user_obj else None
        first_name = user_obj.first_name if user_obj else f"Admin_{admin_id}"
        last_name = user_obj.last_name if user_obj else None

        try:
            user_doc = await db.get_user(admin_id)
            update_data = {
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'is_chat_admin': True, # Mark as admin in this chat
                'last_seen': datetime.datetime.now(datetime.timezone.utc)
            }
            if user_doc:
                await db.update_user(admin_id, update_data)
                if not user_doc.get('is_chat_admin'): # Was not marked as admin before
                     newly_added_admins.append(username or first_name)
                else:
                    already_admin_in_db.append(username or first_name)
            else:
                # Add new admin user
                # Initial karma, warnings etc. can be set here if needed
                initial_data = {
                    'karma': 0, 
                    'warnings': [], 
                    'is_chat_admin': True,
                    'join_date': datetime.datetime.now(datetime.timezone.utc) # approx join date
                }
                full_user_data = {**update_data, **initial_data}
                await db.add_user(admin_id, chat_id, full_user_data) # Ensure add_user can take full_user_data
                newly_added_admins.append(username or first_name)
            synced_count += 1
        except DatabaseError as e: # type: ignore
            logger.error(f"DB error syncing admin {admin_id} in chat {chat_id}: {e}")
            failed_to_sync.append(username or str(admin_id))
        except Exception as e:
            logger.error(f"Unexpected error syncing admin {admin_id} in chat {chat_id}: {e}")
            failed_to_sync.append(f"{username or str(admin_id)} \\(unexpected error\\)")


    response_parts = [f"{EMOJI_CYCLE} *Admin Sync Report for this Chat:* {EMOJI_CHECKMARK}\\n"]
    response_parts.append(f"Total admins found in chat: {len(current_chat_admins)}\\n")
    response_parts.append(f"Successfully synced with DB: {synced_count}\\n")
    if newly_added_admins:
        response_parts.append(f"{EMOJI_GREEN_CIRCLE} New admins registered/marked: {escape_markdown_v2(', '.join(newly_added_admins))}\\n")
    if already_admin_in_db:
        response_parts.append(f"{EMOJI_YELLOW_CIRCLE} Already known admins updated: {escape_markdown_v2(', '.join(already_admin_in_db))}\\n")
    if failed_to_sync:
        response_parts.append(f"{EMOJI_RED_CIRCLE} Failed to sync: {escape_markdown_v2(', '.join(failed_to_sync))}\\n")

    final_response = "".join(response_parts)
    message_chunks = chunk_message(final_response, 4096)
    for i, chunk_val in enumerate(message_chunks): # Renamed chunk to chunk_val
        # No separate header per chunk for sync report, it\'s usually short.
        # If it can be long, add similar header logic as list_users.
        # For now, assume it\'s one message.
        # header = f"{EMOJI_PAGER} *Sync Report Part {i+1}/{len(message_chunks)}*\\n" if len(message_chunks) > 1 else ""
        # await safe_markdown_message(update, header + chunk_val, logger, parse_mode=ParseMode.MARKDOWN_V2)
        await safe_markdown_message(update, chunk_val, logger, parse_mode=ParseMode.MARKDOWN_V2)


    if callable(_update_stats): _update_stats(command="sync_users", success=True, synced_count=synced_count, chat_id=chat_id, failed_count=len(failed_to_sync))


@chat_type_allowed(['group', 'supergroup', 'private']) # Allow checking own karma in private
@command_cooldown("karma")
@error_handler
async def get_karma_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gets the karma of a user or the command sender.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id # Can be None in private chat with bot
    requesting_user_id = update.effective_user.id

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot fetch karma\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_karma", error_occurred="db_not_connected", user_id=requesting_user_id)
        return

    target_user_id, target_username_display, user_doc = await _get_target_user_info(update, context, db)

    if not target_user_id:
        # _get_target_user_info already sent a message if args were provided but invalid
        if not context.args: # Only send if no args were given (meaning target was self and failed)
             await safe_markdown_message(update, f"{EMOJI_QUESTION} Couldn\\'t figure out who you\\'re asking about\\. Try replying or using @username\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_karma", error_occurred="target_not_found", user_id=requesting_user_id)
        return

    if user_doc:
        karma = user_doc.get('karma', 0)
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        message = f"{KARMA_EMOJI} {name_to_show} has {karma} karma points\\. "
        if karma > 100: message += "Damn, son\\! Impressive\\!"
        elif karma > 50: message += "Not bad, not bad at all\\."
        elif karma > 0: message += "Keep it up, maggot\\."
        elif karma == 0: message += "Perfectly neutral\\. Or just new\\."
        elif karma < -50: message += "Ouch\\. Someone\\'s been naughty\\."
        else: message += "Better watch your step\\."
        
        await safe_markdown_message(update, message, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_karma", success=True, target_user_id=target_user_id, karma=karma, user_id=requesting_user_id)
    else:
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        await safe_markdown_message(update, f"{EMOJI_THINKING} Don\\'t have {name_to_show} in my records for this chat, or they\\'re too new to have karma\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_karma", error_occurred="user_not_in_db", target_user_id=target_user_id, user_id=requesting_user_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("give_karma")
@admin_required(fetch_chat_admins=True) # Only admins can give karma
@error_handler
async def give_karma_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gives karma to a user.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    admin_user_id = update.effective_user.id

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot give karma\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="give_karma", error_occurred="db_not_connected", admin_user_id=admin_user_id)
        return

    # We need context.args for the target user and optionally reason
    # _get_target_user_info expects the target as the first arg if not a reply.
    # We need to adjust args for reason if present.
    
    target_user_id, target_username_display, user_doc = await _get_target_user_info(update, context, db) # This will use first arg for target
    
    if not target_user_id:
        # Message already sent by _get_target_user_info if args were bad
        if not (update.message and update.message.reply_to_message) and not context.args:
             await safe_markdown_message(update, f"{EMOJI_QUESTION} Who gets the karma\\? Reply to their message or use `{escape_markdown_v2('/give_karma @username [reason]')}`\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="give_karma", error_occurred="target_not_found", admin_user_id=admin_user_id)
        return

    if target_user_id == admin_user_id:
        await safe_markdown_message(update, f"{EMOJI_ROBOT} Trying to give yourself karma, eh\\? Narcissist\\! {EMOJI_SUNGLASSES}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="give_karma", error_occurred="self_karma_attempt", admin_user_id=admin_user_id)
        return

    reason = ""
    if context.args:
        # If target was from reply, all args are reason.
        # If target was from args[0], then args[1:] is reason.
        if update.message and update.message.reply_to_message:
            reason = " ".join(context.args)
        elif len(context.args) > 1:
            reason = " ".join(context.args[1:])
    
    escaped_reason = f" Reason: {escape_markdown_v2(reason)}" if reason else ""

    if user_doc:
        try:
            new_karma = await db.update_karma(target_user_id, 1) # Increment by 1
            name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
            await safe_markdown_message(update, f"{EMOJI_CHART_UP} Gave +1 karma to {name_to_show}\\. They now have {new_karma} karma\\.{escaped_reason}", logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2) # reply_to=False to not make it a reply to the command
            if callable(_update_stats): _update_stats(command="give_karma", success=True, target_user_id=target_user_id, new_karma=new_karma, admin_user_id=admin_user_id, reason=reason)
        except DatabaseError as e: # type: ignore
            logger.error(f"DB error giving karma to {target_user_id}: {e}")
            await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while giving karma\\. Try again\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="give_karma", error_occurred=f"db_error: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    else:
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        await safe_markdown_message(update, f"{EMOJI_THINKING} Can\\'t find {name_to_show} in my records for this chat\\. Are they real\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="give_karma", error_occurred="user_not_in_db", target_user_id=target_user_id, admin_user_id=admin_user_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("remove_karma")
@admin_required(fetch_chat_admins=True) # Only admins can remove karma
@error_handler
async def remove_karma_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes karma from a user.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    admin_user_id = update.effective_user.id

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot remove karma\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="remove_karma", error_occurred="db_not_connected", admin_user_id=admin_user_id)
        return

    target_user_id, target_username_display, user_doc = await _get_target_user_info(update, context, db)

    if not target_user_id:
        if not (update.message and update.message.reply_to_message) and not context.args:
            await safe_markdown_message(update, f"{EMOJI_QUESTION} Who loses the karma\\? Reply or use `{escape_markdown_v2('/remove_karma @username [reason]')}`\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="remove_karma", error_occurred="target_not_found", admin_user_id=admin_user_id)
        return
        
    if target_user_id == admin_user_id:
        await safe_markdown_message(update, f"{EMOJI_ROBOT} Trying to dock your own pay\\? Weirdo\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="remove_karma", error_occurred="self_karma_attempt", admin_user_id=admin_user_id)
        return

    reason = ""
    if context.args:
        if update.message and update.message.reply_to_message:
            reason = " ".join(context.args)
        elif len(context.args) > 1:
            reason = " ".join(context.args[1:])
    escaped_reason = f" Reason: {escape_markdown_v2(reason)}" if reason else ""


    if user_doc:
        try:
            new_karma = await db.update_karma(target_user_id, -1) # Decrement by 1
            name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
            await safe_markdown_message(update, f"{EMOJI_CHART_DOWN} Took \\-1 karma from {name_to_show}\\. They now have {new_karma} karma\\.{escaped_reason}", logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="remove_karma", success=True, target_user_id=target_user_id, new_karma=new_karma, admin_user_id=admin_user_id, reason=reason)
        except DatabaseError as e: # type: ignore
            logger.error(f"DB error removing karma from {target_user_id}: {e}")
            await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while removing karma\\. Try again\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="remove_karma", error_occurred=f"db_error: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    else:
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        await safe_markdown_message(update, f"{EMOJI_THINKING} Can\\'t find {name_to_show} in my records for this chat\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="remove_karma", error_occurred="user_not_in_db", target_user_id=target_user_id, admin_user_id=admin_user_id)


# --- Moderation ---
@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("warn")
@admin_required(fetch_chat_admins=True)
@error_handler
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Warns a user, stores the warning, and notifies them.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    admin_user_id = update.effective_user.id
    admin_username = update.effective_user.username or f"Admin {admin_user_id}"

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot issue warning\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="warn", error_occurred="db_not_connected", admin_user_id=admin_user_id)
        return

    target_user_id, target_username_display, user_doc = await _get_target_user_info(update, context, db)

    if not target_user_id:
        if not (update.message and update.message.reply_to_message) and not context.args:
             await safe_markdown_message(update, f"{EMOJI_QUESTION} Who gets the warning\\? Reply or use `{escape_markdown_v2('/warn @username <reason>')}`\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="warn", error_occurred="target_not_found", admin_user_id=admin_user_id)
        return

    if target_user_id == admin_user_id:
        await safe_markdown_message(update, f"{EMOJI_ROBOT} Trying to warn yourself\\? You been drinkin\\' my beer again\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="warn", error_occurred="self_warn_attempt", admin_user_id=admin_user_id)
        return
        
    # Check if target is also an admin
    # chat_admins = context.chat_data.get('chat_admins', [])
    # if target_user_id in chat_admins:
    #     await safe_markdown_message(update, f"{EMOJI_SHIELD} Woah there, hotshot. Can\\'t warn another admin. You gotta settle that in the ring.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    #     if callable(_update_stats): _update_stats(command="warn", error_occurred="target_is_admin", target_user_id=target_user_id, admin_user_id=admin_user_id)
    #     return

    reason = "No reason specified"
    if context.args:
        if update.message and update.message.reply_to_message: # Target from reply, all args are reason
            reason = " ".join(context.args)
        elif len(context.args) > 1: # Target from args[0], reason from args[1:]
            reason = " ".join(context.args[1:])
    
    if not user_doc: # If user not in DB, add them first
        # This might happen if a user is in chat but hasn\'t interacted or been synced
        # We need their basic info to add them.
        # For simplicity, if _get_target_user_info didn\'t find them in DB, we might not have full details.
        # Let\'s try to add them with what we have.
        # A better approach: ensure message_tracker adds users on first message.
        logger.info(f"User {target_user_id} not in DB. Attempting to add before warning.")
        # We need chat_id to add user to a specific chat\'s user list in some DB designs
        # For now, assume add_user can handle it or it\'s a global user record.
        # This part needs robust handling of adding a new user on-the-fly.
        # For now, let\'s assume if user_doc is None, we can\'t reliably warn.
        # A more robust _get_target_user_info would try to fetch from Telegram API if not in DB
        # and add to DB.
        
        # Let\'s try to fetch the user if not in DB to get their details
        try:
            chat_member_target = await context.bot.get_chat_member(chat_id, target_user_id)
            target_tg_user = chat_member_target.user
            await db.add_user(
                user_id=target_tg_user.id,
                chat_id=chat_id, # Important for chat-specific context
                user_data={
                    'username': target_tg_user.username,
                    'first_name': target_tg_user.first_name,
                    'last_name': target_tg_user.last_name,
                    'karma': 0,
                    'warnings': [],
                    'is_chat_admin': target_user_id in context.chat_data.get('chat_admins', []), # Check if they are admin
                    'join_date': datetime.datetime.now(datetime.timezone.utc) # approx join date
                }
            )
            user_doc = await db.get_user(target_user_id) # Re-fetch
            if not user_doc: # Still not found after add attempt
                 raise DatabaseError("Failed to add and retrieve user for warning.") # type: ignore
        except (TelegramError, DatabaseError, Exception) as e: # type: ignore
            logger.error(f"Failed to fetch/add user {target_user_id} to DB before warning: {e}")
            await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn\\'t process user {escape_markdown_v2(target_username_display or str(target_user_id))} for warning\\. They might be new or there was a DB hiccup\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="warn", error_occurred=f"add_user_fail: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
            return

    # Now user_doc should exist
    try:
        warning_doc = await db.add_warning(target_user_id, reason, admin_user_id, admin_username)
        warnings_count = len((await db.get_user(target_user_id)).get('warnings', [])) # Re-fetch to get updated count
        
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        
        warn_message_to_chat = (
            f"{EMOJI_WARNING} {name_to_show} has been warned by {escape_markdown_v2(admin_username)}\\! "
            f"Reason: {escape_markdown_v2(reason)}\\. "
            f"This is warning \\#{warnings_count}\\. Watch it, pal\\!"
        )
        await safe_markdown_message(update, warn_message_to_chat, logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)

        # Optionally, try to DM the user (if bot can initiate DMs)
        try:
            dm_message = (
                f"{EMOJI_WARNING} You have received a warning in chat: {escape_markdown_v2(update.effective_chat.title if update.effective_chat else 'Unknown Chat')}\\.\\n"
                f"Reason: {escape_markdown_v2(reason)}\\n"
                f"Issued by: {escape_markdown_v2(admin_username)}\\n"
                f"This is your warning \\#{warnings_count}\\. Repeated offenses may lead to further action\\."
            )
            await context.bot.send_message(chat_id=target_user_id, text=dm_message, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramError as e:
            logger.warning(f"Could not DM user {target_user_id} about their warning: {e}")
            await safe_markdown_message(update, f"\\(Couldn\\'t DM {name_to_show} about the warning\\. They might have DMs blocked or something\\.\\)", logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)

        if callable(_update_stats): _update_stats(command="warn", success=True, target_user_id=target_user_id, admin_user_id=admin_user_id, reason=reason, warnings_count=warnings_count)

    except DatabaseError as e: # type: ignore
        logger.error(f"DB error warning user {target_user_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while issuing warning\\. Try again\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="warn", error_occurred=f"db_error: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    except Exception as e:
        logger.error(f"Unexpected error warning user {target_user_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_SKULL} Something blew up trying to warn users\\. The tech grunts are on it \\(maybe\\)\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="warn", error_occurred=f"unexpected: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("unwarn")
@admin_required(fetch_chat_admins=True)
@error_handler
async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes the last warning for a user.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    admin_user_id = update.effective_user.id

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot remove warning\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unwarn", error_occurred="db_not_connected", admin_user_id=admin_user_id)
        return

    target_user_id, target_username_display, user_doc = await _get_target_user_info(update, context, db)

    if not target_user_id:
        if not (update.message and update.message.reply_to_message) and not context.args:
            await safe_markdown_message(update, f"{EMOJI_QUESTION} Whose warning gets removed\\? Reply or use `{escape_markdown_v2('/unwarn @username')}`\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unwarn", error_occurred="target_not_found", admin_user_id=admin_user_id)
        return

    if not user_doc or not user_doc.get('warnings'):
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        await safe_markdown_message(update, f"{EMOJI_THINKING} {name_to_show} has no warnings on record to remove\\. Clean slate\\!", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unwarn", error_occurred="no_warnings_for_user", target_user_id=target_user_id, admin_user_id=admin_user_id)
        return

    try:
        removed_warning = await db.remove_last_warning(target_user_id)
        if removed_warning:
            warnings_count = len((await db.get_user(target_user_id)).get('warnings', []))
            name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
            reason_of_removed = escape_markdown_v2(removed_warning.get('reason', 'N/A'))
            
            response_message = (
                f"{EMOJI_SUCCESS} Last warning for {name_to_show} has been removed\\. "
                f"\\(Removed warning was for: \\'{reason_of_removed}\\'\\)\\. "
                f"They now have {warnings_count} warnings\\."
            )
            await safe_markdown_message(update, response_message, logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="unwarn", success=True, target_user_id=target_user_id, warnings_count=warnings_count, admin_user_id=admin_user_id)
        else: # Should be caught by earlier check, but as a fallback
            await safe_markdown_message(update, f"{EMOJI_ERROR} Something went wrong, couldn\\'t remove the warning though it seemed like there was one\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="unwarn", error_occurred="removal_failed_unexpectedly", target_user_id=target_user_id, admin_user_id=admin_user_id)

    except DatabaseError as e: # type: ignore
        logger.error(f"DB error unwarning user {target_user_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while removing warning\\. Try again\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unwarn", error_occurred=f"db_error: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    except Exception as e:
        logger.error(f"Unexpected error unwarning user {target_user_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_SKULL} Something blew up trying to unwarn users\\. The tech grunts are on it \\(maybe\\)\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unwarn", error_occurred=f"unexpected: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)


@chat_type_allowed(['group', 'supergroup', 'private']) # Allow checking own warnings in private if implemented
@command_cooldown("warnings")
@error_handler # No admin_required by default, users can check their own, admins can check others.
async def get_warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gets the warning history for a user.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    requesting_user_id = update.effective_user.id

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot fetch warnings\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_warnings", error_occurred="db_not_connected", user_id=requesting_user_id)
        return

    target_user_id, target_username_display, user_doc = await _get_target_user_info(update, context, db)

    if not target_user_id:
        if not (update.message and update.message.reply_to_message) and not context.args:
            await safe_markdown_message(update, f"{EMOJI_QUESTION} Whose warnings are we looking up\\? Reply, use @username, or type nothing for your own\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_warnings", error_occurred="target_not_found", user_id=requesting_user_id)
        return

    # Authorization: Allow users to see their own warnings. Admins can see anyone's.
    is_admin_requesting = requesting_user_id in context.chat_data.get('chat_admins', [])
    if target_user_id != requesting_user_id and not is_admin_requesting:
        await safe_markdown_message(update, f"{EMOJI_SHIELD} You can only view your own rap sheet, maggot\\. Admins can view others\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_warnings", error_occurred="unauthorized_access_attempt", target_user_id=target_user_id, user_id=requesting_user_id)
        return

    if user_doc and user_doc.get('warnings'):
        warnings_list = user_doc['warnings']
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        
        response_parts = [f"{EMOJI_MEMO} *Warning History for {name_to_show} ({len(warnings_list)} total):*\\\\n"]
        for i, warn_doc in enumerate(warnings_list):
            reason = escape_markdown_v2(warn_doc.get('reason', 'N/A'))
            date_warned_obj = warn_doc.get('timestamp')
            if isinstance(date_warned_obj, str): # Handle if timestamp is stored as ISO string
                try:
                    date_warned_obj = datetime.datetime.fromisoformat(date_warned_obj.replace("Z", "+00:00"))
                except ValueError:
                     date_warned_obj = None # Keep as None if parsing fails
            
            date_str = date_warned_obj.strftime("%Y-%m-%d %H:%M UTC") if date_warned_obj and isinstance(date_warned_obj, datetime.datetime) else "Unknown Date"
            
            admin_name = escape_markdown_v2(warn_doc.get('admin_username', 'Unknown Admin'))
            response_parts.append(f"`{i+1}`\\. {date_str} \\- By: {admin_name} \\- Reason: _{reason}_\\\\n")

        full_warning_text = "".join(response_parts)
        message_chunks = chunk_message(full_warning_text, 4096)
        for i, chunk in enumerate(message_chunks):
            header = f"{EMOJI_PAGER} *Warning List Part {i+1}/{len(message_chunks)}*\\\\n" if len(message_chunks) > 1 else ""
            # Send to user directly if it's their own warnings and in private chat, else to chat
            reply_target_chat_id = update.effective_chat.id
            # if target_user_id == requesting_user_id and update.effective_chat.type == 'private':
            #    reply_target_chat_id = target_user_id # Send as DM
            # For now, always send in current chat. DMs can be complex.
            await safe_markdown_message(update, header + chunk, logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2, chat_id_override=reply_target_chat_id)

        if callable(_update_stats): _update_stats(command="get_warnings", success=True, target_user_id=target_user_id, warnings_count=len(warnings_list), user_id=requesting_user_id)
    else:
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        await safe_markdown_message(update, f"{EMOJI_SUCCESS} {name_to_show} is squeaky clean\\. No warnings on record\\!", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="get_warnings", success=True, target_user_id=target_user_id, warnings_count=0, user_id=requesting_user_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("mute")
@admin_required(fetch_chat_admins=True)
@error_handler
async def mute_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mutes a user for a specified duration.""" # Simplified docstring
    # This command is complex due to Telegram's permissions model.
    # The bot itself needs to be an admin with rights to restrict members.
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    admin_user_id = update.effective_user.id
    db = await _get_db_instance(context) # For logging mute, if desired

    # Args: @user <duration> [reason]
    # Duration examples: 10m, 1h, 1d, 0 (for permanent until unmute)
    if not context.args or len(context.args) < 2:
        await safe_markdown_message(update, f"{EMOJI_QUESTION} Who gets gagged, for how long, and why\\? Use: `{escape_markdown_v2('/mute @username <duration> [reason]')}` \\(e\\.g\\., 10m, 1h, 1d, 0 for perm\\)\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred="not_enough_args", admin_user_id=admin_user_id)
        return

    target_arg = context.args[0]
    duration_str = context.args[1]
    reason = " ".join(context.args[2:]) if len(context.args) > 2 else "No reason specified\\."

    target_user_id, target_username_display, _ = await _get_target_user_info(update, context, db) # Pass only first arg to _get_target_user_info

    if not target_user_id:
        # _get_target_user_info sends its own message if target_arg was bad
        if not target_arg.startswith('@') and not target_arg.isdigit(): # If it wasn't even a valid format for target
             await safe_markdown_message(update, f"{EMOJI_QUESTION} Couldn\\'t figure out who `{escape_markdown_v2(target_arg)}` is\\. Try @username or reply\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred="target_not_found", admin_user_id=admin_user_id)
        return

    if target_user_id == admin_user_id:
        await safe_markdown_message(update, f"{EMOJI_ROBOT} Mute yourself\\? Go stick your head in a bucket\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred="self_mute_attempt", admin_user_id=admin_user_id)
        return
        
    # Check if target is admin
    # chat_admins = context.chat_data.get('chat_admins', [])
    # if target_user_id in chat_admins:
    #     await safe_markdown_message(update, f"{EMOJI_SHIELD} Can't mute an admin, genius. That's like trying to handcuff a ghost.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
    #     if callable(_update_stats): _update_stats(command="mute", error_occurred="target_is_admin", target_user_id=target_user_id, admin_user_id=admin_user_id)
    #     return

    duration_delta = parse_duration(duration_str)
    if duration_delta is None:
        await safe_markdown_message(update, f"{EMOJI_QUESTION} Invalid duration: `{escape_markdown_v2(duration_str)}`\\. Use formats like 10m, 2h, 1d, or 0 for permanent \\(until unmute command\\)\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred="invalid_duration", admin_user_id=admin_user_id)
        return

    # Telegram API: until_date is Unix timestamp. 0 or None for permanent.
    # For timed mutes, it's current time + duration.
    # If duration_delta is timedelta(0), it means permanent.
    until_date_ts = None
    if duration_delta.total_seconds() > 0:
        until_date_ts = int((datetime.datetime.now(datetime.timezone.utc) + duration_delta).timestamp())
    
    # Default permissions: no sending messages. Other perms remain.
    # To lift all restrictions, use ChatPermissions with all True.
    # To mute (no text, media, stickers, polls):
    permissions_to_set = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False, # Mute images/videos
        can_send_other_messages=False, # Mute stickers/gifs/etc.
        can_send_polls=False,
        # Keep other permissions as they were (or explicitly set if needed)
        # If any of these are None, it means "no change" from current.
        # To be sure, one might fetch current perms and modify.
        # For a simple mute, setting these to False is usually enough.
    )

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            permissions=permissions_to_set,
            until_date=until_date_ts # Pass None for permanent, or timestamp for temporary
          )
        
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        duration_readable = f"for {duration_str}" if duration_delta.total_seconds() > 0 else "permanently \\(until /unmute\\)"
        
        mute_message = f"{EMOJI_NO_ENTRY} {name_to_show} has been muted {duration_readable}\\. Reason: {escape_markdown_v2(reason)}\\. Sweet silence\\."
        await safe_markdown_message(update, mute_message, logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)
      
        # Log mute to DB if needed
        if db:
            await db.log_moderation_action(chat_id, target_user_id, "mute", reason, admin_user_id, duration_delta)
        if callable(_update_stats): _update_stats(command="mute", success=True, target_user_id=target_user_id, duration=duration_str, admin_user_id=admin_user_id, reason=reason)

    except Forbidden as e:
        logger.error(f"Forbidden to mute user {target_user_id} in chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_ERROR} Can\\'t mute\\. The bot probably doesn\\'t have admin rights to restrict users, or is trying to mute another admin with equal/higher rank\\. Telegram said: {escape_markdown_v2(str(e))}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred=f"forbidden: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    except BadRequest as e: # Other issues like user not in chat, etc.
        logger.error(f"BadRequest muting user {target_user_id} in chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn\\'t mute\\. Telegram said: {escape_markdown_v2(str(e))}\\. Maybe they left the chat\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred=f"bad_request: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    except TelegramError as e:
        logger.error(f"TelegramError muting user {target_user_id} in chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_ERROR} A Telegram error occurred trying to mute\\. Details: {escape_markdown_v2(str(e))}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="mute", error_occurred=f"telegram_error: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("unmute")
@admin_required(fetch_chat_admins=True)
@error_handler
async def unmute_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmutes a user.""" # Simplified docstring
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    admin_user_id = update.effective_user.id
    db = await _get_db_instance(context)

    if not context.args:
        await safe_markdown_message(update, f"{EMOJI_QUESTION} Who gets to talk again\\? Use: `{escape_markdown_v2('/unmute @username')}` or reply to them\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unmute", error_occurred="no_target", admin_user_id=admin_user_id)
        return

    target_user_id, target_username_display, _ = await _get_target_user_info(update, context, db)

    if not target_user_id:
        # _get_target_user_info sends its own message
        if callable(_update_stats): _update_stats(command="unmute", error_occurred="target_not_found", admin_user_id=admin_user_id)
        return

    # To unmute, grant all permissions (or specific ones if your bot has a more granular system)
    # Setting all to True restores default permissions for a non-restricted user.
    permissions_to_set = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=True, # Be careful with these if you don't want users changing chat info
        can_invite_users=True,
        can_pin_messages=True # And this one
    )
    # A safer unmute might be to only restore send permissions:
    # permissions_to_set = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_send_polls=True)
    # and pass use_chat_permissions=True to restrict_chat_member to use current chat perms as base for True values.
    # However, the typical way to "unmute" is to grant all basic send perms.
    # The `until_date` param is not used for unmuting (it's for timed restrictions).

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            permissions=permissions_to_set
            # No until_date needed for unmuting (it lifts all restrictions set by bot)
        )
        name_to_show = escape_markdown_v2(target_username_display or f"User {target_user_id}")
        unmute_message = f"{EMOJI_CHAT} Alright, {name_to_show}, you can talk again\\. Don\\'t make me regret this\\."
        await safe_markdown_message(update, unmute_message, logger, reply_to=False, parse_mode=ParseMode.MARKDOWN_V2)
        
        if db:
            await db.log_moderation_action(chat_id, target_user_id, "unmute", "Admin unmute", admin_user_id)
        if callable(_update_stats): _update_stats(command="unmute", success=True, target_user_id=target_user_id, admin_user_id=admin_user_id)

    except Forbidden as e:
        logger.error(f"Forbidden to unmute user {target_user_id} in chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_ERROR} Can\\'t unmute\\. Bot needs admin rights to restrict users, or target is an admin\\. Telegram said: {escape_markdown_v2(str(e))}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unmute", error_occurred=f"forbidden: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    except BadRequest as e:
        logger.error(f"BadRequest unmuting user {target_user_id} in chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn\\'t unmute\\. Telegram said: {escape_markdown_v2(str(e))}\\. Maybe they weren\\'t muted or left\\?", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unmute", error_occurred=f"bad_request: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)
    except TelegramError as e:
        logger.error(f"TelegramError unmuting user {target_user_id} in chat {chat_id}: {e}")
        await safe_markdown_message(update, f"{EMOJI_ERROR} A Telegram error occurred trying to unmute\\. Details: {escape_markdown_v2(str(e))}", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="unmute", error_occurred=f"telegram_error: {str(e)}", target_user_id=target_user_id, admin_user_id=admin_user_id)


# --- Stats & Leaderboard ---
@chat_type_allowed(['group', 'supergroup', 'private'])
@command_cooldown("stats")
@error_handler
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows bot statistics.""" # Simplified docstring
    db = await _get_db_instance(context)
    _get_bot_stats = context.bot_data.get('get_bot_stats') # Function from main bot script
    _update_stats_func = context.bot_data.get('update_stats') # For logging this command
    user_id = update.effective_user.id if update.effective_user else None

    if db is None or not callable(_get_bot_stats):
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Stats system or database is currently unavailable\\. Try again later, champ\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats_func): _update_stats_func(command="show_stats", error_occurred="db_or_stats_func_unavailable", user_id=user_id)
        return

    try:
        # Overall bot stats (from main bot logic, passed via context)
        bot_stats = await _get_bot_stats() # This function needs to be defined in nukem_bot.py and passed
        
        # Chat-specific stats (from DB)
        chat_id = update.effective_chat.id
        total_users_in_db = 0
        total_karma_in_chat = 0
        total_warnings_in_chat = 0
        
        if chat_id: # Only get chat-specific if in a group/supergroup
            chat_users = await db.get_all_users_in_chat(chat_id)
            total_users_in_db = len(chat_users)
            for user_doc in chat_users:
                total_karma_in_chat += user_doc.get('karma', 0)
                total_warnings_in_chat += len(user_doc.get('warnings', []))

        response_parts = [f"{EMOJI_BAR_CHART} *NUKEM Bot Statistics:* {EMOJI_LEADERBOARD}\\\\n\\\\n"]
        
        # Bot-wide stats from get_bot_stats()
        response_parts.append(f"{EMOJI_ROBOT} *Overall Bot Performance:*\\\\n")
        response_parts.append(f"  Total commands processed: `{bot_stats.get('total_commands_processed', 'N/A')}`\\\\n")
        response_parts.append(f"  Bot uptime: `{bot_stats.get('uptime_readable', 'N/A')}`\\\\n")
        response_parts.append(f"  Active chats (where bot is member): `{bot_stats.get('active_chats_count', 'N/A')}`\\\\n")
        # Add more global stats as available from bot_stats

        if chat_id:
            response_parts.append(f"\\\\n{EMOJI_CHAT} *This Chat ({escape_markdown_v2(update.effective_chat.title or str(chat_id))}):*\\\\n")
            response_parts.append(f"  Users on record: `{total_users_in_db}`\\\\n")
            response_parts.append(f"  Total karma points: `{total_karma_in_chat}` {KARMA_EMOJI}\\\\n")
            response_parts.append(f"  Total warnings issued: `{total_warnings_in_chat}` {EMOJI_WARNING}\\\\n")
            # Add more chat-specific stats if tracked

        response_parts.append(f"\\\\n{EMOJI_EYES} *Remember, Duke is always watching\\\\.\\\\.\\\\.*")

        full_message = "".join(response_parts)
        await safe_markdown_message(update, full_message, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats_func): _update_stats_func(command="show_stats", success=True, user_id=user_id, chat_id=chat_id)

    except DatabaseError as e: # type: ignore
        logger.error(f"DB error fetching stats: {e}")
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while crunching numbers\\. Try later\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats_func): _update_stats_func(command="show_stats", error_occurred=f"db_error: {str(e)}", user_id=user_id)
    except Exception as e:
        logger.error(f"Unexpected error in show_stats: {e}")
        await safe_markdown_message(update, f"{EMOJI_SKULL} The stats machine exploded\\. Figures\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats_func): _update_stats_func(command="show_stats", error_occurred=f"unexpected: {str(e)}", user_id=user_id)


@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("leaderboard")
@error_handler
async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the karma or activity leaderboard.""" # Simplified docstring
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id if update.effective_user else None

    if db is None:
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected\\. Cannot fetch leaderboard\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="show_leaderboard", error_occurred="db_not_connected", user_id=user_id)
        return

    leaderboard_type = "karma" # Default
    if context.args and context.args[0].lower() in ["karma", "activity"]: # Add more types if needed
        leaderboard_type = context.args[0].lower()
    
    # For "activity", you'd need to store message counts or similar activity metrics.
    # This example will focus on karma.
    if leaderboard_type == "activity":
        await safe_markdown_message(update, f"{EMOJI_THINKING} Activity leaderboard is still under construction\\. Try `{escape_markdown_v2('/leaderboard karma')}` for now, maggot\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="show_leaderboard", error_occurred="activity_leaderboard_unavailable", user_id=user_id)
        return

    try:
        # Fetch top N users by karma for this chat
        top_n = 10
        users_for_leaderboard = await db.get_leaderboard(chat_id, sort_by='karma', limit=top_n)

        if not users_for_leaderboard:
            await safe_markdown_message(update, f"{EMOJI_THINKING} No one worth mentioning on the karma leaderboard yet\\. Bunch of zeroes\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
            if callable(_update_stats): _update_stats(command="show_leaderboard", success=True, type="karma", result="empty", user_id=user_id)
            return

        response_parts = [f"{EMOJI_LEADERBOARD} *Top {top_n} Soldiers by Karma in this Chat:* {EMOJI_STAR}\\\\n"]
        for i, user_doc in enumerate(users_for_leaderboard):
            name = escape_markdown_v2(user_doc.get('first_name', user_doc.get('username', f"User {user_doc['user_id']}")))
            karma = user_doc.get('karma', 0)
            response_parts.append(f"`{i+1}`\\. {name} \\- {karma} {KARMA_EMOJI}\\\\n")
        
        full_message = "".join(response_parts)
        await safe_markdown_message(update, full_message, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="show_leaderboard", success=True, type="karma", users_shown=len(users_for_leaderboard), user_id=user_id)

    except DatabaseError as e: # type: ignore
        logger.error(f"DB error fetching leaderboard: {e}")
        await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error while fetching leaderboard\\. Try later\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="show_leaderboard", error_occurred=f"db_error: {str(e)}", user_id=user_id)
    except Exception as e:
        logger.error(f"Unexpected error in show_leaderboard: {e}")
        await safe_markdown_message(update, f"{EMOJI_SKULL} The leaderboard machine is busted\\. Typical\\.", logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
        if callable(_update_stats): _update_stats(command="show_leaderboard", error_occurred=f"unexpected: {str(e)}", user_id=user_id)


# --- Message & Chat Member Handlers ---
async def message_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tracks messages for user activity and updates user info in DB."""
    if not update.message or not update.message.from_user or not update.effective_chat:
        return # Ignore updates without necessary info

    user = update.message.from_user
    chat_id = update.effective_chat.id
    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats') # For logging message activity

    if db is None:
        # logger.warning("DB not available in message_tracker, cannot update user stats.")
        return # Silently return if DB not available, or log less verbosely

    try:
        # Update user info (username, first/last name, last_seen)
        # This also adds the user if they are not already in the DB for this chat
        user_data_to_update = {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'last_seen': datetime.datetime.now(datetime.timezone.utc),
            # Increment message count if you're tracking that
            # 'message_count': user_doc.get('message_count', 0) + 1 if user_doc else 1
        }
        
        # Check if user exists, then update or add
        user_doc = await db.get_user(user.id) # Assuming get_user checks globally or by a primary user ID
        if user_doc:
            # If your DB stores chat-specific info under the user, ensure this update targets that.
            # For now, assume update_user updates the global user record, and chat association is separate or handled by add_user.
            await db.update_user(user.id, user_data_to_update)
            # If you have a specific "user_in_chat" collection/table, update that too.
            # e.g., await db.update_user_in_chat(user.id, chat_id, {'last_active': datetime.datetime.now(datetime.timezone.utc)})
        else:
            # Add new user with initial data
            initial_data = {
                'karma': 0,
                'warnings': [],
                'is_chat_admin': user.id in context.chat_data.get('chat_admins', []), # Check if new user is admin
                'join_date': datetime.datetime.now(datetime.timezone.utc) # approx join date
                # 'message_count': 1
            }
            full_new_user_data = {**user_data_to_update, **initial_data}
            await db.add_user(user.id, chat_id, full_new_user_data) # Ensure add_user handles chat_id for association

        if callable(_update_stats):
            _update_stats(
                event_type="message_received", 
                user_id=user.id, 
                chat_id=chat_id, 
                message_length=len(update.message.text or "") if update.message.text else 0,
                is_command=update.message.text.startswith('/') if update.message.text else False
            )

    except DatabaseError as e: # type: ignore
        logger.error(f"DB error in message_tracker for user {user.id} in chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in message_tracker for user {user.id} in chat {chat_id}: {e}")


async def chat_member_update_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles chat member updates (joins, leaves, promotions, etc.)."""
    if not update.chat_member:
        return

    db = await _get_db_instance(context)
    _update_stats = context.bot_data.get('update_stats')
    
    chat = update.chat_member.chat
    user = update.chat_member.new_chat_member.user
    old_status = update.chat_member.old_chat_member.status
    new_status = update.chat_member.new_chat_member.status

    logger.info(f"Chat member update in chat {chat.id} ('{chat.title}') for user {user.id} ('{user.username or user.first_name}'): {old_status} -> {new_status}")

    if db is None:
        logger.warning("DB not available in chat_member_update_handler.")
        # Potentially log this event to stats even if DB is down
        if callable(_update_stats):
            _update_stats(event_type="chat_member_update", user_id=user.id, chat_id=chat.id, old_status=old_status, new_status=new_status, db_status="unavailable")
        return

    try:
        user_data_to_update = {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'last_seen': datetime.datetime.now(datetime.timezone.utc)
        }
        is_admin_now = new_status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        
        user_doc = await db.get_user(user.id)
        if user_doc:
            user_data_to_update['is_chat_admin'] = is_admin_now # Update admin status
            # Potentially update 'is_member_of_chat_X': True/False if you track that explicitly
            await db.update_user(user.id, user_data_to_update)
        else:
            # User not in DB, add them if they are now a member or admin
            if new_status not in [ChatMember.LEFT, ChatMember.KICKED]:
                initial_data = {
                    'karma': 0, 
                    'warnings': [], 
                    'is_chat_admin': is_admin_now,
                    'join_date': datetime.datetime.now(datetime.timezone.utc) # approx join date
                }
                full_new_user_data = {**user_data_to_update, **initial_data}
                await db.add_user(user.id, chat.id, full_new_user_data)

        # Update chat_admins cache in context.chat_data if an admin status changed
        if old_status != ChatMember.ADMINISTRATOR and new_status == ChatMember.ADMINISTRATOR:
            admin_list = context.chat_data.get('chat_admins', [])
            if user.id not in admin_list:
                admin_list.append(user.id)
                context.chat_data['chat_admins'] = admin_list
            logger.info(f"User {user.id} promoted to admin in chat {chat.id}. Updated cache.")
        elif old_status == ChatMember.ADMINISTRATOR and new_status != ChatMember.ADMINISTRATOR:
            admin_list = context.chat_data.get('chat_admins', [])
            if user.id in admin_list:
                admin_list.remove(user.id)
                context.chat_data['chat_admins'] = admin_list
            logger.info(f"User {user.id} no longer admin in chat {chat.id}. Updated cache.")

        # Send welcome/goodbye messages (optional, can be spammy)
        # if new_status == ChatMember.MEMBER and old_status == ChatMember.LEFT:
        #     await safe_markdown_message(update, f"Welcome {user.mention_markdown_v2()} to the shitshow!", logger, chat_id_override=chat.id)
        
        if callable(_update_stats):
            _update_stats(event_type="chat_member_update", user_id=user.id, chat_id=chat.id, old_status=old_status, new_status=new_status, db_status="updated")

    except DatabaseError as e: # type: ignore
        logger.error(f"DB error in chat_member_update_handler for user {user.id}, chat {chat.id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in chat_member_update_handler for user {user.id}, chat {chat.id}: {e}")


# --- Error Handler for Bot ---
async def handle_telegram_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    _update_stats = context.bot_data.get('update_stats')
    if callable(_update_stats):
        _update_stats(
            event_type="telegram_error", 
            error_message=str(context.error), 
            update_details=str(update)[:500] # Log a snippet of the update
        )

    # Optionally, inform user or admin if it's a critical/actionable error
    # if isinstance(context.error, Forbidden):
    #     # e.g., bot was kicked or lost permissions
    #     if update and hasattr(update, 'effective_chat') and update.effective_chat:
    #         try:
    #             await safe_markdown_message(update, "I seem to have lost some permissions here. Make sure I'm an admin with all necessary rights!", logger, chat_id_override=update.effective_chat.id)
    #         except Exception: # Avoid error loops
    #             pass 
    # elif isinstance(context.error, NetworkError):
    #     # Temporary network issue, usually resolves itself.
    #     pass


# --- Conversation Handlers (if any) ---
# Example:
# async def ask_for_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#     await update.message.reply_text("Gimme some input, maggot!")
#     return EXAMPLE_STATE

# async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#     user_input = update.message.text
#     await update.message.reply_text(f"You said: {user_input}. Not bad.")
#     return ConversationHandler.END

# async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#     await update.message.reply_text("Fine, be that way. Conversation over.")
#     return ConversationHandler.END

# example_conv_handler = ConversationHandler(
# entry_points=[CommandHandler('start_conversation', ask_for_input)],
# states={
# EXAMPLE_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_input)],
#     },
# fallbacks=[CommandHandler('cancel', cancel_conversation)],
# )

# Add all handlers to __all__ for easier import in main bot file (optional)
__all__ = [
    'start', 'help_nukem', 'mention_all', 'mention_specific', 'pin_nukem',
    'info', 'nukem_quote', 'rate_my_play', 'alien_scan', 'arsenal_command',
    'list_users', 'sync_users', 'get_karma_command', 'give_karma_command', 'remove_karma_command',
    'warn_user', 'unwarn_user', 'get_warnings_command', 'mute_user_command', 'unmute_user_command',
    'show_stats', 'show_leaderboard',
    'message_tracker', 'chat_member_update_handler',
    'handle_telegram_error',
    # Add conversation handlers here if any, e.g., 'example_conv_handler'
]