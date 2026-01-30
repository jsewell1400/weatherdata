#!/usr/bin/env python3
"""
Weather Data CLI - View statistics, observations, and warnings from MongoDB.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


def get_mongo_client():
    """Create MongoDB connection from environment variables."""
    host = os.environ.get("MONGO_HOST", "localhost")
    port = int(os.environ.get("MONGO_PORT", "27017"))
    database = os.environ.get("MONGO_DATABASE", "weatherdata")
    username = os.environ.get("MONGO_USERNAME", "weatherapp")
    password = os.environ.get("MONGO_PASSWORD", "")
    
    if not password:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith("MONGO_PASSWORD="):
                        password = line.strip().split("=", 1)[1]
                    elif line.startswith("MONGO_APP_PASSWORD="):
                        password = line.strip().split("=", 1)[1]
    
    if not password:
        print("Error: MONGO_PASSWORD environment variable not set")
        sys.exit(1)
    
    uri = f"mongodb://{username}:{password}@{host}:{port}/{database}?authSource={database}"
    
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client[database]
    except ConnectionFailure as e:
        print(f"Error: Could not connect to MongoDB at {host}:{port}")
        print(f"Details: {e}")
        sys.exit(1)


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def cmd_stats(db, args):
    """Show database statistics."""
    print("=" * 60)
    print("WEATHER DATABASE STATISTICS")
    print("=" * 60)
    
    total_stations = db.stations.count_documents({})
    active_stations = db.stations.count_documents({"active": True})
    inactive_stations = total_stations - active_stations
    
    print(f"\n📍 STATIONS")
    print(f"   Total:    {total_stations:,}")
    print(f"   Active:   {active_stations:,}")
    print(f"   Inactive: {inactive_stations:,}")
    
    pipeline = [
        {"$match": {"active": True}},
        {"$group": {"_id": "$province", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    by_province = list(db.stations.aggregate(pipeline))
    if by_province:
        print(f"\n   By Province:")
        for p in by_province:
            print(f"      {p['_id']}: {p['count']}")
    
    total_obs = db.observations.count_documents({})
    print(f"\n🌡️  OBSERVATIONS")
    print(f"   Total: {total_obs:,}")
    
    if total_obs > 0:
        oldest = db.observations.find_one(sort=[("observed_at", 1)])
        newest = db.observations.find_one(sort=[("observed_at", -1)])
        
        if oldest and newest:
            oldest_date = oldest["observed_at"]
            newest_date = newest["observed_at"]
            print(f"   Oldest: {oldest_date}")
            print(f"   Newest: {newest_date}")
            
            if isinstance(oldest_date, datetime) and isinstance(newest_date, datetime):
                duration = newest_date - oldest_date
                print(f"   Span:   {duration.days} days, {duration.seconds // 3600} hours")
        
        yesterday = utcnow() - timedelta(days=1)
        recent_count = db.observations.count_documents({"observed_at": {"$gte": yesterday}})
        print(f"\n   Last 24 hours: {recent_count:,}")
        
        last_hour = utcnow() - timedelta(hours=1)
        hourly_count = db.observations.count_documents({"observed_at": {"$gte": last_hour}})
        print(f"   Last hour:     {hourly_count:,}")
    
    # Warnings stats
    total_warnings = db.warnings.count_documents({})
    active_warnings = db.warnings.count_documents({"active": True})
    print(f"\n⚠️  WARNINGS")
    print(f"   Total:  {total_warnings:,}")
    print(f"   Active: {active_warnings:,}")
    
    if active_warnings > 0:
        # Show breakdown by province
        pipeline = [
            {"$match": {"active": True}},
            {"$lookup": {
                "from": "stations",
                "localField": "station_code",
                "foreignField": "station_code",
                "as": "station"
            }},
            {"$unwind": "$station"},
            {"$group": {"_id": "$station.province", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        warnings_by_prov = list(db.warnings.aggregate(pipeline))
        if warnings_by_prov:
            print(f"\n   By Province:")
            for w in warnings_by_prov:
                print(f"      {w['_id']}: {w['count']}")
    
    stats = db.command("dbstats")
    size_mb = stats.get("dataSize", 0) / (1024 * 1024)
    storage_mb = stats.get("storageSize", 0) / (1024 * 1024)
    print(f"\n💾 STORAGE")
    print(f"   Data size:    {size_mb:.2f} MB")
    print(f"   Storage size: {storage_mb:.2f} MB")
    print()


def cmd_stations(db, args):
    """List all active stations."""
    query = {"active": True}
    if args.province:
        query["province"] = args.province.upper()
    
    stations = db.stations.find(query).sort([("province", 1), ("name_en", 1)])
    
    print(f"{'Code':<12} {'Province':<4} {'Name':<40} {'Lat':>8} {'Lon':>9}")
    print("-" * 80)
    
    count = 0
    for station in stations:
        coords = station.get("coordinates", {})
        lat = coords.get("lat", 0)
        lon = coords.get("lon", 0)
        
        if args.with_coords and (lat == 0 and lon == 0):
            continue
        
        print(f"{station['station_code']:<12} {station['province']:<4} {station['name_en'][:40]:<40} {lat:>8.4f} {lon:>9.4f}")
        count += 1
        
        if args.limit and count >= args.limit:
            print(f"\n... (showing {args.limit} of more results)")
            break
    
    print(f"\nTotal: {count} stations")


def cmd_recent(db, args):
    """Show recent observations."""
    limit = args.limit or 10
    
    pipeline = [
        {"$sort": {"observed_at": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "stations",
            "localField": "station_code",
            "foreignField": "station_code",
            "as": "station"
        }},
        {"$unwind": {"path": "$station", "preserveNullAndEmptyArrays": True}}
    ]
    
    observations = list(db.observations.aggregate(pipeline))
    
    print(f"{'Time (UTC)':<20} {'Station':<30} {'Temp':>6} {'Humidity':>8} {'Wind':>8} {'Condition':<20}")
    print("-" * 100)
    
    for obs in observations:
        station_name = obs.get("station", {}).get("name_en", obs["station_code"])[:30]
        observed = obs.get("observed_at", "")
        if isinstance(observed, datetime):
            observed = observed.strftime("%Y-%m-%d %H:%M")
        
        temp = obs.get("temperature_c")
        temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
        
        humidity = obs.get("humidity_pct")
        hum_str = f"{humidity:.0f}%" if humidity is not None else "N/A"
        
        wind = obs.get("wind_speed_kmh")
        wind_str = f"{wind:.0f} km/h" if wind is not None else "N/A"
        
        condition = (obs.get("condition_en") or "")[:20]
        
        print(f"{observed:<20} {station_name:<30} {temp_str:>6} {hum_str:>8} {wind_str:>8} {condition:<20}")


def cmd_station(db, args):
    """Show data for a specific station."""
    if not args.code:
        print("Error: --code is required for station command")
        sys.exit(1)
    
    code = args.code
    station = db.stations.find_one({"station_code": code})
    if not station:
        print(f"Station '{code}' not found")
        sys.exit(1)
    
    print("=" * 60)
    print(f"STATION: {station['name_en']}")
    print("=" * 60)
    
    print(f"\n📍 INFO")
    print(f"   Code:     {station['station_code']}")
    print(f"   Name EN:  {station['name_en']}")
    print(f"   Name FR:  {station.get('name_fr', 'N/A')}")
    print(f"   Province: {station['province']}")
    print(f"   Active:   {'Yes' if station.get('active') else 'No'}")
    
    coords = station.get("coordinates", {})
    print(f"   Location: {coords.get('lat', 0):.4f}, {coords.get('lon', 0):.4f}")
    
    # Check for active warnings
    active_warnings = list(db.warnings.find({"station_code": code, "active": True}))
    if active_warnings:
        print(f"\n⚠️  ACTIVE WARNINGS ({len(active_warnings)})")
        for w in active_warnings:
            priority_icon = "🔴" if w.get("priority") == "urgent" else "🟠" if w.get("priority") == "high" else "🟡"
            print(f"   {priority_icon} {w.get('headline', 'Unknown')}")
            if w.get("expires"):
                print(f"      Expires: {w['expires']}")
    
    latest = db.observations.find_one({"station_code": code}, sort=[("observed_at", -1)])
    
    if latest:
        print(f"\n🌡️  LATEST OBSERVATION")
        print(f"   Time: {latest.get('observed_at')}")
        
        if latest.get("temperature_c") is not None:
            print(f"   Temperature: {latest['temperature_c']:.1f}°C")
        if latest.get("humidity_pct") is not None:
            print(f"   Humidity: {latest['humidity_pct']:.0f}%")
        if latest.get("pressure_kpa") is not None:
            print(f"   Pressure: {latest['pressure_kpa']:.1f} kPa")
        if latest.get("wind_speed_kmh") is not None:
            direction = latest.get("wind_direction_text", "")
            print(f"   Wind: {latest['wind_speed_kmh']:.0f} km/h {direction}")
        if latest.get("wind_chill") is not None:
            print(f"   Wind Chill: {latest['wind_chill']:.0f}°C")
        if latest.get("condition_en"):
            print(f"   Condition: {latest['condition_en']}")
    
    obs_count = db.observations.count_documents({"station_code": code})
    print(f"\n📊 HISTORY")
    print(f"   Total observations: {obs_count:,}")
    
    limit = args.limit or 5
    print(f"\n   Last {limit} observations:")
    recent = db.observations.find({"station_code": code}).sort("observed_at", -1).limit(limit)
    
    for obs in recent:
        time_str = obs.get("observed_at", "")
        if isinstance(time_str, datetime):
            time_str = time_str.strftime("%Y-%m-%d %H:%M")
        temp = obs.get("temperature_c")
        temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
        cond = obs.get("condition_en", "")[:20]
        print(f"      {time_str}  {temp_str:>8}  {cond}")
    print()


def cmd_warnings(db, args):
    """Show active weather warnings."""
    query = {"active": True}
    
    if args.province:
        # Need to join with stations to filter by province
        pipeline = [
            {"$match": {"active": True}},
            {"$lookup": {
                "from": "stations",
                "localField": "station_code",
                "foreignField": "station_code",
                "as": "station"
            }},
            {"$unwind": "$station"},
            {"$match": {"station.province": args.province.upper()}},
            {"$sort": {"priority": 1, "fetched_at": -1}}
        ]
        warnings = list(db.warnings.aggregate(pipeline))
    else:
        pipeline = [
            {"$match": {"active": True}},
            {"$lookup": {
                "from": "stations",
                "localField": "station_code",
                "foreignField": "station_code",
                "as": "station"
            }},
            {"$unwind": {"path": "$station", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"priority": 1, "fetched_at": -1}}
        ]
        warnings = list(db.warnings.aggregate(pipeline))
    
    if not warnings:
        print("✅ No active weather warnings!")
        return
    
    print("=" * 70)
    print(f"ACTIVE WEATHER WARNINGS ({len(warnings)})")
    print("=" * 70)
    
    # Group by priority
    urgent = [w for w in warnings if w.get("priority") == "urgent"]
    high = [w for w in warnings if w.get("priority") == "high"]
    medium = [w for w in warnings if w.get("priority") == "medium"]
    low = [w for w in warnings if w.get("priority") not in ("urgent", "high", "medium")]
    
    for priority_name, priority_warnings, icon in [
        ("URGENT", urgent, "🔴"),
        ("HIGH", high, "🟠"),
        ("MEDIUM", medium, "🟡"),
        ("LOW", low, "🟢")
    ]:
        if not priority_warnings:
            continue
        
        print(f"\n{icon} {priority_name} ({len(priority_warnings)})")
        print("-" * 50)
        
        count = 0
        for w in priority_warnings:
            station_name = w.get("station", {}).get("name_en", w["station_code"])
            province = w.get("station", {}).get("province", "??")
            
            print(f"\n   📍 {station_name}, {province}")
            print(f"   ⚠️  {w.get('headline', 'No headline')}")
            
            if w.get("effective"):
                print(f"   📅 Effective: {w['effective']}")
            if w.get("expires"):
                print(f"   ⏰ Expires:   {w['expires']}")
            if w.get("url"):
                print(f"   🔗 {w['url']}")
            
            count += 1
            if args.limit and count >= args.limit:
                remaining = len(priority_warnings) - count
                if remaining > 0:
                    print(f"\n   ... and {remaining} more {priority_name.lower()} warnings")
                break
    
    print()


def main():
    parser = argparse.ArgumentParser(description="Weather Data CLI")
    parser.add_argument("command", nargs="?", default="stats",
                        choices=["stats", "stations", "recent", "station", "warnings"])
    parser.add_argument("--limit", "-n", type=int)
    parser.add_argument("--province", "-p")
    parser.add_argument("--code", "-c")
    parser.add_argument("--with-coords", action="store_true")
    
    args = parser.parse_args()
    db = get_mongo_client()
    
    commands = {
        "stats": cmd_stats,
        "stations": cmd_stations,
        "recent": cmd_recent,
        "station": cmd_station,
        "warnings": cmd_warnings,
    }
    
    commands[args.command](db, args)


if __name__ == "__main__":
    main()
