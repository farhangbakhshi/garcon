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
        logging.basicConfig(
            filename=str(current_dir / "logs" / "app.log"),
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        
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
            
            # Log successful deployment
            service.log_deployment_status(
                project['id'], 
                'success', 
                processed_data.get('commit_hash')
            )
            
            logging.info(f"Webhook processed successfully! Repository: {processed_data['repo_name']}")
            return jsonify(
                message="Webhook received and processed successfully",
                repository=processed_data['repo_name'],
                project_id=project['id']
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
    return "<h1>Garcon is running!</h1>"


@bp.route("/projects")
def list_projects():
    """List all projects being managed."""
    try:
        service = services.Services()
        projects = service.db.get_all_projects()
        return jsonify(projects=projects), 200
    except Exception as e:
        logging.error(f"Error listing projects: {str(e)}")
        return jsonify(error="Failed to retrieve projects"), 500
