# WeatherData JSON API

A secure, read-only API for publishing Canadian weather observations and warnings from your weatherdata MongoDB database.

## Features

- **Rate Limited**: 60 requests/minute for weather data, 30/minute for station lists
- **Input Validation**: All parameters validated and sanitized
- **CORS Support**: Configurable cross-origin access
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, Cache-Control
- **Read-Only**: Only reads from MongoDB, never writes
- **Health Checks**: Built-in endpoint for load balancers
- **Non-Root Container**: Runs as unprivileged user

## API Endpoints

### GET /api/v1/weather

Get current weather observations and warnings.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `stations` | string | Comma-separated station codes (max 50) |
| `province` | string | Two-letter province code (e.g., MB, ON) |
| `city` | string | City name to search (partial match) |

**Examples:**
```bash
# Get weather for specific stations
curl "https://api.example.com/api/v1/weather?stations=s0000458,s0000492"

# Get all Manitoba stations
curl "https://api.example.com/api/v1/weather?province=MB"

# Search by city name
curl "https://api.example.com/api/v1/weather?city=Brandon"
```

**Response:**
```json
{
  "Brandon": {
    "title": "Brandon - Weather - Environment Canada",
    "city": "Brandon",
    "updated": "2026-01-29T15:05:28Z",
    "temperature": "-30.8°C",
    "condition": "Mainly Sunny",
    "warnings": "",
    "forecast": "mix of sun and cloud. High -18."
  },
  "Winnipeg": {
    "title": "Winnipeg - Weather - Environment Canada",
    "city": "Winnipeg",
    "updated": "2026-01-29T15:05:31Z",
    "temperature": "-21.2°C",
    "condition": "Mostly Cloudy",
    "warnings": "Extreme Cold Warning",
    "forecast": "flurries. High -17. POP 30%"
  }
}
```

### GET /api/v1/stations

List available weather stations.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `province` | string | Two-letter province code to filter by |

**Example:**
```bash
curl "https://api.example.com/api/v1/stations?province=MB"
```

**Response:**
```json
{
  "stations": [
    {"code": "s0000492", "name": "Brandon", "province": "MB"},
    {"code": "s0000193", "name": "Dauphin", "province": "MB"},
    {"code": "s0000391", "name": "Winnipeg", "province": "MB"}
  ]
}
```

### GET /api/v1/warnings

Get all active weather warnings.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `province` | string | Two-letter province code to filter by |

**Response:**
```json
{
  "s0000391": {
    "station": "Winnipeg",
    "warnings": [
      {
        "type": "warning",
        "priority": "high",
        "headline": "Extreme Cold Warning",
        "effective": "2026-01-29T06:00:00",
        "expires": "2026-01-30T12:00:00"
      }
    ]
  }
}
```

### GET /health

Health check for load balancers.

**Response:**
```json
{"status": "healthy", "database": "connected"}
```

## Installation

### 1. Copy API files to your project

```bash
# From your weatherdata project root
cp -r /path/to/weather-api ./weather-api
```

### 2. Add service to docker-compose.yml

Add the following to your existing `docker-compose.yml` under `services:`:

```yaml
  weather-api:
    build:
      context: ./weather-api
      dockerfile: Dockerfile
    container_name: weatherdata-api
    restart: unless-stopped
    
    environment:
      MONGO_HOST: mongodb
      MONGO_PORT: 27017
      MONGO_DATABASE: weatherdata
      MONGO_USERNAME: ${MONGO_APP_USERNAME}
      MONGO_PASSWORD: ${MONGO_APP_PASSWORD}
      API_PORT: 8080
      LOG_LEVEL: INFO
      ENABLE_DOCS: "false"
      # CORS_ORIGINS: "https://yoursite.com"
    
    depends_on:
      mongodb:
        condition: service_healthy
    
    networks:
      - weatherdata_net
    
    ports:
      - "127.0.0.1:8080:8080"
    
    deploy:
      resources:
        limits:
          memory: 256M
    
    security_opt:
      - no-new-privileges:true
    
    read_only: true
    tmpfs:
      - /tmp
```

### 3. Start the API

```bash
docker compose up -d weather-api

# Check logs
docker compose logs -f weather-api
```

### 4. Test it

```bash
# Health check
curl http://localhost:8080/health

# Get weather
curl "http://localhost:8080/api/v1/weather?province=MB"
```

## Production Deployment

### Reverse Proxy with TLS (Recommended)

Use nginx or Caddy to handle TLS termination:

**Caddy (automatic HTTPS):**
```
api.weather.example.com {
    reverse_proxy localhost:8080
}
```

**nginx:**
```nginx
server {
    listen 443 ssl http2;
    server_name api.weather.example.com;
    
    ssl_certificate /etc/letsencrypt/live/api.weather.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.weather.example.com/privkey.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_HOST` | mongodb | MongoDB hostname |
| `MONGO_PORT` | 27017 | MongoDB port |
| `MONGO_DATABASE` | weatherdata | Database name |
| `MONGO_USERNAME` | weatherapp | Database user |
| `MONGO_PASSWORD` | (required) | Database password |
| `API_PORT` | 8080 | Port to listen on |
| `LOG_LEVEL` | INFO | Logging verbosity |
| `ENABLE_DOCS` | false | Enable /docs endpoint |
| `CORS_ORIGINS` | * | Allowed origins (comma-separated) |

### CORS Configuration

For production, restrict CORS to your domains:

```yaml
environment:
  CORS_ORIGINS: "https://weather.example.com,https://app.example.com"
```

### Rate Limits

Default limits (per IP address):
- `/api/v1/weather`: 60 requests/minute
- `/api/v1/stations`: 30 requests/minute
- `/api/v1/warnings`: 30 requests/minute

To modify, edit `main.py` and change the `@limiter.limit()` decorators.

## Security Considerations

1. **Always use TLS** in production (via reverse proxy)
2. **Restrict CORS** to known domains
3. **Firewall**: Only expose port 8080 to your reverse proxy
4. **API Keys**: For additional security, you can add API key authentication (see below)

### Optional: Add API Key Authentication

To add API key validation, modify `main.py`:

```python
from fastapi import Header

API_KEYS = set(os.getenv("API_KEYS", "").split(","))

async def verify_api_key(x_api_key: str = Header(...)):
    if not API_KEYS or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.get("/api/v1/weather")
@limiter.limit("60/minute")
async def get_weather(
    request: Request,
    api_key: str = Depends(verify_api_key),
    # ... rest of parameters
):
```

Then set `API_KEYS=key1,key2,key3` in your environment.

## File Structure

```
weather-api/
├── Dockerfile
├── requirements.txt
├── docker-compose-service.yml  # Snippet to add to main compose
├── README.md
└── src/
    └── weather_api/
        ├── __init__.py
        └── main.py
```

## Troubleshooting

### API returns empty results

```bash
# Check if data exists in MongoDB
docker compose exec mongodb mongosh -u weatherapp \
  -p "$(grep MONGO_APP_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase weatherdata weatherdata \
  --eval "db.stations.countDocuments({active: true})"
```

### Connection refused

```bash
# Check API container is running
docker compose ps weather-api

# Check logs
docker compose logs weather-api --tail 50
```

### Rate limit errors

If you see 429 errors, you've exceeded the rate limit. Wait a minute or increase limits in the code.

## License

MIT License - Same as the main weatherdata project.
