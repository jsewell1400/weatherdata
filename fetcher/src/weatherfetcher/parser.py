"""
XML and GeoJSON parsing for Environment Canada weather data.
"""

import json
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import structlog
from lxml import etree
from dateutil import parser as dateparser

from .models import Station, Observation, Coordinates, StationListEntry, Warning

logger = structlog.get_logger(__name__)


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def parse_site_list_geojson(content: bytes) -> List[StationListEntry]:
    """
    Parse the site_list_en.geojson file to get all available stations.
    """
    stations = []
    
    try:
        data = json.loads(content)
        
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            
            code = props.get("Codes")
            name_en = props.get("English Names")
            name_fr = props.get("French Names")
            province = props.get("Province Codes")
            lat = props.get("Latitude")
            lon = props.get("Longitude")
            
            if code and name_en and province:
                stations.append(StationListEntry(
                    station_code=code,
                    name_en=name_en,
                    name_fr=name_fr or name_en,
                    province=province,
                    lat=float(lat) if lat else None,
                    lon=float(lon) if lon else None,
                ))
        
        logger.info("Parsed site list (GeoJSON)", station_count=len(stations))
        return stations
        
    except json.JSONDecodeError as e:
        logger.error("Failed to parse site list GeoJSON", error=str(e))
        raise


def parse_site_list(content: bytes) -> List[StationListEntry]:
    """
    Parse the site list - tries GeoJSON first, falls back to XML.
    """
    try:
        return parse_site_list_geojson(content)
    except (json.JSONDecodeError, KeyError):
        pass
    
    return parse_site_list_xml(content)


def parse_site_list_xml(xml_content: bytes) -> List[StationListEntry]:
    """
    Parse the legacy siteList.xml file to get all available stations.
    """
    stations = []
    
    try:
        root = etree.fromstring(xml_content)
        
        for site in root.findall('.//site'):
            code = site.get('code')
            name_en = _get_text(site, 'nameEn')
            name_fr = _get_text(site, 'nameFr')
            province = _get_text(site, 'provinceCode')
            
            if code and name_en and province:
                stations.append(StationListEntry(
                    station_code=code,
                    name_en=name_en,
                    name_fr=name_fr or name_en,
                    province=province
                ))
        
        logger.info("Parsed site list (XML)", station_count=len(stations))
        return stations
        
    except etree.XMLSyntaxError as e:
        logger.error("Failed to parse site list XML", error=str(e))
        raise


def parse_station_data(xml_content: bytes, station_code: str, province: str) -> Tuple[Optional[Station], Optional[Observation], List[Warning]]:
    """
    Parse a station's XML data to extract station metadata, current observation, and warnings.
    
    Returns tuple of (Station, Observation, List[Warning]) or (None, None, []) on parse failure.
    """
    try:
        root = etree.fromstring(xml_content)
        
        # Parse station metadata
        station = _parse_station_metadata(root, station_code, province)
        
        # Parse current conditions
        observation = _parse_current_conditions(root, station_code)
        
        # Parse warnings
        warnings = _parse_warnings(root, station_code)
        
        return station, observation, warnings
        
    except etree.XMLSyntaxError as e:
        logger.warning("Failed to parse station XML", station_code=station_code, error=str(e))
        return None, None, []
    except Exception as e:
        logger.warning("Error parsing station data", station_code=station_code, error=str(e))
        return None, None, []


def _parse_coordinate_string(coord_str: Optional[str]) -> Optional[float]:
    """
    Parse coordinate string like '49.85N' or '99.95W' to decimal degrees.
    North and East are positive, South and West are negative.
    """
    if not coord_str:
        return None
    
    coord_str = coord_str.strip()
    
    # Match pattern like "49.85N" or "99.95W"
    match = re.match(r'^([\d.]+)([NSEW])$', coord_str, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        direction = match.group(2).upper()
        
        # South and West are negative
        if direction in ('S', 'W'):
            value = -value
        
        return value
    
    # Try parsing as plain float
    try:
        return float(coord_str)
    except (ValueError, TypeError):
        return None


def _parse_station_metadata(root: etree._Element, station_code: str, province: str) -> Optional[Station]:
    """Extract station metadata from XML."""
    try:
        # Get location info
        location = root.find('.//location')
        if location is None:
            return None
        
        # Get name element which contains coordinates
        name_elem = location.find('name')
        
        name_en = name_elem.text if name_elem is not None and name_elem.text else station_code
        name_fr = name_en  # Default to English
        
        region_elem = location.find('region')
        region_en = region_elem.text if region_elem is not None else None
        region_fr = region_en
        
        # Parse coordinates from name element attributes (e.g., lat="49.85N" lon="99.95W")
        lat = None
        lon = None
        
        if name_elem is not None:
            lat = _parse_coordinate_string(name_elem.get('lat'))
            lon = _parse_coordinate_string(name_elem.get('lon'))
        
        # If not found in location, try currentConditions station element
        if lat is None or lon is None:
            station_elem = root.find('.//currentConditions/station')
            if station_elem is not None:
                if lat is None:
                    lat = _parse_coordinate_string(station_elem.get('lat'))
                if lon is None:
                    lon = _parse_coordinate_string(station_elem.get('lon'))
        
        # Default to 0 if still not found
        if lat is None:
            lat = 0.0
        if lon is None:
            lon = 0.0
        
        return Station(
            station_code=station_code,
            name_en=name_en,
            name_fr=name_fr,
            province=province.upper(),
            coordinates=Coordinates(lat=lat, lon=lon),
            region_en=region_en,
            region_fr=region_fr,
            active=True,
            updated_at=utcnow()
        )
        
    except Exception as e:
        logger.warning("Error parsing station metadata", station_code=station_code, error=str(e))
        return None


def _parse_current_conditions(root: etree._Element, station_code: str) -> Optional[Observation]:
    """Extract current weather conditions from XML."""
    try:
        cc = root.find('.//currentConditions')
        if cc is None:
            return None
        
        # Parse observation timestamp
        date_time = cc.find('dateTime[@zone="UTC"][@name="observation"]')
        if date_time is None:
            date_time = cc.find('dateTime[@name="observation"]')
        
        observed_at = _parse_datetime(date_time)
        if observed_at is None:
            return None
        
        # Parse weather conditions
        condition_en = _get_text(cc, 'condition')
        icon_code = _get_text(cc, 'iconCode')
        
        # Temperature
        temperature_c = _get_float(cc, 'temperature')
        dewpoint_c = _get_float(cc, 'dewpoint')
        humidity_pct = _get_float(cc, 'relativeHumidity')
        humidex = _get_float(cc, 'humidex')
        wind_chill_elem = cc.find('windChill')
        wind_chill = _parse_float(wind_chill_elem.text) if wind_chill_elem is not None and wind_chill_elem.text else None
        
        # Pressure
        pressure_elem = cc.find('pressure')
        pressure_kpa = _parse_float(pressure_elem.text) if pressure_elem is not None else None
        pressure_tendency = pressure_elem.get('tendency') if pressure_elem is not None else None
        
        # Wind
        wind = cc.find('wind')
        wind_speed_kmh = None
        wind_direction_deg = None
        wind_direction_text = None
        wind_gust_kmh = None
        
        if wind is not None:
            wind_speed_kmh = _get_float(wind, 'speed')
            wind_gust_kmh = _get_float(wind, 'gust')
            wind_direction_text = _get_text(wind, 'direction')
            bearing = _get_text(wind, 'bearing')
            if bearing:
                try:
                    wind_direction_deg = int(float(bearing))
                except (ValueError, TypeError):
                    pass
        
        # Visibility
        visibility_km = _get_float(cc, 'visibility')
        
        return Observation(
            station_code=station_code,
            observed_at=observed_at,
            fetched_at=utcnow(),
            temperature_c=temperature_c,
            humidity_pct=humidity_pct,
            dewpoint_c=dewpoint_c,
            pressure_kpa=pressure_kpa,
            pressure_tendency=pressure_tendency,
            wind_speed_kmh=wind_speed_kmh,
            wind_direction_deg=wind_direction_deg,
            wind_direction_text=wind_direction_text,
            wind_gust_kmh=wind_gust_kmh,
            wind_chill=wind_chill,
            humidex=humidex,
            visibility_km=visibility_km,
            condition_en=condition_en,
            condition_fr=None,
            icon_code=icon_code
        )
        
    except Exception as e:
        logger.warning("Error parsing current conditions", station_code=station_code, error=str(e))
        return None


def _parse_warnings(root: etree._Element, station_code: str) -> List[Warning]:
    """Extract weather warnings from XML."""
    warnings = []
    
    try:
        warnings_elem = root.find('.//warnings')
        if warnings_elem is None:
            return warnings
        
        # Get URL for more information
        warnings_url = warnings_elem.get('url')
        
        # Parse each event
        for event in warnings_elem.findall('event'):
            event_type = event.get('type', 'unknown')
            priority = event.get('priority', 'medium')
            description = event.get('description', '')
            
            # Get headline from textSummary or description attribute
            headline_elem = event.find('textSummary')
            headline = headline_elem.text if headline_elem is not None and headline_elem.text else description
            
            if not headline:
                headline = f"{event_type.title()}"
            
            # Parse effective/expiry times
            effective = None
            expires = None
            
            # Look for dateTime elements
            for dt in event.findall('dateTime'):
                dt_name = dt.get('name', '')
                if 'effective' in dt_name.lower() or 'issue' in dt_name.lower():
                    effective = _parse_datetime(dt)
                elif 'expir' in dt_name.lower() or 'end' in dt_name.lower():
                    expires = _parse_datetime(dt)
            
            warnings.append(Warning(
                station_code=station_code,
                event_type=event_type,
                priority=priority,
                headline=headline,
                description=description if description != headline else None,
                effective=effective,
                expires=expires,
                url=warnings_url,
                fetched_at=utcnow(),
                active=True
            ))
        
        if warnings:
            logger.info("Parsed warnings", station_code=station_code, count=len(warnings))
        
    except Exception as e:
        logger.warning("Error parsing warnings", station_code=station_code, error=str(e))
    
    return warnings


def _get_text(element: etree._Element, path: str) -> Optional[str]:
    """Get text content from an element by path."""
    if element is None:
        return None
    
    if '/@' in path:
        elem_path, attr = path.rsplit('/@', 1)
        found = element.find(elem_path) if elem_path else element
        if found is not None:
            return found.get(attr)
        return None
    
    found = element.find(path)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _get_float(element: etree._Element, path: str) -> Optional[float]:
    """Get float value from an element by path."""
    text = _get_text(element, path)
    return _parse_float(text)


def _parse_float(value: Optional[str]) -> Optional[float]:
    """Parse a string to float, returning None on failure."""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_datetime(date_time_elem: Optional[etree._Element]) -> Optional[datetime]:
    """Parse a dateTime element from Environment Canada XML."""
    if date_time_elem is None:
        return None
    
    try:
        year = date_time_elem.find('year')
        month = date_time_elem.find('month')
        day = date_time_elem.find('day')
        hour = date_time_elem.find('hour')
        minute = date_time_elem.find('minute')
        
        if all(e is not None and e.text for e in [year, month, day, hour, minute]):
            dt = datetime(
                year=int(year.text),
                month=int(month.text),
                day=int(day.text),
                hour=int(hour.text),
                minute=int(minute.text),
                tzinfo=timezone.utc
            )
            return dt
        
        # Try parsing timestamp attribute
        timestamp = date_time_elem.get('timestamp')
        if timestamp:
            parsed = dateparser.parse(timestamp)
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
        
    except (ValueError, TypeError) as e:
        pass
    
    return None
