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

show_help() {
    echo "Garcon Traefik Management Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  setup       Setup Traefik infrastructure (network and container)"
    echo "  start       Start Traefik container"
    echo "  stop        Stop Traefik container"
    echo "  restart     Restart Traefik container"
    echo "  status      Show Traefik status"
    echo "  logs        Show Traefik logs"
    echo "  dashboard   Open Traefik dashboard URL"
    echo "  cleanup     Remove Traefik container and network"
    echo "  help        Show this help message"
    echo ""
}

setup_traefik() {
    log "INFO" "Setting up Traefik infrastructure"
    ./setup-traefik.sh
}

start_traefik() {
    log "INFO" "Starting Traefik container"
    if docker compose -f traefik-docker-compose.yml up -d; then
        log "INFO" "Traefik started successfully"
        echo "Traefik dashboard: http://localhost:8080"
    else
        log "ERROR" "Failed to start Traefik"
        exit 1
    fi
}

stop_traefik() {
    log "INFO" "Stopping Traefik container"
    if docker compose -f traefik-docker-compose.yml down; then
        log "INFO" "Traefik stopped successfully"
    else
        log "ERROR" "Failed to stop Traefik"
        exit 1
    fi
}

restart_traefik() {
    log "INFO" "Restarting Traefik container"
    stop_traefik
    start_traefik
}

show_status() {
    echo "=== Traefik Status ==="
    echo ""
    
    # Check if container is running
    if docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep traefik-garcon; then
        echo ""
        echo "✓ Traefik is running"
        echo "Dashboard: http://localhost:8080"
    else
        echo "✗ Traefik is not running"
    fi
    
    echo ""
    echo "=== Web-Proxy Network ==="
    if docker network ls | grep web-proxy; then
        echo "✓ web-proxy network exists"
    else
        echo "✗ web-proxy network does not exist"
    fi
    
    echo ""
    echo "=== Connected Containers ==="
    docker network inspect web-proxy --format "{{range .Containers}}{{.Name}} ({{.IPv4Address}}){{end}}" 2>/dev/null | tr ' ' '\n' | grep -v "^$" || echo "No containers connected"
}

show_logs() {
    echo "=== Traefik Logs ==="
    docker logs traefik-garcon --tail=50
}

open_dashboard() {
    echo "Opening Traefik dashboard..."
    echo "Dashboard URL: http://localhost:8080"
    
    # Try to open in browser (works on most Linux desktop environments)
    if command -v xdg-open > /dev/null; then
        xdg-open http://localhost:8080
    elif command -v gnome-open > /dev/null; then
        gnome-open http://localhost:8080
    else
        echo "Please open http://localhost:8080 in your browser manually"
    fi
}

cleanup_traefik() {
    log "INFO" "Cleaning up Traefik infrastructure"
    
    # Stop and remove Traefik container
    docker compose -f traefik-docker-compose.yml down
    
    # Remove web-proxy network (only if no containers are connected)
    if docker network inspect web-proxy >/dev/null 2>&1; then
        connected_containers=$(docker network inspect web-proxy --format "{{len .Containers}}")
        if [ "$connected_containers" -eq 0 ]; then
            docker network rm web-proxy
            log "INFO" "Removed web-proxy network"
        else
            log "WARNING" "web-proxy network has connected containers, not removing"
        fi
    fi
    
    log "INFO" "Cleanup completed"
}

# Main script logic
case "${1:-help}" in
    setup)
        setup_traefik
        ;;
    start)
        start_traefik
        ;;
    stop)
        stop_traefik
        ;;
    restart)
        restart_traefik
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    dashboard)
        open_dashboard
        ;;
    cleanup)
        cleanup_traefik
        ;;
    help)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
