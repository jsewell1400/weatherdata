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
