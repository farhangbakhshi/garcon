#!/bin/bash

set -euo pipefail

LOG_DIR="$(pwd)/logs"
LOG_FILE="$LOG_DIR/deploy.log"

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp - $level - $message" >> "$LOG_FILE"
    echo "$timestamp - $level - $message"
}

log "INFO" "Setting up Traefik infrastructure"

# Create the web-proxy network if it doesn't exist
if ! docker network ls | grep -q web-proxy; then
    log "INFO" "Creating web-proxy network"
    docker network create web-proxy
    log "INFO" "Created web-proxy network"
else
    log "INFO" "web-proxy network already exists"
fi

# Start Traefik if it's not already running
if ! docker ps | grep -q traefik-garcon; then
    log "INFO" "Starting Traefik container"
    docker compose -f traefik-docker-compose.yml up -d
    log "INFO" "Traefik started successfully"
    log "INFO" "Traefik dashboard available at: http://localhost:8080"
else
    log "INFO" "Traefik container is already running"
fi

log "INFO" "Traefik infrastructure setup completed"
