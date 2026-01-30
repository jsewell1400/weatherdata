"""
Main weather data fetcher - handles scheduling and data collection.
"""

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import List, Optional, Set, Dict
import aiohttp
import structlog
from asyncio_throttle import Throttler

from .config import settings
from .db import db
from .models import Station, Observation, StationListEntry, Coordinates, Warning
from .parser import parse_site_list, parse_station_data

logger = structlog.get_logger(__name__)


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class WeatherFetcher:
    """
    Fetches weather data from Environment Canada and stores it in MongoDB.
    
    - Refreshes station list once per day
    - Fetches observations for all stations 6 times per hour (every 10 minutes)
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._throttler: Optional[Throttler] = None
        self._station_list: List[StationListEntry] = []
        self._last_station_refresh: Optional[datetime] = None
        self._running = False
        # Cache of province -> file map to avoid repeated directory listings
        self._province_file_cache: Dict[str, Dict[str, str]] = {}
        self._province_file_cache_time: Optional[datetime] = None

    async def start(self) -> None:
        """Start the fetcher service."""
        logger.info("Starting weather fetcher service")
        
        # Connect to database
        db.connect()
        db.ensure_indexes()
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=settings.request_timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Create throttler to limit concurrent requests
        self._throttler = Throttler(
            rate_limit=settings.max_concurrent_requests,
            period=1.0
        )
        
        self._running = True
        
        # Initial station list fetch
        await self._refresh_station_list()
        
        # Main loop
        await self._run_loop()

    async def stop(self) -> None:
        """Stop the fetcher service."""
        logger.info("Stopping weather fetcher service")
        self._running = False
        
        if self._session:
            await self._session.close()
        
        db.disconnect()

    async def _run_loop(self) -> None:
        """Main run loop - schedules station refresh and observation fetches."""
        last_observation_fetch = datetime.min.replace(tzinfo=timezone.utc)
        
        while self._running:
            now = utcnow()
            
            # Check if we need to refresh station list (once per day)
            if self._should_refresh_stations():
                await self._refresh_station_list()
            
            # Check if we need to fetch observations (6 times per hour)
            seconds_since_last = (now - last_observation_fetch).total_seconds()
            if seconds_since_last >= settings.observation_interval_seconds:
                await self._fetch_all_observations()
                last_observation_fetch = utcnow()
                
                # Expire old warnings after each fetch
                db.expire_old_warnings()
            
            # Sleep for a short interval before checking again
            await asyncio.sleep(10)

    def _should_refresh_stations(self) -> bool:
        """Check if it's time to refresh the station list."""
        if self._last_station_refresh is None:
            return True
        
        elapsed = (utcnow() - self._last_station_refresh).total_seconds()
        return elapsed >= settings.station_refresh_interval_seconds

    async def _refresh_station_list(self) -> None:
        """Fetch and update the station list from Environment Canada."""
        logger.info("Refreshing station list from Environment Canada")
        
        try:
            content = await self._fetch_url(settings.ec_site_list_url)
            if content is None:
                logger.error("Failed to fetch station list")
                return
            
            # Parse the station list (handles both GeoJSON and XML formats)
            self._station_list = parse_site_list(content)
            
            if not self._station_list:
                logger.warning("No stations found in site list")
                return
            
            # Get current active station codes
            active_codes: Set[str] = {s.station_code for s in self._station_list}
            
            # Create station records with coordinates from GeoJSON
            stations_to_upsert: List[Station] = []
            for entry in self._station_list:
                # Use coordinates from GeoJSON if available
                lat = entry.lat if entry.lat is not None else 0.0
                lon = entry.lon if entry.lon is not None else 0.0
                
                stations_to_upsert.append(Station(
                    station_code=entry.station_code,
                    name_en=entry.name_en,
                    name_fr=entry.name_fr,
                    province=entry.province,
                    coordinates=Coordinates(lat=lat, lon=lon),
                    active=True,
                    updated_at=utcnow()
                ))
            
            # Upsert stations to database
            db.upsert_stations(stations_to_upsert)
            
            # Mark stations not in the list as inactive
            db.mark_inactive_stations(active_codes)
            
            self._last_station_refresh = utcnow()
            
            logger.info(
                "Station list refreshed",
                total_stations=len(self._station_list),
            )
            
        except Exception as e:
            logger.error("Error refreshing station list", error=str(e))

    async def _fetch_station_metadata(self, entry: StationListEntry) -> Optional[Station]:
        """Fetch detailed metadata for a station using the new URL structure."""
        # Use the province file map to get the station's latest file
        file_map = await self._get_province_file_map(entry.province)
        
        if entry.station_code not in file_map:
            return None
        
        url = file_map[entry.station_code]
        
        try:
            xml_content = await self._fetch_url(url)
            if xml_content is None:
                return None
            
            station, _, _ = parse_station_data(xml_content, entry.station_code, entry.province)
            return station
            
        except Exception as e:
            return None

    async def _fetch_all_observations(self) -> None:
        """Fetch current observations for all active stations."""
        start_time = time.time()
        
        # Clear file cache to get fresh directory listings
        self._province_file_cache = {}
        self._province_file_cache_time = None
        
        # Get active stations from database
        active_stations = db.get_active_stations()
        
        if not active_stations:
            # Fall back to cached station list
            if self._station_list:
                logger.info("Using cached station list for observations")
                active_stations = [
                    {"station_code": s.station_code, "province": s.province}
                    for s in self._station_list
                ]
            else:
                logger.warning("No stations available for observation fetch")
                return
        
        logger.info("Fetching observations for all stations", count=len(active_stations))
        
        # Group stations by province for efficient directory listing
        stations_by_province: Dict[str, List[dict]] = {}
        for station in active_stations:
            province = station.get("province", "")
            if province:
                if province not in stations_by_province:
                    stations_by_province[province] = []
                stations_by_province[province].append(station)
        
        # Fetch observations by province (to reuse directory listings)
        observations: List[Observation] = []
        stations_to_update: List[Station] = []
        all_warnings: List[Warning] = []
        stations_with_warnings: Set[str] = set()
        errors = 0
        
        for province, province_stations in stations_by_province.items():
            # Get available files for this province
            file_map = await self._get_province_file_map(province)
            
            if not file_map:
                errors += len(province_stations)
                continue
            
            # Fetch each station's data
            for station in province_stations:
                station_code = station["station_code"]
                
                # Find the latest file for this station
                file_url = file_map.get(station_code)
                if not file_url:
                    continue
                
                try:
                    async with self._throttler:
                        result = await self._fetch_station_from_url(file_url, station_code, province)
                    
                    if result:
                        station_obj, observation, warnings = result
                        if station_obj:
                            stations_to_update.append(station_obj)
                        if observation:
                            observations.append(observation)
                        if warnings:
                            all_warnings.extend(warnings)
                            stations_with_warnings.add(station_code)
                        elif station_code not in stations_with_warnings:
                            # Station had no warnings - clear any existing active warnings
                            db.clear_station_warnings(station_code)
                except Exception as e:
                    errors += 1
        
        # Batch insert observations
        if observations:
            inserted = db.insert_observations(observations)
        else:
            inserted = 0
        
        # Update station metadata (coordinates, etc.)
        if stations_to_update:
            db.upsert_stations(stations_to_update)
        
        # Upsert warnings
        warnings_stats = {"inserted": 0, "updated": 0}
        if all_warnings:
            warnings_stats = db.upsert_warnings(all_warnings)
        
        elapsed = time.time() - start_time
        
        logger.info(
            "Observation fetch complete",
            total_stations=len(active_stations),
            observations_collected=len(observations),
            observations_inserted=inserted,
            stations_updated=len(stations_to_update),
            warnings_found=len(all_warnings),
            errors=errors,
            elapsed_seconds=round(elapsed, 2)
        )

    async def _get_province_file_map(self, province: str) -> Dict[str, str]:
        """
        Get a mapping of station_code -> latest file URL for a province.
        
        The new EC structure uses timestamped files in hourly directories:
        https://dd.weather.gc.ca/today/citypage_weather/{PROV}/{HH}/
        
        Files are named like: {timestamp}_MSC_CitypageWeather_{station}_en.xml
        """
        # Check cache
        if province in self._province_file_cache:
            return self._province_file_cache[province]
        
        file_map: Dict[str, str] = {}
        base_url = f"{settings.ec_base_url}/{province}"
        
        try:
            # First, list the province directory to get available hours
            dir_content = await self._fetch_url(base_url + "/")
            if not dir_content:
                logger.warning("Could not list province directory", province=province)
                return file_map
            
            # Parse directory listing to find hour directories
            # Look for links to hour directories (00, 01, ..., 23)
            hour_pattern = re.compile(r'href="(\d{2})/"')
            hours = hour_pattern.findall(dir_content.decode('utf-8', errors='ignore'))
            
            if not hours:
                logger.warning("No hour directories found", province=province)
                return file_map
            
            # Get the most recent hour directory
            latest_hour = max(hours)
            hour_url = f"{base_url}/{latest_hour}/"
            
            # List the hour directory to get files
            hour_content = await self._fetch_url(hour_url)
            if not hour_content:
                logger.warning("Could not list hour directory", province=province, hour=latest_hour)
                return file_map
            
            # Parse file listing - files are named like:
            # {timestamp}_MSC_CitypageWeather_{station}_en.xml
            file_pattern = re.compile(
                r'href="([^"]*_MSC_CitypageWeather_(s\d+)_en\.xml)"'
            )
            
            # Build map of station -> latest file
            # Files are timestamped, so we track the latest for each station
            station_files: Dict[str, List[str]] = {}
            for match in file_pattern.finditer(hour_content.decode('utf-8', errors='ignore')):
                filename, station_code = match.groups()
                if station_code not in station_files:
                    station_files[station_code] = []
                station_files[station_code].append(filename)
            
            # Use the latest file for each station (alphabetically last = most recent timestamp)
            for station_code, files in station_files.items():
                latest_file = sorted(files)[-1]  # Timestamps sort alphabetically
                file_map[station_code] = f"{hour_url}{latest_file}"
            
            # Cache the result
            self._province_file_cache[province] = file_map
            
        except Exception as e:
            logger.warning("Error building file map", province=province, error=str(e))
        
        return file_map

    async def _fetch_station_from_url(
        self,
        url: str,
        station_code: str,
        province: str
    ) -> Optional[tuple]:
        """Fetch and parse station data from a specific URL."""
        try:
            xml_content = await self._fetch_url(url)
            if xml_content is None:
                return None
            
            station, observation, warnings = parse_station_data(xml_content, station_code, province)
            return (station, observation, warnings)
            
        except Exception as e:
            return None

    async def _fetch_url(self, url: str, retries: int = None) -> Optional[bytes]:
        """Fetch URL content with retries."""
        if retries is None:
            retries = settings.max_retries
        
        for attempt in range(retries + 1):
            try:
                async with self._session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
                    elif response.status == 404:
                        # Station might not exist or have data
                        return None
                    else:
                        logger.warning(
                            "HTTP error fetching URL",
                            url=url,
                            status=response.status,
                            attempt=attempt + 1
                        )
                        
            except asyncio.TimeoutError:
                logger.warning("Request timeout", url=url, attempt=attempt + 1)
            except aiohttp.ClientError as e:
                logger.warning("Client error", url=url, error=str(e), attempt=attempt + 1)
            except Exception as e:
                logger.warning("Unexpected error fetching URL", url=url, error=str(e))
                return None
            
            if attempt < retries:
                await asyncio.sleep(settings.retry_delay_seconds * (attempt + 1))
        
        return None


async def run_fetcher() -> None:
    """Main entry point to run the weather fetcher."""
    fetcher = WeatherFetcher()
    
    try:
        await fetcher.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error("Fetcher error", error=str(e))
        raise
    finally:
        await fetcher.stop()
