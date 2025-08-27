#!/bin/bash

# Test script for blue-green deployment functionality
# This script creates a simple test scenario to demonstrate zero-downtime deployment

SCRIPT_DIR="$(dirname "$0")"
TEST_REPO_NAME="garcon-test"
TEST_DIR="$SCRIPT_DIR/test_deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Garcon Blue-Green Deployment Test ===${NC}"

# Create a test repository structure
echo -e "${YELLOW}Creating test repository structure...${NC}"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Initialize git repo
git init
git config user.name "Test User"
git config user.email "test@example.com"

# Create a simple Flask app for testing
cat > app.py << 'EOF'
from flask import Flask, jsonify
import os
import socket
import time

app = Flask(__name__)

@app.route('/')
def hello():
    return jsonify({
        'message': 'Hello from Blue-Green Deployment Test!',
        'hostname': socket.gethostname(),
        'timestamp': time.time(),
        'version': os.environ.get('APP_VERSION', '1.0')
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
EOF

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install Flask
RUN pip install flask

# Copy application
COPY app.py .

# Add health check script
COPY health-check.sh /app/health-check.sh
RUN chmod +x /app/health-check.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/app/health-check.sh", "8000", "/health"]

# Expose port
EXPOSE 8000

CMD ["python", "app.py"]
EOF

# Copy health check script
cp "$SCRIPT_DIR/health-check.sh" ./

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  web:
    build: .
    environment:
      - APP_VERSION=1.0
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "/app/health-check.sh", "8000", "/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
EOF

# Create README
cat > README.md << 'EOF'
# Garcon Test Application

This is a simple test application for demonstrating Garcon's blue-green deployment capabilities.

## Endpoints
- `/` - Main endpoint with container info
- `/health` - Health check endpoint

The application returns the hostname and timestamp to help verify zero-downtime deployments.
EOF

# Commit initial version
git add .
git commit -m "Initial version of test app"

echo -e "${GREEN}✓ Test repository created at: $TEST_DIR${NC}"
echo -e "${BLUE}You can now test the blue-green deployment with:${NC}"
echo -e "${YELLOW}  cd $SCRIPT_DIR${NC}"
echo -e "${YELLOW}  ./blue_green_deploy.sh $TEST_DIR${NC}"
echo ""
echo -e "${BLUE}Or use the management script:${NC}"
echo -e "${YELLOW}  ./garcon-manage.sh deploy $TEST_DIR${NC}"
echo ""
echo -e "${BLUE}Monitor the deployment with:${NC}"
echo -e "${YELLOW}  ./garcon-manage.sh monitor${NC}"
echo ""
echo -e "${BLUE}Check deployment status with:${NC}"
echo -e "${YELLOW}  ./garcon-manage.sh status${NC}"
