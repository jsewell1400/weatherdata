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

