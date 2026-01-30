"""
MongoDB connection and database operations.
"""

from datetime import datetime, timezone
from typing import List, Optional
import structlog
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
from pymongo.database import Database

from .config import settings
from .models import Station, Observation, Warning

logger = structlog.get_logger(__name__)


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class WeatherDatabase:
    """MongoDB database operations for weather data."""

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> None:
        """Establish connection to MongoDB."""
        logger.info("Connecting to MongoDB", host=settings.mongo_host, port=settings.mongo_port)
        try:
            self._client = MongoClient(
                settings.mongo_uri,
                serverSelectionTimeoutMS=5000,
            )
            # Test connection
            self._client.admin.command('ping')
            self._db = self._client[settings.mongo_database]
            logger.info("Connected to MongoDB successfully")
        except PyMongoError as e:
            logger.error("Failed to connect to MongoDB", error=str(e))
            raise

    def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            logger.info("Disconnected from MongoDB")

    @property
    def db(self) -> Database:
        """Get database instance."""
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    def ensure_indexes(self) -> None:
        """Create necessary indexes if they don't exist."""
        logger.info("Ensuring database indexes exist")
        
        # Stations collection indexes
        self.db.stations.create_index("station_code", unique=True, name="idx_station_code")
        self.db.stations.create_index("province", name="idx_province")
        
        # Observations collection indexes
        self.db.observations.create_index(
            [("station_code", 1), ("observed_at", -1)],
            name="idx_station_time"
        )
        self.db.observations.create_index(
            [("observed_at", -1)],
            name="idx_time"
        )
        self.db.observations.create_index(
            [("station_code", 1), ("fetched_at", -1)],
            name="idx_station_fetched"
        )
        
        # Warnings collection indexes
        self.db.warnings.create_index(
            [("station_code", 1), ("headline", 1), ("effective", 1)],
            name="idx_warning_unique"
        )
        self.db.warnings.create_index(
            [("active", 1), ("expires", 1)],
            name="idx_active_expires"
        )
        self.db.warnings.create_index(
            [("station_code", 1), ("active", 1)],
            name="idx_station_active"
        )
        
        logger.info("Database indexes ensured")

    def upsert_stations(self, stations: List[Station]) -> dict:
        """
        Upsert multiple stations (insert or update).
        Returns counts of inserted/updated/unchanged stations.
        """
        if not stations:
            return {"inserted": 0, "updated": 0, "unchanged": 0}

        operations = []
        for station in stations:
            doc = station.to_mongo_doc()
            operations.append(
                UpdateOne(
                    {"station_code": station.station_code},
                    {"$set": doc},
                    upsert=True
                )
            )

        try:
            result = self.db.stations.bulk_write(operations)
            stats = {
                "inserted": result.upserted_count,
                "updated": result.modified_count,
                "matched": result.matched_count,
            }
            logger.info("Upserted stations", **stats)
            return stats
        except PyMongoError as e:
            logger.error("Failed to upsert stations", error=str(e))
            raise

    def mark_inactive_stations(self, active_codes: set) -> int:
        """
        Mark stations as inactive if they're not in the active_codes set.
        Returns count of stations marked inactive.
        """
        try:
            result = self.db.stations.update_many(
                {
                    "station_code": {"$nin": list(active_codes)},
                    "active": True
                },
                {
                    "$set": {
                        "active": False,
                        "updated_at": utcnow()
                    }
                }
            )
            if result.modified_count > 0:
                logger.info("Marked stations as inactive", count=result.modified_count)
            return result.modified_count
        except PyMongoError as e:
            logger.error("Failed to mark inactive stations", error=str(e))
            raise

    def get_active_stations(self) -> List[dict]:
        """Get all active stations from the database."""
        try:
            stations = list(self.db.stations.find({"active": True}))
            return stations
        except PyMongoError as e:
            logger.error("Failed to get active stations", error=str(e))
            raise

    def insert_observations(self, observations: List[Observation]) -> int:
        """
        Insert multiple observations.
        Skips duplicates based on station_code + observed_at.
        Returns count of inserted observations.
        """
        if not observations:
            return 0

        operations = []
        for obs in observations:
            doc = obs.to_mongo_doc()
            operations.append(
                UpdateOne(
                    {
                        "station_code": obs.station_code,
                        "observed_at": obs.observed_at
                    },
                    {"$setOnInsert": doc},
                    upsert=True
                )
            )

        try:
            result = self.db.observations.bulk_write(operations, ordered=False)
            inserted = result.upserted_count
            if inserted > 0:
                logger.info("Inserted observations", count=inserted, total=len(observations))
            return inserted
        except PyMongoError as e:
            logger.error("Failed to insert observations", error=str(e))
            raise

    def upsert_warnings(self, warnings: List[Warning]) -> dict:
        """
        Upsert warnings - update existing or insert new.
        Returns counts of inserted/updated warnings.
        """
        if not warnings:
            return {"inserted": 0, "updated": 0}

        operations = []
        for warning in warnings:
            doc = warning.to_mongo_doc()
            operations.append(
                UpdateOne(
                    {
                        "station_code": warning.station_code,
                        "headline": warning.headline,
                        "effective": warning.effective
                    },
                    {"$set": doc},
                    upsert=True
                )
            )

        try:
            result = self.db.warnings.bulk_write(operations, ordered=False)
            stats = {
                "inserted": result.upserted_count,
                "updated": result.modified_count,
            }
            if stats["inserted"] > 0 or stats["updated"] > 0:
                logger.info("Upserted warnings", **stats)
            return stats
        except PyMongoError as e:
            logger.error("Failed to upsert warnings", error=str(e))
            raise

    def clear_station_warnings(self, station_code: str) -> int:
        """
        Mark all active warnings for a station as inactive.
        Called when a station has no warnings in the current fetch.
        Returns count of warnings marked inactive.
        """
        try:
            result = self.db.warnings.update_many(
                {
                    "station_code": station_code,
                    "active": True
                },
                {
                    "$set": {
                        "active": False,
                        "updated_at": utcnow()
                    }
                }
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error("Failed to clear station warnings", error=str(e))
            raise

    def expire_old_warnings(self) -> int:
        """
        Mark warnings as inactive if they have expired.
        Returns count of warnings marked inactive.
        """
        try:
            result = self.db.warnings.update_many(
                {
                    "active": True,
                    "expires": {"$lt": utcnow()}
                },
                {
                    "$set": {"active": False}
                }
            )
            if result.modified_count > 0:
                logger.info("Expired old warnings", count=result.modified_count)
            return result.modified_count
        except PyMongoError as e:
            logger.error("Failed to expire old warnings", error=str(e))
            raise

    def get_active_warnings(self, station_code: Optional[str] = None) -> List[dict]:
        """Get all active warnings, optionally filtered by station."""
        try:
            query = {"active": True}
            if station_code:
                query["station_code"] = station_code
            return list(self.db.warnings.find(query).sort("fetched_at", -1))
        except PyMongoError as e:
            logger.error("Failed to get active warnings", error=str(e))
            raise

    def get_observation_count(self) -> int:
        """Get total count of observations."""
        return self.db.observations.count_documents({})

    def get_station_count(self, active_only: bool = True) -> int:
        """Get count of stations."""
        query = {"active": True} if active_only else {}
        return self.db.stations.count_documents(query)

    def get_warning_count(self, active_only: bool = True) -> int:
        """Get count of warnings."""
        query = {"active": True} if active_only else {}
        return self.db.warnings.count_documents(query)

    def get_latest_observation(self, station_code: str) -> Optional[dict]:
        """Get the most recent observation for a station."""
        return self.db.observations.find_one(
            {"station_code": station_code},
            sort=[("observed_at", -1)]
        )


# Global database instance
db = WeatherDatabase()
