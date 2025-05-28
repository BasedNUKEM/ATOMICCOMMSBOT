# Environment variables should be in .env file, define as Python variables here
NUKEM_BOT_TOKEN = "your_bot_token_here"
ADMIN_USER_IDS = [123456789, 987654321]
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "nukem_bot"
ADMIN_USER_IDS=123456789,987654321
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "nukem_bot"
NUKEM_BOT_TOKEN = "7755487759:AAFVG3LYSy1-1opvPEvUiua9C186Hk0uX-we"
ADMIN_USER_IDS = [123456789, 987654321]
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME=nukem_botNUKEM_BOT_TOKEN=7755487759:AAFVG3LYSy1-1opvPEvUiua9C186Hk0uX-w
ADMIN_USER_IDS=123456789,987654321
MONGO_URI=mongodb://localhost:27017/
DB_NAME=nukem_bot# --- Imports ---
import logging
import json
import os
import sys
import time
import random
import signal
import atexit
import telegram
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from telegram import Update, Bot, ParseMode, ChatMember, ChatPermissions
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ChatMemberHandler
from telegram.error import Unauthorized, BadRequest, TimedOut, NetworkError
from functools import wraps
from db import Database

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
BOT_TOKEN = os.getenv("NUKEM_BOT_TOKEN")
ADMIN_USER_IDS = set([int(id) for id in os.getenv("ADMIN_USER_IDS", "").split(",") if id.strip()])  # Add your admin IDs to .env file
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "nukem_bot")
BACKUP_INTERVAL = 3600  # Backup every hour

# Initialize database
db = Database()

def validate_config():
    """Validate configuration and environment variables."""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TOKEN_HERE":
        logger.error("Bot token not properly configured in .env file")
        return False
        
    if not ADMIN_USER_IDS:
        logger.warning("No admin IDs configured. Bot will run with limited functionality.")
        return False
        
    for admin_id in ADMIN_USER_IDS:
        if not isinstance(admin_id, int):
            logger.error(f"Invalid admin ID format: {admin_id}")
            return False
            
    # Test database connection
    try:
        db.client.server_info()
        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return False
            
    return True

# --- NUKEM'S ARSENAL OF WORDS ---
NUKEM_QUOTES = [
    "It's time to kick ass and chew bubble gum... and I'm all out of gum.",
    "Damn, I'm looking good!",
    "Hail to the king, baby!",
    "Come get some!",
    "What are you waiting for, Christmas?",
    "I've got balls of steel.",
    "Groovy!",
    "Let God sort 'em out.",
    "Nobody steals our chicks... and lives!",
    "Your face, your ass, what's the difference?",
    "I'm gonna get medieval on your asses!",
    "Blow it out your ass!",
    "Eat shit and die!",
    "My boot, your face; the perfect couple.",
    "This is gonna be a blast!",
    "Always bet on Duke.",
    "Based. Extremely based.",
    "That's what I'm talkin' about!",
    "Get that alien scum!",
    "Time to deliver the pain!"
]

NUKEM_REACTIONS_POSITIVE = [
    "Hell yeah! That's what I'm talkin' about!",
    "Based and Nukem-pilled.",
    "Damn straight, maggot!",
    "Now you're thinking with portals... I mean, with NUKEM power!",
    "That's some big dick energy right there.",
    "Sounds like a plan. A kick-ass plan."
]

NUKEM_REACTIONS_NEGATIVE = [
    "What in the goddamn...? That sounds like alien talk.",
    "Are you on somethin', pal? Or just naturally stupid?",
    "That's about as useful as a screen door on a battleship.",
    "My grandma could come up with a better idea, and she's... well, never mind."
]

NUKEM_RATINGS = [
    "That's a 10 on the NUKEM scale of badassery! Hell yeah!",
    "Solid play. Almost as good as something I'd do.",
    "Not bad, for a rookie. Keep it up.",
    "Meh. Seen better, seen worse. Mostly worse.",
    "Are you even trying? That was weaker than alien coffee.",
    "My dog could make a better play, and he's a chihuahua... a *dead* chihuahua.",
    "What was that, a love tap? Hit 'em like you mean it!"
]

ALIEN_SCAN_REPORTS = [
    "Scanners clear. For now. Stay frosty, maggot.",
    "Detected a blip... nah, just some space junk. Or a really ugly bird.",
    "High levels of bullshit detected in this sector. Typical.",
    "Alien activity? Negative. But I did find a half-eaten donut. Score!",
    "The only alien thing around here is your fashion sense. Kidding! Mostly.",
    "All quiet on the alien front. Too quiet... Makes me wanna shoot somethin'."
]

PROJECT_INFO = {
    "roadmap": "Roadmap? We make the road as we go... and blow stuff up along the way. Q1: More ass-kicking. Q2: More bubblegum (if I find any). Q3: Moon. Q4: Your mom's house. Got a problem?",
    "tokenomics": "1 Billion $NUKEM. 5% tax - 2% to 'Babes & Ammo Fund' (marketing & development), 3% to 'Reactor Core' (liquidity & burns). Simple. Deadly. Don't like it? Tough.",
    "website": "Point your browser to www.basednukem.base - if it ain't got explosions, it ain't my site.",
    "default": "Whatcha want, maggot? Spit it out! Try `/info roadmap`, `/info tokenomics`, or `/info website`."
}

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- User Data Management ---
def load_users():
    """Load user data from JSON file with backup and error handling."""
    try:
        with open(USER_DATA_FILE, 'r') as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except FileNotFoundError:
        logger.info(f"{USER_DATA_FILE} not found. Starting with empty user list.")
        return {}
    except json.JSONDecodeError as e:
        backup_file = f"{USER_DATA_FILE}.bak"
        logger.error(f"Error reading {USER_DATA_FILE}: {e}. Trying backup...")
        try:
            if os.path.exists(backup_file):
                with open(backup_file, 'r') as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
        except Exception as backup_error:
            logger.error(f"Backup recovery failed: {backup_error}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading users: {e}")
        return {}

def save_users(users):
    """Save user data with backup creation."""
    backup_file = f"{USER_DATA_FILE}.bak"
    try:
        # Create backup of current file if it exists
        if os.path.exists(USER_DATA_FILE):
            os.replace(USER_DATA_FILE, backup_file)
            
        # Save new data
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(users, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save users: {e}")

chat_users = load_users()

# --- Admin Check Decorator ---
def admin_required(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            insults = [
                "Nice try, pencil-neck. This command's for the big boys.",
                "Whoa there, slick. You ain't got the clearance for that.",
                "Access denied. Go cry to your mama.",
                "You? Admin? Ha! That's funnier than a pig in a prom dress."
            ]
            update.message.reply_text(random.choice(insults))
            return
        return func(update, context, *args, **kwargs)
    return wrapped

# --- Helper to escape MarkdownV2 ---
def escape_markdown_v2(text):
    """Helper function to escape telegram MarkdownV2 special characters."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in str(text))

# --- Rate Limiting ---

# Rate limiting configuration
RATE_LIMIT_MESSAGES = 5  # messages
RATE_LIMIT_PERIOD = 60   # seconds
MESSAGE_TIMESTAMPS = defaultdict(list)  # user_id -> list of timestamps

def is_rate_limited(user_id: int) -> bool:
    """Check if a user has exceeded their rate limit."""
    current_time = time.time()
    user_timestamps = MESSAGE_TIMESTAMPS[user_id]
    
    # Remove timestamps older than the rate limit period
    while user_timestamps and user_timestamps[0] < current_time - RATE_LIMIT_PERIOD:
        user_timestamps.pop(0)
    
    # Add current timestamp
    user_timestamps.append(current_time)
    
    # Check if user has exceeded rate limit
    return len(user_timestamps) > RATE_LIMIT_MESSAGES

def check_rate_limit(func):
    """Decorator to add rate limiting to commands."""
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Admins bypass rate limiting
        if user_id in ADMIN_USER_IDS:
            return func(update, context, *args, **kwargs)
            
        if is_rate_limited(user_id):
            insults = [
                "Slow down, speed racer! You're typing faster than my bullets fly!",
                "Cool your jets! Even I need to reload sometimes.",
                "RATE LIMITED, maggot! Try again in a minute.",
                "What are you, a machine gun? Pace yourself!"
            ]
            update.message.reply_text(random.choice(insults))
            return None
            
        return func(update, context, *args, **kwargs)
    return wrapped

# --- Cooldown Management ---
COMMAND_COOLDOWNS = {
    "mentionall": 300,  # 5 minutes
    "pin_nukem": 60,    # 1 minute
    "alien_scan": 30,   # 30 seconds
}

LAST_COMMAND_USAGE = defaultdict(lambda: defaultdict(datetime.fromtimestamp(0).timestamp))

def command_cooldown(command_name: str):
    """Decorator to add cooldown to commands."""
    def decorator(func):
        @wraps(func)
        def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            user_id = update.effective_user.id
            current_time = datetime.now().timestamp()
            
            # Admins bypass cooldown
            if user_id in ADMIN_USER_IDS:
                return func(update, context, *args, **kwargs)
            
            last_usage = LAST_COMMAND_USAGE[command_name][user_id]
            cooldown = COMMAND_COOLDOWNS.get(command_name, 0)
            
            if current_time - last_usage < cooldown:
                remaining = int(cooldown - (current_time - last_usage))
                responses = [
                    f"Command's still recharging, maggot! {remaining}s left.",
                    f"My {command_name} cannon needs {remaining} more seconds!",
                    f"Patience, rookie! {remaining}s cooldown remaining.",
                    f"Can't do that for {remaining}s. Even Duke needs a breather!"
                ]
                update.message.reply_text(random.choice(responses))
                return None
                
            LAST_COMMAND_USAGE[command_name][user_id] = current_time
            return func(update, context, *args, **kwargs)
        return wrapped
    return decorator

# --- NUKEM Bot Commands ---

@admin_required
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Based NUKEM online and ready to party! If you're an admin, type `/help_nukem` to see the real firepower. Everyone else, try not to get any on ya."
    )

@admin_required
def help_nukem(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Alright, listen up, you privileged bastards! Here's the command console:\n\n"
        "*Basic Commands:*\n"
        "`/mentionall <message>` - Yell at *everyone*\\. Use sparingly\\, or I'll use *you* for target practice\\.\n"
        "`/mention @user1 @user2 <message>` - Point your finger at specific chumps\\.\n"
        "`/pin_nukem <message_or_reply>` - Make somethin' stick\\. Like gum to a boot\\.\n"
        "`/info <topic>` - Get the damn intel \\(roadmap\\, tokenomics\\, website\\)\\.\n"
        "`/nukem_quote` - Get a dose of pure\\, unadulterated wisdom\\.\n"
        "`/rate_my_play <your_epic_description>` - Let the Duke judge your so\\-called 'skills'\\.\n"
        "`/alien_scan` - Check if any green\\-blooded freaks are sniffin' around\\.\n\n"
        "*User Management:*\n"
        "`/sync_users` - Try to refresh my list of cannon fodder \\(admins mostly\\)\\.\n"
        "`/list_users` - See who's on my shit\\-list \\(user list\\)\\.\n"
        "`/karma @user` - Check someone's karma level\\.\n"
        "`/give_karma @user [reason]` - Award karma to a worthy soldier\\.\n"
        "`/remove_karma @user [reason]` - Take karma from a disappointment\\.\n\n"
        "*Moderation:*\n"
        "`/warn @user [reason]` - Issue a warning to a troublemaker\\.\n"
        "`/unwarn @user` - Remove a warning if they've learned their lesson\\.\n"
        "`/warnings @user` - Check someone's rap sheet\\."
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

# --- Chat Type Management ---
def chat_type_allowed(allowed_types: list):
    """Decorator to restrict commands to specific chat types."""
    def decorator(func):
        @wraps(func)
        def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            chat_type = update.effective_chat.type
            if chat_type not in allowed_types:
                responses = [
                    f"Wrong battlefield, soldier! This command only works in {', '.join(allowed_types)}.",
                    f"Can't do that here! Move to {', '.join(allowed_types)} first.",
                    f"Command restricted to {', '.join(allowed_types)}. Know your arena!"
                ]
                update.message.reply_text(random.choice(responses))
                return None
            return func(update, context, *args, **kwargs)
        return wrapped
    return decorator

# --- Apply chat type restrictions to commands ---
@chat_type_allowed(['group', 'supergroup'])
@command_cooldown("mentionall")
@admin_required
def mention_all(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    message_text = " ".join(context.args)

    if not message_text:
        update.message.reply_text("Spit it out, genius! `/mentionall <your damn message>`")
        return

    if chat_id not in chat_users or not chat_users[chat_id]:
        update.message.reply_text("My list's emptier than a politician's promises. No one to yell at.")
        return

    users_to_mention = [
        f"[@{escape_markdown_v2(username)}](tg://user?id={user_id})"
        for user_id, username in chat_users[chat_id].items()
        if username and not username.startswith("Grunt_") # Only mention users with actual usernames
    ]

    if not users_to_mention:
        update.message.reply_text("Looks like these maggots are too shy to set a username. Can't tag ghosts.")
        return

    MAX_MENTIONS_PER_MSG = 40 # Reduced for safety with longer messages
    escaped_message = escape_markdown_v2(message_text)
    base_message = f"*ATTENTION, ALL YOU SLACK-JAWED TROOPERS\\! THE DUKE HAS SPOKEN\\!*\n\n{escaped_message}\n\nTagging the usual suspects:"
    
    update.message.reply_text("Alright, lettin' 'em have it with both barrels! This might take a few shots...")

    for i in range(0, len(users_to_mention), MAX_MENTIONS_PER_MSG):
        chunk = users_to_mention[i:i + MAX_MENTIONS_PER_MSG]
        mention_block = " ".join(chunk)
        full_message = f"{base_message}\n{mention_block}"
        
        if len(full_message) > 4096: # Should be rare with chunking
            full_message = full_message[:4090] + "\\.\\.\\."
            
        try:
            context.bot.send_message(chat_id=chat_id, text=full_message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Failed to send mention chunk: {e}")
            update.message.reply_text(f"Damn it all to hell! Hit a snag: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)
            break

@admin_required
def mention_specific(update: Update, context: CallbackContext) -> None:
    args = context.args
    if not args:
        update.message.reply_text("Who am I pointing my gun at? Use `/mention @user1 @user2 <message>`")
        return

    mentions = []
    message_parts = []
    for arg in args:
        if arg.startswith('@'): mentions.append(escape_markdown_v2(arg))
        else: message_parts.append(arg)

    if not mentions: update.message.reply_text("No @'s? Are you blind or just stupid?"); return
    if not message_parts: update.message.reply_text("A message, genius! They ain't mind readers."); return

    message_text = escape_markdown_v2(" ".join(message_parts))
    mention_block = " ".join(mentions)
    full_message = f"*HEY, YOU LOT\\!* {mention_block}\n\n{message_text}\n\n*That is all\\. Carry on, or don't\\. I don't care\\.*"
    try:
        context.bot.send_message(chat_id=update.effective_chat.id, text=full_message, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        update.message.reply_text(f"Son of a bitch! Couldn't send it: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)

@admin_required
@command_cooldown("pin_nukem")
def pin_nukem(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if update.message.reply_to_message:
        message_id = update.message.reply_to_message.message_id
        try:
            context.bot.pin_chat_message(chat_id, message_id, disable_notification=False)
            update.message.reply_text("Pinned it. Like a butterfly... a really pissed-off butterfly. *KA-CHUNK!*")
        except Exception as e:
            update.message.reply_text(f"Couldn't nail that one down. Error: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        message_text = " ".join(context.args)
        if not message_text: update.message.reply_text("Pin *what*? Air? Reply or use `/pin_nukem <your message>`."); return
        try:
            sent_message = context.bot.send_message(chat_id, f"*NUKEM COMMAND DECREE\\:*\n{escape_markdown_v2(message_text)}", parse_mode=ParseMode.MARKDOWN_V2)
            context.bot.pin_chat_message(chat_id, sent_message.message_id, disable_notification=False)
            update.message.reply_text("Message sent and hammered to the top. Let's see 'em ignore that.")
        except Exception as e:
            update.message.reply_text(f"Damn space-worms ate my pin! Error: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)

@check_rate_limit
@chat_type_allowed(['private', 'group', 'supergroup'])
def info(update: Update, context: CallbackContext) -> None:
    topic = " ".join(context.args).lower() if context.args else "default"
    response = PROJECT_INFO.get(topic, PROJECT_INFO["default"])
    header = "*DUKE'S INTEL DROP:*" if topic != "default" else ""
    update.message.reply_text(f"{header}\n{escape_markdown_v2(response)}", parse_mode=ParseMode.MARKDOWN_V2)

@admin_required
def list_users(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    users = db.get_chat_users(chat_id)
    
    if not users:
        safe_markdown_message(update, "My kill list is empty for this chat\\. Either they're all hiding, or I need new glasses\\.", reply_to=True)
        return

    user_list_md = []
    for user in users:
        username = escape_markdown_v2(user['username'])
        user_id = escape_markdown_v2(str(user['user_id']))
        karma = db.get_karma(chat_id, user['user_id'])
        warnings = len(db.get_warnings(chat_id, user['user_id']))
        status = f"⭐ {karma}" if karma else ""
        status += f" 🚨 {warnings}" if warnings else ""
        status = f" \\[{escape_markdown_v2(status)}\\]" if status else ""
        
        user_list_md.append(f"\\- @{username} \\({user_id}\\){status}")

    response_header = "*CURRENT ROSTER OF POTENTIAL HEROES \\(OR TARGETS\\):*\n"
    full_response = response_header + "\n".join(user_list_md)
    
    chunks = chunk_message(full_response)
    if len(chunks) > 1:
        safe_markdown_message(update, "Got a whole damn army here\\.\\.\\. Sending the list in pieces, try to keep up\\.", reply_to=True)
        
    for chunk in chunks:
        safe_markdown_message(update, chunk)

@admin_required
def sync_users(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    update.message.reply_text("Attempting recon on the chain of command... My intel on the grunts is usually what they tell me.")
    try:
        admins = context.bot.get_chat_administrators(chat_id)
        admin_list_md = []
        synced_count = 0

        for admin_member in admins:
            user = admin_member.user
            if not user.is_bot:
                username_display = user.username if user.username else f"Admin_{user.id}"
                current_user = db.get_user(chat_id, user.id)
                
                if not current_user or current_user.get('username') != username_display:
                    db.add_or_update_user(chat_id, user.id, username_display, "administrator")
                    synced_count += 1
                    
                admin_list_md.append(f"\\- @{escape_markdown_v2(username_display)}")
        
        if admin_list_md:
            update.message.reply_text(
                f"Reconfirmed these high\\-ranking badasses \\({synced_count} new/updated\\):\n" + 
                "\n".join(admin_list_md),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            update.message.reply_text("Couldn't find any human admins, or they're already perfectly cataloged. How boring.")
    except Exception as e:
        update.message.reply_text(f"Recon failed. Maybe I got demoted? Error: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)

# --- Stats Tracking ---
BOT_STATS = {
    'start_time': datetime.now(),
    'commands_used': defaultdict(int),
    'messages_processed': 0,
    'users_tracked': 0
}

def update_stats(command: str = None):
    """Decorator to track command usage statistics."""
    def decorator(func):
        @wraps(func)
        def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
            if command:
                BOT_STATS['commands_used'][command] += 1
            return func(update, context, *args, **kwargs)
        return wrapped
    return decorator

@admin_required
def show_stats(update: Update, context: CallbackContext) -> None:
    """Show bot statistics."""
    uptime = datetime.now() - BOT_STATS['start_time']
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Get total users across all chats
    total_users = sum(len(users) for users in chat_users.values())
    
    stats_message = (
        "*NUKEM BOT BATTLE REPORT:*\n\n"
        f"Uptime: {days}d {hours}h {minutes}m {seconds}s\n"
        f"Total Users Tracked: {total_users}\n"
        f"Messages Processed: {BOT_STATS['messages_processed']}\n\n"
        "*Command Usage:*\n"
    )
    
    # Add command usage stats
    for cmd, count in sorted(BOT_STATS['commands_used'].items()):
        stats_message += f"/{cmd}: {count} uses\n"
    
    safe_markdown_message(update, escape_markdown_v2(stats_message))

# Apply stats tracking to message handler
def message_tracker(update: Update, context: CallbackContext) -> None:
    """Tracks users who send messages and handles reactions."""
    if update.message:  # Ensure it's a message update
        track_user_event(update, context, "sent a message")
        
        # Update stats
        BOT_STATS['messages_processed'] += 1
        db.update_stats("messages_total")
        db.update_stats("messages_by_chat", chat_id=update.effective_chat.id)
        db.update_stats("messages_by_user", chat_id=update.effective_chat.id, user_id=update.effective_user.id)

        # Keyword reaction
        if update.message.text:
            text = update.message.text.lower()
            if any(keyword in text for keyword in ["based", "nukem", "kick ass", "hail to the king"]):
                if update.effective_user.id not in ADMIN_USER_IDS:  # Don't react to admins to avoid loop/spam
                    context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=random.choice(NUKEM_REACTIONS_POSITIVE),
                        reply_to_message_id=update.message.message_id
                    )

# --- User Tracking ---
def track_user_event(update: Update, context: CallbackContext, action: str) -> None:
    """Track user activity and update their status in the database."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    if not user or user.is_bot:
        return

    new_username = user.username if user.username else f"Grunt_{user.id}"
    current_user = db.get_user(chat_id, user.id)

    if not current_user or current_user.get('username') != new_username:
        logger.info(f"User @{new_username} (ID: {user.id}) {action} in chat {chat_id}")
        db.add_or_update_user(chat_id, user.id, new_username)
        
    # Update message count and last seen
    db.increment_user_messages(chat_id, user.id)

# --- Enhanced Markdown Handling ---
def safe_markdown_message(update: Update, text: str, reply_to: bool = False, **kwargs) -> None:
    """Safely send a markdown message with fallback to plain text."""
    try:
        if reply_to:
            update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, **kwargs)
        else:
            update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN_V2, **kwargs)
    except Exception as e:
        logger.warning(f"Failed to send markdown message: {e}. Falling back to plain text.")
        # Strip markdown and try again
        plain_text = text.replace('\\', '').replace('*', '').replace('_', '')
        if reply_to:
            update.message.reply_text(plain_text, **kwargs)
        else:
            update.effective_chat.send_message(plain_text, **kwargs)

def chunk_message(text: str, max_length: int = 4096) -> list:
    """Split a message into chunks that respect markdown and message limits."""
    if len(text) <= max_length:
        return [text]
        
    chunks = []
    current_chunk = ""
    lines = text.split('\n')
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + '\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            current_chunk = line + '\n'
            
    if current_chunk:
        chunks.append(current_chunk.rstrip())
        
    return chunks

# --- Karma System Commands ---
@admin_required
def give_karma(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    
    if not context.args or len(context.args) < 1:
        update.message.reply_text("Who deserves the praise? Use `/give_karma @username [reason]`")
        return
        
    target_username = context.args[0].lstrip('@')
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "being awesome"
    
    users = db.get_chat_users(chat_id)
    target_user = next((user for user in users if user['username'] == target_username), None)
    
    if not target_user:
        update.message.reply_text("Can't find that user in my database. Are they even real?")
        return
        
    new_karma = db.update_karma(chat_id, target_user['user_id'], 1)
    update.message.reply_text(
        f"@{escape_markdown_v2(target_username)} just leveled up for {escape_markdown_v2(reason)}\\!\n"
        f"Current karma: {new_karma} ⭐",
        parse_mode=ParseMode.MARKDOWN_V2
    )

@admin_required
def remove_karma(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    
    if not context.args or len(context.args) < 1:
        update.message.reply_text("Who's in trouble? Use `/remove_karma @username [reason]`")
        return
        
    target_username = context.args[0].lstrip('@')
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "being a disappointment"
    
    users = db.get_chat_users(chat_id)
    target_user = next((user for user in users if user['username'] == target_username), None)
    
    if not target_user:
        update.message.reply_text("Can't find that user. Maybe they already ran away?")
        return
        
    new_karma = db.update_karma(chat_id, target_user['user_id'], -1)
    update.message.reply_text(
        f"@{escape_markdown_v2(target_username)} just lost karma for {escape_markdown_v2(reason)}\\.\n"
        f"Current karma: {new_karma} ⭐",
        parse_mode=ParseMode.MARKDOWN_V2
    )

@check_rate_limit
def check_karma(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if context.args and context.args[0].startswith('@'):
        target_username = context.args[0].lstrip('@')
        users = db.get_chat_users(chat_id)
        target_user = next((user for user in users if user['username'] == target_username), None)
        
        if not target_user:
            update.message.reply_text("That user? Never heard of 'em.")
            return
            
        karma = db.get_karma(chat_id, target_user['user_id'])
        update.message.reply_text(
            f"@{escape_markdown_v2(target_username)}'s karma: {karma} ⭐",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        karma = db.get_karma(chat_id, user.id)
        update.message.reply_text(
            f"Your karma: {karma} ⭐\n"
            f"Keep it up, soldier\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )

# --- Warning System Commands ---
@admin_required
def warn_user(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    
    if not context.args or len(context.args) < 1:
        update.message.reply_text("Who needs a warning? Use `/warn @username [reason]`")
        return
        
    target_username = context.args[0].lstrip('@')
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "violating chat rules"
    
    users = db.get_chat_users(chat_id)
    target_user = next((user for user in users if user['username'] == target_username), None)
    
    if not target_user:
        update.message.reply_text("Can't find that troublemaker in the database.")
        return
        
    admin_id = update.effective_user.id
    db.add_warning(chat_id, target_user['user_id'], reason, admin_id)
    
    warnings = len(db.get_warnings(chat_id, target_user['user_id']))
    warning_msg = (
        f"⚠️ *WARNING ISSUED* ⚠️\n\n"
        f"User: @{escape_markdown_v2(target_username)}\n"
        f"Reason: {escape_markdown_v2(reason)}\n"
        f"Total Active Warnings: {warnings}"
    )
    
    # If user has too many warnings, take action
    if warnings >= 3:
        warning_msg += "\n\n*⚠️ STRIKE THREE ⚠️*\nInitiating temporary mute..."
        try:
            # Mute for 24 hours
            until_date = datetime.now() + timedelta(hours=24)
            context.bot.restrict_chat_member(
                chat_id, target_user['user_id'],
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            db.add_mute(chat_id, target_user['user_id'], until_date, "Exceeded warning limit", admin_id)
            warning_msg += "\nMuted for 24 hours."
        except Exception as e:
            warning_msg += f"\nFailed to mute: {escape_markdown_v2(str(e))}"
    
    update.message.reply_text(warning_msg, parse_mode=ParseMode.MARKDOWN_V2)

@admin_required
def remove_warning(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    
    if not context.args or len(context.args) < 1:
        update.message.reply_text("Whose warning should I remove? Use `/unwarn @username`")
        return
        
    target_username = context.args[0].lstrip('@')
    users = db.get_chat_users(chat_id)
    target_user = next((user for user in users if user['username'] == target_username), None)
    
    if not target_user:
        update.message.reply_text("Can't find that user. Lucky them?")
        return
        
    warnings = db.get_warnings(chat_id, target_user['user_id'])
    if not warnings:
        update.message.reply_text("This user has no active warnings. They're clean... for now.")
        return
        
    # Mark the latest warning as expired by setting expiry to now
    warning = warnings[-1]  # Get most recent warning
    warning_id = warning.get('_id')
    if warning_id:
        db.warnings.update_one(
            {"_id": warning_id},
            {"$set": {"expiry": datetime.now()}})
    
    remaining = len(db.get_warnings(chat_id, target_user['user_id']))
    update.message.reply_text(
        f"Removed one warning from @{escape_markdown_v2(target_username)}\\.\n"
        f"Remaining active warnings: {remaining}",
        parse_mode=ParseMode.MARKDOWN_V2
    )

@check_rate_limit
def check_warnings(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if context.args and context.args[0].startswith('@'):
        target_username = context.args[0].lstrip('@')
        users = db.get_chat_users(chat_id)
        target_user = next((user for user in users if user['username'] == target_username), None)
        
        if not target_user:
            update.message.reply_text("That user doesn't exist in my database.")
            return
            
        user_id = target_user['user_id']
    else:
        user_id = user.id
        target_username = user.username or f"Grunt_{user.id}"
    
    warnings = db.get_warnings(chat_id, user_id)
    if not warnings:
        update.message.reply_text(
            f"@{escape_markdown_v2(target_username)} has a clean record\\. For now\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    warning_list = []
    for i, warn in enumerate(warnings, 1):
        admin = context.bot.get_chat_member(chat_id, warn['admin_id']).user
        admin_name = escape_markdown_v2(admin.username or f"Admin_{admin.id}")
        warning_list.append(
            f"{i}\\. By @{admin_name}: {escape_markdown_v2(warn['reason'])}"
        )
    
    update.message.reply_text(
        f"*Active warnings for @{escape_markdown_v2(target_username)}:*\n\n" +
        "\n".join(warning_list),
        parse_mode=ParseMode.MARKDOWN_V2
    )

# --- Public Commands ---
@check_rate_limit
def nukem_quote(update: Update, context: CallbackContext) -> None:
    """Get a random Duke Nukem quote."""
    update.message.reply_text(random.choice(NUKEM_QUOTES))

@check_rate_limit
def rate_my_play(update: Update, context: CallbackContext) -> None:
    """Rate someone's play or action."""
    if not context.args:
        update.message.reply_text("What am I rating here? Use `/rate_my_play <your epic description>`")
        return
        
    play_description = " ".join(context.args)
    rating = random.choice(NUKEM_RATINGS)
    update.message.reply_text(
        f"*Rating your play:* _{escape_markdown_v2(play_description)}_\n\n{escape_markdown_v2(rating)}",
        parse_mode=ParseMode.MARKDOWN_V2
    )

@check_rate_limit
@command_cooldown("alien_scan")
def alien_scan(update: Update, context: CallbackContext) -> None:
    """Scan for alien activity."""
    update.message.reply_text(random.choice(ALIEN_SCAN_REPORTS))

def schedule_backups(context: CallbackContext) -> None:
    """Scheduled backup task."""
    try:
        # MongoDB provides automatic persistence
        # Here we could implement additional backup logic if needed
        logger.info("Scheduled backup check completed")
    except Exception as e:
        logger.error(f"Failed to perform scheduled backup: {e}")

# --- Error Handling ---
def handle_telegram_error(update: Update, context: CallbackContext) -> None:
    """Handle Telegram API errors."""
    logger.error(f"Update {update} caused error: {context.error}")
    
    error_msg = "Mission failed! We'll get 'em next time."
    if isinstance(context.error, Unauthorized):
        error_msg = "I've been kicked out or blocked. Can't continue mission."
    elif isinstance(context.error, BadRequest):
        error_msg = "Bad request. Someone's not playing by the rules."
    elif isinstance(context.error, TimedOut):
        error_msg = "Connection timed out. Servers must be running on potato power."
    elif isinstance(context.error, NetworkError):
        error_msg = "Network error. The aliens must be jamming our signal."
    
    if update and update.effective_message:
        update.effective_message.reply_text(
            escape_markdown_v2(error_msg),
            parse_mode=ParseMode.MARKDOWN_V2
        )

# --- User Tracking ---
def chat_member_update_handler(update: Update, context: CallbackContext) -> None:
    """Tracks users joining or leaving based on ChatMember updates."""
    result = update.chat_member
    if not result: return

    chat_id = result.chat.id
    user = result.new_chat_member.user
    status = result.new_chat_member.status

    if user.is_bot: return
    
    username_display = user.username if user.username else f"Grunt_{user.id}"

    if status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.CREATOR]:
        db.add_or_update_user(chat_id, user.id, username_display, status)
        logger.info(f"User @{username_display} (ID: {user.id}) joined/updated in chat {chat_id}")
        
        # Send welcome message for new members
        welcome_msg = db.get_welcome_message(chat_id)
        if welcome_msg:
            context.bot.send_message(
                chat_id,
                welcome_msg.format(
                    username=username_display,
                    chat_name=update.effective_chat.title or "this chat"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    elif status in [ChatMember.LEFT, ChatMember.KICKED]:
        db.remove_user(chat_id, user.id)
        logger.info(f"User @{username_display} (ID: {user.id}) left/kicked from chat {chat_id}")

# --- Main Function ---
def main() -> None:
    """Main bot function with improved initialization and shutdown handling."""
    if not validate_config():
        logger.error("!!! Configuration validation failed. Check your .env file and admin IDs !!!")
        return

    try:
        logger.info("Initializing Based NUKEM Bot...")
        updater = Updater(BOT_TOKEN)
        dispatcher = updater.dispatcher

        # Set up periodic backups
        job_queue = updater.job_queue
        job_queue.run_repeating(schedule_backups, interval=BACKUP_INTERVAL, first=BACKUP_INTERVAL)
        
        # Admin Commands
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("help_nukem", help_nukem))
        dispatcher.add_handler(CommandHandler("mentionall", mention_all))
        dispatcher.add_handler(CommandHandler("mention", mention_specific))
        dispatcher.add_handler(CommandHandler("pin_nukem", pin_nukem))
        dispatcher.add_handler(CommandHandler("list_users", list_users))
        dispatcher.add_handler(CommandHandler("sync_users", sync_users))
        dispatcher.add_handler(CommandHandler("stats", show_stats))
        
        # User Management Commands
        dispatcher.add_handler(CommandHandler("karma", check_karma))
        dispatcher.add_handler(CommandHandler("give_karma", give_karma))
        dispatcher.add_handler(CommandHandler("remove_karma", remove_karma))
        dispatcher.add_handler(CommandHandler("warn", warn_user))
        dispatcher.add_handler(CommandHandler("unwarn", remove_warning))
        dispatcher.add_handler(CommandHandler("warnings", check_warnings))

        # Public Commands
        dispatcher.add_handler(CommandHandler("info", info))
        dispatcher.add_handler(CommandHandler("nukem_quote", nukem_quote))
        dispatcher.add_handler(CommandHandler("rate_my_play", rate_my_play))
        dispatcher.add_handler(CommandHandler("alien_scan", alien_scan))
        
        # Message and Member Handlers
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, message_tracker))
        dispatcher.add_handler(ChatMemberHandler(chat_member_update_handler, ChatMemberHandler.MY_CHAT_MEMBER | ChatMemberHandler.CHAT_MEMBER))

        # Error handler
        dispatcher.add_error_handler(handle_telegram_error)
        
        # Start the bot
        logger.info("Based NUKEM Bot locked, loaded, and starting polling... Time to paint the town red.")
        updater.start_polling()
        
        # Run the bot until Ctrl-C is pressed or the bot receives SIGTERM/SIGINT
        updater.idle()
        
    except Exception as e:
        logger.error(f"Critical failure starting NUKEM Bot: {e}")
        raise
    finally:
        logger.info("Based NUKEM signing off. I need a drink... and a bigger gun.")
        db.close()

if __name__ == '__main__':
    main()