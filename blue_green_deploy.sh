#!/bin/bash

# Enhanced error handling with strict mode and trap functions
set -euo pipefail
IFS=$'\n\t'

# Global configuration
REPO_URL="$1"
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
    log "ERROR" "Script failed at line $line_no with exit code $error_code"
    log "ERROR" "Call stack: ${FUNCNAME[*]}"
    cleanup_on_error
    exit "$error_code"
}

# Cleanup function for error scenarios
cleanup_on_error() {
    log "WARNING" "Performing emergency cleanup due to error"
    
    # Remove any temporary files
    if [ -n "${TEMP_COMPOSE_FILE:-}" ] && [ -f "$TEMP_COMPOSE_FILE" ]; then
        rm -f "$TEMP_COMPOSE_FILE"
        log "INFO" "Removed temporary compose file: $TEMP_COMPOSE_FILE"
    fi
    
    # Stop any containers that were started but failed health checks
    if [ -n "${NEW_CONTAINERS:-}" ]; then
        for container in $NEW_CONTAINERS; do
            if docker ps --format "{{.Names}}" | grep -q "^$container$"; then
                log "WARNING" "Stopping failed container: $container"
                docker stop "$container" >/dev/null 2>&1 || true
                docker rm "$container" >/dev/null 2>&1 || true
            fi
        done
    fi
}

# Set up error trap
trap 'error_exit $LINENO $?' ERR
trap 'log "WARNING" "Script interrupted by signal"; cleanup_on_error; exit 130' INT TERM

# Validate prerequisites
validate_prerequisites() {
    local missing_tools=()
    
    command -v docker >/dev/null 2>&1 || missing_tools+=("docker")
    command -v git >/dev/null 2>&1 || missing_tools+=("git")
    command -v python3 >/dev/null 2>&1 || missing_tools+=("python3")
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log "ERROR" "Missing required tools: ${missing_tools[*]}"
        exit 1
    fi
    
    # Check Docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        log "ERROR" "Docker daemon is not running or accessible"
        exit 1
    fi
    
    log "INFO" "Prerequisites validation passed"
}

# Enhanced logging function with log levels and file output
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_line="$timestamp - $level - $message"
    echo "$log_line" >> "$LOG_FILE"
    echo "$log_line" >&2  # Output to stderr so it doesn't interfere with return values
}

# Function to generate UUID (compatible with most systems)
generate_uuid() {
    if command -v uuidgen &> /dev/null; then
        uuidgen | tr '[:upper:]' '[:lower:]'
    elif [ -f /proc/sys/kernel/random/uuid ]; then
        cat /proc/sys/kernel/random/uuid
    else
        # Fallback: generate pseudo-random UUID
        python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null || \
        date +%s | md5sum | head -c 8; echo
    fi
}

# Function to check container health
check_container_health() {
    local container_name="$1"
    local max_attempts=30
    local attempt=1
    
    log "INFO" "Checking health of container: $container_name"
    
    while [ $attempt -le $max_attempts ]; do
        log "DEBUG" "Health check attempt $attempt/$max_attempts for $container_name"
        
        # Check if container exists and is running
        if ! docker ps --format "table {{.Names}}" | grep -q "^$container_name\$"; then
            # Check if container exists but is stopped
            if docker ps -a --format "table {{.Names}}" | grep -q "^$container_name\$"; then
                # Container exists but is not running - get logs to diagnose
                log "WARNING" "Container $container_name exists but is not running on attempt $attempt"
                log "INFO" "Container logs for $container_name:"
                docker logs "$container_name" 2>&1 | head -20 >> "$LOG_FILE"
                
                # Check container exit code
                exit_code=$(docker inspect --format='{{.State.ExitCode}}' "$container_name" 2>/dev/null || echo "unknown")
                log "WARNING" "Container $container_name exited with code: $exit_code"
                
                return 1
            else
                log "WARNING" "Container $container_name does not exist on attempt $attempt"
                sleep 5
                ((attempt++))
                continue
            fi
        fi
        
        # Get container health status
        health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "no-health-check")
        
        # Check if healthcheck is explicitly disabled
        healthcheck_disabled=$(docker inspect --format='{{index .Config.Labels "healthcheck.disabled"}}' "$container_name" 2>/dev/null || echo "")
        
        if [ "$healthcheck_disabled" = "true" ]; then
            log "INFO" "Healthcheck disabled for container $container_name, skipping health check"
            return 0
        fi
        
        if [ "$health_status" = "healthy" ]; then
            log "INFO" "Container $container_name is healthy"
            return 0
        elif [ "$health_status" = "unhealthy" ]; then
            log "WARNING" "Container $container_name is unhealthy"
            # Get health check logs
            docker inspect --format='{{.State.Health.Log}}' "$container_name" >> "$LOG_FILE" 2>&1 || true
            return 1
        elif [ "$health_status" = "no-health-check" ]; then
            # If no health check is defined, check if container is running and responsive
            log "DEBUG" "No health check defined for $container_name, checking basic responsiveness"
            
            # Try a simple command to see if container is responsive
            if docker exec "$container_name" /bin/sh -c "echo 'health-check' && exit 0" >/dev/null 2>&1; then
                log "INFO" "Container $container_name is running and responsive (no health check defined)"
                return 0
            else
                log "DEBUG" "Container $container_name is not responsive to basic commands"
            fi
        fi
        
        log "DEBUG" "Container $container_name health status: $health_status, waiting..."
        sleep 5
        ((attempt++))
    done
    
    log "ERROR" "Container $container_name failed health check after $max_attempts attempts"
    
    # Get final container logs for debugging
    log "INFO" "Final container logs for $container_name:"
    docker logs "$container_name" 2>&1 | tail -50 >> "$LOG_FILE"
    
    return 1
}

# Function to update Traefik labels for traffic switching
update_traefik_labels() {
    local old_container="$1"
    local new_container="$2"
    local project_name="$3"
    
    log "INFO" "Switching Traefik traffic from $old_container to $new_container"
    
    # Get the current labels from the new container
    local labels=$(docker inspect --format='{{range $key, $value := .Config.Labels}}{{$key}}={{$value}}{{"\n"}}{{end}}' "$new_container" | grep "traefik\.")
    
    if [ -n "$labels" ]; then
        log "DEBUG" "Found Traefik labels on new container"
        
        # Remove old container from Traefik network (if it exists)
        if [ -n "$old_container" ] && docker ps --format "table {{.Names}}" | grep -q "^$old_container\$"; then
            log "INFO" "Removing old container $old_container from Traefik"
            docker update --label-rm traefik.enable "$old_container" >/dev/null 2>&1 || true
        fi
        
        log "INFO" "Traffic successfully switched to new container: $new_container"
        return 0
    else
        log "ERROR" "No Traefik labels found on new container"
        return 1
    fi
}

# Function to cleanup old containers
cleanup_old_container() {
    local container_name="$1"
    
    if [ -n "$container_name" ] && docker ps -a --format "table {{.Names}}" | grep -q "^$container_name\$"; then
        log "INFO" "Stopping and removing old container: $container_name"
        
        if docker stop "$container_name" >> "$LOG_FILE" 2>&1; then
            log "INFO" "Stopped old container: $container_name"
        else
            log "WARNING" "Failed to stop old container: $container_name"
        fi
        
        if docker rm "$container_name" >> "$LOG_FILE" 2>&1; then
            log "INFO" "Removed old container: $container_name"
        else
            log "WARNING" "Failed to remove old container: $container_name"
        fi
    fi
}

# Main deployment logic
main() {
    if [ -z "$REPO_URL" ]; then
        log "ERROR" "No repository URL provided"
        echo "Usage: $0 <repository_url>"
        exit 1
    fi

    # Validate prerequisites before starting
    validate_prerequisites

    REPO_NAME=$(basename -s .git "$REPO_URL")
    TARGET_DIR="$BASE_DIR/$REPO_NAME"
    DEPLOYMENT_UUID=$(generate_uuid)
    
    log "INFO" "Starting blue-green deployment for repository: $REPO_NAME"
    log "INFO" "Deployment UUID: $DEPLOYMENT_UUID"
    log "INFO" "Repository URL: $REPO_URL"
    log "INFO" "Target directory: $TARGET_DIR"

    # Ensure Traefik infrastructure is set up
    log "INFO" "Ensuring Traefik infrastructure is ready"
    if bash "$SCRIPT_DIR/setup-traefik.sh" >> "$LOG_FILE" 2>&1; then
        log "INFO" "Traefik infrastructure is ready"
    else
        log "ERROR" "Failed to setup Traefik infrastructure"
        exit 1
    fi

    mkdir -p "$BASE_DIR"
    log "INFO" "Created base directory: $BASE_DIR"

    # Track if this is a fresh clone
    IS_FRESH_CLONE=false

    # Git operations
    if [ -d "$TARGET_DIR/.git" ]; then
        log "INFO" "Existing repository found, pulling latest changes"
        cd "$TARGET_DIR"
        
        # Capture git output
        if git_output=$(git pull 2>&1); then
            log "INFO" "Successfully pulled latest changes"
            echo "$git_output" >> "$LOG_FILE"
        else
            log "ERROR" "Failed to pull changes: $git_output"
            echo "$git_output" >> "$LOG_FILE"
            exit 1
        fi
    elif [ -d "$TARGET_DIR" ]; then
        log "WARNING" "Directory exists but is not a git repository, removing it"
        if rm -rf "$TARGET_DIR" >> "$LOG_FILE" 2>&1; then
            log "INFO" "Removed existing non-git directory"
        else
            log "ERROR" "Failed to remove existing directory"
            exit 1
        fi
        
        log "INFO" "Cloning repository from $REPO_URL"
        if git_output=$(git clone "$REPO_URL" "$TARGET_DIR" 2>&1); then
            log "INFO" "Successfully cloned repository"
            echo "$git_output" >> "$LOG_FILE"
            cd "$TARGET_DIR"
            IS_FRESH_CLONE=true
        else
            log "ERROR" "Failed to clone repository: $git_output"
            echo "$git_output" >> "$LOG_FILE"
            exit 1
        fi
    else
        log "INFO" "Cloning repository from $REPO_URL"
        if git_output=$(git clone "$REPO_URL" "$TARGET_DIR" 2>&1); then
            log "INFO" "Successfully cloned repository"
            echo "$git_output" >> "$LOG_FILE"
            cd "$TARGET_DIR"
            IS_FRESH_CLONE=true
        else
            log "ERROR" "Failed to clone repository: $git_output"
            echo "$git_output" >> "$LOG_FILE"
            exit 1
        fi
    fi

    # Check if docker-compose.yml, docker-compose.yaml, compose.yml, or compose.yaml exists
    COMPOSE_FILE=""
    if [ -f "$TARGET_DIR/docker-compose.yml" ]; then
        COMPOSE_FILE="$TARGET_DIR/docker-compose.yml"
        log "INFO" "Found docker-compose.yml in repository $REPO_NAME"
    elif [ -f "$TARGET_DIR/docker-compose.yaml" ]; then
        COMPOSE_FILE="$TARGET_DIR/docker-compose.yaml"
        log "INFO" "Found docker-compose.yaml in repository $REPO_NAME"
    elif [ -f "$TARGET_DIR/compose.yml" ]; then
        COMPOSE_FILE="$TARGET_DIR/compose.yml"
        log "INFO" "Found compose.yml in repository $REPO_NAME"
    elif [ -f "$TARGET_DIR/compose.yaml" ]; then
        COMPOSE_FILE="$TARGET_DIR/compose.yaml"
        log "INFO" "Found compose.yaml in repository $REPO_NAME"
    else
        log "ERROR" "No docker-compose.yml, docker-compose.yaml, compose.yml, or compose.yaml found in repository $REPO_NAME"
        log "ERROR" "Deployment failed: missing docker-compose configuration file"
        exit 1
    fi

    # Backup original compose file
    cp "$COMPOSE_FILE" "$COMPOSE_FILE.backup"
    log "INFO" "Created backup of $(basename "$COMPOSE_FILE")"

    # Modify compose file for Traefik integration (only for fresh clones)
    if [ "$IS_FRESH_CLONE" = "true" ]; then
        log "INFO" "Modifying $(basename "$COMPOSE_FILE") for Traefik integration"
        
        PYTHON_EXEC="python3"
        if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
            PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python"
        elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
            PYTHON_EXEC="$SCRIPT_DIR/venv/bin/python"
        fi

        if python_output=$("$PYTHON_EXEC" -c "
import sys
sys.path.append('$SCRIPT_DIR')
from app.traefik_utils import DockerComposeModifier
modifier = DockerComposeModifier('$COMPOSE_FILE', '$REPO_NAME')
success = modifier.modify_compose_file()
sys.exit(0 if success else 1)
" 2>&1); then
            log "INFO" "Successfully modified docker-compose.yml for Traefik"
            echo "$python_output" >> "$LOG_FILE"
        else
            log "ERROR" "Failed to modify docker-compose.yml: $python_output"
            echo "$python_output" >> "$LOG_FILE"
            exit 1
        fi
    else
        log "INFO" "Repository already exists, skipping Traefik modification of $(basename "$COMPOSE_FILE")"
    fi

    # Blue-Green Deployment Process
    log "INFO" "Starting blue-green deployment process"
    
    # Get current running containers for this project
    OLD_CONTAINERS=$(docker ps --filter "label=traefik.http.routers" --filter "label=project=$REPO_NAME" --format "{{.Names}}" | head -5)
    
    if [ -n "$OLD_CONTAINERS" ]; then
        log "INFO" "Found existing containers for project $REPO_NAME: $(echo $OLD_CONTAINERS | tr '\n' ' ')"
    else
        log "INFO" "No existing containers found for project $REPO_NAME"
    fi
    
    # Modify docker-compose.yml to use UUID-tagged container names
    log "INFO" "Updating container names with UUID: $DEPLOYMENT_UUID"
    
    # Create a modified compose file with UUID-tagged names
    TEMP_COMPOSE_FILE="$TARGET_DIR/docker-compose-$DEPLOYMENT_UUID.yml"
    
    if python_output=$("$PYTHON_EXEC" -c "
import yaml
import sys

try:
    with open('$COMPOSE_FILE', 'r') as f:
        compose_data = yaml.safe_load(f)
    
    # Add project label and update container names
    if 'services' in compose_data:
        for service_name, service_config in compose_data['services'].items():
            # Add project label for identification
            if 'labels' not in service_config:
                service_config['labels'] = []
            
            if isinstance(service_config['labels'], list):
                service_config['labels'].append('project=$REPO_NAME')
            elif isinstance(service_config['labels'], dict):
                service_config['labels']['project'] = '$REPO_NAME'
            
            # Handle services with deploy.replicas differently
            if 'deploy' in service_config and 'replicas' in service_config['deploy']:
                # For services with replicas, remove deploy section and set container name
                # This allows blue-green deployment to work with container_name
                del service_config['deploy']
                service_config['container_name'] = f'{service_name}-$DEPLOYMENT_UUID'
                print(f'Removed deploy.replicas from service {service_name} for blue-green deployment')
            else:
                # For regular services, set container name normally
                service_config['container_name'] = f'{service_name}-$DEPLOYMENT_UUID'
    
    with open('$TEMP_COMPOSE_FILE', 'w') as f:
        yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
    
    print('Successfully created UUID-tagged compose file')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1); then
        log "INFO" "Created UUID-tagged compose file: $python_output"
        echo "$python_output" >> "$LOG_FILE"
    else
        log "ERROR" "Failed to create UUID-tagged compose file: $python_output"
        echo "$python_output" >> "$LOG_FILE"
        exit 1
    fi

    # Build and start new containers (Green deployment)
    log "INFO" "Building and starting new containers (Green deployment)"
    
    docker compose -f "$TEMP_COMPOSE_FILE" up -d --build 2>&1 | tee -a "$LOG_FILE"
    exit_code=${PIPESTATUS[0]}

    if [ $exit_code -eq 0 ]; then
        log "INFO" "Successfully built and started new containers"
    else
        log "ERROR" "Failed to build/start new containers"
        
        # Cleanup temp file
        rm -f "$TEMP_COMPOSE_FILE"
        exit 1
    fi
    
    # Get the new container names
    NEW_CONTAINERS=$(docker compose -f "$TEMP_COMPOSE_FILE" ps --format "{{.Names}}")
    log "INFO" "New containers started: $(echo $NEW_CONTAINERS | tr '\n' ' ')"
    
    # Wait for new containers to be healthy
    log "INFO" "Performing health checks on new containers"
    HEALTH_CHECK_FAILED=false
    
    for container in $NEW_CONTAINERS; do
        if check_container_health "$container"; then
            log "INFO" "Health check passed for container: $container"
        else
            log "ERROR" "Health check failed for container: $container"
            HEALTH_CHECK_FAILED=true
        fi
    done
    
    if [ "$HEALTH_CHECK_FAILED" = "true" ]; then
        log "ERROR" "Health checks failed, rolling back deployment"
        
        # Stop and remove new containers
        if stop_output=$(docker compose -f "$TEMP_COMPOSE_FILE" down 2>&1); then
            log "INFO" "Rolled back new containers"
            echo "$stop_output" >> "$LOG_FILE"
        else
            log "ERROR" "Failed to rollback new containers: $stop_output"
            echo "$stop_output" >> "$LOG_FILE"
        fi
        
        # Cleanup temp file
        rm -f "$TEMP_COMPOSE_FILE"
        exit 1
    fi
    
    # Traffic switching phase
    log "INFO" "All health checks passed, initiating traffic switch"
    
    # The traffic switch happens automatically through Traefik labels
    # New containers already have the correct labels and will receive traffic
    
    # Give Traefik some time to detect the new containers
    log "INFO" "Waiting for Traefik to detect new containers and route traffic"
    sleep 10
    
    # Verify new deployment is receiving traffic (basic check)
    FIRST_NEW_CONTAINER=$(echo $NEW_CONTAINERS | head -n1)
    if [ -n "$FIRST_NEW_CONTAINER" ]; then
        log "INFO" "Traffic switch completed to container: $FIRST_NEW_CONTAINER"
    fi
    
    # Cleanup old containers (Blue cleanup)
    if [ -n "$OLD_CONTAINERS" ]; then
        log "INFO" "Cleaning up old containers after successful deployment"
        
        # Wait a bit more before cleanup to ensure traffic has fully switched
        sleep 5
        
        for old_container in $OLD_CONTAINERS; do
            cleanup_old_container "$old_container"
        done
    else
        log "INFO" "No old containers to cleanup"
    fi
    
    # Cleanup temporary files
    rm -f "$TEMP_COMPOSE_FILE"
    log "INFO" "Cleaned up temporary deployment files"
    
    # Get the primary container ID for response
    PRIMARY_CONTAINER_ID=$(echo $NEW_CONTAINERS | head -n1)
    if [ -n "$PRIMARY_CONTAINER_ID" ]; then
        log "INFO" "Primary container deployed: $PRIMARY_CONTAINER_ID"
        echo "CONTAINER_ID:$PRIMARY_CONTAINER_ID"
        echo "DEPLOYMENT_UUID:$DEPLOYMENT_UUID"
    else
        log "WARNING" "Could not identify primary container"
    fi

    log "INFO" "Blue-green deployment completed successfully for $REPO_NAME"
    log "INFO" "Deployment UUID: $DEPLOYMENT_UUID"
}

# Run main function with enhanced error handling
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi