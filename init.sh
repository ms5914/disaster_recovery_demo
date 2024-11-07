#!/bin/bash

# Stop all containers
docker compose down

# Remove all stopped containers
docker rm $(docker ps -a -q) 2>/dev/null || true

# Remove all volumes
docker volume rm $(docker volume ls -q) 2>/dev/null || true

# Remove data directories
rm -rf data

# Recreate directories
mkdir -p data/primary data/backup

# Set permissions
chmod 777 data/primary data/backup

# Initialize empty JSON files
echo "{}" > data/primary/data.json
echo "{}" > data/backup/data.json
chmod 666 data/primary/data.json data/backup/data.json

# Rebuild and start
docker compose up --build
