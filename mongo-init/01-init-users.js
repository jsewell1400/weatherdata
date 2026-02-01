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

// Create stations collection with schema validation
// Note: Most fields allow null because Environment Canada data is inconsistent
db.createCollection('stations', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['station_code', 'name_en', 'province', 'coordinates'],
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
                    bsonType: ['string', 'null'],
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
                        elevation_m: { bsonType: ['double', 'null'] }
                    }
                },
                region_en: {
                    bsonType: ['string', 'null'],
                    description: 'Region name in English'
                },
                region_fr: {
                    bsonType: ['string', 'null'],
                    description: 'Region name in French'
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
    },
    validationLevel: 'moderate'
});

// Create observations collection with schema validation
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
                dewpoint_c: { bsonType: ['double', 'null'] },
                pressure_kpa: { bsonType: ['double', 'null'] },
                pressure_tendency: { bsonType: ['string', 'null'] },
                wind_speed_kmh: { bsonType: ['double', 'null'] },
                wind_direction_deg: { bsonType: ['int', 'double', 'null'] },
                wind_direction_text: { bsonType: ['string', 'null'] },
                wind_gust_kmh: { bsonType: ['double', 'null'] },
                wind_chill: { bsonType: ['double', 'int', 'null'] },
                humidex: { bsonType: ['double', 'null'] },
                visibility_km: { bsonType: ['double', 'null'] },
                condition_en: { bsonType: ['string', 'null'] },
                condition_fr: { bsonType: ['string', 'null'] },
                icon_code: { bsonType: ['string', 'null'] }
            }
        }
    },
    validationLevel: 'moderate'
});

// Create warnings collection with schema validation
db.createCollection('warnings', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['station_code', 'event_type', 'priority', 'headline'],
            properties: {
                station_code: {
                    bsonType: 'string',
                    description: 'Reference to stations collection'
                },
                event_type: {
                    bsonType: 'string',
                    description: 'Type: warning, watch, advisory, statement, ended'
                },
                priority: {
                    bsonType: 'string',
                    description: 'Priority: urgent, high, medium, low'
                },
                headline: {
                    bsonType: 'string',
                    description: 'Warning headline text'
                },
                description: {
                    bsonType: ['string', 'null'],
                    description: 'Full warning description'
                },
                effective: {
                    bsonType: ['date', 'null'],
                    description: 'When warning takes effect'
                },
                expires: {
                    bsonType: ['date', 'null'],
                    description: 'When warning expires'
                },
                url: {
                    bsonType: ['string', 'null'],
                    description: 'URL for more information'
                },
                fetched_at: {
                    bsonType: 'date',
                    description: 'When we retrieved this data'
                },
                active: {
                    bsonType: 'bool',
                    description: 'Whether warning is currently active'
                }
            }
        }
    },
    validationLevel: 'moderate'
});

db.createCollection('forecasts', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['station_code', 'issued_at', 'fetched_at', 'periods'],
            properties: {
                station_code: { bsonType: 'string' },
                issued_at: { bsonType: 'date' },
                fetched_at: { bsonType: 'date' },
                periods: {
                    bsonType: 'array',
                    items: {
                        bsonType: 'object',
                        required: ['period_name', 'text_summary'],
                        properties: {
                            period_name: { bsonType: 'string' },           // "Tonight", "Saturday"
                            text_summary: { bsonType: 'string' },          // "Clearing. Low minus 21."
                            abbreviated_summary: { bsonType: ['string', 'null'] }, // "Clear"
                            icon_code: { bsonType: ['string', 'null'] },
                            temperature_c: { bsonType: ['double', 'null'] },
                            temperature_class: { bsonType: ['string', 'null'] }, // "high" or "low"
                            pop_pct: { bsonType: ['int', 'null'] },        // probability of precipitation
                            wind_summary: { bsonType: ['string', 'null'] },
                            humidity_pct: { bsonType: ['double', 'null'] }
                        }
                    }
                }
            }
        }
    }
});

// Create indexes for stations collection
db.stations.createIndex({ "station_code": 1 }, { unique: true, name: "idx_station_code" });
db.stations.createIndex({ "province": 1 }, { name: "idx_province" });

// Create indexes for observations collection
db.observations.createIndex({ "station_code": 1, "observed_at": -1 }, { name: "idx_station_time" });
db.observations.createIndex({ "observed_at": -1 }, { name: "idx_time" });
db.observations.createIndex({ "station_code": 1, "fetched_at": -1 }, { name: "idx_station_fetched" });

// Create indexes for warnings collection
db.warnings.createIndex({ "station_code": 1, "headline": 1, "effective": 1 }, { name: "idx_warning_unique" });
db.warnings.createIndex({ "active": 1, "expires": 1 }, { name: "idx_active_expires" });
db.warnings.createIndex({ "station_code": 1, "active": 1 }, { name: "idx_station_active" });

// Index for latest forecast per station
db.forecasts.createIndex(
    { "station_code": 1, "issued_at": -1 },
    { name: "idx_station_issued" }
);

print('=== MongoDB initialization complete ===');
print('Created user: ' + (process.env.MONGO_APP_USERNAME || 'weatherapp'));
print('Created collections: stations, observations, warnings');
print('Created indexes for all collections');

