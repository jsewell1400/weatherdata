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


