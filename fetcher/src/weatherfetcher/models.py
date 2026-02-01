"""
Data models for weather stations, observations, and warnings.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
from typing import Optional, List


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class Coordinates(BaseModel):
    """Geographic coordinates for a weather station."""
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")
    elevation_m: Optional[float] = Field(None, description="Elevation in meters")


class Station(BaseModel):
    """Weather station metadata."""
    station_code: str = Field(..., description="Environment Canada station identifier")
    name_en: str = Field(..., description="Station name in English")
    name_fr: str = Field(..., description="Station name in French")
    province: str = Field(..., description="Province/territory code")
    coordinates: Coordinates = Field(..., description="Geographic coordinates")
    region_en: Optional[str] = Field(None, description="Region name in English")
    region_fr: Optional[str] = Field(None, description="Region name in French")
    active: bool = Field(default=True, description="Whether station is currently active")
    updated_at: datetime = Field(default_factory=utcnow, description="Last update timestamp")

    def to_mongo_doc(self) -> dict:
        """Convert to MongoDB document format."""
        return {
            "station_code": self.station_code,
            "name_en": self.name_en,
            "name_fr": self.name_fr,
            "province": self.province,
            "coordinates": {
                "lat": self.coordinates.lat,
                "lon": self.coordinates.lon,
                "elevation_m": self.coordinates.elevation_m,
            },
            "region_en": self.region_en,
            "region_fr": self.region_fr,
            "active": self.active,
            "updated_at": self.updated_at,
        }


class Observation(BaseModel):
    """Weather observation from a station."""
    station_code: str = Field(..., description="Reference to stations collection")
    observed_at: datetime = Field(..., description="When the observation was recorded")
    fetched_at: datetime = Field(default_factory=utcnow, description="When we retrieved this data")
    
    # Temperature and humidity
    temperature_c: Optional[float] = Field(None, description="Temperature in Celsius")
    humidity_pct: Optional[float] = Field(None, description="Relative humidity percentage")
    dewpoint_c: Optional[float] = Field(None, description="Dewpoint in Celsius")
    
    # Pressure
    pressure_kpa: Optional[float] = Field(None, description="Atmospheric pressure in kPa")
    pressure_tendency: Optional[str] = Field(None, description="Pressure tendency (rising/falling/steady)")
    
    # Wind
    wind_speed_kmh: Optional[float] = Field(None, description="Wind speed in km/h")
    wind_direction_deg: Optional[int] = Field(None, description="Wind direction in degrees")
    wind_direction_text: Optional[str] = Field(None, description="Wind direction as compass text")
    wind_gust_kmh: Optional[float] = Field(None, description="Wind gust speed in km/h")
    wind_chill: Optional[float] = Field(None, description="Wind chill temperature")
    humidex: Optional[float] = Field(None, description="Humidex value")
    
    # Visibility and conditions
    visibility_km: Optional[float] = Field(None, description="Visibility in kilometers")
    condition_en: Optional[str] = Field(None, description="Weather condition in English")
    condition_fr: Optional[str] = Field(None, description="Weather condition in French")
    icon_code: Optional[str] = Field(None, description="Weather icon code")

    def to_mongo_doc(self) -> dict:
        """Convert to MongoDB document format."""
        return {
            "station_code": self.station_code,
            "observed_at": self.observed_at,
            "fetched_at": self.fetched_at,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "dewpoint_c": self.dewpoint_c,
            "pressure_kpa": self.pressure_kpa,
            "pressure_tendency": self.pressure_tendency,
            "wind_speed_kmh": self.wind_speed_kmh,
            "wind_direction_deg": self.wind_direction_deg,
            "wind_direction_text": self.wind_direction_text,
            "wind_gust_kmh": self.wind_gust_kmh,
            "wind_chill": self.wind_chill,
            "humidex": self.humidex,
            "visibility_km": self.visibility_km,
            "condition_en": self.condition_en,
            "condition_fr": self.condition_fr,
            "icon_code": self.icon_code,
        }


class Warning(BaseModel):
    """Weather warning/watch/advisory for a station."""
    station_code: str = Field(..., description="Reference to stations collection")
    event_type: str = Field(..., description="Type: warning, watch, advisory, statement, ended")
    priority: str = Field(..., description="Priority: urgent, high, medium, low")
    headline: str = Field(..., description="Warning headline text")
    description: Optional[str] = Field(None, description="Full warning description")
    effective: Optional[datetime] = Field(None, description="When warning takes effect")
    expires: Optional[datetime] = Field(None, description="When warning expires")
    url: Optional[str] = Field(None, description="URL for more information")
    fetched_at: datetime = Field(default_factory=utcnow, description="When we retrieved this data")
    active: bool = Field(default=True, description="Whether warning is currently active")

    def to_mongo_doc(self) -> dict:
        """Convert to MongoDB document format."""
        return {
            "station_code": self.station_code,
            "event_type": self.event_type,
            "priority": self.priority,
            "headline": self.headline,
            "description": self.description,
            "effective": self.effective,
            "expires": self.expires,
            "url": self.url,
            "fetched_at": self.fetched_at,
            "active": self.active,
        }


class ForecastPeriod(BaseModel):
    """Single forecast period (e.g., 'Tonight', 'Saturday')."""
    period_name: str = Field(..., description="Period name like 'Tonight' or 'Saturday'")
    text_summary: str = Field(..., description="Short forecast text like 'Clearing. Low minus 21.'")
    abbreviated_summary: Optional[str] = Field(None, description="Even shorter summary like 'Clear'")
    icon_code: Optional[str] = Field(None, description="Weather icon code")
    temperature_c: Optional[float] = Field(None, description="Forecast temperature")
    temperature_class: Optional[str] = Field(None, description="'high' or 'low'")
    pop_pct: Optional[int] = Field(None, description="Probability of precipitation")
    wind_summary: Optional[str] = Field(None, description="Wind forecast text")
    humidity_pct: Optional[float] = Field(None, description="Relative humidity percentage")


class Forecast(BaseModel):
    """Weather forecast for a station."""
    station_code: str = Field(..., description="Reference to stations collection")
    issued_at: datetime = Field(..., description="When the forecast was issued")
    fetched_at: datetime = Field(default_factory=utcnow, description="When we retrieved this data")
    periods: List[ForecastPeriod] = Field(default_factory=list, description="Forecast periods")

    def to_mongo_doc(self) -> dict:
        """Convert to MongoDB document format."""
        return {
            "station_code": self.station_code,
            "issued_at": self.issued_at,
            "fetched_at": self.fetched_at,
            "periods": [
                {
                    "period_name": p.period_name,
                    "text_summary": p.text_summary,
                    "abbreviated_summary": p.abbreviated_summary,
                    "icon_code": p.icon_code,
                    "temperature_c": p.temperature_c,
                    "temperature_class": p.temperature_class,
                    "pop_pct": p.pop_pct,
                    "wind_summary": p.wind_summary,
                    "humidity_pct": p.humidity_pct,
                }
                for p in self.periods
            ],
        }



class StationListEntry(BaseModel):
    """Entry from the Environment Canada site list."""
    station_code: str
    name_en: str
    name_fr: str
    province: str
    lat: Optional[float] = None
    lon: Optional[float] = None
