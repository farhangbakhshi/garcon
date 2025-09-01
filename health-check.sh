#!/bin/bash

set -euo pipefail

# Health check script for containers
# This can be used as a Docker health check command

PORT="${1:-80}"
ENDPOINT="${2:-/}"
HOST="${3:-localhost}"

# Function to check HTTP endpoint
check_http() {
    local url="http://$HOST:$PORT$ENDPOINT"
    
    if command -v curl >/dev/null 2>&1; then
        # Use curl if available
        if curl -f -s --max-time 10 "$url" >/dev/null; then
            echo "Health check passed: $url"
            return 0
        else
            echo "Health check failed: $url (curl)"
            return 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        # Use wget if curl is not available
        if wget -q --timeout=10 --tries=1 "$url" -O /dev/null; then
            echo "Health check passed: $url"
            return 0
        else
            echo "Health check failed: $url (wget)"
            return 1
        fi
    else
        # Fallback to netcat for port check
        if command -v nc >/dev/null 2>&1; then
            if nc -z "$HOST" "$PORT"; then
                echo "Port check passed: $HOST:$PORT"
                return 0
            else
                echo "Port check failed: $HOST:$PORT"
                return 1
            fi
        else
            echo "No health check tools available (curl, wget, nc)"
            return 1
        fi
    fi
}

# Main health check
check_http
