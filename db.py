import os
from datetime import datetime
from typing import Dict, List, Optional, Union
from pymongo import MongoClient
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv()

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "nukem_bot")

class Database:
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        
        # Collections
        self.users = self.db.users
        self.chats = self.db.chats
        self.stats = self.db.stats
        self.warnings = self.db.warnings
        self.karma = self.db.karma
        self.moderation = self.db.moderation
        
        # Create indexes
        self._setup_indexes()
    
    def _setup_indexes(self):
        """Set up database indexes for better query performance."""
        # User indexes
        self.users.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        self.users.create_index("username")
        
        # Karma indexes
        self.karma.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        
        # Warning indexes
        self.warnings.create_index([("user_id", 1), ("chat_id", 1)])
        self.warnings.create_index("expiry")
        
        # Moderation indexes
        self.moderation.create_index([("chat_id", 1), ("type", 1)])
        self.moderation.create_index("expiry")
    
    def add_or_update_user(self, chat_id: int, user_id: int, username: str, status: str = "member") -> None:
        """Add or update a user in the database."""
        self.users.update_one(
            {"user_id": user_id, "chat_id": chat_id},
            {
                "$set": {
                    "username": username,
                    "status": status,
                    "last_seen": datetime.now(),
                    "messages_count": 0,
                }
            },
            upsert=True
        )
    
    def remove_user(self, chat_id: int, user_id: int) -> None:
        """Remove a user from the database."""
        self.users.delete_one({"user_id": user_id, "chat_id": chat_id})
    
    def get_user(self, chat_id: int, user_id: int) -> Optional[Dict]:
        """Get user information."""
        return self.users.find_one({"user_id": user_id, "chat_id": chat_id})
    
    def get_chat_users(self, chat_id: int) -> List[Dict]:
        """Get all users in a chat."""
        return list(self.users.find({"chat_id": chat_id}))
    
    def increment_user_messages(self, chat_id: int, user_id: int) -> None:
        """Increment user message count."""
        self.users.update_one(
            {"user_id": user_id, "chat_id": chat_id},
            {
                "$inc": {"messages_count": 1},
                "$set": {"last_seen": datetime.now()}
            }
        )
    
    def update_karma(self, chat_id: int, user_id: int, change: int) -> int:
        """Update user karma and return new value."""
        result = self.karma.find_one_and_update(
            {"user_id": user_id, "chat_id": chat_id},
            {
                "$inc": {"karma": change},
                "$setOnInsert": {"created_at": datetime.now()}
            },
            upsert=True,
            return_document=True
        )
        return result["karma"]
    
    def get_karma(self, chat_id: int, user_id: int) -> int:
        """Get user karma."""
        result = self.karma.find_one({"user_id": user_id, "chat_id": chat_id})
        return result["karma"] if result else 0
    
    def add_warning(self, chat_id: int, user_id: int, reason: str, 
                    admin_id: int, expiry: Optional[datetime] = None) -> None:
        """Add a warning for a user."""
        self.warnings.insert_one({
            "user_id": user_id,
            "chat_id": chat_id,
            "reason": reason,
            "admin_id": admin_id,
            "timestamp": datetime.now(),
            "expiry": expiry
        })
    
    def get_warnings(self, chat_id: int, user_id: int, active_only: bool = True) -> List[Dict]:
        """Get user warnings."""
        query = {"user_id": user_id, "chat_id": chat_id}
        if active_only:
            query["$or"] = [
                {"expiry": {"$gt": datetime.now()}},
                {"expiry": None}
            ]
        return list(self.warnings.find(query))
    
    def add_mute(self, chat_id: int, user_id: int, until: datetime, 
                reason: str, admin_id: int) -> None:
        """Add a temporary mute for a user."""
        self.moderation.insert_one({
            "chat_id": chat_id,
            "user_id": user_id,
            "type": "mute",
            "until": until,
            "reason": reason,
            "admin_id": admin_id,
            "timestamp": datetime.now()
        })
    
    def get_active_mutes(self, chat_id: int) -> List[Dict]:
        """Get all active mutes in a chat."""
        return list(self.moderation.find({
            "chat_id": chat_id,
            "type": "mute",
            "until": {"$gt": datetime.now()}
        }))
    
    def add_chat_rule(self, chat_id: int, rule: str) -> None:
        """Add a chat rule."""
        self.chats.update_one(
            {"chat_id": chat_id},
            {
                "$push": {"rules": rule},
                "$setOnInsert": {"created_at": datetime.now()}
            },
            upsert=True
        )
    
    def get_chat_rules(self, chat_id: int) -> List[str]:
        """Get chat rules."""
        chat = self.chats.find_one({"chat_id": chat_id})
        return chat.get("rules", []) if chat else []
    
    def add_welcome_message(self, chat_id: int, message: str) -> None:
        """Set custom welcome message for a chat."""
        self.chats.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"welcome_message": message},
                "$setOnInsert": {"created_at": datetime.now()}
            },
            upsert=True
        )
    
    def get_welcome_message(self, chat_id: int) -> Optional[str]:
        """Get chat welcome message."""
        chat = self.chats.find_one({"chat_id": chat_id})
        return chat.get("welcome_message") if chat else None
    
    def update_stats(self, stat_name: str, chat_id: Optional[int] = None, 
                    user_id: Optional[int] = None, increment: int = 1) -> None:
        """Update bot statistics."""
        query = {"stat_name": stat_name}
        if chat_id:
            query["chat_id"] = chat_id
        if user_id:
            query["user_id"] = user_id
            
        self.stats.update_one(
            query,
            {
                "$inc": {"count": increment},
                "$setOnInsert": {"created_at": datetime.now()}
            },
            upsert=True
        )
    
    def get_stats(self, stat_name: Optional[str] = None, chat_id: Optional[int] = None,
                user_id: Optional[int] = None) -> Union[int, Dict[str, int]]:
        """Get bot statistics."""
        query = {}
        if stat_name:
            query["stat_name"] = stat_name
        if chat_id:
            query["chat_id"] = chat_id
        if user_id:
            query["user_id"] = user_id
            
        stats = list(self.stats.find(query))
        if not stats:
            return 0 if stat_name else {}
            
        if stat_name:
            return stats[0]["count"] if stats else 0
        return {stat["stat_name"]: stat["count"] for stat in stats}
    
    def close(self):
        """Close database connection."""
        self.client.close()
