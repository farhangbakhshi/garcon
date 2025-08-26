# 🧑‍🍳 Garcon: Automatic Docker Deployment

Garcon is a lightweight, automated deployment system that uses GitHub webhooks to deploy Docker-based projects. It seamlessly integrates with Traefik to provide dynamic reverse proxying, allowing you to deploy and manage multiple web services on a single server with minimal configuration.

## Features

- **Automated Deployments:** Trigger deployments automatically with a `git push` to your repository.
- **Dynamic Reverse Proxy:** Uses Traefik to automatically discover and route traffic to your services.
- **Zero-Downtime Updates:** Docker and Traefik manage the container lifecycle, ensuring smooth updates.
- **Project Database:** Keeps a record of all deployed projects and their deployment history in a local SQLite database.
- **Extensible:** Easily adaptable for different project structures as long as they are containerized with Docker.
- **Simple API:** Provides endpoints to view the status and URLs of deployed projects.

## How It Works

The deployment process is designed to be simple and efficient:

1.  **Webhook Trigger:** You push a new commit to your GitHub repository.
2.  **Garcon Receives:** GitHub sends a webhook to the Garcon Flask application.
3.  **Signature Verification:** Garcon verifies the webhook's signature to ensure it's a legitimate request from GitHub.
4.  **Deployment Script:** The application invokes the `deploy.sh` script, passing the repository URL.
5.  **Code Update:** The script clones the repository (if it's the first time) or pulls the latest changes into the `projects_data` directory.
6.  **Traefik Integration:** A Python utility (`traefik_utils.py`) dynamically modifies the project's `docker-compose.yml` file, adding the necessary labels for Traefik to recognize and route traffic.
7.  **Docker Compose:** The script runs `docker-compose up -d --build` to build the new images and restart the services.
8.  **Live Service:** Traefik detects the running containers and automatically routes traffic to them based on the host rules defined in the labels (e.g., `http://your-repo-name.localhost`).

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/farhangbakhshi/garcon
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

- `GET /`: A simple HTML dashboard showing the status of the Garcon service.
- `POST /webhook`: The main endpoint that listens for GitHub webhook payloads.
- `GET /projects`: Returns a JSON list of all projects managed by Garcon.
- `GET /projects/<project_name>/urls`: Returns potential Traefik URLs for a specific project.

## Project Structure

```
.
├── app/                # Core Flask application
│   ├── __init__.py     # Application factory
│   ├── models.py       # Database models and management
│   ├── routes.py       # API endpoints
│   ├── services.py     # Business logic
│   └── traefik_utils.py# Utility to modify compose files
├── projects_data/      # Cloned repositories are stored here
├── logs/               # Application and deployment logs
├── config.py           # Application configuration
├── deploy.sh           # Main deployment script
├── run.py              # Application entry point
├── requirements.txt    # Python dependencies
└── setup-traefik.sh    # Script to set up Traefik network
```

## Dependencies

- **Python 3**
- **Flask**
- **Docker** & **Docker Compose**
- **Traefik**
