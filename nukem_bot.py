"""
NUKEM Bot - A Telegram bot that brings Duke Nukem's attitude to your group chats.
Features user tracking, admin commands, karma system, warnings, and Duke's signature style.

This module contains the main bot implementation including:
- Command handlers
- User tracking
- Karma system
- Warning system
- Rate limiting
- Error handling
"""

# Standard library imports
import asyncio
import atexit
import logging
import os
import random
import signal
import sys
from collections import defaultdict # Added import
from datetime import datetime, timedelta # Added timedelta import
from functools import wraps # Keep if still used directly, else remove
from typing import Optional

# Third party imports
from dotenv import load_dotenv
from telegram import Update, ChatMember, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters
)
from telegram.error import NetworkError, BadRequest, TelegramError # Added TelegramError

# Local imports
from db import Database, DatabaseError
from constants import (
    NUKEM_QUOTES, NUKEM_REACTIONS_POSITIVE, NUKEM_REACTIONS_NEGATIVE,
    NUKEM_RATINGS, ALIEN_SCAN_REPORTS, PROJECT_INFO, ADMIN_USER_IDS,
    # Comprehensive list of Emojis used by the bot:
    EMOJI_SUCCESS, EMOJI_ERROR, EMOJI_WARNING, EMOJI_INFO, EMOJI_QUESTION, EMOJI_WAIT,
    EMOJI_ROCKET, EMOJI_BOMB, EMOJI_NUKE, EMOJI_FIRE, EMOJI_SKULL, EMOJI_ALIEN, EMOJI_ROBOT,
    EMOJI_TARGET, EMOJI_SHIELD, EMOJI_NO_ENTRY, EMOJI_ADMIN, EMOJI_USER, EMOJI_CHAT,
    EMOJI_STAR, EMOJI_CHART_UP, EMOJI_CHART_DOWN, EMOJI_LEADERBOARD, EMOJI_BOOK, EMOJI_GEAR,
    EMOJI_DATABASE, EMOJI_BROADCAST, EMOJI_LINK, EMOJI_SUNGLASSES, EMOJI_WAVE, EMOJI_THINKING,
    EMOJI_LIGHTBULB, EMOJI_PARTY, EMOJI_STOPWATCH, EMOJI_EYES, EMOJI_BRAIN, EMOJI_SCROLL,
    EMOJI_GREEN_CIRCLE, EMOJI_RED_CIRCLE, EMOJI_YELLOW_CIRCLE, EMOJI_TOOLS
)
from utils import (
    escape_markdown_v2, 
    check_rate_limit, command_cooldown, 
    safe_markdown_message, chunk_message, # rate_limiter instance is in utils
    error_handler, admin_required, chat_type_allowed
    # LAST_COMMAND_USAGE is managed within utils.py
)
# Import handlers
from handlers import (
    start, help_nukem, mention_all, mention_specific, pin_nukem,
    info, nukem_quote, rate_my_play, alien_scan, list_users, sync_users,
    get_karma_command, give_karma_command, remove_karma_command,
    warn_user, unwarn_user, get_warnings_command, mute_user_command, unmute_user_command,
    show_stats, show_leaderboard,
    arsenal_command,  # Added arsenal_command
    message_tracker, chat_member_update_handler, handle_telegram_error
)

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
BOT_TOKEN = os.getenv("NUKEM_BOT_TOKEN")
# ADMIN_USER_IDS is now loaded from constants.py
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "nukem_bot")

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO # Changed to INFO for production, DEBUG can be too verbose
)
logger = logging.getLogger(__name__)

# --- Database Setup ---
db: Optional[Database] = None

async def setup_database():
    """Initialize database connection with error handling."""
    global db
    try:
        db = Database() # MONGO_URI and DB_NAME are accessible globally
        await db.ensure_async_setup()
        logger.info(f"{EMOJI_DATABASE}{EMOJI_SUCCESS} Successfully initialized and set up asynchronous database connection")
        return True
    except DatabaseError as e:
        logger.error(f"{EMOJI_DATABASE}{EMOJI_ERROR} Failed to initialize database (DatabaseError): {e}", exc_info=True)
        return False
    except Exception as e: # General exception
        logger.error(f"{EMOJI_DATABASE}{EMOJI_ERROR} Failed to initialize database (General Exception): {e}", exc_info=True)
        return False

# --- Resource Cleanup ---
async def cleanup():
    """Cleanup resources before shutdown."""
    global db  # pylint: disable=global-statement
    if db:
        db.close() # This is now an async method in db.py
        logger.info(f"{EMOJI_TOOLS} Database connections closed")

# --- Configuration Validation ---
async def validate_config():
    """Validate configuration and environment variables."""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TOKEN_HERE":
        logger.error(f"{EMOJI_ERROR} Critical: Bot token not properly configured in .env file. Bot cannot start.")
        return False
    
    # ADMIN_USER_IDS is imported from constants.py where it's loaded and validated.
    # constants.py prints its own warnings/errors if ADMIN_USER_IDS is missing or malformed.
    if not ADMIN_USER_IDS: # Check the imported set from constants
        logger.warning(f"{EMOJI_WARNING} ADMIN_USER_IDS is empty (checked in nukem_bot.py after import). Ensure it's set correctly in .env and loaded by constants.py. Admin commands might not be restricted as expected globally, relying on chat admin checks where applicable.")
        # Depending on requirements, you might return False or allow continuation.
        # For now, allowing continuation as some bots might operate without global admins.

    if not MONGO_URI or not DB_NAME:
        logger.error(f"{EMOJI_ERROR} Critical: MONGO_URI or DB_NAME not configured. Database connection will fail.")
        return False

    if not await setup_database(): # This now calls the async setup_database
        logger.error(f"{EMOJI_ERROR} Critical: Database setup failed. Bot cannot start.")
        return False
    logger.info(f"{EMOJI_SUCCESS} Configuration validated successfully.")
    return True

# --- Signal Handling & Graceful Shutdown ---
def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    logger.info(f"{EMOJI_WARNING} Received signal {signum}. Initiating graceful shutdown...")
    # The atexit handler will manage the async cleanup.
    # Forcing exit here ensures the process terminates after logging.
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def _atexit_cleanup():
    logger.info(f"{EMOJI_WAIT} Running cleanup tasks at exit...")
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # Create a task for cleanup, but don't necessarily wait for it here
            # as atexit might not play well with blocking calls.
            # The loop should ideally process it before full exit.
            loop.create_task(cleanup())
            logger.info(f"{EMOJI_INFO} Asynchronous cleanup task scheduled.")
        else:
            # Fallback if loop is not running (e.g. already closed or never started properly)
            logger.warning(f"{EMOJI_WARNING} Asyncio event loop not running at exit. Attempting to run cleanup in a new loop.")
            asyncio.run(cleanup()) # Try to run it in a new loop if necessary
    except RuntimeError: # No running event loop
        logger.error(f"{EMOJI_ERROR} No asyncio event loop found at exit. Cleanup might be incomplete.")
    except Exception as e:
        logger.error(f"{EMOJI_ERROR} Error during atexit cleanup: {e}", exc_info=True)
    logger.info(f"{EMOJI_SUCCESS} Cleanup process initiated via atexit.")

atexit.register(_atexit_cleanup)


# --- Stats Tracking (to be moved to bot_setup.py later) ---
BOT_STATS = {
    'start_time': datetime.now(),
    'commands_used': defaultdict(int),
    'messages_processed': 0,
    'users_tracked': 0, 
    'nukem_quotes_delivered': 0,
    'karma_given': 0,
    'karma_removed': 0,
    'users_warned': 0,
    'users_muted': 0,
    'errors_occurred': defaultdict(int) # New: Track errors by type/command
}

def update_stats(command: Optional[str] = None, message_processed: bool = False,
                 user_tracked: bool = False, quote_delivered: bool = False,
                 karma_change: Optional[int] = None, user_warned: bool = False,
                 user_muted: bool = False, error_occurred: Optional[str] = None) -> None: # Corrected signature
    """Updates various bot statistics."""
    if command:
        BOT_STATS['commands_used'][command] += 1
    if message_processed:
        BOT_STATS['messages_processed'] += 1
    if user_tracked: # This should be called when a new user is added to DB
        BOT_STATS['users_tracked'] += 1 
    if quote_delivered:
        BOT_STATS['nukem_quotes_delivered'] += 1
    if karma_change is not None:
        if karma_change > 0:
            BOT_STATS['karma_given'] += karma_change
        else:
            BOT_STATS['karma_removed'] += abs(karma_change)
    if user_warned:
        BOT_STATS['users_warned'] +=1
    if user_muted:
        BOT_STATS['users_muted'] +=1
    if error_occurred:
        BOT_STATS['errors_occurred'][error_occurred] += 1


# --- User Data Management (Consider moving to a dedicated module if it grows) ---
# chat_users = {} # In-memory cache, potentially replaced by more direct DB calls or a smarter caching strategy.
# For now, direct DB calls are preferred for consistency, unless performance dictates caching.

# --- NUKEM Bot Commands (To be moved to handlers.py) ---

# @admin_required
# @command_cooldown("start") 
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Handles the /start command with Duke's flair."""
#     start_message = (
#         f"{EMOJI_WAVE} Yo! The Duke is in the house! {EMOJI_SUNGLASSES}\\n"
#         f"Ready to kick ass and chew bubble gum... and I\'m all outta gum.\\n"
#         f"If you\'re an {EMOJI_ADMIN} admin, type `{escape_markdown_v2('/help_nukem')}` for the full arsenal. "
#         f"Everyone else, try not to get any on ya. {EMOJI_ROCKET}"
#     )
#     await safe_markdown_message(update, start_message, logger, reply_to=True)
#     update_stats(command="start")

# @admin_required
# @command_cooldown("help_nukem")
# async def help_nukem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Handles the /help_nukem command, displaying available commands with emojis."""
#     help_text = (
#         f"{EMOJI_BOOK} {EMOJI_ADMIN} *Alright, maggots, listen up! Here's the NUKEM command console:*\\\\n\\\\n"
#         f"{EMOJI_GEAR} *Basic Operations:*\\\\n"
#         f"`/mentionall <message>` - {EMOJI_BROADCAST} Yell at *everyone*. Use sparingly, or I'll use *you* for target practice.\\\\n"
#         f"`/mention @user1 @user2 <message>` - {EMOJI_TARGET} Point your finger at specific chumps.\\\\n"
#         f"`/pin_nukem <message_or_reply>` - {EMOJI_TOOLS} Make somethin' stick. Like gum to a boot.\\\\n"
#         f"`/info [topic]` - {EMOJI_INFO} Get the damn intel (e.g., roadmap, tokenomics, website). Default for general info.\\\\n"
#         f"`/nukem_quote` - {EMOJI_BRAIN} Get a dose of pure, unadulterated wisdom from yours truly.\\\\n"
#         f"`/rate_my_play <description>` - {EMOJI_STAR} Let the Duke judge your so-called 'skills'.\\\\n"
#         f"`/alien_scan` - {EMOJI_ALIEN} Check if any green-blooded freaks are sniffin' around.\\\\n\\\\n"
        
#         f"{EMOJI_USER} *User Management & Karma:*\\\\n"
#         # f"`/sync_users` - {EMOJI_TOOLS} Try to refresh my list of cannon fodder (admins mostly).\\\\n" # Potentially intensive, review need
#         f"`/list_users` - {EMOJI_SCROLL} See who's on my list (user list with karma/warnings).\\\\n"
#         f"`/karma @user` - {EMOJI_QUESTION} Check someone's karma level.\\\\n"
#         f"`/give_karma @user [reason]` - {EMOJI_CHART_UP} Award karma to a worthy soldier.\\\\n"
#         f"`/remove_karma @user [reason]` - {EMOJI_CHART_DOWN} Take karma from a disappointment.\\\\n\\\\n"
        
#         f"{EMOJI_SHIELD} *Moderation Arsenal:*\\\\n"
#         f"`/warn @user [reason]` - {EMOJI_WARNING} Issue a warning to a troublemaker.\\\\n"
#         f"`/unwarn @user` - {EMOJI_SUCCESS} Remove a warning if they've learned their lesson.\\\\n"
#         f"`/warnings @user` - {EMOJI_INFO} Check someone's rap sheet (warning history).\\\\n"
#         f"`/mute @user <duration> [reason]` - {EMOJI_NO_ENTRY} Shut someone up (e.g., 10m, 1h, 1d).\\\\n"
#         f"`/unmute @user` - {EMOJI_CHAT} Let 'em talk again, if they've learned their place.\\\\n\\\\n"
        
#         f"{EMOJI_LEADERBOARD} *Stats & Glory:*\\\\n"
#         f"`/stats` - {EMOJI_CHART_UP} See how much ass this bot has kicked (bot statistics).\\\\n"
#         f"`/leaderboard [karma|activity]` - {EMOJI_LEADERBOARD} See who's top dog.\\\\n\\\\n"
        
#         f"{EMOJI_ROBOT} *Remember, I'm always watching... and judging. So make it good.* {EMOJI_SUNGLASSES}"
#     )
#     await safe_markdown_message(update, help_text, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
#     update_stats(command="help_nukem")


# @chat_type_allowed(['group', 'supergroup'])
# @command_cooldown("mentionall")
# @admin_required 
# @error_handler 
# async def mention_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Mentions all users in a chat with a message, using emojis and improved formatting."""
#     chat_id = update.effective_chat.id
#     message_text_parts = context.args
    
#     if not message_text_parts:
#         await safe_markdown_message(update,
#             f"{EMOJI_QUESTION} Spit it out, genius! `/mentionall <your damn message>`",
#             logger, reply_to=True
#         )
#         update_stats(command="mentionall", error_occurred="no_message")
#         return

#     message_text = " ".join(message_text_parts)
#     escaped_custom_message = escape_markdown_v2(message_text)

#     try:
#         if db is None: # Ensure db is initialized
#             await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database not connected. Cannot fetch users.", logger, reply_to=True)
#             update_stats(command="mentionall", error_occurred="db_not_connected")
#             return

#         users = await db.get_chat_users(chat_id)
#         if not users:
#             await safe_markdown_message(update,
#                 f"{EMOJI_INFO} My list's emptier than a politician's promises. No one to yell at in this chat. {EMOJI_SKULL}",
#                 logger, reply_to=True
#             )
#             update_stats(command="mentionall", error_occurred="no_users_in_db")
#             return

#         users_to_mention = [
#             f"[@{escape_markdown_v2(user['username'])}](tg://user?id={user['user_id']})"
#             for user in users
#             if user.get('username') and not user['username'].lower().startswith("grunt_") and not user.get('is_bot', False) # Avoid bots and placeholders
#         ]

#         if not users_to_mention:
#             await safe_markdown_message(update,
#                 f"{EMOJI_INFO} Looks like these maggots are too shy to set a username or they're all bots. Can't tag ghosts. {EMOJI_EYES}",
#                 logger, reply_to=True
#             )
#             update_stats(command="mentionall", error_occurred="no_mentionable_users")
#             return

#         max_mentions_per_msg = 30 # Reduced for safety and readability
        
#         # Send initial notification
#         await safe_markdown_message(update,
#             f"{EMOJI_BROADCAST}{EMOJI_WAIT} Alright, lettin' 'em have it with both barrels! This might take a few shots to tag everyone with: \"{escaped_custom_message}\"",
#             logger, reply_to=True
#         )
#         await asyncio.sleep(1) # Small pause

#         # Constructing the message header that repeats
#         header_message = f"{EMOJI_BROADCAST} *ATTENTION, ALL YOU SLACK-JAWED TROOPERS!*\\\\n{escaped_custom_message}\\\\n\\\\nTagging batch:"

#         for i in range(0, len(users_to_mention), max_mentions_per_msg):
#             user_chunk = users_to_mention[i:i + max_mentions_per_msg]
#             mention_block = " ".join(user_chunk)
            
#             # Message for this specific chunk
#             chunk_message_content = f"{header_message}\\\\n{mention_block}"
            
#             # Use the chunk_message utility from utils.py if the content itself is too long (unlikely with header + 30 mentions)
#             # For now, assume each chunk_message_content is within limits.
#             # If it can exceed, then:
#             # final_messages_to_send = chunk_message(chunk_message_content, 4096)
#             # for final_chunk in final_messages_to_send:
#             #    await safe_markdown_message(update, final_chunk, logger, reply_to=False, chat_id_override=chat_id)
#             #    await asyncio.sleep(1.5) # Increased delay between message sends
            
#             try:
#                 await safe_markdown_message(update, chunk_message_content, logger, reply_to=False, chat_id_override=chat_id)
#                 await asyncio.sleep(1.5) # Increased delay between message sends
#             except BadRequest as br_err:
#                 error_detail = escape_markdown_v2(str(br_err))
#                 logger.error(f"{EMOJI_ERROR} Failed to send mention chunk (BadRequest): {error_detail} for chat {chat_id}")
#                 await safe_markdown_message(update, f"{EMOJI_ERROR} Telegram choked on that one: {error_detail}. Some users might not have been tagged.", logger, reply_to=True)
#                 update_stats(command="mentionall", error_occurred=f"telegram_badrequest_{br_err.message[:20]}")
#                 break 
#             except Exception as e:
#                 error_detail = escape_markdown_v2(str(e))
#                 logger.error(f"{EMOJI_ERROR} Failed to send mention chunk (Other): {error_detail} for chat {chat_id}", exc_info=True)
#                 await safe_markdown_message(update, f"{EMOJI_ERROR} Damn it all to hell! Hit a snag: {error_detail}. Some users might not have been tagged.", logger, reply_to=True)
#                 update_stats(command="mentionall", error_occurred="mention_send_exception")
#                 break
#         else: # If loop completed without break
#             await safe_markdown_message(update, f"{EMOJI_SUCCESS} All mention batches sent for your message: \"{escaped_custom_message}\"", logger, reply_to=True, chat_id_override=chat_id)
        
#         update_stats(command="mentionall")

#     except DatabaseError as e:
#         logger.error(f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error in mention_all for chat {chat_id}: {e}", exc_info=True)
#         await safe_markdown_message(update,
#             f"{EMOJI_DATABASE}{EMOJI_ERROR} Had trouble getting the user list. Database is acting up!",
#             logger, reply_to=True
#         )
#         update_stats(command="mentionall", error_occurred="db_error")
#     except Exception as e: # Catch-all for unexpected issues
#         logger.error(f"{EMOJI_ERROR} Unexpected error in mention_all for chat {chat_id}: {e}", exc_info=True)
#         await safe_markdown_message(update, f"{EMOJI_ERROR} Something went seriously sideways with `/mentionall`. Try again later.", logger, reply_to=True)
#         update_stats(command="mentionall", error_occurred="unexpected_exception")


# @admin_required
# @command_cooldown("mention") # Assuming 'mention' for specific users
# @error_handler
# async def mention_specific(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Mentions specific users with a message, with Duke's style."""
#     args = context.args
#     if not args:
#         await safe_markdown_message(update,
#             f"{EMOJI_QUESTION} Who am I pointing my gun at, and what am I sayin'? Use `/mention @user1 @user2 <message>`",
#             logger, reply_to=True
#         )
#         update_stats(command="mention_specific", error_occurred="no_args")
#         return

#     mentions = []
#     message_parts = []
#     for arg in args:
#         if arg.startswith('@') and len(arg) > 1: # Ensure it's a valid mention start
#             mentions.append(escape_markdown_v2(arg))
#         else:
#             message_parts.append(arg)

#     if not mentions:
#         await safe_markdown_message(update, f"{EMOJI_TARGET}{EMOJI_ERROR} No @'s? Are you blind or just stupid? I need targets!", logger, reply_to=True)
#         update_stats(command="mention_specific", error_occurred="no_mentions_provided")
#         return
#     if not message_parts:
#         await safe_markdown_message(update, f"{EMOJI_QUESTION} A message, genius! They ain't mind readers. What do you want to tell 'em?", logger, reply_to=True)
#         update_stats(command="mention_specific", error_occurred="no_message_provided")
#         return

#     message_text_content = escape_markdown_v2(" ".join(message_parts))
#     mention_block_content = " ".join(mentions)
    
#     full_message_to_send = (
#         f"{EMOJI_BROADCAST} *HEY, YOU LOT!* {mention_block_content}\\\\n\\\\n"
#         f"{message_text_content}\\\\n\\\\n"
#         f"*That is all. Carry on, or don't. I don't care.* {EMOJI_SUNGLASSES}"
#     )
    
#     await safe_markdown_message(update, full_message_to_send, logger, reply_to=False, chat_id_override=update.effective_chat.id)
#     update_stats(command="mention_specific", karma_change=None) # Example if you track command usage without other specific stats


# @admin_required
# @command_cooldown("pin_nukem")
# @error_handler
# async def pin_nukem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Pins a message in the chat, either the replied-to message or the command's message, with Duke's commentary."""
#     chat_id = update.effective_chat.id
#     message_to_pin_id: Optional[int] = None
#     pin_message_text_reply: Optional[str] = None

#     if update.message.reply_to_message:
#         message_to_pin_id = update.message.reply_to_message.message_id
#         pin_message_text_reply = f"{EMOJI_TOOLS}{EMOJI_SUCCESS} Pinned that sucker! It ain't goin' nowhere."
#     elif context.args:
#         text_to_pin_content = " ".join(context.args)
#         if text_to_pin_content:
#             try:
#                 # Send the message first, then pin it.
#                 # Use safe_markdown_message for consistency, though for pinning, content is key.
#                 # Let's make the pinned message itself clean.
#                 sent_message = await update.message.reply_text(text_to_pin_content) # Send as plain text to avoid issues if it's complex
#                 message_to_pin_id = sent_message.message_id
#                 pin_message_text_reply = f"{EMOJI_TOOLS}{EMOJI_SUCCESS} Pinned your words of wisdom, hotshot: \"{escape_markdown_v2(text_to_pin_content[:30])}...\""
#             except TelegramError as e:
#                 logger.error(f"{EMOJI_ERROR} Failed to send message for pinning: {e}", exc_info=True)
#                 await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn't even say it to pin it: {escape_markdown_v2(str(e))}", logger, reply_to=True)
#                 update_stats(command="pin_nukem", error_occurred="send_for_pin_failed")
#                 return
#         else:
#             await safe_markdown_message(update, f"{EMOJI_QUESTION} Pin what? Air? Give me a message or reply to one, meathead.", logger, reply_to=True)
#             update_stats(command="pin_nukem", error_occurred="no_content_to_pin")
#             return
#     else:
#         await safe_markdown_message(update, f"{EMOJI_QUESTION} Pin what? Reply to a message or type `/pin_nukem <your important message>`.", logger, reply_to=True)
#         update_stats(command="pin_nukem", error_occurred="no_target_for_pin")
#         return

#     if message_to_pin_id:
#         try:
#             await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_to_pin_id, disable_notification=False)
#             if pin_message_text_reply:
#                 await safe_markdown_message(update, pin_message_text_reply, logger, reply_to=True)
#             else: # Should not happen given the logic above
#                 await safe_markdown_message(update, f"{EMOJI_TOOLS}{EMOJI_SUCCESS} Pinned it. Like a boss.", logger, reply_to=True)
#             update_stats(command="pin_nukem")
#         except BadRequest as e:
#             logger.error(f"{EMOJI_ERROR} Failed to pin message (BadRequest): {e}", exc_info=True)
#             error_msg = escape_markdown_v2(str(e))
#             if "message to pin not found" in error_msg.lower():
#                  await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn't pin it. Message seems to have vanished. Spooky. {EMOJI_SKULL}", logger, reply_to=True)
#             elif "not enough rights" in error_msg.lower():
#                  await safe_markdown_message(update, f"{EMOJI_NO_ENTRY} Couldn't pin it. Looks like I ain't got the juice (permissions) in this chat. {EMOJI_ADMIN}", logger, reply_to=True)
#             else:
#                 await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn't pin it. Telegram says: {error_msg}", logger, reply_to=True)
#             update_stats(command="pin_nukem", error_occurred=f"pin_badrequest_{e.message[:20]}")
#         except Exception as e: # Other TelegramErrors or general errors
#             logger.error(f"{EMOJI_ERROR} Failed to pin message (Other): {e}", exc_info=True)
#             await safe_markdown_message(update, f"{EMOJI_ERROR} Pinning failed. Something blew up: {escape_markdown_v2(str(e))}", logger, reply_to=True)
#             update_stats(command="pin_nukem", error_occurred="pin_exception")


# @check_rate_limit 
# @chat_type_allowed(['private', 'group', 'supergroup']) 
# @command_cooldown("info")
# @error_handler
# async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Provides information about the project based on the topic given, with Duke's style."""
#     topic_args = context.args
#     topic = " ".join(topic_args).lower().strip() if topic_args else "default"

#     # PROJECT_INFO should be a dictionary in constants.py
#     # Example: PROJECT_INFO = { "default": "...", "roadmap": "...", "tokenomics": "..." }
    
#     # Ensure PROJECT_INFO is a dict and topic exists, else provide a default/error
#     if not isinstance(PROJECT_INFO, dict):
#         logger.error(f"{EMOJI_ERROR} PROJECT_INFO in constants.py is not a dictionary!")
#         await safe_markdown_message(update, f"{EMOJI_ERROR} My intel files are corrupted. Can't fetch info right now.", logger, reply_to=True)
#         update_stats(command="info", error_occurred="project_info_misconfigured")
#         return

#     response_text = PROJECT_INFO.get(topic)
    
#     if response_text is None:
#         # If specific topic not found, try to give a list of available topics or the default.
#         available_topics = [key for key in PROJECT_INFO if key != "default"]
#         if topic == "default" or not available_topics : # Should always have default
#              response_text = PROJECT_INFO.get("default", "No information available, maggot. Try asking about something specific or check `/help_nukem`.")
#              header_text = f"{EMOJI_ROBOT} *DUKE'S GENERAL BRIEFING:*"
#         else:
#             response_text = (f"Don't have intel on `{escape_markdown_v2(topic)}` specifically, try one of these, badass: "
#                              f"`{escape_markdown_v2(', '.join(available_topics))}`. "
#                              f"Or use `/info` for the general lowdown.")
#             header_text = f"{EMOJI_QUESTION} *INTEL NOT FOUND ON '{escape_markdown_v2(topic).upper()}':*"
#     else:
#         header_text = f"{EMOJI_INFO} *DUKE'S INTEL DROP ON '{escape_markdown_v2(topic).upper()}':*" if topic != "default" else f"{EMOJI_ROBOT} *DUKE'S GENERAL BRIEFING:*"

#     # The PROJECT_INFO strings in constants.py should NOT be pre-escaped.
#     # We escape them here before sending.
#     full_response_text = f"{header_text}\\\\n{escape_markdown_v2(response_text)}"
#     await safe_markdown_message(update, full_response_text, logger, reply_to=True)
#     update_stats(command="info", karma_change=None) # Track command usage


# @admin_required
# @command_cooldown("list_users")
# @error_handler
# async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Lists users in the chat with karma and warnings, for admins, with enhanced output."""
#     chat_id = update.effective_chat.id
    
#     if db is None:
#         await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database connection MIA. Can't fetch the user roster.", logger, reply_to=True)
#         update_stats(command="list_users", error_occurred="db_not_connected")
#         return

#     try:
#         users_data = await db.get_chat_users(chat_id) # This should fetch all users the bot knows in this chat
#         if not users_data:
#             await safe_markdown_message(update, f"{EMOJI_INFO} No grunts in the database for this chat. It's lonely here, or they're all ghosts. {EMOJI_SKULL}", logger, reply_to=True)
#             update_stats(command="list_users", error_occurred="no_users_in_db_for_chat")
#             return

#         response_lines_list = [f"{EMOJI_SCROLL} *USER ROSTER - FOR {EMOJI_ADMIN} ADMIN EYES ONLY (Chat ID: `{chat_id}`):*\\\\n"]
#         active_users_count = 0

#         for user_doc in users_data:
#             user_id = user_doc.get('user_id')
#             if not user_id: # Should not happen if data is clean
#                 continue

#             username = user_doc.get('username', f"Grunt_{user_id}")
#             first_name = user_doc.get('first_name', 'N/A')
#             status = user_doc.get('status', 'member') # e.g., member, administrator, left, kicked
            
#             # Skip users who are no longer part of the chat if that's desired, or indicate status
#             # For now, list all known users.
            
#             karma = await db.get_karma(chat_id, user_id)
#             warnings_list = await db.get_warnings(chat_id, user_id) # This returns a list of warning dicts
            
#             # User's mention string
#             user_mention = f"[@{escape_markdown_v2(username)}](tg://user?id={user_id})" if username and not username.startswith("Grunt_") else escape_markdown_v2(first_name)

#             user_info_str = (
#                 f"\\\\- {user_mention} (ID: `{user_id}`)\\\\n"
#                 f"  Status: `{escape_markdown_v2(status)}` {EMOJI_USER}\\\\n"
#                 f"  Karma: {karma} {EMOJI_STAR}\\\\n"
#                 f"  Warnings: {len(warnings_list)} {EMOJI_WARNING}"
#             )
#             response_lines_list.append(user_info_str)
#             active_users_count += 1
        
#         response_lines_list.append(f"\\\\nTotal users listed: {active_users_count}")

#         if active_users_count == 0: # All users were filtered or none had user_id
#             await safe_markdown_message(update, f"{EMOJI_INFO} Found some user records, but couldn't fetch details or all are inactive. Weird. {EMOJI_THINKING}", logger, reply_to=True)
#             update_stats(command="list_users", error_occurred="no_active_users_to_list")
#             return

#         full_message_text_users = "\\\\n\\\\n".join(response_lines_list)
        
#         # Use the chunk_message utility from utils.py
#         message_chunks_users = chunk_message(full_message_text_users, 4096) 
        
#         if len(message_chunks_users) > 1 :
#              await safe_markdown_message(update, f"{EMOJI_INFO} User roster is extensive, sending in {len(message_chunks_users)} parts...", logger, reply_to=True)
#              await asyncio.sleep(0.5)

#         for i, chunk_text_user in enumerate(message_chunks_users):
#             # Add part number if multiple chunks
#             chunk_header = f"*Part {i+1}/{len(message_chunks_users)}*\\\\n" if len(message_chunks_users) > 1 else ""
#             await safe_markdown_message(update, chunk_header + chunk_text_user, logger, reply_to=False, chat_id_override=chat_id) 
#             if len(message_chunks_users) > 1:
#                 await asyncio.sleep(1) # Delay between chunks
        
#         update_stats(command="list_users")

#     except DatabaseError as e:
#         logger.error(f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error in list_users for chat {chat_id}: {e}", exc_info=True)
#         await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database is on the fritz. Can't get the user list.", logger, reply_to=True)
#         update_stats(command="list_users", error_occurred="db_error")
#     except Exception as e:
#         logger.error(f"{EMOJI_ERROR} Unexpected error in list_users for chat {chat_id}: {e}", exc_info=True)
#         await safe_markdown_message(update, f"{EMOJI_ERROR} Couldn't list users. Something went kaboom.", logger, reply_to=True)
#         update_stats(command="list_users", error_occurred="unexpected_exception")


# @admin_required
# @command_cooldown("sync_users")
# @error_handler
# async def sync_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Synchronizes chat administrators with the database, enhancing feedback."""
#     chat_id = update.effective_chat.id
#     if not chat_id:
#         await safe_markdown_message(update, f"{EMOJI_ERROR} Cannot determine chat ID for sync.", logger, reply_to=True)
#         update_stats(command="sync_users", error_occurred="no_chat_id")
#         return

#     await safe_markdown_message(update,
#         f"{EMOJI_GEAR}{EMOJI_WAIT} Performing recon on the chain of command in chat `{chat_id}`... Let's see who's really in charge here.",
#         logger, reply_to=True
#     )
    
#     if db is None:
#         await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database connection MIA. Cannot sync users.", logger, reply_to=True)
#         update_stats(command="sync_users", error_occurred="db_not_connected")
#         return

#     try:
#         chat_admins = await context.bot.get_chat_administrators(chat_id)
#         if not chat_admins:
#             await safe_markdown_message(update, f"{EMOJI_INFO} This place is a ghost town or I can't see 'em. No admins found by Telegram API in chat `{chat_id}`. {EMOJI_SKULL}", logger, reply_to=True)
#             update_stats(command="sync_users", error_occurred="no_admins_found_api")
#             return

#         admin_list_md_parts = []
#         synced_count = 0
#         newly_added_count = 0
#         updated_users_count = 0
#         already_ok_count = 0

#         for admin_member in chat_admins:
#             user = admin_member.user
#             if user.is_bot: # Skip bots
#                 continue

#             user_id = user.id
#             username = user.username if user.username else f"Admin_{user.id}" # Fallback username
#             first_name = user.first_name if user.first_name else "N/A"
#             # Determine status based on ChatMember object
#             # admin_member.status will be 'creator' or 'administrator'
#             user_status = admin_member.status 

#             # Add or update user in DB
#             # The add_or_update_user method in db.py should handle the logic of new vs update.
#             # We can get a flag back from it, or check existing doc first.
            
#             existing_user_doc = await db.get_user(chat_id, user_id)
            
#             update_data = {
#                 'username': username,
#                 'first_name': first_name,
#                 'last_seen': datetime.now(),
#                 'status': user_status, # Ensure this reflects admin status
#                 'is_bot': False
#             }

#             if not existing_user_doc:
#                 await db.add_or_update_user(chat_id, user_id, username, first_name, user_status, is_bot=False)
#                 newly_added_count += 1
#                 synced_count +=1
#                 admin_list_md_parts.append(f"  {EMOJI_GREEN_CIRCLE} {escape_markdown_v2(first_name)} (@{escape_markdown_v2(username)}) - *NEWLY ADDED* as {user_status}")
#             # Check if update is needed
#             elif (existing_user_doc.get('username') != username or
#                   existing_user_doc.get('first_name') != first_name or
#                   existing_user_doc.get('status') != user_status):
#                 await db.add_or_update_user(chat_id, user_id, username, first_name, user_status, is_bot=False)
#                 updated_users_count += 1
#                 synced_count += 1
#                 admin_list_md_parts.append(f"  {EMOJI_YELLOW_CIRCLE} {escape_markdown_v2(first_name)} (@{escape_markdown_v2(username)}) - *UPDATED* to {user_status}")
#             else:
#                 # No change needed, but good to acknowledge
#                 # Optionally update last_seen if not done by add_or_update_user for existing unchanged users
#                 await db.add_or_update_user(chat_id, user_id, username, first_name, user_status, is_bot=False, update_last_seen=True) # ensure last_seen updates
#                 already_ok_count +=1
#                 admin_list_md_parts.append(f"  {EMOJI_INFO} {escape_markdown_v2(first_name)} (@{escape_markdown_v2(username)}) - Already synced as {user_status}")


#         if not admin_list_md_parts and already_ok_count == 0 : # No human admins found or processed
#              await safe_markdown_message(update, f"{EMOJI_INFO} No human admins found to sync in chat `{chat_id}`. How peculiar.", logger, reply_to=True)
#              update_stats(command="sync_users", error_occurred="no_human_admins_to_sync")
#              return

#         response_summary = [f"{EMOJI_SUCCESS} *Chain of Command Recon Complete for Chat `{chat_id}`!*"]
#         if newly_added_count > 0:
#             response_summary.append(f"{EMOJI_GREEN_CIRCLE} {newly_added_count} new admin(s) added to the roster.")
#         if updated_users_count > 0:
#             response_summary.append(f"{EMOJI_YELLOW_CIRCLE} {updated_users_count} existing admin record(s) updated.")
#         if already_ok_count > 0 and newly_added_count == 0 and updated_users_count == 0:
#              response_summary.append(f"{EMOJI_INFO} All {already_ok_count} admin(s) already perfectly cataloged and up-to-date.")
#         elif already_ok_count > 0 :
#              response_summary.append(f"{EMOJI_INFO} {already_ok_count} admin(s) were already up-to-date.")
        
#         response_summary.append(f"Total human admins processed: {newly_added_count + updated_users_count + already_ok_count}")

#         if admin_list_md_parts: # Only show list if there were actual changes or detailed view is desired
#             response_summary.append("\\\\n*Details:*\\\\n" + "\\\\n".join(admin_list_md_parts))
        
#         final_response = "\\\\n".join(response_summary)
        
#         # Chunk and send
#         message_chunks = chunk_message(final_response, 4096)
#         for i, chunk_text in enumerate(message_chunks):
#             header = f"*Sync Report Part {i+1}/{len(message_chunks)}*\\\\n" if len(message_chunks) > 1 else ""
#             await safe_markdown_message(update, header + chunk_text, logger, reply_to=False, chat_id_override=chat_id)
#             if len(message_chunks) > 1: await asyncio.sleep(1)
        
#         update_stats(command="sync_users")

#     except DatabaseError as e:
#         logger.error(f"{EMOJI_DATABASE}{EMOJI_ERROR} Database error during user sync for chat {chat_id}: {e}", exc_info=True)
#         await safe_markdown_message(update, f"{EMOJI_DATABASE}{EMOJI_ERROR} Database is acting up. Couldn't sync the brass.", logger, reply_to=True)
#         update_stats(command="sync_users", error_occurred="db_error")
#     except BadRequest as br_err: # Specifically for Telegram API issues
#         logger.error(f"{EMOJI_ERROR} Telegram API error during user sync for chat {chat_id}: {br_err}", exc_info=True)
#         await safe_markdown_message(update, f"{EMOJI_ERROR} Telegram threw a fit trying to get admin list: {escape_markdown_v2(str(br_err))}", logger, reply_to=True)
#         update_stats(command="sync_users", error_occurred=f"telegram_badrequest_{br_err.message[:20]}")
#     except Exception as e:
#         logger.error(f"{EMOJI_ERROR} Unexpected error during user sync for chat {chat_id}: {e}", exc_info=True)
#         await safe_markdown_message(update, f"{EMOJI_ERROR} Something went haywire during admin sync. Try again, maggot.", logger, reply_to=True)
#         update_stats(command="sync_users", error_occurred="unexpected_exception")


# @admin_required 
# @command_cooldown("nukem_quote")
# @error_handler
# async def nukem_quote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Sends a random Nukem quote with appropriate emoji."""
#     quote = random.choice(NUKEM_QUOTES) # NUKEM_QUOTES from constants.py
#     # Quotes in constants.py can already include emojis or we add one here
#     # Assuming quotes are just text, let's add a thematic emoji.
#     # Or, ensure NUKEM_QUOTES in constants.py are f-strings with emojis.
#     # For this example, let's assume NUKEM_QUOTES in constants are already formatted with emojis.
#     # e.g., NUKEM_QUOTES = [ f"{EMOJI_SUNGLASSES} I'm Duke Nukem. And I'm coming to get the rest of you alien bastards!" ]
    
#     # If quotes are plain, pick a random relevant emoji:
#     # quote_emojis = [EMOJI_SUNGLASSES, EMOJI_ROCKET, EMOJI_BOMB, EMOJI_SKULL, EMOJI_FIRE]
#     # final_quote = f"{random.choice(quote_emojis)} {escape_markdown_v2(quote)}"
    
#     # Assuming NUKEM_QUOTES in constants.py are already well-formatted (possibly with markdown and emojis)
#     # We still need to escape if they are NOT pre-escaped.
#     # If they ARE pre-escaped or contain markdown, then parse_mode should be handled carefully.
#     # Let's assume they are plain text and need escaping + emoji.
    
#     # Re-evaluating: constants.py now has NUKEM_QUOTES with f-string emojis.
#     # So, they contain markdown characters if emojis are used like f"{EMOJI_NUKE} text".
#     # This means the quote string itself contains the emoji unicode.
#     # If we escape the whole string, emojis might not render as emojis but as their unicode representation.
#     # Let's assume the quotes in constants.py are ready to be sent with MarkdownV2.
    
#     # The NUKEM_QUOTES in constants.py are now f-strings with emojis.
#     # These are fine to send directly if safe_markdown_message handles ParseMode.MARKDOWN_V2
#     # and the emojis don't conflict with markdown. Standard emojis are fine.
    
#     await safe_markdown_message(update, quote, logger, reply_to=True, parse_mode=ParseMode.MARKDOWN_V2)
#     update_stats(quote_delivered=True, command="nukem_quote")


# @check_rate_limit
# @command_cooldown("rate_my_play")
# @error_handler
# async def rate_my_play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Rates the user's described play with Duke's signature commentary and a random rating."""
#     play_description = " ".join(context.args)
#     if not play_description:
#         await safe_markdown_message(update,
#             f"{EMOJI_QUESTION} Rate what? Your stunning ability to type nothing? `/rate_my_play <your so-called epic play>`",
#             logger, reply_to=True
#         )
#         update_stats(command="rate_my_play", error_occurred="no_description")
#         return

#     # NUKEM_RATINGS from constants.py, assumed to be formatted with emojis
#     rating = random.choice(NUKEM_RATINGS) 
#     escaped_description = escape_markdown_v2(play_description)

#     response = (
#         f"{EMOJI_TARGET} So you think you're hot stuff with your play: \"_{escaped_description}_\"\\\\n"
#         f"Let's see... The Duke rates your performance a...\\\\n\\\\n"
#         f"**{rating}**\\\\n\\\\n"
#         f"{random.choice([f'Keep practicing, kid. {EMOJI_SUNGLASSES}', f'Not bad... for a rookie. {EMOJI_THINKING}', f'Impressive... most impressive. {EMOJI_ROCKET}'])}"
#     )
#     await safe_markdown_message(update, response, logger, reply_to=True)
#     update_stats(command="rate_my_play")


# @check_rate_limit
# @command_cooldown("alien_scan")
# @error_handler
# async def alien_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Performs an 'alien scan' and reports findings with Duke's usual charm."""
#     # ALIEN_SCAN_REPORTS from constants.py, assumed to be formatted with emojis
#     report = random.choice(ALIEN_SCAN_REPORTS)
    
#     scan_message = (
#         f"{EMOJI_ALIEN}{EMOJI_WAIT} Scanning for alien slimeballs... Hold your breath, maggot!\\\\n"
#         f"My high-tech gear is buzzing... beep... boop...\\\\n\\\\n"
#         f"**Scan Results:** {report}"
#     )
#     await safe_markdown_message(update, scan_message, logger, reply_to=True)
#     update_stats(command="alien_scan")

# --- Karma System Commands ---
# async def _get_target_user_id_and_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[int], Optional[str], Optional[str]]:
# """Helper function to get target user ID and reason from a command."""
# logger.debug("Entering _get_target_user_id_and_reason")
# message = update.effective_message
# if not message or not message.text:
# logger.warning("Message or message.text is None")
# return None, None, None

# parts = message.text.split(maxsplit=2)
# target_mention_or_id = None
# reason = None
# command_name = parts[0]

# if len(parts) > 1:
# target_mention_or_id = parts[1]
# if len(parts) > 2:
# reason = parts[2]

# if not target_mention_or_id:
# await message.reply_text(f"Please specify a user to {command_name[1:]}.")
# return None, None, None

# target_user_id = None
# target_username = None

# # Check if it's a direct user ID
# if target_mention_or_id.isdigit():
# target_user_id = int(target_mention_or_id)
# else:
# # Check if it's a mention
# entities = message.entities or []
# for entity in entities:
# if entity.type == MessageEntityType.MENTION:
# # Extract username mentioned (e.g., @username)
# mentioned_username = message.text[entity.offset : entity.offset + entity.length]
# if mentioned_username == target_mention_or_id: # Ensure it's the one we're looking for
# if entity.user:
# target_user_id = entity.user.id
# target_username = entity.user.username
# break
# else: # It's a reply, target is the replied-to user
# if message.reply_to_message and message.reply_to_message.from_user:
# target_user_id = message.reply_to_message.from_user.id
# target_username = message.reply_to_message.from_user.username
# # The "reason" would be target_mention_or_id if it wasn't a user ID or mention
# if not reason and not target_mention_or_id.isdigit() and not target_mention_or_id.startswith('@'):
# reason = target_mention_or_id

# if not target_user_id and message.reply_to_message and message.reply_to_message.from_user:
# logger.debug("Targeting user from reply_to_message")
# target_user_id = message.reply_to_message.from_user.id
# target_username = message.reply_to_message.from_user.username
# # If target_mention_or_id was not a user and no reason was split, it's the reason
# if not reason and target_mention_or_id and not target_mention_or_id.isdigit() and not (target_mention_or_id.startswith('@') and any(entity.type == MessageEntityType.MENTION and message.text[entity.offset : entity.offset + entity.length] == target_mention_or_id for entity in entities)):
# reason = target_mention_or_id
# elif not reason and len(parts) > 1 and not (parts[1].isdigit() or (parts[1].startswith('@') and any(entity.type == MessageEntityType.MENTION and message.text[entity.offset : entity.offset + entity.length] == parts[1] for entity in entities))):
# reason = parts[1]


# if not target_user_id:
# # If still no ID, try to find user by username (if it was provided as text without @)
# if target_mention_or_id and not target_mention_or_id.startswith("@") and not target_mention_or_id.isdigit():
# # This part is tricky as we don't have a direct way to search user by username text
# # without iterating through known users or making an API call if available.
# # For now, we'll assume if it's not an ID or a mention, it's an error or part of the reason.
# # However, if it was the only argument after command, it might be an attempt to specify user by name.
# # This logic might need refinement based on how users are typically specified.
# pass # Cannot resolve username text to ID easily here.

# if not target_user_id:
# await message.reply_text(f"Could not identify the target user. Please mention them, use their ID, or reply to their message.")
# return None, None, None

# logger.debug(f"Target User ID: {target_user_id}, Username: {target_username}, Reason: {reason}")
# return target_user_id, reason, target_username


# async def get_karma_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
# """Gets the karma of a user or the user who sent the command."""
# logger.debug("Entering get_karma_command")
# message = update.effective_message
# chat_id = update.effective_chat.id
# user_to_check_id = None
# user_to_check_username = None

# if message.reply_to_message and message.reply_to_message.from_user:
# user_to_check_id = message.reply_to_message.from_user.id
# user_to_check_username = message.reply_to_message.from_user.username or f"User {user_to_check_id}"
# elif context.args:
# target_arg = context.args[0]
# if target_arg.isdigit():
# user_to_check_id = int(target_arg)
# # Attempt to get username if ID is known (e.g., from a previous interaction or DB)
# # This might require fetching user details if not readily available
# # For simplicity, we'll just show ID if username isn't easily found
# user_details = await get_user_details_for_karma(user_to_check_id, chat_id) # Placeholder
# if user_details:
# user_to_check_username = user_details.get('username', f"User {user_to_check_id}")
# else:
# user_to_check_username = f"User {user_to_check_id}"
# elif target_arg.startswith('@'):
# mentioned_username_to_check = target_arg[1:]
# # Find user ID from mention (requires iterating through message entities or a helper)
# # This is a simplified approach; robust parsing is in _get_target_user_id_and_reason
# entities = message.entities or []
# found_in_entities = False
# for entity in entities:
# if entity.type == MessageEntityType.MENTION:
# username_in_entity = message.text[entity.offset+1 : entity.offset + entity.length]
# if username_in_entity == mentioned_username_to_check and entity.user:
# user_to_check_id = entity.user.id
# user_to_check_username = entity.user.username or f"User {user_to_check_id}"
# found_in_entities = True
# break
# if not found_in_entities:
# await message.reply_text(f"Could not find user {target_arg}. Please use their ID or mention them directly.")
# return
# else:
# await message.reply_text(f"Invalid argument. Use /karma @username, /karma user_id, or reply to a message.")
# return
# else:
# user_to_check_id = message.from_user.id
# user_to_check_username = message.from_user.username or f"User {user_to_check_id}"

# if user_to_check_id is None:
# await message.reply_text("Could not determine user to check karma for.")
# return

# karma_points = get_karma(user_to_check_id, chat_id)
# if karma_points is not None:
# await message.reply_text(f"{KARMA_EMOJI} {user_to_check_username} has {karma_points} karma points.")
# else:
# await message.reply_text(f"Could not retrieve karma for {user_to_check_username}.")
