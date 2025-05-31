"""
This module stores all constant values and configurations for the NUKEM Bot.
This includes quotes, reaction messages, API configurations, and other static data.
"""

import os
from dotenv import load_dotenv
from datetime import timedelta

# Load environment variables from .env file
load_dotenv()

# Emojis for Bot Responses (Defined first to be available for other constants)
EMOJI_SUCCESS = "✅"
EMOJI_ERROR = "❌"
EMOJI_WARNING = "⚠️"
EMOJI_INFO = "ℹ️"
EMOJI_QUESTION = "❓"
EMOJI_WAIT = "⏳"
EMOJI_ROCKET = "🚀"
EMOJI_BOMB = "💣"
EMOJI_NUKE = "☢️"
EMOJI_FIRE = "🔥"
EMOJI_SKULL = "💀"
EMOJI_ALIEN = "👽"
EMOJI_ROBOT = "🤖"
EMOJI_TARGET = "🎯"
EMOJI_SHIELD = "🛡️"
EMOJI_NO_ENTRY = "⛔"
EMOJI_ADMIN = "👑"
EMOJI_USER = "👤"
EMOJI_CHAT = "💬"
EMOJI_STAR = "⭐"
KARMA_EMOJI = EMOJI_STAR
EMOJI_PIN = "📌"
EMOJI_COMMAND = "⚙️"
EMOJI_CYCLE = "🔄"
EMOJI_CHECKMARK = "✅"
EMOJI_SUNGLASSES = "😎"
EMOJI_PARTY = "🎉"
EMOJI_THINKING = "🤔"
EMOJI_EYES = "👀"
EMOJI_CHART_DOWN = "📉"
EMOJI_YELLOW_CIRCLE = "🟡"
EMOJI_GREEN_CIRCLE = "🟢"
EMOJI_RED_CIRCLE = "🔴"
EMOJI_BRAIN = "🧠"
EMOJI_TOOLS = "🛠️"
EMOJI_LINK = "🔗"
EMOJI_BOOK = "📖"
EMOJI_CHART_UP = "📈"
EMOJI_GEAR = "⚙️"  # Note: EMOJI_COMMAND also uses "⚙️", this is fine.
EMOJI_STOPWATCH = "⏱️"
EMOJI_LEADERBOARD = "🏆"
EMOJI_DATABASE = "💾"
EMOJI_BROADCAST = "📢"
EMOJI_WAVE = "👋"
EMOJI_LIGHTBULB = "💡"
EMOJI_SCROLL = "📜"
EMOJI_CROSS_MARK = "❌"
EMOJI_HOURGLASS = "⏳"  # Added EMOJI_HOURGLASS (Note: EMOJI_WAIT also uses "⏳")
EMOJI_PAGER = "📟"  # Added EMOJI_PAGER
EMOJI_INBOX = "📥"  # Added EMOJI_INBOX
EMOJI_OUTBOX = "📤"  # Added EMOJI_OUTBOX
EMOJI_PACKAGE = "📦"  # Added EMOJI_PACKAGE
EMOJI_MEMO = "📝"  # Added EMOJI_MEMO
EMOJI_CLIPBOARD = "📋"
EMOJI_PUSHPIN = "📌"
EMOJI_NOTEPAD = "🗒️"
EMOJI_CALENDAR = "📅"
EMOJI_GRAPH = "📊"
EMOJI_BAR_CHART = "📈"
EMOJI_SPEECH_BUBBLE = "💬"
EMOJI_EXPLOSION = "💥"  # Added EMOJI_EXPLOSION

# Admin User IDs - Loaded from environment variable
RAW_ADMIN_USER_IDS = os.getenv("NUKEM_ADMIN_USER_IDS", "") # Changed "ADMIN_USER_IDS" to "NUKEM_ADMIN_USER_IDS"
if not RAW_ADMIN_USER_IDS:
    print(f"{EMOJI_WARNING} WARNING: NUKEM_ADMIN_USER_IDS environment variable not set. Admin commands will not be restricted.")
    ADMIN_USER_IDS = set()
else:
    try:
        ADMIN_USER_IDS = {int(admin_id.strip()) for admin_id in RAW_ADMIN_USER_IDS.split(',') if admin_id.strip()}
    except ValueError:
        print(f"{EMOJI_ERROR} ERROR: NUKEM_ADMIN_USER_IDS environment variable contains non-integer values. Please check your .env file.")
        ADMIN_USER_IDS = set()

# Bot Behavior Constants
RATE_LIMIT_PERIOD = timedelta(seconds=5)
COMMAND_COOLDOWNS = {
    "default": 5,
    "nukem": 60,
    "scan_alien": 30,
    "mention_all": 120,
    "rate_user": 10,
    "warn": 10,
    "karma": 5,
    "stats": 10,
    "info": 10,
    "help": 5,
}

NUKEM_QUOTES = [
    f"{EMOJI_NUKE} Initiating NUKEM sequence!",
    f"{EMOJI_TARGET} Target acquired. NUKEM incoming!",
    f"{EMOJI_ROCKET} Launching the big one!",
    f"{EMOJI_FIRE} Prepare for annihilation!",
    f"{EMOJI_SKULL} Dust off, it's NUKEM time!",
]

NUKEM_REACTIONS_POSITIVE = [EMOJI_FIRE, EMOJI_ROCKET, EMOJI_BOMB, EMOJI_NUKE, EMOJI_SUNGLASSES, EMOJI_PARTY, "💥", "💯"]
NUKEM_REACTIONS_NEGATIVE = [EMOJI_NO_ENTRY, EMOJI_SHIELD, EMOJI_THINKING, EMOJI_EYES, "🚫", "🤦‍♂️"]

NUKEM_RATINGS = [
    f"1/10 {EMOJI_CHART_DOWN} - Needs more radioactive material.",
    f"3/10 {EMOJI_YELLOW_CIRCLE} - A bit of a dud.",
    f"5/10 {EMOJI_TARGET} - Decent blast radius.",
    f"7/10 {EMOJI_FIRE} - Now we're talking!",
    f"10/10 {EMOJI_STAR} - Absolutely devastating! Magnificent!",
    f"Over 9000! {EMOJI_ROCKET}{EMOJI_FIRE}{EMOJI_NUKE} - It's... it's beautiful!",
]

ALIEN_SCAN_REPORTS = [
    f"{EMOJI_GREEN_CIRCLE} All clear. No {EMOJI_ALIEN} life signs detected. You're safe... for now.",
    f"{EMOJI_YELLOW_CIRCLE} Minor energy fluctuations detected. Could be space cows or a very shy {EMOJI_ALIEN}.",
    f"{EMOJI_RED_CIRCLE} High probability of {EMOJI_ALIEN} presence! Shields up! {EMOJI_SHIELD}",
    f"{EMOJI_ALIEN}{EMOJI_TARGET} Confirmed {EMOJI_ALIEN} contact! They're asking for our leader... or maybe just sugar.",
    f"{EMOJI_BRAIN} Scanners indicate a non-corporeal entity. Spooky {EMOJI_ALIEN}!",
]

PROJECT_INFO = {
    "default": f"""{EMOJI_ROBOT} **NUKEM Bot Enhanced** {EMOJI_NUKE}
Version: 2.1.0 (Codename: 'Perfectionist\'s Fallout')
Developed by: The NUKEM Command
Purpose: {EMOJI_TOOLS} Tactical communication & chat enhancement.
{EMOJI_LINK} Source: [GitHub](https://github.com/yourrepo/NUKEMBot)  # Replace with your actual repo link
{EMOJI_BOOK} Use /help for a list of commands.""",
    "roadmap": f"{EMOJI_ROCKET} **Roadmap:** Placeholder - Our top-secret plans for making this bot even more badass! Stay tuned for updates on new features, game integrations, and more ways to kick alien butt.",
    "tokenomics": f"{EMOJI_CHART_UP} **Tokenomics:** Placeholder - Currently, the NUKEM Bot operates on pure, unadulterated awesomeness (and server resources). No tokens here, just glory!",
    "website": f"{EMOJI_LINK} **Website:** Placeholder - The official NUKEM Bot command center is under construction. Check back soon for a dedicated site!"
    # Add other topics here if needed
}

DUKE_ARSENAL = {
    "pistol": f"{EMOJI_TARGET} **M1911 Pistol:** \"My trusty sidearm. Good for plinkin' pigs or when I'm fresh outta gum.\"",
    "shotgun": f"{EMOJI_FIRE} **Shotgun:** \"Close encounters? This baby makes 'em real personal. Spread the love!\"",
    "ripper": f"{EMOJI_GEAR} **Ripper Chaingun:** \"Time to chew! This thing turns alien scum into swiss cheese faster than you can say 'Hail to the King!\"",
    "rpg": f"{EMOJI_ROCKET} **RPG:** \"For when you absolutely, positively gotta blow every motherf***er in the room away. Accept no substitutes!\"",
    "pipebomb": f"{EMOJI_BOMB} **Pipe Bomb:** \"Cook 'em, toss 'em, and watch the giblets fly! Heh heh, what a mess.\"",
    "freezethrower": f"{EMOJI_ALIEN} **Freezethrower:** \"Let's kick some ice! Perfect for stopping those hot-headed aliens in their tracks.\"",
    "shrinker": f"{EMOJI_ROBOT} **Shrinker/Expander:** \"Size matters. Sometimes smaller is better... for stompin'! Then, boom! Back to normal, or bigger!\"",
    "devastator": f"{EMOJI_NUKE} **Devastator:** \"Dual-barreled rocket mayhem! If one rocket ain't enough, two oughta do the trick. Twice the fun, twice the destruction!\"",
    "tripbomb": f"{EMOJI_WARNING} **Laser Tripbomb:** \"Surprise! Set these babies up and watch the fireworks when some unsuspecting alien schmuck walks by. Always a classic.\""
}

RATE_LIMIT_MESSAGES = {
    "user": f"{EMOJI_STOPWATCH} Hold your horses, commander! You're sending commands too quickly. Try again in a few seconds.",
    "chat": f"{EMOJI_STOPWATCH} This chat is getting a bit too spicy with commands! {EMOJI_FIRE} Please wait a moment before sending more."
}
