#!/bin/bash

# Enhanced error handling with strict mode and trap functions
set -euo pipefail
IFS=$'\n\t'

REPO_URL="$1"
DEPLOYMENT_TYPE="${2:-blue-green}"  # Default to blue-green deployment
BASE_DIR="$(dirname "$0")/projects_data"
LOG_DIR="$(pwd)/logs"
LOG_FILE="$LOG_DIR/deploy.log"
SCRIPT_DIR="$(dirname "$0")"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Enhanced error handling functions
error_exit() {
    local line_no=$1
    local error_code=${2:-1}
    log "ERROR" "Simple deployment script failed at line $line_no with exit code $error_code"
    exit "$error_code"
}

# Set up error trap
trap 'error_exit $LINENO $?' ERR
trap 'log "WARNING" "Simple deployment script interrupted by signal"; exit 130' INT TERM

# Enhanced logging function with better output handling
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_line="$timestamp - $level - $message"
    echo "$log_line" >> "$LOG_FILE"
    echo "$log_line" >&2  # Output to stderr to avoid interfering with return values
}

# Function to capture and log command output
run_with_logging() {
    local description="$1"
    shift
    local command="$@"
    
    log "INFO" "Executing: $description"
    log "DEBUG" "Command: $command"
    
    if output=$($command 2>&1); then
        log "INFO" "$description completed successfully"
        echo "$output" >> "$LOG_FILE"
        return 0
    else
        local exit_code=$?
        log "ERROR" "$description failed with exit code $exit_code"
        echo "$output" >> "$LOG_FILE"
        return $exit_code
    fi
}

if [ -z "$REPO_URL" ]; then
    log "ERROR" "No repository URL provided"
    echo "Usage: $0 <repository_url> [deployment_type]"
    echo "Deployment types: blue-green (default), simple"
    exit 1
fi

REPO_NAME=$(basename -s .git "$REPO_URL")
TARGET_DIR="$BASE_DIR/$REPO_NAME"

log "INFO" "Starting deployment for repository: $REPO_NAME"
log "INFO" "Repository URL: $REPO_URL"
log "INFO" "Target directory: $TARGET_DIR"
log "INFO" "Deployment type: $DEPLOYMENT_TYPE"

# If blue-green deployment is requested, delegate to the specialized script
if [ "$DEPLOYMENT_TYPE" = "blue-green" ]; then
    log "INFO" "Delegating to blue-green deployment script"
    exec "$SCRIPT_DIR/blue_green_deploy.sh" "$REPO_URL"
fi

# Ensure Traefik infrastructure is set up
log "INFO" "Ensuring Traefik infrastructure is ready"
if run_with_logging "Traefik infrastructure setup" bash "$SCRIPT_DIR/setup-traefik.sh"; then
    log "INFO" "Traefik infrastructure is ready"
else
    log "ERROR" "Failed to setup Traefik infrastructure"
    exit 1
fi

mkdir -p "$BASE_DIR"
log "INFO" "Created base directory: $BASE_DIR"

if [ -d "$TARGET_DIR/.git" ]; then
    log "INFO" "Existing repository found, pulling latest changes"
    cd "$TARGET_DIR"
    if run_with_logging "Git pull operation" git pull; then
        log "INFO" "Successfully pulled latest changes"
    else
        log "ERROR" "Failed to pull changes"
        exit 1
    fi
elif [ -d "$TARGET_DIR" ]; then
    log "WARNING" "Directory exists but is not a git repository, removing it"
    if run_with_logging "Directory cleanup" rm -rf "$TARGET_DIR"; then
        log "INFO" "Removed existing non-git directory"
    else
        log "ERROR" "Failed to remove existing directory"
        exit 1
    fi
    
    log "INFO" "Cloning repository from $REPO_URL"
    if run_with_logging "Git clone operation" git clone "$REPO_URL" "$TARGET_DIR"; then
        log "INFO" "Successfully cloned repository"
        cd "$TARGET_DIR"
    else
        log "ERROR" "Failed to clone repository"
        exit 1
    fi
else
    log "INFO" "Cloning repository from $REPO_URL"
    if run_with_logging "Git clone operation" git clone "$REPO_URL" "$TARGET_DIR"; then
        log "INFO" "Successfully cloned repository"
        cd "$TARGET_DIR"
    else
        log "ERROR" "Failed to clone repository"
        exit 1
    fi
fi

# Check if docker-compose.yml or docker-compose.yaml exists and modify it for Traefik
COMPOSE_FILE=""
if [ -f "$TARGET_DIR/docker-compose.yml" ]; then
    COMPOSE_FILE="$TARGET_DIR/docker-compose.yml"
    log "INFO" "Found docker-compose.yml, modifying for Traefik integration"
elif [ -f "$TARGET_DIR/docker-compose.yaml" ]; then
    COMPOSE_FILE="$TARGET_DIR/docker-compose.yaml"
    log "INFO" "Found docker-compose.yaml, modifying for Traefik integration"
fi

if [ -n "$COMPOSE_FILE" ]; then
    # Use Python to modify the compose file
    PYTHON_EXEC="python3" # Default to system python
    if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
        PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python"
    elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
        PYTHON_EXEC="$SCRIPT_DIR/venv/bin/python"
    fi

    if run_with_logging "Docker Compose Traefik modification" "$PYTHON_EXEC" -c "
import sys
sys.path.append('$SCRIPT_DIR')
from app.traefik_utils import DockerComposeModifier
modifier = DockerComposeModifier('$COMPOSE_FILE', '$REPO_NAME')
success = modifier.modify_compose_file()
sys.exit(0 if success else 1)
"; then
        log "INFO" "Successfully modified docker-compose file for Traefik"
    else
        log "ERROR" "Failed to modify docker-compose file for Traefik"
        exit 1
    fi
else
    log "WARNING" "No docker-compose.yml or docker-compose.yaml found in repository $REPO_NAME"
    log "INFO" "Skipping Traefik integration for $REPO_NAME"
    exit 0
fi

log "INFO" "Starting simple Docker Compose deployment for $REPO_NAME (non-blue-green)"

# Stop any existing containers for this project first
log "INFO" "Stopping any existing containers for $REPO_NAME"
if run_with_logging "Docker Compose down" docker compose down; then
    log "INFO" "Stopped existing containers"
else
    log "WARNING" "No existing containers to stop or failed to stop"
fi

if run_with_logging "Docker Compose build and deploy" docker compose up -d --build; then
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

log "INFO" "Simple deployment completed successfully for $REPO_NAME"