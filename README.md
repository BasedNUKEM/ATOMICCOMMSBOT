# Based NUKEM Bot

A Telegram bot that brings Duke Nukem's attitude to your group chats! Features user tracking, admin commands, and Duke's signature style.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a .env file in the project root with your bot token and admin IDs:
```env
NUKEM_BOT_TOKEN=7755487759:AAFVG3LYSyl-lopvPEvUiua9Cl86Hk0uX-w
ADMIN_USER_IDS=7898354400
```

Replace `your_bot_token_here` with your bot token from @BotFather, and add your Telegram user IDs (comma-separated) for admin access.

## Running the Bot

```bash
python nukem_bot.py
```

## Features

### Admin Commands
- `/start` - Start the bot (admin only)
- `/help_nukem` - Show all commands
- `/mentionall <message>` - Mention all users with a message
- `/mention @user1 @user2 <message>` - Mention specific users
- `/pin_nukem <message>` - Pin a message
- `/list_users` - Show all tracked users
- `/sync_users` - Update admin list

### Public Commands
- `/info <topic>` - Get project info (roadmap, tokenomics, website)
- `/nukem_quote` - Get a random Duke Nukem quote
- `/rate_my_play <description>` - Get Duke's opinion on your play
- `/alien_scan` - Check for alien activity

### Auto Features
- Tracks users in chats
- Reacts to keywords with Duke's attitude
- Monitors chat member updates

## Notes

- Bot uses MongoDB to save user data.
- Make sure your bot has appropriate permissions in the group
- Run with Python 3.7+
