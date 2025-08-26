#!/bin/bash

set -e

REPO_URL="$1"
BASE_DIR="$(dirname "$0")/projects_data"
LOG_DIR="$(pwd)/logs"
LOG_FILE="$LOG_DIR/deploy.log"
SCRIPT_DIR="$(dirname "$0")"

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

# Ensure Traefik infrastructure is set up
log "INFO" "Ensuring Traefik infrastructure is ready"
if bash "$SCRIPT_DIR/setup-traefik.sh" >> "$LOG_FILE" 2>&1; then
    log "INFO" "Traefik infrastructure is ready"
else
    log "ERROR" "Failed to setup Traefik infrastructure"
    exit 1
fi

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
elif [ -d "$TARGET_DIR" ]; then
    log "WARNING" "Directory $TARGET_DIR exists but is not a git repository, removing it"
    if rm -rf "$TARGET_DIR" >> "$LOG_FILE" 2>&1; then
        log "INFO" "Removed existing non-git directory for $REPO_NAME"
    else
        log "ERROR" "Failed to remove existing directory for $REPO_NAME"
        exit 1
    fi
    
    log "INFO" "Cloning repository $REPO_NAME from $REPO_URL"
    if git clone "$REPO_URL" "$TARGET_DIR" >> "$LOG_FILE" 2>&1; then
        log "INFO" "Successfully cloned repository $REPO_NAME"
        cd "$TARGET_DIR"
    else
        log "ERROR" "Failed to clone repository $REPO_NAME"
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

# Check if docker-compose.yml exists and modify it for Traefik
COMPOSE_FILE="$TARGET_DIR/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
    log "INFO" "Found docker-compose.yml, modifying for Traefik integration"
    
    # Use Python to modify the compose file
    PYTHON_EXEC="python3" # Default to system python
    if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
        PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python"
    elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
        PYTHON_EXEC="$SCRIPT_DIR/venv/bin/python"
    fi

    if "$PYTHON_EXEC" -c "
import sys
sys.path.append('$SCRIPT_DIR')
from app.traefik_utils import DockerComposeModifier
modifier = DockerComposeModifier('$COMPOSE_FILE', '$REPO_NAME')
success = modifier.modify_compose_file()
sys.exit(0 if success else 1)
" >> "$LOG_FILE" 2>&1; then
        log "INFO" "Successfully modified docker-compose.yml for Traefik"
    else
        log "ERROR" "Failed to modify docker-compose.yml for Traefik"
        exit 1
    fi
else
    log "WARNING" "No docker-compose.yml found in repository $REPO_NAME"
    log "INFO" "Skipping Traefik integration for $REPO_NAME"
fi

log "INFO" "Starting Docker Compose build and deployment for $REPO_NAME"

# Stop any existing containers for this project first
log "INFO" "Stopping any existing containers for $REPO_NAME"
if docker compose down >> "$LOG_FILE" 2>&1; then
    log "INFO" "Stopped existing containers for $REPO_NAME"
else
    log "WARNING" "No existing containers to stop for $REPO_NAME"
fi

if docker compose up -d --build >> "$LOG_FILE" 2>&1; then
    log "INFO" "Successfully deployed $REPO_NAME using Docker Compose"
    
    # Get the container ID of the first service
    CONTAINER_ID=$(docker compose ps -q | head -n 1)
    if [ -n "$CONTAINER_ID" ]; then
        log "INFO" "Retrieved container ID: $CONTAINER_ID"
        # Echo the container ID so it can be captured by the calling script
        echo "CONTAINER_ID:$CONTAINER_ID"
    else
        log "WARNING" "Could not retrieve container ID for $REPO_NAME"
    fi
else
    log "ERROR" "Failed to deploy $REPO_NAME using Docker Compose"
    exit 1
fi

log "INFO" "Deployment completed successfully for $REPO_NAME"