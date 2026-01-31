# WeatherData Project: MongoDB + Docker Setup Guide

A complete guide for setting up a MongoDB-backed weather data collection system on Ubuntu Noble, designed for development with production-ready security practices.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Directory Structure](#3-directory-structure)
4. [Docker Compose Configuration](#4-docker-compose-configuration)
5. [Environment and Secrets Management](#5-environment-and-secrets-management)
6. [MongoDB Initialization](#6-mongodb-initialization)
7. [Deployment Steps](#7-deployment-steps)
8. [MongoDB Schema Design](#8-mongodb-schema-design)
9. [Indexing Strategy](#9-indexing-strategy)
10. [Backup Strategy](#10-backup-strategy)
11. [Python Project Structure](#11-python-project-structure)
12. [Operations and Maintenance](#12-operations-and-maintenance)
13. [Production Hardening Checklist](#13-production-hardening-checklist)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Ubuntu Noble VM                        │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │   Python    │    │   MongoDB   │    │   Prometheus    │ │
│  │   Fetcher   │───▶│   (Docker)  │◀───│   (Future)      │ │
│  │  (Docker)   │    │             │    │                 │ │
│  └─────────────┘    └─────────────┘    └─────────────────┘ │
│         │                  │                    │          │
│         ▼                  ▼                    ▼          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Docker Network: weatherdata_net        │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                               │
│                            ▼                               │
│                   /var/lib/mongodb                         │
│                   (Persistent Data)                        │
└─────────────────────────────────────────────────────────────┘
```

**Components:**
- **MongoDB**: Stores normalized weather data from all Canadian stations
- **Python Fetcher**: Polls Environment Canada XML feeds, normalizes data, writes to MongoDB
- **Prometheus Exporter**: (Future) Exposes weather metrics for scraping
- **Prometheus**: (Future) Scrapes and stores time-series metrics

---

## 2. Prerequisites

### 2.1 Install Docker Engine

```bash
# Update package index
sudo apt update

# Install prerequisites
sudo apt install -y ca-certificates curl

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine and Compose plugin
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to docker group (avoids needing sudo)
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker

# Verify installation
docker --version
docker compose version
```

### 2.2 Create MongoDB Data Directory

```bash
# Create conventional data directory
sudo mkdir -p /var/lib/mongodb

# Set ownership (Docker will map this; we'll use a fixed UID)
sudo chown -R 999:999 /var/lib/mongodb
```

> **Note**: MongoDB's official Docker image runs as UID 999. Setting ownership now prevents permission issues.

---

## 3. Directory Structure

```bash
# Create project directory
sudo mkdir -p /opt/weatherdata
sudo chown $USER:$USER /opt/weatherdata
cd /opt/weatherdata

# Create directory structure
mkdir -p {scripts,mongo-init,backups,fetcher,exporter}
```

**Resulting structure:**

```
/opt/weatherdata/
├── docker-compose.yml      # Main compose file
├── .env                    # Environment variables (secrets)
├── .env.example            # Template for .env (safe to commit)
├── mongo-init/
│   └── 01-init-users.js    # MongoDB initialization script
├── scripts/
│   └── backup.sh           # Backup script
├── backups/                # Backup storage
├── fetcher/                # Python fetcher project
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
└── exporter/               # Prometheus exporter (future)
```

---

## 4. Docker Compose Configuration

Create `/opt/weatherdata/docker-compose.yml`:

```yaml
name: weatherdata

services:
  # ============================================
  # MongoDB - Primary data store
  # ============================================
  mongodb:
    image: mongo:7
    container_name: weatherdata-mongodb
    restart: unless-stopped
    
    # Security: don't run as root inside container
    user: "999:999"
    
    environment:
      # Root credentials (only used for initial setup)
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USERNAME}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD}
      MONGO_INITDB_DATABASE: weatherdata
    
    volumes:
      # Persistent data storage
      - /var/lib/mongodb:/data/db
      
      # Initialization scripts (run once on first start)
      - ./mongo-init:/docker-entrypoint-initdb.d:ro
    
    networks:
      - weatherdata_net
    
    # Only expose to localhost - not to the world
    ports:
      - "127.0.0.1:27017:27017"
    
    # Health check for dependent services
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    
    # Resource limits (adjust based on your needs)
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
    
    # Logging configuration
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # ============================================
  # Python Weather Fetcher (uncomment when ready)
  # ============================================
  # fetcher:
  #   build:
  #     context: ./fetcher
  #     dockerfile: Dockerfile
  #   container_name: weatherdata-fetcher
  #   restart: unless-stopped
  #   
  #   environment:
  #     MONGO_HOST: mongodb
  #     MONGO_PORT: 27017
  #     MONGO_DATABASE: weatherdata
  #     MONGO_USERNAME: ${MONGO_APP_USERNAME}
  #     MONGO_PASSWORD: ${MONGO_APP_PASSWORD}
  #     POLL_INTERVAL_SECONDS: 600
  #   
  #   depends_on:
  #     mongodb:
  #       condition: service_healthy
  #   
  #   networks:
  #     - weatherdata_net
  #   
  #   logging:
  #     driver: "json-file"
  #     options:
  #       max-size: "10m"
  #       max-file: "3"

  # ============================================
  # Prometheus (uncomment when ready)
  # ============================================
  # prometheus:
  #   image: prom/prometheus:latest
  #   container_name: weatherdata-prometheus
  #   restart: unless-stopped
  #   
  #   volumes:
  #     - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
  #     - prometheus_data:/prometheus
  #   
  #   command:
  #     - '--config.file=/etc/prometheus/prometheus.yml'
  #     - '--storage.tsdb.path=/prometheus'
  #     - '--storage.tsdb.retention.time=90d'
  #     - '--web.enable-lifecycle'
  #   
  #   ports:
  #     - "127.0.0.1:9090:9090"
  #   
  #   networks:
  #     - weatherdata_net
  #   
  #   logging:
  #     driver: "json-file"
  #     options:
  #       max-size: "10m"
  #       max-file: "3"

networks:
  weatherdata_net:
    driver: bridge
    # Internal network - containers can reach each other by service name

# Uncomment when Prometheus is enabled
# volumes:
#   prometheus_data:
```

**Key security features:**

| Feature | Purpose |
|---------|---------|
| `127.0.0.1:27017:27017` | MongoDB only accessible from localhost, not internet |
| `user: "999:999"` | Runs as non-root user inside container |
| Authentication enabled | Requires username/password |
| Named network | Isolates services; containers communicate by name |
| Resource limits | Prevents MongoDB from consuming all RAM |
| Health checks | Ensures dependent services wait for MongoDB |

---

## 5. Environment and Secrets Management

### 5.1 Create `.env.example` (safe to commit to git)

```bash
cat > /opt/weatherdata/.env.example << 'EOF'
# MongoDB Root Credentials (admin)
# Used only for initial setup and administrative tasks
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=CHANGE_ME_STRONG_PASSWORD

# MongoDB Application Credentials
# Used by the Python fetcher/exporter
MONGO_APP_USERNAME=weatherapp
MONGO_APP_PASSWORD=CHANGE_ME_ANOTHER_STRONG_PASSWORD
EOF
```

### 5.2 Create actual `.env` file with real secrets

```bash
# Generate strong passwords
generate_password() {
    openssl rand -base64 24 | tr -d '/+=' | head -c 24
}

cat > /opt/weatherdata/.env << EOF
# MongoDB Root Credentials
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=$(generate_password)

# MongoDB Application Credentials
MONGO_APP_USERNAME=weatherapp
MONGO_APP_PASSWORD=$(generate_password)
EOF

# Secure the file
chmod 600 /opt/weatherdata/.env

# Display credentials (save these somewhere safe!)
echo "=== SAVE THESE CREDENTIALS ==="
cat /opt/weatherdata/.env
echo "=============================="
```

### 5.3 Add `.env` to `.gitignore`

```bash
cat > /opt/weatherdata/.gitignore << 'EOF'
# Never commit secrets
.env

# Backup files contain data
backups/

# Python
__pycache__/
*.pyc
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
EOF
```

---

## 6. MongoDB Initialization

This script runs **once** on first container start. It creates an application user with limited privileges.

Create `/opt/weatherdata/mongo-init/01-init-users.js`:

```javascript
// This script runs automatically on first MongoDB start
// It creates an application user with appropriate permissions

// Switch to the weatherdata database
db = db.getSiblingDB('weatherdata');

// Create application user with readWrite access to weatherdata only
// This follows principle of least privilege
db.createUser({
    user: process.env.MONGO_APP_USERNAME || 'weatherapp',
    pwd: process.env.MONGO_APP_PASSWORD || 'changeme',
    roles: [
        {
            role: 'readWrite',
            db: 'weatherdata'
        }
    ]
});

// Create initial collections with schema validation (optional but recommended)
db.createCollection('stations', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['station_code', 'name_en', 'name_fr', 'province', 'coordinates'],
            properties: {
                station_code: {
                    bsonType: 'string',
                    description: 'Environment Canada station identifier'
                },
                name_en: {
                    bsonType: 'string',
                    description: 'Station name in English'
                },
                name_fr: {
                    bsonType: 'string',
                    description: 'Station name in French'
                },
                province: {
                    bsonType: 'string',
                    description: 'Province/territory code'
                },
                coordinates: {
                    bsonType: 'object',
                    required: ['lat', 'lon'],
                    properties: {
                        lat: { bsonType: 'double' },
                        lon: { bsonType: 'double' },
                        elevation_m: { bsonType: 'double' }
                    }
                },
                active: {
                    bsonType: 'bool',
                    description: 'Whether station is currently reporting'
                },
                updated_at: {
                    bsonType: 'date'
                }
            }
        }
    }
});

db.createCollection('observations', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['station_code', 'observed_at', 'fetched_at'],
            properties: {
                station_code: {
                    bsonType: 'string',
                    description: 'Reference to stations collection'
                },
                observed_at: {
                    bsonType: 'date',
                    description: 'When the observation was recorded by Environment Canada'
                },
                fetched_at: {
                    bsonType: 'date',
                    description: 'When we retrieved this data'
                },
                temperature_c: { bsonType: ['double', 'null'] },
                humidity_pct: { bsonType: ['double', 'null'] },
                pressure_kpa: { bsonType: ['double', 'null'] },
                wind_speed_kmh: { bsonType: ['double', 'null'] },
                wind_direction_deg: { bsonType: ['int', 'null'] },
                wind_gust_kmh: { bsonType: ['double', 'null'] },
                visibility_km: { bsonType: ['double', 'null'] },
                condition_en: { bsonType: ['string', 'null'] },
                condition_fr: { bsonType: ['string', 'null'] },
                icon_code: { bsonType: ['string', 'null'] }
            }
        }
    }
});

print('=== MongoDB initialization complete ===');
print('Created user: ' + (process.env.MONGO_APP_USERNAME || 'weatherapp'));
print('Created collections: stations, observations');
```

**Note**: The application password is read from environment variables passed by Docker Compose. We need to modify the init script to receive these:

Update `docker-compose.yml` MongoDB service to pass app credentials:

```yaml
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USERNAME}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD}
      MONGO_INITDB_DATABASE: weatherdata
      # Pass app credentials for init script
      MONGO_APP_USERNAME: ${MONGO_APP_USERNAME}
      MONGO_APP_PASSWORD: ${MONGO_APP_PASSWORD}
```

---

## 7. Deployment Steps

### 7.1 Initial Deployment

```bash
cd /opt/weatherdata

# Verify your configuration
cat .env  # Confirm credentials are set
cat docker-compose.yml  # Review compose file

# Start MongoDB
docker compose up -d mongodb

# Watch the logs for initialization
docker compose logs -f mongodb

# You should see:
# - "MongoDB starting"
# - "Creating user..." (from init script)
# - "MongoDB init process complete; ready for start up"
```

### 7.2 Verify MongoDB is Running

```bash
# Check container status
docker compose ps

# Test connection with root user
docker compose exec mongodb mongosh \
  --username admin \
  --password "$(grep MONGO_ROOT_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase admin \
  --eval "db.adminCommand('ping')"

# Test application user
docker compose exec mongodb mongosh \
  --username weatherapp \
  --password "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase weatherdata \
  weatherdata \
  --eval "db.getCollectionNames()"

# Should output: [ 'observations', 'stations' ]
```

### 7.3 Useful Commands

```bash
# Stop all services
docker compose down

# Stop and remove volumes (DELETES ALL DATA)
docker compose down -v

# View logs
docker compose logs -f mongodb

# Enter MongoDB shell as admin
docker compose exec mongodb mongosh -u admin -p "$(grep MONGO_ROOT_PASSWORD .env | cut -d= -f2)" --authenticationDatabase admin

# Enter MongoDB shell as app user
docker compose exec mongodb mongosh -u weatherapp -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" --authenticationDatabase weatherdata weatherdata

# Restart MongoDB
docker compose restart mongodb

# Update MongoDB image
docker compose pull mongodb
docker compose up -d mongodb
```

---

## 8. MongoDB Schema Design

### 8.1 Collections Overview

| Collection | Purpose | Growth Rate |
|------------|---------|-------------|
| `stations` | Weather station metadata | ~600 docs, rarely changes |
| `observations` | Weather readings | ~600 × 6/hour = 3,600 docs/hour |

### 8.2 Sample Documents

**stations collection:**

```javascript
{
  "_id": ObjectId("..."),
  "station_code": "s0000458",
  "name_en": "Toronto Pearson Int'l Airport",
  "name_fr": "Aéroport int'l Toronto Pearson",
  "province": "ON",
  "coordinates": {
    "lat": 43.6777,
    "lon": -79.6248,
    "elevation_m": 173.0
  },
  "region_en": "City of Toronto",
  "region_fr": "Ville de Toronto",
  "active": true,
  "updated_at": ISODate("2025-01-15T12:00:00Z")
}
```

**observations collection:**

```javascript
{
  "_id": ObjectId("..."),
  "station_code": "s0000458",
  "observed_at": ISODate("2025-01-15T12:00:00Z"),
  "fetched_at": ISODate("2025-01-15T12:02:34Z"),
  "temperature_c": -5.2,
  "humidity_pct": 78.0,
  "pressure_kpa": 101.2,
  "wind_speed_kmh": 15.0,
  "wind_direction_deg": 270,
  "wind_gust_kmh": 25.0,
  "visibility_km": 24.0,
  "condition_en": "Light Snow",
  "condition_fr": "Faible neige",
  "icon_code": "16"
}
```

### 8.3 Why This Schema?

1. **Separate stations and observations**: Avoids duplicating station metadata with every reading
2. **Timestamps are ISODate**: Enables time-range queries and proper sorting
3. **Nullable fields**: Weather stations don't always report all metrics
4. **Both languages stored**: Query in either language without re-fetching

---

## 9. Indexing Strategy

Create indexes for your query patterns. Run this in the MongoDB shell:

```javascript
use weatherdata;

// === stations collection ===

// Primary lookup by station code
db.stations.createIndex(
  { "station_code": 1 },
  { unique: true, name: "idx_station_code" }
);

// Find stations by province
db.stations.createIndex(
  { "province": 1 },
  { name: "idx_province" }
);

// Geospatial queries (find stations near a location)
db.stations.createIndex(
  { "coordinates": "2dsphere" },
  { name: "idx_geo" }
);

// === observations collection ===

// Primary query pattern: latest observation for a station
db.observations.createIndex(
  { "station_code": 1, "observed_at": -1 },
  { name: "idx_station_time" }
);

// Time-range queries across all stations
db.observations.createIndex(
  { "observed_at": -1 },
  { name: "idx_time" }
);

// Compound index for Prometheus exporter queries
// "Give me the latest observation for each station"
db.observations.createIndex(
  { "station_code": 1, "fetched_at": -1 },
  { name: "idx_station_fetched" }
);

// Verify indexes
db.stations.getIndexes();
db.observations.getIndexes();
```

**Save this as a script** at `/opt/weatherdata/scripts/create-indexes.js` for reproducibility.

---

## 10. Backup Strategy

### 10.1 Backup Script

Create `/opt/weatherdata/scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Configuration
BACKUP_DIR="/opt/weatherdata/backups"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="weatherdata_${DATE}"

# Load credentials
source /opt/weatherdata/.env

echo "Starting backup: ${BACKUP_NAME}"

# Create backup using mongodump inside container
docker compose -f /opt/weatherdata/docker-compose.yml exec -T mongodb mongodump \
  --username="${MONGO_ROOT_USERNAME}" \
  --password="${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase=admin \
  --db=weatherdata \
  --archive \
  --gzip \
  > "${BACKUP_DIR}/${BACKUP_NAME}.archive.gz"

# Verify backup was created and has content
if [[ -s "${BACKUP_DIR}/${BACKUP_NAME}.archive.gz" ]]; then
  SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.archive.gz" | cut -f1)
  echo "Backup successful: ${BACKUP_NAME}.archive.gz (${SIZE})"
else
  echo "ERROR: Backup file is empty!"
  rm -f "${BACKUP_DIR}/${BACKUP_NAME}.archive.gz"
  exit 1
fi

# Clean up old backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "weatherdata_*.archive.gz" -type f -mtime +${RETENTION_DAYS} -delete

# List current backups
echo "Current backups:"
ls -lh "${BACKUP_DIR}"/*.archive.gz 2>/dev/null || echo "No backups found"
```

```bash
# Make executable
chmod +x /opt/weatherdata/scripts/backup.sh

# Test it
/opt/weatherdata/scripts/backup.sh
```

### 10.2 Schedule Daily Backups (Cron)

```bash
# Edit crontab
crontab -e

# Add this line (runs at 2:00 AM daily)
0 2 * * * /opt/weatherdata/scripts/backup.sh >> /opt/weatherdata/backups/backup.log 2>&1
```

### 10.3 Restore from Backup

```bash
# Restore a backup
BACKUP_FILE="/opt/weatherdata/backups/weatherdata_20250115_020000.archive.gz"

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

---

## 11. Python Project Structure

Recommended structure for your fetcher:

```
/opt/weatherdata/fetcher/
├── Dockerfile
├── requirements.txt
├── pyproject.toml          # Modern Python packaging
├── src/
│   └── weatherfetcher/
│       ├── __init__.py
│       ├── __main__.py     # Entry point
│       ├── config.py       # Configuration from env vars
│       ├── db.py           # MongoDB connection handling
│       ├── fetcher.py      # Main fetch loop
│       ├── parser.py       # XML parsing logic
│       └── models.py       # Data classes for Station, Observation
└── tests/
    └── ...
```

### 11.1 Sample Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

CMD ["python", "-m", "weatherfetcher"]
```

### 11.2 Sample requirements.txt

```
pymongo>=4.6.0
requests>=2.31.0
lxml>=5.0.0
python-dateutil>=2.8.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
structlog>=24.1.0
```

### 11.3 Sample config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Configuration loaded from environment variables."""
    
    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    mongo_database: str = "weatherdata"
    mongo_username: str
    mongo_password: str
    
    poll_interval_seconds: int = 600
    
    # Environment Canada base URL
    ec_base_url: str = "https://dd.weather.gc.ca/citypage_weather/xml"
    
    class Config:
        env_file = ".env"
        
    @property
    def mongo_uri(self) -> str:
        return (
            f"mongodb://{self.mongo_username}:{self.mongo_password}"
            f"@{self.mongo_host}:{self.mongo_port}/{self.mongo_database}"
            f"?authSource={self.mongo_database}"
        )

settings = Settings()
```

---

## 12. Operations and Maintenance

### 12.1 Monitoring MongoDB

```bash
# Quick health check
docker compose exec mongodb mongosh -u admin -p "$(grep MONGO_ROOT_PASSWORD .env | cut -d= -f2)" --authenticationDatabase admin --eval "db.serverStatus().ok"

# Database statistics
docker compose exec mongodb mongosh -u weatherapp -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" --authenticationDatabase weatherdata weatherdata --eval "db.stats()"

# Collection document counts
docker compose exec mongodb mongosh -u weatherapp -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" --authenticationDatabase weatherdata weatherdata --eval "
  print('Stations:', db.stations.countDocuments({}));
  print('Observations:', db.observations.countDocuments({}));
"

# Index usage statistics
docker compose exec mongodb mongosh -u weatherapp -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" --authenticationDatabase weatherdata weatherdata --eval "db.observations.aggregate([{\$indexStats:{}}])"
```

### 12.2 Log Monitoring

```bash
# Follow MongoDB logs
docker compose logs -f mongodb

# Check for slow queries (if enabled)
docker compose exec mongodb mongosh -u admin -p "$(grep MONGO_ROOT_PASSWORD .env | cut -d= -f2)" --authenticationDatabase admin --eval "db.adminCommand({getLog:'global'})" | grep -i slow
```

### 12.3 Updating MongoDB

```bash
cd /opt/weatherdata

# Pull latest image
docker compose pull mongodb

# Recreate container with new image (data preserved)
docker compose up -d mongodb

# Verify version
docker compose exec mongodb mongosh --eval "db.version()"
```

---

## 13. Production Hardening Checklist

When deploying to Digital Ocean or similar:

### Network Security

- [ ] **Firewall**: Only allow SSH (22) and your app ports; block 27017 from internet
- [ ] **VPC**: Use Digital Ocean's VPC for private networking between droplets
- [ ] **SSH**: Disable password auth, use SSH keys only
- [ ] Change `127.0.0.1:27017:27017` to just internal network if needed

### MongoDB Security

- [ ] **Strong passwords**: Ensure production passwords are 24+ characters
- [ ] **TLS/SSL**: Enable TLS for MongoDB connections (add cert configuration)
- [ ] **IP allowlist**: Bind MongoDB to specific internal IPs only
- [ ] **Authentication**: Already enabled ✓
- [ ] **Authorization**: App user has minimal privileges ✓

### Application Security

- [ ] **Secrets management**: Consider HashiCorp Vault or DO's secrets for production
- [ ] **Environment isolation**: Separate credentials for dev/staging/prod
- [ ] **Log sanitization**: Ensure passwords aren't logged

### Operations

- [ ] **Automated backups**: Cron job configured ✓
- [ ] **Off-site backups**: Copy backups to Digital Ocean Spaces or S3
- [ ] **Monitoring**: Set up alerts for disk space, memory, container health
- [ ] **Log aggregation**: Consider shipping logs to a central location

### Docker Security

- [ ] **Non-root user**: Configured ✓
- [ ] **Resource limits**: Configured ✓
- [ ] **Read-only filesystem**: Consider adding `read_only: true` where possible
- [ ] **No privileged mode**: Don't use `privileged: true`
- [ ] **Regular image updates**: Schedule monthly image pulls

### Sample production docker-compose additions:

```yaml
services:
  mongodb:
    # ... existing config ...
    
    # Production additions:
    security_opt:
      - no-new-privileges:true
    
    # If using TLS:
    command: ["mongod", "--tlsMode", "requireTLS", "--tlsCertificateKeyFile", "/etc/ssl/mongodb.pem"]
    volumes:
      - /var/lib/mongodb:/data/db
      - ./certs/mongodb.pem:/etc/ssl/mongodb.pem:ro
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start stack | `docker compose up -d` |
| Stop stack | `docker compose down` |
| View logs | `docker compose logs -f mongodb` |
| MongoDB shell (admin) | `docker compose exec mongodb mongosh -u admin -p 'PASSWORD' --authenticationDatabase admin` |
| MongoDB shell (app) | `docker compose exec mongodb mongosh -u weatherapp -p 'PASSWORD' --authenticationDatabase weatherdata weatherdata` |
| Manual backup | `/opt/weatherdata/scripts/backup.sh` |
| Update MongoDB | `docker compose pull && docker compose up -d` |
| Check disk usage | `du -sh /var/lib/mongodb` |

---

## Environment Canada Data Notes

- **XML Feed URL Pattern**: `https://dd.weather.gc.ca/citypage_weather/xml/{province}/{station_code}_{lang}.xml`
- **Languages**: `e` (English), `f` (French)
- **Province codes**: AB, BC, MB, NB, NL, NS, NT, NU, ON, PE, QC, SK, YT
- **Station list**: Available at `https://dd.weather.gc.ca/citypage_weather/xml/siteList.xml`

Example URL: `https://dd.weather.gc.ca/citypage_weather/xml/ON/s0000458_e.xml` (Toronto)

---

*Guide created for the weatherdata project. Last updated: January 2025*
