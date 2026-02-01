"""
WeatherData JSON API
A secure, read-only API for publishing weather observations and warnings.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title="WeatherData Canada API",
    description="Public API for Canadian weather observations and warnings",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration - restrictive by default
allowed_origins = os.getenv("CORS_ORIGINS", "").split(",")
allowed_origins = [o.strip() for o in allowed_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Accept-Language", "Content-Type"],
)


# MongoDB connection
def get_db():
    """Get MongoDB database connection."""
    mongo_host = os.getenv("MONGO_HOST", "mongodb")
    mongo_port = int(os.getenv("MONGO_PORT", "27017"))
    mongo_database = os.getenv("MONGO_DATABASE", "weatherdata")
    mongo_username = os.getenv("MONGO_USERNAME", "weatherapp")
    mongo_password = os.getenv("MONGO_PASSWORD", "")
    
    uri = (
        f"mongodb://{mongo_username}:{mongo_password}"
        f"@{mongo_host}:{mongo_port}/{mongo_database}"
        f"?authSource={mongo_database}"
    )
    
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client[mongo_database]


# Cache database connection
_db = None

def get_database():
    global _db
    if _db is None:
        _db = get_db()
    return _db


@app.on_event("startup")
async def startup_event():
    """Verify database connection on startup."""
    try:
        db = get_database()
        db.command("ping")
        logger.info("Successfully connected to MongoDB")
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    try:
        db = get_database()
        db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"}
        )


def get_first_sentence(text: str) -> str:
    """Extract the first sentence from text (up to and including first period)."""
    if not text:
        return ""
    # Find the first period
    period_idx = text.find(".")
    if period_idx != -1:
        return text[:period_idx + 1]
    return text


def format_station_response(station: dict, observation: dict, warnings: list, forecast_doc: dict) -> dict:
    """Format station data into the expected JSON structure."""
    city_name = station.get("name_en", "Unknown")
    
    # Format temperature
    temp = observation.get("temperature_c")
    if temp is not None:
        temp_str = f"{temp}°C"
    else:
        temp_str = ""
    
    # Format updated timestamp
    observed_at = observation.get("observed_at")
    if observed_at:
        if isinstance(observed_at, datetime):
            updated_str = observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            updated_str = str(observed_at)
    else:
        updated_str = ""
    
    # Combine warnings into a single string (deduplicated)
    seen_headlines = set()
    warning_texts = []
    for w in warnings:
        if w.get("active", False):
            headline = w.get("headline", "")
            if headline and headline not in seen_headlines:
                seen_headlines.add(headline)
                warning_texts.append(headline)
    warnings_str = "; ".join(warning_texts)
    
    # Get forecast: first period's text_summary, first sentence only
    forecast = ""
    if forecast_doc:
        periods = forecast_doc.get("periods", [])
        if periods:
            first_period = periods[0]
            full_text = first_period.get("text_summary", "")
            forecast = get_first_sentence(full_text)
    
    return {
        "title": f"{city_name} - Weather - Environment Canada",
        "city": city_name,
        "updated": updated_str,
        "temperature": temp_str,
        "condition": observation.get("condition_en", ""),
        "warnings": warnings_str,
        "forecast": forecast
    }


@app.get("/api/v1/weather")
@limiter.limit("60/minute")
async def get_weather(
    request: Request,
    stations: Optional[str] = Query(
        None,
        description="Comma-separated list of station codes (e.g., s0000458,s0000492)",
        max_length=500
    ),
    province: Optional[str] = Query(
        None,
        description="Province code (e.g., MB, ON, BC)",
        min_length=2,
        max_length=2,
        regex="^[A-Z]{2}$"
    ),
    city: Optional[str] = Query(
        None,
        description="City name to search for (partial match)",
        max_length=100
    )
):
    """
    Get current weather observations and warnings.
    
    Returns data for requested stations in the format:
    ```json
    {
      "CityName": {
        "title": "CityName - Weather - Environment Canada",
        "city": "CityName",
        "updated": "2026-01-30T12:00:00Z",
        "temperature": "-5.2°C",
        "condition": "Light Snow",
        "warnings": "",
        "forecast": "mix of sun and cloud. High -10."
      }
    }
    ```
    """
    db = get_database()
    
    # Build station query
    station_query = {"active": True}
    
    if stations:
        # Parse and validate station codes
        station_codes = [s.strip().lower() for s in stations.split(",")]
        station_codes = [s for s in station_codes if s and len(s) <= 20]
        if not station_codes:
            raise HTTPException(status_code=400, detail="No valid station codes provided")
        if len(station_codes) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 stations per request")
        station_query["station_code"] = {"$in": station_codes}
    
    if province:
        station_query["province"] = province.upper()
    
    if city:
        # Case-insensitive partial match on city name
        station_query["name_en"] = {"$regex": city, "$options": "i"}
    
    # Limit results if no specific filter
    limit = 100 if (stations or city) else 50
    
    # Fetch stations
    stations_cursor = db.stations.find(station_query).limit(limit)
    stations_list = list(stations_cursor)
    
    if not stations_list:
        return {}
    
    # Build response
    result = {}
    station_codes = [s["station_code"] for s in stations_list]
    
    # Fetch latest observations for all stations in one query
    pipeline = [
        {"$match": {"station_code": {"$in": station_codes}}},
        {"$sort": {"observed_at": -1}},
        {"$group": {
            "_id": "$station_code",
            "latest": {"$first": "$$ROOT"}
        }}
    ]
    observations = {doc["_id"]: doc["latest"] for doc in db.observations.aggregate(pipeline)}
    
    # Fetch latest forecasts for all stations
    forecast_pipeline = [
        {"$match": {"station_code": {"$in": station_codes}}},
        {"$sort": {"issued_at": -1}},
        {"$group": {
            "_id": "$station_code",
            "latest": {"$first": "$$ROOT"}
        }}
    ]
    forecasts = {doc["_id"]: doc["latest"] for doc in db.forecasts.aggregate(forecast_pipeline)}
    
    # Fetch active warnings for all stations
    warnings_cursor = db.warnings.find({
        "station_code": {"$in": station_codes},
        "active": True
    })
    warnings_by_station = {}
    for w in warnings_cursor:
        code = w["station_code"]
        if code not in warnings_by_station:
            warnings_by_station[code] = []
        warnings_by_station[code].append(w)
    
    # Format response
    for station in stations_list:
        code = station["station_code"]
        city_name = station.get("name_en", code)
        observation = observations.get(code, {})
        station_warnings = warnings_by_station.get(code, [])
        station_forecast = forecasts.get(code, {})
        
        result[city_name] = format_station_response(station, observation, station_warnings, station_forecast)
    
    return result


@app.get("/api/v1/stations")
@limiter.limit("30/minute")
async def list_stations(
    request: Request,
    province: Optional[str] = Query(
        None,
        description="Province code (e.g., MB, ON, BC)",
        min_length=2,
        max_length=2,
        regex="^[A-Z]{2}$"
    )
):
    """
    List available weather stations.
    
    Returns a list of station codes and names for use with the /weather endpoint.
    """
    db = get_database()
    
    query = {"active": True}
    if province:
        query["province"] = province.upper()
    
    stations = db.stations.find(
        query,
        {"station_code": 1, "name_en": 1, "province": 1, "_id": 0}
    ).sort("name_en", 1).limit(500)
    
    return {
        "stations": [
            {
                "code": s["station_code"],
                "name": s["name_en"],
                "province": s["province"]
            }
            for s in stations
        ]
    }


@app.get("/api/v1/warnings")
@limiter.limit("30/minute")
async def get_active_warnings(
    request: Request,
    province: Optional[str] = Query(
        None,
        description="Province code (e.g., MB, ON, BC)",
        min_length=2,
        max_length=2,
        regex="^[A-Z]{2}$"
    )
):
    """
    Get all active weather warnings.
    
    Returns warnings grouped by station.
    """
    db = get_database()
    
    # Get active warnings
    warning_query = {"active": True}
    
    if province:
        # First get station codes for the province
        stations = db.stations.find(
            {"province": province.upper(), "active": True},
            {"station_code": 1}
        )
        station_codes = [s["station_code"] for s in stations]
        warning_query["station_code"] = {"$in": station_codes}
    
    warnings = db.warnings.find(warning_query).limit(200)
    
    result = {}
    for w in warnings:
        code = w["station_code"]
        if code not in result:
            # Get station name
            station = db.stations.find_one({"station_code": code}, {"name_en": 1})
            result[code] = {
                "station": station.get("name_en", code) if station else code,
                "warnings": []
            }
        
        result[code]["warnings"].append({
            "type": w.get("event_type", ""),
            "priority": w.get("priority", ""),
            "headline": w.get("headline", ""),
            "effective": w.get("effective").isoformat() if w.get("effective") else None,
            "expires": w.get("expires").isoformat() if w.get("expires") else None
        })
    
    return result


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
