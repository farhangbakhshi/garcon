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
            
            # Run the blue-green deployment script by default
            deploy_script = current_dir / "blue_green_deploy.sh"
            
            logging.info(f"Starting blue-green deployment for {processed_data['repo_name']}")
            logging.debug(f"Using deployment script: {deploy_script}")
            logging.debug(f"Repository URL: {processed_data['repo_url']}")
            
            result = subprocess.run(
                [str(deploy_script), processed_data["repo_url"]], 
                check=True,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            logging.debug(f"Deployment script stdout: {result.stdout}")
            logging.debug(f"Deployment script stderr: {result.stderr}")
            
            # Extract container ID and deployment UUID from the script's output
            container_id = None
            deployment_uuid = None
            
            for line in result.stdout.strip().split('\n'):
                if line.startswith("CONTAINER_ID:"):
                    container_id = line.split(':', 1)[1].strip()
                elif line.startswith("DEPLOYMENT_UUID:"):
                    deployment_uuid = line.split(':', 1)[1].strip()
            
            # Update project with new container information
            if container_id:
                service.update_project_deployment_info(
                    processed_data['repo_name'],
                    container_id=container_id
                )
            
            # Log successful deployment
            service.log_deployment_status(
                project['id'], 
                'success', 
                processed_data.get('commit_hash'),
                container_id=container_id,
                deployment_uuid=deployment_uuid,
                deployment_type="blue-green"
            )
            
            logging.info(f"Blue-green deployment completed successfully for {processed_data['repo_name']}")
            logging.info(f"Container ID: {container_id}, Deployment UUID: {deployment_uuid}")
            
            return jsonify(
                message="Webhook received and blue-green deployment completed successfully",
                repository=processed_data['repo_name'],
                project_id=project['id'],
                container_id=container_id,
                deployment_uuid=deployment_uuid,
                deployment_type="blue-green"
            ), 200
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"Deployment timed out after 10 minutes: {str(e)}"
            logging.error(error_msg)
            
            # Log failed deployment
            service.log_deployment_status(
                project['id'], 
                'failed', 
                processed_data.get('commit_hash'),
                error_message=error_msg,
                deployment_type="blue-green"
            )
            
            return jsonify(
                error="Deployment timed out", 
                details=error_msg
            ), 500
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Blue-green deployment failed: {e.stderr if e.stderr else str(e)}"
            logging.error(error_msg)
            logging.error(f"Deployment stdout: {e.stdout if hasattr(e, 'stdout') and e.stdout else 'N/A'}")
            logging.error(f"Return code: {e.returncode}")
            
            # Log failed deployment
            service.log_deployment_status(
                project['id'], 
                'failed', 
                processed_data.get('commit_hash'),
                error_message=error_msg,
                deployment_type="blue-green"
            )
            
            return jsonify(
                error="Blue-green deployment failed", 
                details=error_msg
            ), 500
            
        except Exception as e:
            error_msg = f"Unexpected error during blue-green deployment: {str(e)}"
            logging.error(error_msg, exc_info=True)  # Include stack trace
            
            # Log failed deployment
            service.log_deployment_status(
                project['id'], 
                'failed', 
                processed_data.get('commit_hash'),
                error_message=error_msg,
                deployment_type="blue-green"
            )
            
            return jsonify(error="Internal server error during deployment"), 500
            
    else:
        return jsonify(error="Request was not JSON"), 400


@bp.route("/")
def index():
    """Main dashboard showing Garcon status, recent deployments, and links."""
    try:
        service = services.Services()
        recent_deployments = service.db.get_recent_deployments(5)  # Get last 5 deployments
        all_projects = service.db.get_all_projects()
        
        # Generate deployment history HTML
        deployment_html = ""
        if recent_deployments:
            deployment_html = "<h3>Recent Deployments:</h3><div class='deployments'>"
            for deployment in recent_deployments:
                status_class = "success" if deployment['status'] == 'success' else "failed" if deployment['status'] == 'failed' else "running"
                deployment_type = deployment.get('deployment_type', 'unknown')
                commit_info = f" ({deployment['commit_hash'][:8]})" if deployment.get('commit_hash') else ""
                
                deployment_html += f"""
                <div class='deployment-item {status_class}'>
                    <strong>{deployment['repo_name']}</strong> - {deployment['status'].title()} 
                    ({deployment_type}){commit_info}
                    <span class='timestamp'>{deployment['deploy_time']}</span>
                </div>
                """
            deployment_html += "</div>"
        else:
            deployment_html = "<div class='info'><p>No deployments yet. Send a webhook to start deploying!</p></div>"
        
        # Generate projects HTML
        projects_html = ""
        if all_projects:
            projects_html = "<h3>Active Projects:</h3><div class='projects'>"
            for project in all_projects:
                container_status = "🟢 Running" if project.get('container_id') else "🔴 Not Running"
                projects_html += f"""
                <div class='project-item'>
                    <strong>{project['repo_name']}</strong> - {container_status}
                    <div class='project-links'>
                        <a href='/projects/{project['repo_name']}/deployments'>Deployments</a>
                        <a href='/projects/{project['repo_name']}/urls'>URLs</a>
                    </div>
                </div>
                """
            projects_html += "</div>"
    except Exception as e:
        logging.error(f"Error loading dashboard data: {str(e)}")
        deployment_html = "<div class='error'>Error loading deployment data</div>"
        projects_html = "<div class='error'>Error loading projects data</div>"
    
    html = f"""
    <html>
    <head>
        <title>Garcon - Zero-Downtime Docker Deployment</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
            .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .status {{ padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .status.running {{ background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; }}
            .status.stopped {{ background-color: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }}
            .links {{ margin: 20px 0; }}
            .links a {{ display: inline-block; margin: 5px 10px; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            .links a:hover {{ background-color: #0056b3; }}
            .info {{ background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .error {{ background-color: #f8d7da; padding: 15px; border-radius: 5px; margin: 15px 0; color: #721c24; }}
            .endpoint {{ font-family: monospace; background-color: #f8f9fa; padding: 5px; border-radius: 3px; }}
            .deployments {{ margin: 10px 0; }}
            .deployment-item {{ padding: 10px; margin: 5px 0; border-radius: 5px; border-left: 4px solid #ccc; }}
            .deployment-item.success {{ border-left-color: #28a745; background-color: #d4edda; }}
            .deployment-item.failed {{ border-left-color: #dc3545; background-color: #f8d7da; }}
            .deployment-item.running {{ border-left-color: #ffc107; background-color: #fff3cd; }}
            .timestamp {{ float: right; font-size: 0.9em; color: #666; }}
            .projects {{ margin: 10px 0; }}
            .project-item {{ padding: 10px; margin: 5px 0; border-radius: 5px; background-color: #f8f9fa; border: 1px solid #e9ecef; }}
            .project-links {{ margin-top: 5px; }}
            .project-links a {{ font-size: 0.9em; margin-right: 10px; padding: 5px 10px; background-color: #6c757d; color: white; text-decoration: none; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🧑‍🍳 Garcon</h1>
                <p>Zero-Downtime Docker Deployment with Blue-Green Strategy</p>
            </div>
            
            <div class="status running">
                <strong>✓ Garcon is running!</strong><br>
                Ready for blue-green deployments with comprehensive logging and zero downtime.
            </div>
            
            {deployment_html}
            
            {projects_html}
            
            <div class="info">
                <h3>Blue-Green Deployment Features:</h3>
                <ul>
                    <li>Zero-downtime deployments using blue-green strategy</li>
                    <li>Automatic health checks before traffic switching</li>
                    <li>UUID-tagged containers for precise management</li>
                    <li>Automatic cleanup of old containers</li>
                    <li>Comprehensive logging with rotation</li>
                    <li>Rollback capabilities on health check failures</li>
                </ul>
            </div>
            
            <div class="links">
                <h3>Quick Links:</h3>
                <a href="/projects">View All Projects</a>
                <a href="/deployments">Deployment History</a>
                <a href="http://localhost:8080" target="_blank">Traefik Dashboard</a>
                <a href="/logs">View Logs</a>
            </div>
            
            <div class="info">
                <h3>API Endpoints:</h3>
                <p><span class="endpoint">POST /webhook</span> - GitHub webhook endpoint (triggers blue-green deployment)</p>
                <p><span class="endpoint">GET /projects</span> - List all deployed projects</p>
                <p><span class="endpoint">GET /projects/&lt;name&gt;/urls</span> - Get project URLs</p>
                <p><span class="endpoint">GET /projects/&lt;name&gt;/deployments</span> - Get deployment history</p>
                <p><span class="endpoint">POST /projects/&lt;name&gt;/deploy</span> - Manual deployment trigger</p>
                <p><span class="endpoint">GET /deployments</span> - Recent deployments across all projects</p>
            </div>
            
            <div class="info">
                <h3>Blue-Green Deployment Process:</h3>
                <ol>
                    <li>Receive GitHub webhook or manual trigger</li>
                    <li>Clone/update repository with comprehensive logging</li>
                    <li>Build new containers with UUID tags (Green)</li>
                    <li>Perform health checks on new containers</li>
                    <li>Switch Traefik traffic to healthy containers</li>
                    <li>Cleanup old containers (Blue) after successful switch</li>
                    <li>Log all steps with detailed error information</li>
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


@bp.route("/projects/<project_name>/deployments")
def get_project_deployments(project_name):
    """Get deployment history for a specific project."""
    try:
        service = services.Services()
        project = service.db.get_project_by_repo_name(project_name)
        
        if not project:
            return jsonify(error="Project not found"), 404
            
        deployments = service.db.get_deployment_history(project['id'])
        
        return jsonify(
            project=project_name,
            project_id=project['id'],
            deployments=deployments,
            total_deployments=len(deployments)
        ), 200
    except Exception as e:
        logging.error(f"Error getting deployment history for {project_name}: {str(e)}")
        return jsonify(error="Failed to retrieve deployment history"), 500


@bp.route("/deployments")
def get_recent_deployments():
    """Get recent deployments across all projects."""
    try:
        service = services.Services()
        deployments = service.db.get_recent_deployments()
        
        return jsonify(
            deployments=deployments,
            total_shown=len(deployments)
        ), 200
    except Exception as e:
        logging.error(f"Error getting recent deployments: {str(e)}")
        return jsonify(error="Failed to retrieve recent deployments"), 500


@bp.route("/projects/<project_name>/deploy", methods=["POST"])
def manual_deploy(project_name):
    """Manually trigger deployment for a project."""
    try:
        data = request.get_json() if request.is_json else {}
        deployment_type = data.get('type', 'blue-green')  # Default to blue-green
        
        logging.info(f"Manual deployment triggered for {project_name} using {deployment_type} strategy")
        
        service = services.Services()
        project = service.db.get_project_by_repo_name(project_name)
        
        if not project:
            return jsonify(error="Project not found"), 404
        
        # Use the project's repo URL for deployment
        repo_url = project['repo_url']
        
        # Log deployment attempt
        service.log_deployment_status(
            project['id'], 
            'started',
            deployment_type=deployment_type
        )
        
        # Choose deployment script based on type
        current_dir = Path(__file__).parent.parent
        if deployment_type == 'blue-green':
            deploy_script = current_dir / "blue_green_deploy.sh"
        else:
            deploy_script = current_dir / "deploy.sh"
        
        logging.info(f"Using deployment script: {deploy_script}")
        
        # Run deployment
        result = subprocess.run(
            [str(deploy_script), repo_url], 
            check=True,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        # Extract information from deployment output
        container_id = None
        deployment_uuid = None
        
        for line in result.stdout.strip().split('\n'):
            if line.startswith("CONTAINER_ID:"):
                container_id = line.split(':', 1)[1].strip()
            elif line.startswith("DEPLOYMENT_UUID:"):
                deployment_uuid = line.split(':', 1)[1].strip()
        
        # Log successful deployment
        service.log_deployment_status(
            project['id'], 
            'success',
            container_id=container_id,
            deployment_type=deployment_type
        )
        
        logging.info(f"Manual {deployment_type} deployment completed for {project_name}")
        
        return jsonify(
            message=f"Manual {deployment_type} deployment completed successfully",
            repository=project_name,
            project_id=project['id'],
            container_id=container_id,
            deployment_uuid=deployment_uuid,
            deployment_type=deployment_type
        ), 200
        
    except subprocess.TimeoutExpired:
        error_msg = "Manual deployment timed out"
        logging.error(error_msg)
        service.log_deployment_status(project['id'], 'failed', error_message=error_msg)
        return jsonify(error=error_msg), 500
    except subprocess.CalledProcessError as e:
        error_msg = f"Manual deployment failed: {e.stderr if e.stderr else str(e)}"
        logging.error(error_msg)
        service.log_deployment_status(project['id'], 'failed', error_message=error_msg)
        return jsonify(error="Manual deployment failed", details=error_msg), 500
    except Exception as e:
        error_msg = f"Unexpected error during manual deployment: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return jsonify(error="Internal server error"), 500


@bp.route("/logs")
def view_logs():
    """View recent application and deployment logs."""
    try:
        current_dir = Path(__file__).parent.parent
        
        # Read recent app logs
        app_log_file = current_dir / "logs" / "app.log"
        deploy_log_file = current_dir / "logs" / "deploy.log"
        
        app_logs = ""
        deploy_logs = ""
        
        if app_log_file.exists():
            with open(app_log_file, 'r') as f:
                lines = f.readlines()
                # Get last 50 lines
                app_logs = ''.join(lines[-50:]) if lines else "No application logs yet."
        else:
            app_logs = "Application log file not found."
            
        if deploy_log_file.exists():
            with open(deploy_log_file, 'r') as f:
                lines = f.readlines()
                # Get last 100 lines
                deploy_logs = ''.join(lines[-100:]) if lines else "No deployment logs yet."
        else:
            deploy_logs = "Deployment log file not found."
        
        html = f"""
        <html>
        <head>
            <title>Garcon - Logs</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
                .log-section {{ margin: 20px 0; }}
                .log-content {{ background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 5px; padding: 15px; max-height: 400px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 12px; white-space: pre-wrap; }}
                .nav {{ margin-bottom: 20px; }}
                .nav a {{ margin-right: 10px; padding: 8px 16px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px; }}
                h2 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="nav">
                    <a href="/">← Back to Dashboard</a>
                    <a href="/projects">Projects</a>
                    <a href="/deployments">Deployments</a>
                </div>
                
                <h1>🧑‍🍳 Garcon Logs</h1>
                
                <div class="log-section">
                    <h2>Recent Application Logs (Last 50 lines)</h2>
                    <div class="log-content">{app_logs}</div>
                </div>
                
                <div class="log-section">
                    <h2>Recent Deployment Logs (Last 100 lines)</h2>
                    <div class="log-content">{deploy_logs}</div>
                </div>
            </div>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        logging.error(f"Error viewing logs: {str(e)}")
        return jsonify(error="Failed to load logs"), 500
