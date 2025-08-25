#!/bin/bash

set -e

REPO_URL="$1"
BASE_DIR="$(dirname "$0")/projects_data"
LOG_DIR="$(pwd)/logs"
LOG_FILE="$LOG_DIR/deploy.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp - $level - $message" >> "$LOG_FILE"
    echo "$timestamp - $level - $message"
}

if [ -z "$REPO_URL" ]; then
    log "ERROR" "No repository URL provided"
    echo "Usage: $0 <repository_url>"
    exit 1
fi

REPO_NAME=$(basename -s .git "$REPO_URL")
TARGET_DIR="$BASE_DIR/$REPO_NAME"

log "INFO" "Starting deployment for repository: $REPO_NAME"
log "INFO" "Repository URL: $REPO_URL for $REPO_NAME"
log "INFO" "Target directory: $TARGET_DIR for $REPO_NAME"

mkdir -p "$BASE_DIR"
log "INFO" "Created base directory: $BASE_DIR for $REPO_NAME"

if [ -d "$TARGET_DIR/.git" ]; then
    log "INFO" "Existing repository found for $REPO_NAME, pulling latest changes"
    cd "$TARGET_DIR"
    if git pull >> "$LOG_FILE" 2>&1; then
        log "INFO" "Successfully pulled latest changes for $REPO_NAME"
    else
        log "ERROR" "Failed to pull changes for $REPO_NAME"
        exit 1
    fi
else
    log "INFO" "Cloning repository $REPO_NAME from $REPO_URL"
    if git clone "$REPO_URL" "$TARGET_DIR" >> "$LOG_FILE" 2>&1; then
        log "INFO" "Successfully cloned repository $REPO_NAME"
        cd "$TARGET_DIR"
    else
        log "ERROR" "Failed to clone repository $REPO_NAME"
        exit 1
    fi
fi

log "INFO" "Starting Docker Compose build and deployment for $REPO_NAME"
if docker compose up -d --build >> "$LOG_FILE" 2>&1; then
    log "INFO" "Successfully deployed $REPO_NAME using Docker Compose"
else
    log "ERROR" "Failed to deploy $REPO_NAME using Docker Compose"
    exit 1
fi

log "INFO" "Deployment completed successfully for $REPO_NAME"