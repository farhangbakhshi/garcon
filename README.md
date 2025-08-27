# 🧑‍🍳 Garcon: Automatic Docker Deployment

Garcon is a lightweight, automated deployment system that uses GitHub webhooks to deploy Docker-based projects. It seamlessly integrates with Traefik to provide dynamic reverse proxying, allowing you to deploy and manage multiple web services on a single server with minimal configuration.

## Features

- **Zero-Downtime Blue-Green Deployments:** Advanced deployment strategy that ensures no service interruption during updates.
- **Automated Deployments:** Trigger deployments automatically with a `git push` to your repository.
- **Dynamic Reverse Proxy:** Uses Traefik to automatically discover and route traffic to your services.
- **Comprehensive Logging:** Detailed logging with rotation for both application and deployment processes.
- **Health Check Integration:** Automatic health verification before traffic switching.
- **Project Database:** Keeps a record of all deployed projects and their deployment history in a local SQLite database.
- **UUID-Tagged Containers:** Precise container management for blue-green deployments.
- **Rollback Protection:** Failed deployments don't affect running services.
- **Real-Time Monitoring:** Web dashboard and CLI tools for monitoring deployments.
- **Extensible:** Easily adaptable for different project structures as long as they are containerized with Docker.

## How It Works

The blue-green deployment process is designed to be robust and zero-downtime:

1.  **Webhook Trigger:** You push a new commit to your GitHub repository.
2.  **Garcon Receives:** GitHub sends a webhook to the Garcon Flask application.
3.  **Signature Verification:** Garcon verifies the webhook's signature to ensure it's a legitimate request from GitHub.
4.  **Blue-Green Script:** The application invokes the `blue_green_deploy.sh` script with comprehensive logging.
5.  **Code Update:** The script clones the repository (if it's the first time) or pulls the latest changes.
6.  **Container Preparation:** New containers are built with UUID tags (Green environment).
7.  **Health Checks:** System verifies new containers are healthy and responsive.
8.  **Traffic Switch:** Traefik automatically routes traffic to healthy new containers.
9.  **Cleanup:** Old containers (Blue environment) are safely removed.
10. **Monitoring:** All steps are logged with detailed information for debugging.

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone <your-garcon-repo-url>
    cd garcon
    ```

2.  **Install Dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure:**
    Create a `config.py` file or modify the existing one to set your `GITHUB_WEBHOOK_SECRET`.
    ```python
    # config.py
    class DevelopmentConfig:
        GITHUB_WEBHOOK_SECRET = 'your-very-secret-string'
        # ... other configs
    ```

4.  **Run the Application:**
    ```bash
    python run.py
    ```
    The Flask application will start, typically on `http://127.0.0.1:5000`.

## Usage

To deploy your own project with Garcon, follow these steps:

1.  **Dockerize Your Project:** Ensure your project has a `Dockerfile` and a `docker-compose.yml` file.

2.  **Configure GitHub Webhook:**
    - Go to your project's repository on GitHub.
    - Navigate to **Settings > Webhooks**.
    - Click **Add webhook**.
    - **Payload URL:** Enter the URL where Garcon is running (e.g., `http://<your-server-ip>:5000/webhook`).
    - **Content type:** Select `application/json`.
    - **Secret:** Enter the same secret you configured in `config.py`.
    - Save the webhook.

3.  **Push to Deploy:**
    Commit and push a change to your repository. Garcon will automatically handle the rest. Your project will soon be available at a URL like `http://<your-repo-name>.localhost`.

## API Endpoints

### Core Endpoints
- `GET /`: Enhanced dashboard with deployment history and real-time status.
- `POST /webhook`: GitHub webhook endpoint that triggers blue-green deployments.

### Project Management
- `GET /projects`: Returns a JSON list of all projects managed by Garcon.
- `GET /projects/<project_name>/urls`: Returns potential Traefik URLs for a specific project.
- `GET /projects/<project_name>/deployments`: Returns deployment history for a project.
- `POST /projects/<project_name>/deploy`: Manually trigger a deployment (supports blue-green or simple).

### Monitoring & Debugging
- `GET /deployments`: Recent deployments across all projects.
- `GET /logs`: Web interface for viewing application and deployment logs.

## Management Tools

### Garcon Management Script
Use `./garcon-manage.sh` for common operations:

```bash
# Check deployment status
./garcon-manage.sh status

# View logs
./garcon-manage.sh logs tail    # Follow logs in real-time
./garcon-manage.sh logs deploy  # View deployment logs
./garcon-manage.sh logs app     # View application logs

# Manual deployments
./garcon-manage.sh deploy <repo_url>        # Blue-green deployment
./garcon-manage.sh simple-deploy <repo_url> # Simple deployment

# Container management
./garcon-manage.sh containers  # List active containers
./garcon-manage.sh cleanup     # Clean up old containers

# Real-time monitoring
./garcon-manage.sh monitor     # Monitor deployment progress
```

## Deployment Scripts

### Blue-Green Deployment (Recommended)
```bash
./blue_green_deploy.sh https://github.com/user/repo.git
```
- Zero downtime
- Health checks
- Automatic rollback on failure
- UUID-tagged containers

### Simple Deployment (Legacy)
```bash
./deploy.sh https://github.com/user/repo.git simple
```
- Basic deployment
- Service interruption during update
- Simpler process

## Project Structure

```
.
├── app/                       # Core Flask application
│   ├── __init__.py           # Application factory with enhanced logging
│   ├── models.py             # Database models with deployment tracking
│   ├── routes.py             # API endpoints with monitoring
│   ├── services.py           # Business logic with comprehensive logging
│   ├── traefik_utils.py      # Utility to modify compose files
│   └── utils.py              # Helper utilities
├── projects_data/            # Cloned repositories are stored here
├── logs/                     # Application and deployment logs (with rotation)
│   ├── app.log              # Application logs
│   └── deploy.log           # Deployment logs
├── data/                     # Database storage
│   └── projects.db          # SQLite database with deployment history
├── config.py                 # Application configuration
├── deploy.sh                 # Legacy deployment script (supports both modes)
├── blue_green_deploy.sh      # Advanced blue-green deployment script
├── garcon-manage.sh          # Management and monitoring utilities
├── health-check.sh           # Container health check script
├── run.py                    # Application entry point
├── requirements.txt          # Python dependencies
├── setup-traefik.sh          # Script to set up Traefik network
├── README.md                 # This file
└── BLUE_GREEN_DEPLOYMENT.md  # Detailed blue-green deployment guide
```

## Dependencies

- **Python 3**
- **Flask**
- **Docker** & **Docker Compose**
- **Traefik**
