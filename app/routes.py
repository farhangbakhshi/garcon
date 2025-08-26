import subprocess
from flask import Blueprint, request, jsonify, current_app
from . import services
from .utils import verify_github_webhook
import logging
import os
from pathlib import Path

bp = Blueprint("main", __name__)


@bp.route("/webhook", methods=["POST"])
def webhook():
    # Verify the webhook signature first
    signature = request.headers.get('X-Hub-Signature-256')
    webhook_secret = current_app.config.get('GITHUB_WEBHOOK_SECRET')
    
    if not verify_github_webhook(request.get_data(), signature, webhook_secret):
        logging.warning("Invalid webhook signature received")
        return jsonify(error="Unauthorized"), 403

    if request.is_json:
        payload = request.get_json()

        service = services.Services()
        processed_data = service.process_webhook(payload)
        
        if not processed_data['repo_name']:
            return jsonify(error="Invalid payload: missing repository name"), 400
        
        # Get or create project in database
        project = service.get_or_create_project(
            processed_data['repo_name'], 
            processed_data['repo_url']
        )
        
        if not project:
            logging.error(f"Failed to create/retrieve project: {processed_data['repo_name']}")
            return jsonify(error="Database error"), 500
        
        # Configure logging to write to ../logs/app.log
        current_dir = Path(__file__).parent.parent
        
        try:
            # Log deployment attempt
            service.log_deployment_status(
                project['id'], 
                'started', 
                processed_data.get('commit_hash')
            )
            
            # Run the deployment script
            deploy_script = current_dir / "deploy.sh"
            result = subprocess.run(
                [str(deploy_script), processed_data["repo_url"]], 
                check=True,
                capture_output=True,
                text=True
            )
            
            # Extract container ID from the script's output
            container_id = None
            for line in result.stdout.strip().split('\n'):
                if line.startswith("CONTAINER_ID:"):
                    container_id = line.split(':', 1)[1].strip()
                    break
            
            # Log successful deployment
            service.log_deployment_status(
                project['id'], 
                'success', 
                processed_data.get('commit_hash'),
                container_id=container_id
            )
            
            logging.info(f"Webhook processed successfully! Repository: {processed_data['repo_name']}")
            return jsonify(
                message="Webhook received and processed successfully",
                repository=processed_data['repo_name'],
                project_id=project['id'],
                container_id=container_id
            ), 200
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Deployment failed: {e.stderr if e.stderr else str(e)}"
            logging.error(error_msg)
            
            # Log failed deployment
            service.log_deployment_status(
                project['id'], 
                'failed', 
                processed_data.get('commit_hash'),
                error_msg
            )
            
            return jsonify(
                error="Deployment failed", 
                details=error_msg
            ), 500
            
        except Exception as e:
            error_msg = f"Unexpected error during deployment: {str(e)}"
            logging.error(error_msg)
            
            # Log failed deployment
            service.log_deployment_status(
                project['id'], 
                'failed', 
                processed_data.get('commit_hash'),
                error_msg
            )
            
            return jsonify(error="Internal server error"), 500
            
    else:
        return jsonify(error="Request was not JSON"), 400


@bp.route("/")
def index():
    """Main dashboard showing Garcon status and links."""
    html = """
    <html>
    <head>
        <title>Garcon - Automatic Docker Deployment</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .header { text-align: center; margin-bottom: 30px; }
            .status { padding: 15px; margin: 10px 0; border-radius: 5px; }
            .status.running { background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
            .status.stopped { background-color: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
            .links { margin: 20px 0; }
            .links a { display: inline-block; margin: 5px 10px; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }
            .links a:hover { background-color: #0056b3; }
            .info { background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }
            .endpoint { font-family: monospace; background-color: #f8f9fa; padding: 5px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🧑‍🍳 Garcon</h1>
                <p>Automatic Docker Deployment with Traefik Reverse Proxy</p>
            </div>
            
            <div class="status running">
                <strong>✓ Garcon is running!</strong><br>
                Ready to receive webhook deployments and manage Docker containers.
            </div>
            
            <div class="info">
                <h3>Key Features:</h3>
                <ul>
                    <li>Automatic deployment from GitHub webhooks</li>
                    <li>Dynamic routing with Traefik reverse proxy</li>
                    <li>Automatic port conflict resolution</li>
                    <li>Container management and monitoring</li>
                </ul>
            </div>
            
            <div class="links">
                <h3>Quick Links:</h3>
                <a href="/projects">View Projects</a>
                <a href="http://localhost:8080" target="_blank">Traefik Dashboard</a>
            </div>
            
            <div class="info">
                <h3>API Endpoints:</h3>
                <p><span class="endpoint">POST /webhook</span> - GitHub webhook endpoint</p>
                <p><span class="endpoint">GET /projects</span> - List all deployed projects</p>
                <p><span class="endpoint">GET /projects/&lt;name&gt;/urls</span> - Get project URLs</p>
            </div>
            
            <div class="info">
                <h3>How it works:</h3>
                <ol>
                    <li>Receive GitHub webhook when code is pushed</li>
                    <li>Clone/update the repository</li>
                    <li>Modify docker-compose.yml to integrate with Traefik</li>
                    <li>Deploy containers with automatic routing</li>
                    <li>Access your app via generated subdomain (e.g., project-name.localhost)</li>
                </ol>
            </div>
        </div>
    </body>
    </html>
    """
    return html


@bp.route("/projects")
def list_projects():
    """List all projects being managed."""
    try:
        service = services.Services()
        projects = service.db.get_all_projects()
        
        # Add potential URLs for each project
        for project in projects:
            project['urls'] = service.get_project_urls(project['repo_name'])
            
        return jsonify(projects=projects), 200
    except Exception as e:
        logging.error(f"Error listing projects: {str(e)}")
        return jsonify(error="Failed to retrieve projects"), 500


@bp.route("/projects/<project_name>/urls")
def get_project_urls(project_name):
    """Get the Traefik URLs for a specific project."""
    try:
        service = services.Services()
        project = service.db.get_project_by_repo_name(project_name)
        
        if not project:
            return jsonify(error="Project not found"), 404
            
        urls = service.get_project_urls(project_name)
        return jsonify(
            project=project_name,
            urls=urls,
            traefik_dashboard="http://localhost:8080"
        ), 200
    except Exception as e:
        logging.error(f"Error getting project URLs: {str(e)}")
        return jsonify(error="Failed to retrieve project URLs"), 500
