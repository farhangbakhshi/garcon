#!/bin/bash

set -euo pipefail

# Garcon Deployment Management Script
# This script provides utilities for managing zero-downtime deployments

SCRIPT_DIR="$(dirname "$0")"
LOG_DIR="$SCRIPT_DIR/logs"
APP_LOG="$LOG_DIR/app.log"
DEPLOY_LOG="$LOG_DIR/deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Garcon Deployment Management"
    echo "Usage: $0 <command> [arguments]"
    echo ""
    echo "Commands:"
    echo "  status                     - Show deployment status"
    echo "  logs [app|deploy|tail]     - View logs"
    echo "  deploy <repo_url>          - Trigger blue-green deployment"
    echo "  simple-deploy <repo_url>   - Trigger simple deployment"
    echo "  containers                 - List active containers"
    echo "  cleanup                    - Cleanup old containers"
    echo "  monitor                    - Monitor deployment progress"
    echo ""
    echo "Examples:"
    echo "  $0 status"
    echo "  $0 logs tail"
    echo "  $0 deploy https://github.com/user/repo.git"
    echo "  $0 containers"
}

# Function to show deployment status
show_status() {
    echo -e "${BLUE}=== Garcon Deployment Status ===${NC}"
    
    # Check if Traefik is running
    if docker ps | grep -q traefik; then
        echo -e "${GREEN}✓ Traefik reverse proxy is running${NC}"
        traefik_container=$(docker ps --filter "name=traefik" --format "{{.Names}}" | head -1)
        echo -e "  Container: $traefik_container"
    else
        echo -e "${RED}✗ Traefik reverse proxy is not running${NC}"
    fi
    
    # Show active project containers
    echo -e "\n${BLUE}Active project containers:${NC}"
    project_containers=$(docker ps --filter "label=project" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Labels}}" | grep -v "NAMES")
    
    if [ -n "$project_containers" ]; then
        echo "$project_containers" | while read line; do
            if [[ $line == *"project="* ]]; then
                project_name=$(echo "$line" | sed -n 's/.*project=\([^,]*\).*/\1/p')
                echo -e "${GREEN}✓${NC} $line (Project: $project_name)"
            else
                echo -e "${YELLOW}?${NC} $line"
            fi
        done
    else
        echo -e "${YELLOW}No active project containers found${NC}"
    fi
    
    # Show recent deployments from logs
    echo -e "\n${BLUE}Recent deployment activity:${NC}"
    if [ -f "$DEPLOY_LOG" ]; then
        tail -5 "$DEPLOY_LOG" | while read line; do
            if [[ $line == *"ERROR"* ]]; then
                echo -e "${RED}$line${NC}"
            elif [[ $line == *"INFO"* ]]; then
                echo -e "${GREEN}$line${NC}"
            else
                echo "$line"
            fi
        done
    else
        echo -e "${YELLOW}No deployment logs found${NC}"
    fi
}

# Function to view logs
view_logs() {
    local log_type="$1"
    
    case "$log_type" in
        "app")
            echo -e "${BLUE}=== Application Logs ===${NC}"
            if [ -f "$APP_LOG" ]; then
                tail -50 "$APP_LOG"
            else
                echo -e "${YELLOW}Application log file not found${NC}"
            fi
            ;;
        "deploy")
            echo -e "${BLUE}=== Deployment Logs ===${NC}"
            if [ -f "$DEPLOY_LOG" ]; then
                tail -50 "$DEPLOY_LOG"
            else
                echo -e "${YELLOW}Deployment log file not found${NC}"
            fi
            ;;
        "tail")
            echo -e "${BLUE}=== Tailing All Logs (Ctrl+C to exit) ===${NC}"
            if [ -f "$APP_LOG" ] && [ -f "$DEPLOY_LOG" ]; then
                tail -f "$APP_LOG" "$DEPLOY_LOG"
            elif [ -f "$APP_LOG" ]; then
                tail -f "$APP_LOG"
            elif [ -f "$DEPLOY_LOG" ]; then
                tail -f "$DEPLOY_LOG"
            else
                echo -e "${YELLOW}No log files found to tail${NC}"
            fi
            ;;
        *)
            echo -e "${BLUE}=== Recent Deployment Logs ===${NC}"
            if [ -f "$DEPLOY_LOG" ]; then
                tail -20 "$DEPLOY_LOG"
            else
                echo -e "${YELLOW}No deployment logs found${NC}"
            fi
            echo -e "\n${BLUE}=== Recent Application Logs ===${NC}"
            if [ -f "$APP_LOG" ]; then
                tail -10 "$APP_LOG"
            else
                echo -e "${YELLOW}No application logs found${NC}"
            fi
            ;;
    esac
}

# Function to trigger deployment
trigger_deploy() {
    local repo_url="$1"
    local deployment_type="$2"
    
    if [ -z "$repo_url" ]; then
        echo -e "${RED}Error: Repository URL required${NC}"
        echo "Usage: $0 deploy <repository_url>"
        exit 1
    fi
    
    echo -e "${BLUE}=== Triggering $deployment_type deployment ===${NC}"
    echo "Repository: $repo_url"
    echo ""
    
    if [ "$deployment_type" = "blue-green" ]; then
        "$SCRIPT_DIR/blue_green_deploy.sh" "$repo_url"
    else
        "$SCRIPT_DIR/deploy.sh" "$repo_url" "simple"
    fi
}

# Function to list containers
list_containers() {
    echo -e "${BLUE}=== Docker Containers ===${NC}"
    
    echo -e "\n${GREEN}All running containers:${NC}"
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
    
    echo -e "\n${GREEN}Project containers only:${NC}"
    docker ps --filter "label=project" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Labels}}"
    
    echo -e "\n${GREEN}Traefik container:${NC}"
    docker ps --filter "name=traefik" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
}

# Function to cleanup old containers
cleanup_containers() {
    echo -e "${BLUE}=== Cleaning up old containers ===${NC}"
    
    # Remove stopped containers with project labels
    stopped_containers=$(docker ps -a --filter "status=exited" --filter "label=project" --format "{{.Names}}")
    
    if [ -n "$stopped_containers" ]; then
        echo -e "${YELLOW}Found stopped project containers:${NC}"
        echo "$stopped_containers"
        echo ""
        read -p "Remove these containers? (y/N): " confirm
        
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            echo "$stopped_containers" | xargs docker rm
            echo -e "${GREEN}Cleanup completed${NC}"
        else
            echo -e "${YELLOW}Cleanup cancelled${NC}"
        fi
    else
        echo -e "${GREEN}No stopped project containers found${NC}"
    fi
    
    # Clean up unused images
    echo -e "\n${BLUE}Cleaning up unused Docker images...${NC}"
    docker image prune -f
}

# Function to monitor deployment progress
monitor_deployment() {
    echo -e "${BLUE}=== Monitoring Deployment Progress ===${NC}"
    echo "Press Ctrl+C to stop monitoring"
    echo ""
    
    # Monitor logs in real-time
    if [ -f "$DEPLOY_LOG" ]; then
        tail -f "$DEPLOY_LOG" | while read line; do
            if [[ $line == *"ERROR"* ]]; then
                echo -e "${RED}$line${NC}"
            elif [[ $line == *"INFO"* ]]; then
                echo -e "${GREEN}$line${NC}"
            elif [[ $line == *"WARNING"* ]]; then
                echo -e "${YELLOW}$line${NC}"
            else
                echo "$line"
            fi
        done
    else
        echo -e "${YELLOW}Deployment log file not found. Run a deployment first.${NC}"
    fi
}

# Main script logic
case "$1" in
    "status")
        show_status
        ;;
    "logs")
        view_logs "$2"
        ;;
    "deploy")
        trigger_deploy "$2" "blue-green"
        ;;
    "simple-deploy")
        trigger_deploy "$2" "simple"
        ;;
    "containers")
        list_containers
        ;;
    "cleanup")
        cleanup_containers
        ;;
    "monitor")
        monitor_deployment
        ;;
    *)
        usage
        exit 1
        ;;
esac
