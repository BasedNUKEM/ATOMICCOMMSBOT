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

print("--- SCRIPT nukem_bot.py STARTED ---") # First line of the script

# Standard library imports
import asyncio
import atexit
import logging
import os
import random
import signal
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional
import traceback # Added for detailed exception printing

# Third party imports
from dotenv import load_dotenv
from telegram import Update, ChatMember, ChatPermissions, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters
)
from telegram.error import NetworkError, BadRequest, TelegramError

# Local imports
from db import Database, DatabaseError
from constants import * # Import all constants

print("--- IMPORTS COMPLETED ---")
sys.stdout.flush()

print("--- STARTING GLOBAL DEFINITIONS/CALLS (PRE-MAIN) ---")
sys.stdout.flush()
try:
    # Load environment variables from .env file
    print("--- CALLING load_dotenv() ---")
    sys.stdout.flush()
    load_dotenv()
    print("--- load_dotenv() COMPLETED ---")
    sys.stdout.flush()

    # --- Configuration ---
    print("--- GETTING BOT_TOKEN ---")
    sys.stdout.flush()
    BOT_TOKEN = os.getenv("NUKEM_BOT_TOKEN")
    print(f"--- BOT_TOKEN RETRIEVED: {'SET' if BOT_TOKEN and BOT_TOKEN != 'YOUR_TOKEN_HERE' else 'NOT SET or DEFAULT'} ---")
    sys.stdout.flush()
    # ADMIN_USER_IDS is now loaded from constants.py
    print("--- GETTING MONGO_URI ---")
    sys.stdout.flush()
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    print("--- MONGO_URI RETRIEVED ---")
    sys.stdout.flush()
    print("--- GETTING DB_NAME ---")
    sys.stdout.flush()
    DB_NAME = os.getenv("DB_NAME", "nukem_bot")
    print("--- DB_NAME RETRIEVED ---")
    sys.stdout.flush()

    # --- Logging Setup ---
    print("--- CONFIGURING LOGGING ---")
    sys.stdout.flush()
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    print("--- LOGGING CONFIGURED ---")
    sys.stdout.flush()

    # --- Database Setup ---
    db: Optional[Database] = None
    print("--- GLOBAL 'db' VARIABLE INITIALIZED ---")
    sys.stdout.flush()

    async def setup_database():
        '''Initialize database connection with error handling.'''
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
    print("--- setup_database FUNCTION DEFINED ---")
    sys.stdout.flush()

    # --- Resource Cleanup ---
    def cleanup():  # Changed from async def
        '''Cleanup resources before shutdown.'''
        global db  # pylint: disable=global-statement
        if db:
            db.close() # db.close() is synchronous
            logger.info(f"{EMOJI_TOOLS} Database connections closed")
    print("--- cleanup FUNCTION DEFINED ---")
    sys.stdout.flush()

    # --- Configuration Validation ---
    async def validate_config():
        '''Validate configuration and environment variables.'''
        if not BOT_TOKEN or BOT_TOKEN == "YOUR_TOKEN_HERE":
            logger.error(f"{EMOJI_ERROR} Critical: Bot token not properly configured in .env file. Bot cannot start.")
            return False
        
        if not ADMIN_USER_IDS: 
            logger.warning(f"{EMOJI_WARNING} ADMIN_USER_IDS is empty (checked in nukem_bot.py after import). Ensure it\\'s set correctly in .env and loaded by constants.py. Admin commands might not be restricted as expected globally, relying on chat admin checks where applicable.")

        if not MONGO_URI or not DB_NAME:
            logger.error(f"{EMOJI_ERROR} Critical: MONGO_URI or DB_NAME not configured. Database connection will fail.")
            return False

        # Call the async setup_database correctly
        print("--- VALIDATE_CONFIG: CALLING setup_database() ---")
        sys.stdout.flush()
        db_setup_success = await setup_database()
        print(f"--- VALIDATE_CONFIG: setup_database() RETURNED: {db_setup_success} ---")
        sys.stdout.flush()
        if not db_setup_success:
            logger.error(f"{EMOJI_ERROR} Critical: Database setup failed during validation. Bot cannot start.")
            return False
        
        logger.info(f"{EMOJI_SUCCESS} Configuration validated successfully.")
        return True
    print("--- validate_config FUNCTION DEFINED ---")
    sys.stdout.flush()

    # --- Signal Handling & Graceful Shutdown ---
    def signal_handler(signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"{EMOJI_WARNING} Received signal {signum}. Initiating graceful shutdown...")
        # The atexit handler will manage the async cleanup.
        # Forcing exit here ensures the process terminates after logging.
        sys.exit(0)
    print("--- signal_handler FUNCTION DEFINED ---")
    sys.stdout.flush() 
    print("--- SETTING UP SIGNAL HANDLERS ---")
    sys.stdout.flush()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    print("--- SIGNAL HANDLERS SET UP ---")
    sys.stdout.flush()

    # ... existing _atexit_cleanup ...
    print("--- _atexit_cleanup FUNCTION DEFINED ---")
    sys.stdout.flush()
    print("--- REGISTERING ATEXIT CLEANUP ---")
    sys.stdout.flush()
    atexit.register(_atexit_cleanup)
    print("--- ATEXIT CLEANUP REGISTERED ---")
    sys.stdout.flush()

    # --- Stats Tracking (to be moved to bot_setup.py later) ---
    # ... existing BOT_STATS and update_stats ...
    print("--- BOT_STATS DEFINED ---")
    sys.stdout.flush()
    print("--- update_stats FUNCTION DEFINED ---")
    sys.stdout.flush()
    
    print("--- GLOBAL DEFINITIONS/CALLS (PRE-MAIN) BLOCK SUCCESSFULLY COMPLETED ---")
    sys.stdout.flush()

except Exception as e:
    print(f"CRITICAL ERROR during global setup (PRE-MAIN): {type(e).__name__}: {e}", file=sys.stderr)
    sys.stderr.flush()
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    if 'logger' in locals() and logger:
        logger.critical(f"CRITICAL ERROR during global setup (PRE-MAIN): {e}", exc_info=True)
    else:
        logging.critical(f"CRITICAL ERROR during global setup (PRE-MAIN) - logger not fully available: {e}", exc_info=True)
    sys.exit(1)

# --- Command Handlers ---
# ... existing command handlers ...


# --- Message Handlers ---
# ... existing message handlers ...


# --- Chat Member Handlers ---
# ... existing chat member handlers ...


# --- Error Handlers ---
# ... existing error handlers ...


# --- Main Application Setup ---
async def post_init(application: Application): # MODIFIED: Made async
    """
    Post-initialization tasks, like setting bot commands.
    """
    print("--- ENTERING post_init ---") # ADDED
    sys.stdout.flush() # ADDED
    try:
        bot_commands = [
            BotCommand("start", "Kick some alien ass and start the bot!"),
            BotCommand("help", "Show all available commands and how to use 'em."),
            BotCommand("mentionall", "Mention all users in the chat"),
            BotCommand("mention", "Mention specific users"),
            BotCommand("pin_nukem", "Pin a message in the chat"),
            BotCommand("info", "Get information about the project"),
            BotCommand("nukem_quote", "Receive a random Duke Nukem quote"),
            BotCommand("rate_my_play", "Get a rating for your described play"),
            BotCommand("alien_scan", "Scan for aliens in the chat"),
            BotCommand("stats", "Show bot usage statistics."),
            BotCommand("leaderboard", "View the karma or activity leaderboard"),
            BotCommand("arsenal", "View the arsenal of commands"),
            BotCommand("list_users", "List users in the chat"),
            BotCommand("sync_users", "Sync chat administrators with the database"),
            BotCommand("give_karma", "Give karma to a user"),
            BotCommand("remove_karma", "Remove karma from a user"),
            BotCommand("warn", "Warn a user"),
            BotCommand("unwarn", "Remove a warning from a user"),
            BotCommand("mute", "Mute a user"),
            BotCommand("unmute", "Unmute a user"),
            BotCommand("show_stats", "Show your personal stats"),
            BotCommand("help", "Get help using the bot")
        ]
        # Correctly await get_my_commands and set_my_commands
        print("--- post_init: GETTING current bot commands ---") # ADDED
        sys.stdout.flush() # ADDED
        current_commands = await application.bot.get_my_commands()
        print(f"--- post_init: Current bot commands: {current_commands} ---") # ADDED
        sys.stdout.flush() # ADDED

        # Only set commands if they are different to avoid unnecessary API calls
        # Convert current_commands to a comparable format if necessary (e.g., list of dicts)
        # For simplicity, we'll compare based on command name and description for now.
        # A more robust check might involve converting both to sets of tuples.
        current_commands_simple = [(cmd.command, cmd.description) for cmd in current_commands]
        new_commands_simple = [(cmd.command, cmd.description) for cmd in bot_commands]

        if set(current_commands_simple) != set(new_commands_simple):
            print("--- post_init: SETTING new bot commands ---") # ADDED
            sys.stdout.flush() # ADDED
            await application.bot.set_my_commands(bot_commands)
            logger.info(f"{EMOJI_COMMAND} Bot commands updated successfully.")
            print("--- post_init: Bot commands SET ---") # ADDED
            sys.stdout.flush() # ADDED
        else:
            logger.info(f"{EMOJI_COMMAND} Bot commands are already up to date.")
            print("--- post_init: Bot commands ALREADY UP TO DATE ---") # ADDED
            sys.stdout.flush() # ADDED

    except NetworkError as ne:
        logger.error(f"{EMOJI_ERROR} Network error during post_init (setting commands): {ne}", exc_info=True)
        print(f"--- post_init: NetworkError: {ne} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    except BadRequest as br:
        logger.error(f"{EMOJI_ERROR} Bad request during post_init (setting commands): {br}", exc_info=True)
        print(f"--- post_init: BadRequest: {br} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    except TelegramError as te: # Catch broader Telegram errors
        logger.error(f"{EMOJI_ERROR} Telegram error during post_init (setting commands): {te}", exc_info=True)
        print(f"--- post_init: TelegramError: {te} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    except Exception as e:
        logger.error(f"{EMOJI_ERROR} Unexpected error during post_init (setting commands): {e}", exc_info=True)
        print(f"--- post_init: Unexpected error: {e} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    print("--- LEAVING post_init ---") # ADDED
    sys.stdout.flush() # ADDED


async def main() -> None: # MODIFIED: Made async to allow await validate_config()
    """Start the bot."""
    print("--- ENTERING main() ---") # ADDED
    sys.stdout.flush() # ADDED

    print("--- main(): CALLING validate_config() ---") # ADDED
    sys.stdout.flush() # ADDED
    if not await validate_config(): # Correctly await validate_config
        logger.critical(f"{EMOJI_ERROR} Configuration validation failed. Bot cannot start.")
        print("--- main(): validate_config() FAILED. Exiting. ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
        return # Exit if validation fails

    print("--- main(): CREATING Application ---") # ADDED
    sys.stdout.flush() # ADDED
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    print("--- main(): Application CREATED ---") # ADDED
    sys.stdout.flush() # ADDED
    
    # Register handlers
    # ... existing handler registrations ...

    print("--- main(): STARTING application.run_polling() ---") # ADDED
    sys.stdout.flush() # ADDED
    try:
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
    except NetworkError as ne:
        logger.error(f"{EMOJI_ERROR} Network error during application.run_polling: {ne}. Check internet connection and Telegram API status.", exc_info=True)
        print(f"--- main(): NetworkError in run_polling: {ne} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    except TelegramError as te:
        logger.error(f"{EMOJI_ERROR} Telegram error during application.run_polling: {te}", exc_info=True)
        print(f"--- main(): TelegramError in run_polling: {te} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    except Exception as e:
        logger.error(f"{EMOJI_ERROR} Unexpected error during application.run_polling: {e}", exc_info=True)
        print(f"--- main(): Unexpected error in run_polling: {e} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    finally:
        print("--- main(): application.run_polling() EXITED/FINISHED ---") # ADDED
        sys.stdout.flush() # ADDED
        # Cleanup is handled by atexit

# --- Main Execution ---
if __name__ == '__main__':
    print("--- ENTERING __main__ BLOCK ---")
    sys.stdout.flush()
    try:
        print("--- __main__: CALLING asyncio.run(main()) ---") # ADDED
        sys.stdout.flush() # ADDED
        asyncio.run(main())
        print("--- __main__: asyncio.run(main()) COMPLETED ---") # ADDED
        sys.stdout.flush() # ADDED
    except KeyboardInterrupt:
        logger.info(f"{EMOJI_WARNING} Bot manually interrupted by user (KeyboardInterrupt).")
        print("\\n--- __main__: KeyboardInterrupt CAUGHT ---") # ADDED
        sys.stdout.flush() # ADDED
    except SystemExit as se: # To catch sys.exit calls from signal_handler or elsewhere
        logger.info(f"{EMOJI_WARNING} SystemExit called with code: {se.code}")
        print(f"--- __main__: SystemExit CAUGHT with code: {se.code} ---") # ADDED
        sys.stdout.flush() # ADDED
    except Exception as e: # Catch-all for any other unexpected errors at the top level
        logger.critical(f"{EMOJI_ERROR} Unhandled critical error in __main__: {e}", exc_info=True)
        print(f"--- __main__: CRITICAL UNHANDLED ERROR: {e} ---", file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
        traceback.print_exc(file=sys.stderr) # ADDED
        sys.stderr.flush() # ADDED
    finally:
        print("--- __main__ BLOCK FINISHED ---") # ADDED
        sys.stdout.flush() # ADDED
        # atexit will handle cleanup
