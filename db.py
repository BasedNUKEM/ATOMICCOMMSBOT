"""
MongoDB database interface for the NUKEM bot. This module provides asynchronous
database operations for user management, karma tracking, warnings, mutes, and chat rules.
"""

from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from os import getenv
from dotenv import load_dotenv
import backoff
import logging
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

# MongoDB configuration
MONGO_URI = getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = getenv("DB_NAME", "nukem_bot")
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

class Database:
    """Handles all database operations for the NUKEM bot."""

    def __init__(self):
        """Initialize database connection and collections."""
        load_dotenv()
        # Use module-level MONGO_URI and DB_NAME
        if not MONGO_URI:
            raise DatabaseError("MONGO_URI environment variable not set")

        try:
            # Use AsyncIOMotorClient and assign to self.async_client
            self.async_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000) # Added serverSelectionTimeoutMS for quicker failure if DB is down
            self.db = self.async_client[DB_NAME]

            # Initialize collections from the async client
            self.users = self.db.users
            self.karma = self.db.karma
            self.warnings = self.db.warnings
            self.mutes = self.db.mutes
            self.chat_rules = self.db.chat_rules
            self.welcome_messages = self.db.welcome_messages
            self.chat_stats = self.db.chat_stats
            
            # DO NOT call _setup_indices here, it will be called by ensure_async_setup
            logger.info("Async Database client initialized. Call ensure_async_setup() for full setup.")
        except PyMongoError as e:
            logger.error("Async Database client initialization failed: %s", str(e))
            raise DatabaseError(f"Async Database client initialization failed: {str(e)}") from e

    async def _setup_indices_async(self):
        """Set up database indices for better query performance. Must be called after client is connected."""
        try:
            # Create indices for each collection using await
            await self.users.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
            await self.karma.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
            await self.warnings.create_index([("chat_id", 1), ("user_id", 1)])
            await self.warnings.create_index([("expiry", 1)], expireAfterSeconds=0)
            await self.mutes.create_index([("chat_id", 1), ("user_id", 1)])
            await self.mutes.create_index([("expiry", 1)], expireAfterSeconds=0)
            await self.chat_rules.create_index([("chat_id", 1)], unique=True)
            await self.welcome_messages.create_index([("chat_id", 1)], unique=True)
            await self.chat_stats.create_index([("chat_id", 1)], unique=True)
            
            logger.info("Database indices created successfully")
        except PyMongoError as e:
            logger.error("Failed to create indices: %s", str(e))
            raise DatabaseError(f"Failed to create indices: {str(e)}") from e

    async def ensure_async_setup(self):
        """Performs server connectivity check and ensures all async setup like index creation is done."""
        try:
            await self.async_client.server_info()  # Test connection
            logger.info("Successfully connected to MongoDB server.")
            await self._setup_indices_async() # Create indexes
        except PyMongoError as e:
            logger.error("MongoDB server connection or async setup failed: %s", str(e))
            raise DatabaseError(f"MongoDB server connection or async setup failed: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def add_or_update_user(self, chat_id: int, user_id: int, username: str, status: str = "member") -> None:
        """Add or update a user in the database."""
        try:
            await self.users.update_one(
                {"chat_id": chat_id, "user_id": user_id},
                {
                    "$set": {
                        "username": username,
                        "status": status,
                        "last_seen": datetime.now(),
                    },
                    "$inc": {"messages_count": 0}
                },
                upsert=True
            )
            logger.debug("Updated user: %s in chat %s", user_id, chat_id)
        except PyMongoError as e:
            logger.error("Failed to update user: %s", str(e))
            raise DatabaseError(f"Failed to update user: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def remove_user(self, chat_id: int, user_id: int) -> None:
        """Remove a user record from the database.
        
        Args:
            chat_id: The ID of the chat
            user_id: The ID of the user
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            await self.users.delete_one({"chat_id": chat_id, "user_id": user_id})
            logger.debug("Removed user: %s from chat %s", user_id, chat_id)
        except PyMongoError as e:
            logger.error("Failed to remove user: %s", str(e))
            raise DatabaseError(f"Failed to remove user: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_user(self, chat_id: int, user_id: int) -> Optional[Dict]:
        """Get a user record from the database.
        
        Args:
            chat_id: The ID of the chat
            user_id: The ID of the user
            
        Returns:
            Dict containing user information if found, None otherwise
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            result = await self.users.find_one({"chat_id": chat_id, "user_id": user_id})
            return result
        except PyMongoError as e:
            logger.error("Failed to get user: %s", str(e))
            raise DatabaseError(f"Failed to get user: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_chat_users(self, chat_id: int) -> List[Dict]:
        """Get all users in a chat from the database.
        
        Args:
            chat_id: The ID of the chat
            
        Returns:
            List of dictionaries containing user information
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            users = []
            async for user in self.users.find({"chat_id": chat_id}):
                users.append(user)
            return users
        except PyMongoError as e:
            logger.error("Failed to get chat users: %s", str(e))
            raise DatabaseError(f"Failed to get chat users: {str(e)}") from e

    async def increment_user_messages(self, chat_id: int, user_id: int) -> None:
        """Increment the message count for a user in chat stats.
        
        Args:
            chat_id: The ID of the chat
            user_id: The ID of the user
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            await self.chat_stats.update_one(
                {"chat_id": chat_id},
                {
                    "$inc": {f"user_messages.{user_id}": 1},
                    "$setOnInsert": {"chat_id": chat_id}
                },
                upsert=True
            )
            logger.debug("Incremented message count for user %s in chat %s", user_id, chat_id)
        except PyMongoError as e:
            logger.error("Failed to increment user messages: %s", str(e))
            raise DatabaseError(f"Failed to increment user messages: {str(e)}") from e

    async def update_karma(self, chat_id: int, user_id: int, change: int) -> int:
        """Update karma for a user and return the new value.
        
        Args:
            chat_id: The ID of the chat
            user_id: The ID of the user
            change: The amount to change the karma by (positive or negative)
            
        Returns:
            The new karma value
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            result = await self.karma.find_one_and_update(
                {"chat_id": chat_id, "user_id": user_id},
                {
                    "$inc": {"karma": change},
                    "$setOnInsert": {"chat_id": chat_id, "user_id": user_id}
                },
                upsert=True,
                return_document=True
            )
            logger.debug("Updated karma for user %s in chat %s by %s", user_id, chat_id, change)
            return result["karma"]
        except PyMongoError as e:
            logger.error("Failed to update karma: %s", str(e))
            raise DatabaseError(f"Failed to update karma: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_karma(self, chat_id: int, user_id: int) -> int:
        """Get karma for a user.
        
        Args:
            chat_id: The ID of the chat
            user_id: The ID of the user
            
        Returns:
            The user's karma value (0 if not found)
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            result = await self.karma.find_one({"chat_id": chat_id, "user_id": user_id})
            return result["karma"] if result else 0
        except PyMongoError as e:
            logger.error("Failed to get karma: %s", str(e))
            raise DatabaseError(f"Failed to get karma: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def add_warning(self, chat_id: int, user_id: int, reason: str, 
                       admin_id: int, expiry: Optional[datetime] = None) -> None:
        """Add a warning for a user."""
        try:
            await self.warnings.insert_one({
                "user_id": user_id,
                "chat_id": chat_id,
                "reason": reason,
                "admin_id": admin_id,
                "timestamp": datetime.now(),
                "expiry": expiry
            })
        except PyMongoError as e:
            logger.error(f"Failed to add warning for user {user_id} in chat {chat_id}: {e}")
            raise DatabaseError(f"Failed to add warning: {str(e)}")

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_warnings(self, chat_id: int, user_id: int, active_only: bool = True) -> List[Dict]:
        """Get user warnings."""
        try:
            query = {"user_id": user_id, "chat_id": chat_id}
            if active_only:
                current_time = datetime.now()
                query["$or"] = [
                    {"expiry": {"$gt": current_time}},
                    {"expiry": None}
                ]
            return await self.warnings.find(query).to_list(length=None)
        except PyMongoError as e:
            logger.error(f"Failed to get warnings for user {user_id} in chat {chat_id}: {e}")
            raise DatabaseError(f"Failed to get warnings: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def add_mute(self, chat_id: int, user_id: int, until: datetime, 
                    reason: str, admin_id: int) -> None:
        """Add a temporary mute for a user."""
        try:
            await self.mutes.insert_one({
                "chat_id": chat_id,
                "user_id": user_id,
                "type": "mute",
                "until": until,
                "reason": reason,
                "admin_id": admin_id,
                "timestamp": datetime.now()
            })
        except PyMongoError as e:
            logger.error(f"Failed to add mute for user {user_id} in chat {chat_id}: {e}")
            raise DatabaseError(f"Failed to add mute: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_active_mutes(self, chat_id: Optional[int] = None) -> List[Dict]:
        """Get active mutes, optionally filtered by chat.
        
        Args:
            chat_id: Optional chat ID to filter by
            
        Returns:
            List of active mutes
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            query = {"expiry": {"$gt": datetime.utcnow()}}
            if chat_id is not None:
                query["chat_id"] = chat_id
            
            mutes = []
            async for mute in self.mutes.find(query):
                mutes.append(mute)
            return mutes
        except PyMongoError as e:
            logger.error("Failed to get active mutes: %s", str(e))
            raise DatabaseError(f"Failed to get active mutes: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def add_chat_rule(self, chat_id: int, rule: str) -> None:
        """Add a rule to the chat rules.
        
        Args:
            chat_id: The ID of the chat
            rule: The rule to add
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            await self.chat_rules.update_one(
                {"chat_id": chat_id},
                {
                    "$push": {"rules": rule},
                    "$setOnInsert": {"chat_id": chat_id}
                },
                upsert=True
            )
            logger.debug("Added rule to chat %s", chat_id)
        except PyMongoError as e:
            logger.error("Failed to add chat rule: %s", str(e))
            raise DatabaseError(f"Failed to add chat rule: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_chat_rules(self, chat_id: int) -> List[str]:
        """Get all rules for a chat.
        
        Args:
            chat_id: The ID of the chat
            
        Returns:
            List of chat rules
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            result = await self.chat_rules.find_one({"chat_id": chat_id})
            return result.get("rules", []) if result else []
        except PyMongoError as e:
            logger.error("Failed to get chat rules: %s", str(e))
            raise DatabaseError(f"Failed to get chat rules: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def set_welcome_message(self, chat_id: int, message: str) -> None:
        """Set the welcome message for a chat.
        
        Args:
            chat_id: The ID of the chat
            message: The welcome message
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            await self.welcome_messages.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {"message": message}
                },
                upsert=True
            )
            logger.debug("Set welcome message for chat %s", chat_id)
        except PyMongoError as e:
            logger.error("Failed to set welcome message: %s", str(e))
            raise DatabaseError(f"Failed to set welcome message: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_welcome_message(self, chat_id: int) -> Optional[str]:
        """Get the welcome message for a chat.
        
        Args:
            chat_id: The ID of the chat
            
        Returns:
            The welcome message if set, None otherwise
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            result = await self.welcome_messages.find_one({"chat_id": chat_id})
            return result["message"] if result else None
        except PyMongoError as e:
            logger.error("Failed to get welcome message: %s", str(e))
            raise DatabaseError(f"Failed to get welcome message: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def update_stats(self, stat_name: str, chat_id: Optional[int] = None, 
                       user_id: Optional[int] = None, increment: int = 1) -> None:
        """Update bot statistics."""
        try:
            query = {"stat_name": stat_name}
            if chat_id:
                query["chat_id"] = chat_id
            if user_id:
                query["user_id"] = user_id
                
            await self.chat_stats.update_one(
                query,
                {
                    "$inc": {"count": increment},
                    "$setOnInsert": {"created_at": datetime.now()}
                },
                upsert=True
            )
        except PyMongoError as e:
            logger.error(f"Failed to update stats for {stat_name}: {e}")
            raise DatabaseError(f"Failed to update stats: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=MAX_RETRIES)
    async def get_stats(self, stat_name: Optional[str] = None, chat_id: Optional[int] = None,
                     user_id: Optional[int] = None) -> Union[int, Dict[str, int]]:
        """Get bot statistics."""
        try:
            query = {}
            if stat_name:
                query["stat_name"] = stat_name
            if chat_id:
                query["chat_id"] = chat_id
            if user_id:
                query["user_id"] = user_id
                
            stats = await self.chat_stats.find(query).to_list(length=None)
            if not stats:
                return 0 if stat_name else {}
                
            if stat_name:
                return stats[0]["count"] if stats else 0
            return {stat["stat_name"]: stat["count"] for stat in stats}
        except PyMongoError as e:
            logger.error(f"Failed to get stats: {e}")
            raise DatabaseError(f"Failed to get stats: {str(e)}") from e

    async def update_chat_stats(self, chat_id: int, data: Dict) -> None:
        """Update chat statistics.
        
        Args:
            chat_id: The ID of the chat
            data: Dictionary containing statistics to update
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            update = {"$set": {}}
            for key, value in data.items():
                update["$set"][key] = value
            
            await self.chat_stats.update_one(
                {"chat_id": chat_id},
                update,
                upsert=True
            )
            logger.debug("Updated stats for chat %s", chat_id)
        except PyMongoError as e:
            logger.error("Failed to update stats: %s", str(e))
            raise DatabaseError(f"Failed to update stats: {str(e)}") from e

    async def get_chat_stats(self, chat_id: int) -> Optional[Dict]:
        """Get statistics for a chat.
        
        Args:
            chat_id: The ID of the chat
            
        Returns:
            Dictionary containing chat statistics if found, None otherwise
            
        Raises:
            DatabaseError: If the database operation fails
        """
        try:
            result = await self.chat_stats.find_one({"chat_id": chat_id})
            return result
        except PyMongoError as e:
            logger.error("Failed to get stats: %s", str(e))
            raise DatabaseError(f"Failed to get stats: {str(e)}") from e

    @backoff.on_exception(backoff.expo, PyMongoError, max_tries=3)
    async def cleanup_expired_items(self) -> None:
        """Remove expired warnings and mutes. Uses exponential backoff for retries.
        
        This method is called periodically to clean up expired items from the database.
        It uses TTL indices but we also manually clean up as a backup.
        
        Raises:
            DatabaseError: If the database operation fails after max retries
        """
        try:
            now = datetime.utcnow()
            
            # Remove expired warnings
            await self.warnings.delete_many({"expiry": {"$lt": now}})
            
            # Remove expired mutes
            await self.mutes.delete_many({"expiry": {"$lt": now}})
            
            logger.debug("Cleaned up expired items")
        except PyMongoError as e:
            logger.error("Failed to cleanup expired items: %s", str(e))
            raise DatabaseError(f"Failed to cleanup expired items: {str(e)}") from e

    def close(self):
        """Close database connections."""
        try:
            if self.async_client:
                self.async_client.close()
                logger.info("Async database connection closed")
        except Exception as e:
            logger.error("Error closing async database connections: %s", e, exc_info=True) # Added exc_info

    async def __aenter__(self):
        """Async context manager entry."""
        # Consider if ensure_async_setup should be called here or if it's too heavy for every 'with'
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()
