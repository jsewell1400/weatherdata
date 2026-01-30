# WeatherData Canada 🇨🇦

A self-hosted weather data collection system that fetches real-time weather observations and warnings from Environment Canada and stores them in MongoDB.

## Features

- **844 Weather Stations** - Collects data from all Environment Canada reporting stations across every province and territory
- **Real-time Observations** - Fetches current conditions 6 times per hour (every 10 minutes)
- **Weather Warnings** - Captures active watches, warnings, and advisories
- **Daily Station Updates** - Automatically detects new/removed stations
- **Historical Data** - Stores all observations for trend analysis
- **CLI Dashboard** - Query stats, view warnings, and check station data from the command line
- **Docker Deployment** - Simple containerized setup with automatic restarts

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Ubuntu Server                            │
│                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│   │   Python    │    │   MongoDB   │    │   Prometheus    │ │
│   │   Fetcher   │───▶│   (Docker)  │◀───│   (Future)      │ │
│   │  (Docker)   │    │             │    │                 │ │
│   └─────────────┘    └─────────────┘    └─────────────────┘ │
│          │                  │                               │
│          ▼                  ▼                               │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           Docker Network: weatherdata_net           │   │
│   └─────────────────────────────────────────────────────┘   │
│                             │                               │
│                             ▼                               │
│                    /var/lib/mongodb                         │
│                    (Persistent Data)                        │
└─────────────────────────────────────────────────────────────┘
```

## Data Sources

Data is sourced from Environment Canada's open data service:

- **Station List**: [GeoJSON](https://collaboration.cmc.ec.gc.ca/cmc/cmos/public_doc/msc-data/citypage-weather/site_list_en.geojson)
- **Weather Data**: `https://dd.weather.gc.ca/today/citypage_weather/{PROVINCE}/{HOUR}/`
- **Documentation**: [MSC Open Data](https://eccc-msc.github.io/open-data/)

## Prerequisites

- Ubuntu 22.04+ (or similar Linux distribution)
- Docker Engine with Compose plugin
- 2GB+ RAM recommended
- 10GB+ disk space for long-term data storage

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/jsewell1400/weatherdata.git
cd weatherdata
```

### 2. Create Environment File

```bash
# Generate secure passwords
generate_password() {
    openssl rand -base64 24 | tr -d '/+=' | head -c 24
}

cat > .env << EOF
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=$(generate_password)
MONGO_APP_USERNAME=weatherapp
MONGO_APP_PASSWORD=$(generate_password)
EOF

chmod 600 .env

# Save these credentials somewhere safe!
cat .env
```

### 3. Create Data Directory

```bash
sudo mkdir -p /var/lib/mongodb
sudo chown -R 999:999 /var/lib/mongodb
```

### 4. Start Services

```bash
docker compose up -d
```

### 5. Verify It's Working

```bash
# Check container status
docker compose ps

# View fetcher logs
docker compose logs -f fetcher

# Check database stats (after a few minutes)
docker compose exec fetcher python /app/weather_stats.py
```

## Configuration

All configuration is via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_HOST` | mongodb | MongoDB hostname |
| `MONGO_PORT` | 27017 | MongoDB port |
| `MONGO_DATABASE` | weatherdata | Database name |
| `MONGO_USERNAME` | weatherapp | App database user |
| `MONGO_PASSWORD` | (required) | App database password |
| `OBSERVATION_INTERVAL_SECONDS` | 600 | Fetch frequency (10 min) |
| `STATION_REFRESH_INTERVAL_SECONDS` | 86400 | Station list refresh (24 hr) |
| `LOG_LEVEL` | INFO | Logging verbosity |

## CLI Usage

The `weather_stats.py` CLI provides quick access to your data:

```bash
# Overall statistics
docker compose exec fetcher python /app/weather_stats.py

# List all stations
docker compose exec fetcher python /app/weather_stats.py stations

# Filter stations by province
docker compose exec fetcher python /app/weather_stats.py stations --province MB

# Recent observations across all stations
docker compose exec fetcher python /app/weather_stats.py recent --limit 20

# Specific station details
docker compose exec fetcher python /app/weather_stats.py station --code s0000458

# Active weather warnings
docker compose exec fetcher python /app/weather_stats.py warnings

# Warnings for a specific province
docker compose exec fetcher python /app/weather_stats.py warnings --province ON
```

### Finding Station Codes

```bash
# Search for a city
docker compose exec fetcher python /app/weather_stats.py stations --province ON | grep -i toronto

# Common station codes:
# s0000458 - Toronto Pearson
# s0000492 - Brandon
# s0000141 - Vancouver
# s0000045 - Edmonton
# s0000195 - Montreal
```

## Data Schema

### Stations Collection

```javascript
{
  "station_code": "s0000458",
  "name_en": "Toronto Pearson Int'l Airport",
  "name_fr": "Aéroport int'l Toronto Pearson",
  "province": "ON",
  "coordinates": {
    "lat": 43.6777,
    "lon": -79.6248,
    "elevation_m": null
  },
  "region_en": "City of Toronto",
  "active": true,
  "updated_at": ISODate("2026-01-30T12:00:00Z")
}
```

### Observations Collection

```javascript
{
  "station_code": "s0000458",
  "observed_at": ISODate("2026-01-30T12:00:00Z"),
  "fetched_at": ISODate("2026-01-30T12:02:34Z"),
  "temperature_c": -5.2,
  "humidity_pct": 78.0,
  "dewpoint_c": -8.5,
  "pressure_kpa": 101.2,
  "pressure_tendency": "rising",
  "wind_speed_kmh": 15.0,
  "wind_direction_deg": 270,
  "wind_direction_text": "W",
  "wind_gust_kmh": 25.0,
  "wind_chill": -12.0,
  "visibility_km": 24.0,
  "condition_en": "Light Snow",
  "icon_code": "16"
}
```

### Warnings Collection

```javascript
{
  "station_code": "s0000458",
  "event_type": "warning",
  "priority": "high",
  "headline": "Extreme Cold Warning",
  "description": "...",
  "effective": ISODate("2026-01-30T06:00:00Z"),
  "expires": ISODate("2026-01-31T12:00:00Z"),
  "url": "https://weather.gc.ca/...",
  "active": true,
  "fetched_at": ISODate("2026-01-30T12:00:00Z")
}
```

## Operations

### View Logs

```bash
docker compose logs -f fetcher
docker compose logs -f mongodb
```

### Backup Database

```bash
# Manual backup
./scripts/backup.sh

# Backups are stored in ./backups/
ls -la backups/
```

### Restore from Backup

```bash
BACKUP_FILE="./backups/weatherdata_20260130_020000.archive.gz"

docker compose exec -T mongodb mongorestore \
  --username="${MONGO_ROOT_USERNAME}" \
  --password="${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase=admin \
  --db=weatherdata \
  --drop \
  --archive \
  --gzip \
  < "${BACKUP_FILE}"
```

### Update Containers

```bash
docker compose pull
docker compose up -d --build
```

### MongoDB Shell Access

```bash
# As app user (read/write weatherdata)
docker compose exec mongodb mongosh -u weatherapp \
  -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase weatherdata weatherdata

# As admin
docker compose exec mongodb mongosh -u admin \
  -p "$(grep MONGO_ROOT_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase admin
```

## Data Growth

With ~600 active stations reporting every 10 minutes:

| Period | Observations | Estimated Size |
|--------|--------------|----------------|
| Hour | ~3,600 | ~2 MB |
| Day | ~86,400 | ~45 MB |
| Month | ~2.6 million | ~1.3 GB |
| Year | ~31 million | ~16 GB |

Plan your disk space accordingly for long-term storage.

## Troubleshooting

### Fetcher not collecting data

```bash
# Check logs for errors
docker compose logs fetcher --tail 100

# Verify MongoDB is healthy
docker compose exec mongodb mongosh --eval "db.adminCommand('ping')"

# Test Environment Canada connectivity
docker compose exec fetcher python -c "
import requests
r = requests.get('https://dd.weather.gc.ca/today/citypage_weather/ON/12/', timeout=10)
print('Status:', r.status_code)
"
```

### Database connection issues

```bash
# Check MongoDB is running
docker compose ps mongodb

# Verify credentials
docker compose exec mongodb mongosh -u weatherapp \
  -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase weatherdata \
  --eval "db.stats()"
```

### Reset everything

```bash
# Stop services
docker compose down

# Remove data (DESTRUCTIVE!)
sudo rm -rf /var/lib/mongodb/*

# Restart fresh
docker compose up -d
```

## Project Structure

```
/opt/weatherdata/
├── docker-compose.yml      # Container orchestration
├── .env                    # Secrets (not in git)
├── .env.example            # Template for .env
├── .gitignore              # Git exclusions
├── README.md               # This file
├── weather_stats.py        # CLI tool
├── mongo-init/
│   └── 01-init-users.js    # MongoDB initialization
├── scripts/
│   └── backup.sh           # Backup script
├── backups/                # Database backups (not in git)
└── fetcher/                # Python fetcher service
    ├── Dockerfile
    ├── requirements.txt
    ├── pyproject.toml
    └── src/
        └── weatherfetcher/
            ├── __init__.py
            ├── __main__.py
            ├── config.py
            ├── db.py
            ├── fetcher.py
            ├── models.py
            └── parser.py
```

## License

MIT License - See [LICENSE](LICENSE) for details.

## Acknowledgments

- Weather data provided by [Environment and Climate Change Canada](https://weather.gc.ca/)
- Built with [MongoDB](https://www.mongodb.com/), [Docker](https://www.docker.com/), and [Python](https://www.python.org/)

---

*Made with ❄️ in Canada*
