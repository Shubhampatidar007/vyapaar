"""Location updates for customers and shops (GeoJSON only, never bare lat/lng)."""
from typing import Dict, Optional, Tuple

from bson import ObjectId

from app.database import mongo as m
from app.models.user import utcnow
from app.utils.geo import from_geojson_point, to_geojson_point, valid_coordinates
from app.utils.logging import get_logger

logger = get_logger(__name__)


class InvalidLocationError(ValueError):
    pass


async def update_customer_location(user_id, latitude: float, longitude: float) -> None:
    if not valid_coordinates(latitude, longitude):
        raise InvalidLocationError("Coordinates are out of range.")
    now = utcnow()
    await m.customers().update_one(
        {"user_id": ObjectId(str(user_id))},
        {"$set": {
            "location": to_geojson_point(latitude, longitude),
            "location_updated_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    logger.info("customer location updated | user=%s", user_id)


async def update_shop_location(user_id, latitude: float, longitude: float,
                               address: Optional[str] = None) -> None:
    if not valid_coordinates(latitude, longitude):
        raise InvalidLocationError("Coordinates are out of range.")
    update = {
        "location": to_geojson_point(latitude, longitude),
        "updated_at": utcnow(),
    }
    if address:
        update["address"] = address
    await m.shops().update_one({"user_id": ObjectId(str(user_id))}, {"$set": update})
    logger.info("shop location updated | user=%s", user_id)


async def get_customer_location(user_id) -> Optional[Tuple[float, float]]:
    doc = await m.customers().find_one({"user_id": ObjectId(str(user_id))})
    if not doc:
        return None
    return from_geojson_point(doc.get("location"))


async def get_shop_location(user_id) -> Optional[Tuple[float, float]]:
    doc = await m.shops().find_one({"user_id": ObjectId(str(user_id))})
    if not doc:
        return None
    return from_geojson_point(doc.get("location"))


def location_of(doc: Dict) -> Optional[Tuple[float, float]]:
    return from_geojson_point((doc or {}).get("location"))
