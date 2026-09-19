"""Async MongoDB connection (Motor). Collections are exposed as named accessors."""
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MongoManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    connected: bool = False


mongo = MongoManager()


async def connect_to_mongo() -> bool:
    """Connect and ping. Returns False instead of raising so the app can degrade."""
    try:
        mongo.client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            uuidRepresentation="standard",
        )
        await mongo.client.admin.command("ping")
        mongo.db = mongo.client[settings.MONGODB_DATABASE]
        mongo.connected = True
        logger.info("MongoDB connected -> database '%s'", settings.MONGODB_DATABASE)
        return True
    except PyMongoError as exc:
        mongo.connected = False
        logger.error("MongoDB connection failed: %s", exc.__class__.__name__)
        return False


async def close_mongo_connection() -> None:
    if mongo.client is not None:
        mongo.client.close()
        mongo.connected = False
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    if mongo.db is None:
        raise RuntimeError("Database is not available. Is MongoDB running?")
    return mongo.db


def collection(name: str) -> AsyncIOMotorCollection:
    return get_db()[name]


# Named accessors keep collection-name typos out of the service layer.
def users() -> AsyncIOMotorCollection:
    return collection("users")


def customers() -> AsyncIOMotorCollection:
    return collection("customers")


def shops() -> AsyncIOMotorCollection:
    return collection("shops")


def inventory_items() -> AsyncIOMotorCollection:
    return collection("inventory_items")


def product_requests() -> AsyncIOMotorCollection:
    return collection("product_requests")


def merchant_matches() -> AsyncIOMotorCollection:
    return collection("merchant_matches")


def demand_events() -> AsyncIOMotorCollection:
    return collection("demand_events")


def khata_entries() -> AsyncIOMotorCollection:
    return collection("khata_entries")


def auth_tokens() -> AsyncIOMotorCollection:
    return collection("auth_tokens")


def sessions() -> AsyncIOMotorCollection:
    return collection("sessions")


def notifications() -> AsyncIOMotorCollection:
    return collection("notifications")


def merchant_cooldowns() -> AsyncIOMotorCollection:
    return collection("merchant_cooldowns")
