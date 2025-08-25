#!/bin/bash

set -e

REPO_URL="$1"
BASE_DIR="$(dirname "$0")/projects_data"

if [ -z "$REPO_URL" ]; then
    echo "Usage: $0 <repository_url>"
    exit 1
fi

REPO_NAME=$(basename -s .git "$REPO_URL")
TARGET_DIR="$BASE_DIR/$REPO_NAME"

mkdir -p "$BASE_DIR"

if [ -d "$TARGET_DIR/.git" ]; then
    cd "$TARGET_DIR"
    git pull
else
    git clone "$REPO_URL" "$TARGET_DIR"
    cd "$TARGET_DIR"
fi

docker compose up -d --build