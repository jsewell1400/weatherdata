# Weather Fetcher

A Python service that collects weather data from Environment Canada XML feeds and stores it in MongoDB.

## Features

- **Automatic Station Discovery**: Fetches the complete list of active weather stations from Environment Canada's siteList.xml
- **Daily Station Refresh**: Updates the station list once per day to capture new stations and mark removed ones as inactive
- **Frequent Observations**: Collects weather observations 6 times per hour (every 10 minutes) for all active stations
- **Concurrent Fetching**: Uses asyncio for efficient parallel data collection with configurable rate limiting
- **Duplicate Prevention**: Uses upsert operations to avoid duplicate observations
- **Graceful Shutdown**: Handles SIGTERM/SIGINT for clean container orchestration

## Data Collected

### Station Metadata
- Station code and names (English/French)
- Province/territory
- Geographic coordinates
- Region information
- Active/inactive status

### Weather Observations
- Temperature, humidity, dewpoint
- Atmospheric pressure and tendency
- Wind speed, direction, and gusts
- Wind chill and humidex
- Visibility
- Weather conditions (text and icon code)

## Installation

### Using Docker (Recommended)

1. Copy the fetcher directory to your weatherdata project:
   ```bash
   cp -r weatherfetcher /opt/weatherdata/fetcher
   ```

2. Update your `.env` file with application credentials:
   ```bash
   # Ensure these are set in /opt/weatherdata/.env
   MONGO_APP_USERNAME=weatherapp
   MONGO_APP_PASSWORD=your_secure_password
   ```

3. Uncomment the fetcher service in `docker-compose.yml`:
   ```yaml
   fetcher:
     build:
       context: ./fetcher
       dockerfile: Dockerfile
     container_name: weatherdata-fetcher
     restart: unless-stopped
     environment:
       MONGO_HOST: mongodb
       MONGO_PORT: 27017
       MONGO_DATABASE: weatherdata
       MONGO_USERNAME: ${MONGO_APP_USERNAME}
       MONGO_PASSWORD: ${MONGO_APP_PASSWORD}
       OBSERVATION_INTERVAL_SECONDS: 600
       STATION_REFRESH_INTERVAL_SECONDS: 86400
     depends_on:
       mongodb:
         condition: service_healthy
     networks:
       - weatherdata_net
   ```

4. Build and start:
   ```bash
   cd /opt/weatherdata
   docker compose up -d --build fetcher
   ```

### Local Development

1. Create a virtual environment:
   ```bash
   cd /opt/weatherdata/fetcher
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env with your MongoDB credentials
   ```

4. Run the fetcher:
   ```bash
   python -m weatherfetcher
   ```

## Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_HOST` | mongodb | MongoDB hostname |
| `MONGO_PORT` | 27017 | MongoDB port |
| `MONGO_DATABASE` | weatherdata | Database name |
| `MONGO_USERNAME` | (required) | MongoDB username |
| `MONGO_PASSWORD` | (required) | MongoDB password |
| `OBSERVATION_INTERVAL_SECONDS` | 600 | How often to fetch observations (10 min = 6/hour) |
| `STATION_REFRESH_INTERVAL_SECONDS` | 86400 | How often to refresh station list (24 hours) |
| `REQUEST_TIMEOUT_SECONDS` | 30 | HTTP request timeout |
| `MAX_CONCURRENT_REQUESTS` | 20 | Maximum parallel HTTP requests |
| `REQUEST_DELAY_SECONDS` | 0.1 | Delay between requests |
| `MAX_RETRIES` | 3 | Retry count for failed requests |
| `LOG_LEVEL` | INFO | Logging verbosity |

## Environment Canada Data Sources

As of June 2025, Environment Canada changed their data URL structure:

- **Station List (GeoJSON)**: `https://collaboration.cmc.ec.gc.ca/cmc/cmos/public_doc/msc-data/citypage-weather/site_list_en.geojson`
- **Weather Data Base URL**: `https://dd.weather.gc.ca/today/citypage_weather/{PROV}/{HH}/`
- **File naming**: `{timestamp}_MSC_CitypageWeather_{station}_en.xml`
- **Provinces**: AB, BC, MB, NB, NL, NS, NT, NU, ON, PE, QC, SK, YT

The fetcher automatically discovers the latest files by listing the directory structure.

## Monitoring

### View Logs
```bash
docker compose logs -f fetcher
```

### Check Data Counts
```bash
docker compose exec mongodb mongosh -u weatherapp -p 'PASSWORD' \
  --authenticationDatabase weatherdata weatherdata \
  --eval "print('Stations:', db.stations.countDocuments({})); print('Observations:', db.observations.countDocuments({}));"
```

### Query Recent Observations
```bash
docker compose exec mongodb mongosh -u weatherapp -p 'PASSWORD' \
  --authenticationDatabase weatherdata weatherdata \
  --eval "db.observations.find().sort({observed_at: -1}).limit(5).pretty()"
```

## Project Structure

```
fetcher/
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
└── src/
    └── weatherfetcher/
        ├── __init__.py      # Package metadata
        ├── __main__.py      # Entry point
        ├── config.py        # Configuration from env vars
        ├── db.py            # MongoDB operations
        ├── fetcher.py       # Main fetch loop and scheduling
        ├── models.py        # Data models (Station, Observation)
        └── parser.py        # XML parsing logic
```

## Data Growth Estimates

With ~600 active stations and observations every 10 minutes:
- **Per hour**: ~3,600 observations
- **Per day**: ~86,400 observations
- **Per month**: ~2.6 million observations

Estimated storage: ~500 bytes per observation = ~1.3 GB/month uncompressed.

## License

MIT License
