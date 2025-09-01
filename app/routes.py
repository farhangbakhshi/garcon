import subprocess
from flask import Blueprint, request, jsonify, current_app, render_template, flash, redirect, url_for
from . import services
from .utils import verify_github_webhook
import logging
import os
from pathlib import Path

bp = Blueprint("main", __name__)


# Web UI Routes
@bp.route("/dashboard")
def dashboard():
    """Main dashboard web interface."""
    try:
        service = services.Services()
        recent_deployments = service.db.get_recent_deployments(5)
        all_projects = service.db.get_all_projects()
        
        # Add URLs and actual status for each project
        for project in all_projects:
            project['urls'] = service.get_project_urls(project['repo_name'])
            project['actual_status'] = service.get_project_status(project)
        
        # Calculate stats for the dashboard using efficient count methods
        stats = {
            'total_projects': service.db.get_project_count(),
            'total_deployments': service.db.get_deployment_count()
        }
            
        return render_template('dashboard.html', 
                             recent_deployments=recent_deployments,
                             projects=all_projects,
                             stats=stats)
    except Exception as e:
        logging.error(f"Error loading dashboard: {str(e)}")
        flash('Error loading dashboard data', 'error')
        # Provide empty stats to prevent template errors
        empty_stats = {'total_projects': 0, 'total_deployments': 0}
        return render_template('dashboard.html', 
                             recent_deployments=[],
                             projects=[],
                             stats=empty_stats)


@bp.route("/projects_ui")
def projects_ui():
    """Projects management web interface."""
    try:
        service = services.Services()
        projects = service.db.get_all_projects()
        
        # Add URLs, deployment status, and actual status for each project
        for project in projects:
            project['urls'] = service.get_project_urls(project['repo_name'])
            project['actual_status'] = service.get_project_status(project)
            # Get latest deployment status
            deployments = service.db.get_deployment_history(project['id'], limit=1)
            project['latest_deployment'] = deployments[0] if deployments else None
            
        return render_template('projects.html', projects=projects)
    except Exception as e:
        logging.error(f"Error loading projects: {str(e)}")
        flash('Error loading projects', 'error')
        return render_template('projects.html', projects=[])


@bp.route("/add_project", methods=["GET", "POST"])
def add_project_form():
    """Add new project web interface."""
    if request.method == 'POST':
        try:
            # Get form data - using the field names that match the template and JavaScript
            name = request.form.get('name')
            git_url = request.form.get('git_url')
            domain = request.form.get('domain')
            deployment_type = request.form.get('deployment_type', 'blue-green')
            deploy_immediately = request.form.get('deploy_immediately') == 'on'
            
            if not all([name, git_url, domain]):
                flash('All fields are required', 'error')
                return render_template('add_project.html')
            
            service = services.Services()
            
            # Create project using the provided name and git_url
            project = service.get_or_create_project(name, git_url)
            if project:
                flash(f'Project "{name}" added successfully!', 'success')
                
                # TODO: Store domain information if needed in the database
                # For now, we're storing it in the project name/repo_name field
                
                # Deploy immediately if requested
                if deploy_immediately:
                    try:
                        # Log deployment attempt
                        service.log_deployment_status(
                            project['id'], 
                            'started',
                            deployment_type=deployment_type
                        )
                        
                        # Choose deployment script
                        current_dir = Path(__file__).parent.parent
                        if deployment_type == 'blue-green':
                            deploy_script = current_dir / "blue_green_deploy.sh"
                        else:
                            deploy_script = current_dir / "deploy.sh"
                        
                        # Run deployment in background
                        import threading
                        
                        def run_deployment():
                            try:
                                result = subprocess.run(
                                    [str(deploy_script), git_url], 
                                    check=True,
                                    capture_output=True,
                                    text=True,
                                    timeout=600
                                )
                                
                                # Extract deployment info
                                container_id = None
                                deployment_uuid = None
                                
                                for line in result.stdout.strip().split('\n'):
                                    if line.startswith("CONTAINER_ID:"):
                                        container_id = line.split(':', 1)[1].strip()
                                    elif line.startswith("DEPLOYMENT_UUID:"):
                                        deployment_uuid = line.split(':', 1)[1].strip()
                                
                                # Log success
                                service.log_deployment_status(
                                    project['id'], 
                                    'success',
                                    container_id=container_id,
                                    deployment_uuid=deployment_uuid,
                                    deployment_type=deployment_type
                                )
                                
                                logging.info(f"Initial deployment completed for {name}")
                                
                            except Exception as e:
                                error_msg = f"Initial deployment failed: {str(e)}"
                                logging.error(error_msg)
                                service.log_deployment_status(
                                    project['id'], 
                                    'failed', 
                                    error_message=error_msg,
                                    deployment_type=deployment_type
                                )
                        
                        # Start deployment in background
                        deployment_thread = threading.Thread(target=run_deployment)
                        deployment_thread.daemon = True
                        deployment_thread.start()
                        
                        flash('Deployment started successfully!', 'info')
                        
                    except Exception as deploy_e:
                        logging.error(f"Error starting initial deployment: {str(deploy_e)}")
                        flash('Project added but deployment failed to start', 'warning')
                
                return redirect(url_for('main.projects_ui'))
            else:
                flash('Error creating project', 'error')
                
        except Exception as e:
            logging.error(f"Error adding project: {str(e)}")
            flash('Error adding project', 'error')
    
    return render_template('add_project.html')


@bp.route("/project/<project_name>")
def project_detail(project_name):
    """Project detail web interface."""
    try:
        service = services.Services()
        project = service.db.get_project_by_repo_name(project_name)
        
        if not project:
            flash('Project not found', 'error')
            return redirect(url_for('main.projects_ui'))
        
        # Get deployment history
        deployments = service.db.get_deployment_history(project['id'])
        
        # Get project URLs
        project['urls'] = service.get_project_urls(project_name)
        
        # Get actual project status by checking if containers are running
        project['actual_status'] = service.get_project_status(project)
        
        return render_template('project_detail.html', 
                             project=project,
                             deployments=deployments,
                             project_urls=project['urls'])
    except Exception as e:
        logging.error(f"Error loading project {project_name}: {str(e)}")
        flash('Error loading project details', 'error')
        return redirect(url_for('main.projects_ui'))


@bp.route("/deployment_history")
def deployment_history_ui():
    """Deployment history web interface."""
    try:
        service = services.Services()
        deployments = service.db.get_recent_deployments(50)  # Get last 50 deployments
        
        return render_template('deployment_history.html', deployments=deployments)
    except Exception as e:
        logging.error(f"Error loading deployment history: {str(e)}")
        flash('Error loading deployment history', 'error')
        return render_template('deployment_history.html', deployments=[])


@bp.route("/logs_ui")
def view_logs_ui():
    """Logs viewer web interface."""
    try:
        current_dir = Path(__file__).parent.parent
        
        # Read recent logs
        app_log_file = current_dir / "logs" / "app.log"
        deploy_log_file = current_dir / "logs" / "deploy.log"
        
        app_logs = ""
        deploy_logs = ""
        log_stats = {}
        
        if app_log_file.exists():
            with open(app_log_file, 'r') as f:
                lines = f.readlines()
                app_logs = ''.join(lines[-50:]) if lines else "No application logs yet."
            
            # Get file stats
            stat = app_log_file.stat()
            log_stats['app_log_size'] = f"{stat.st_size / 1024:.1f} KB"
        else:
            app_logs = "Application log file not found."
            log_stats['app_log_size'] = "N/A"
        
        if deploy_log_file.exists():
            with open(deploy_log_file, 'r') as f:
                lines = f.readlines()
                deploy_logs = ''.join(lines[-100:]) if lines else "No deployment logs yet."
            
            # Get file stats
            stat = deploy_log_file.stat()
            log_stats['deploy_log_size'] = f"{stat.st_size / 1024:.1f} KB"
            log_stats['last_modified'] = stat.st_mtime
        else:
            deploy_logs = "Deployment log file not found."
            log_stats['deploy_log_size'] = "N/A"
        
        # Format last modified time
        if 'last_modified' in log_stats:
            import datetime
            log_stats['last_modified'] = datetime.datetime.fromtimestamp(
                log_stats['last_modified']
            ).strftime('%Y-%m-%d %H:%M:%S')
        else:
            log_stats['last_modified'] = "N/A"
        
        return render_template('logs.html', 
                             app_logs=app_logs,
                             deploy_logs=deploy_logs,
                             log_stats=log_stats)
    except Exception as e:
        logging.error(f"Error loading logs: {str(e)}")
        flash('Error loading logs', 'error')
        return render_template('logs.html', 
                             app_logs="Error loading logs",
                             deploy_logs="Error loading logs",
                             log_stats={})


@bp.route("/deploy", methods=["POST"])
def deploy_project():
    """Deploy a project via web interface."""
    try:
        data = request.get_json() if request.is_json else request.form
        project_id = data.get('project_id')
        deployment_type = data.get('deployment_type', 'blue-green')
        
        if not project_id:
            if request.is_json:
                return jsonify(success=False, error='Project ID is required'), 400
            flash('Project ID is required', 'error')
            return redirect(url_for('main.projects_ui'))
        
        service = services.Services()
        project = service.db.get_project_by_id(project_id)
        
        if not project:
            if request.is_json:
                return jsonify(success=False, error='Project not found'), 404
            flash('Project not found', 'error')
            return redirect(url_for('main.projects_ui'))
        
        # Trigger deployment using existing logic
        repo_url = project['repo_url']
        project_name = project['repo_name']
        
        logging.info(f"Web UI deployment triggered for {project_name}")
        
        # Log deployment attempt
        service.log_deployment_status(
            project['id'], 
            'started',
            deployment_type=deployment_type
        )
        
        # Choose deployment script
        current_dir = Path(__file__).parent.parent
        if deployment_type == 'blue-green':
            deploy_script = current_dir / "blue_green_deploy.sh"
        else:
            deploy_script = current_dir / "deploy.sh"
        
        # Run deployment in background for web UI
        import threading
        
        def run_deployment():
            try:
                result = subprocess.run(
                    [str(deploy_script), repo_url], 
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                # Extract deployment info
                container_id = None
                deployment_uuid = None
                
                for line in result.stdout.strip().split('\n'):
                    if line.startswith("CONTAINER_ID:"):
                        container_id = line.split(':', 1)[1].strip()
                    elif line.startswith("DEPLOYMENT_UUID:"):
                        deployment_uuid = line.split(':', 1)[1].strip()
                
                # Log success
                service.log_deployment_status(
                    project['id'], 
                    'success',
                    container_id=container_id,
                    deployment_uuid=deployment_uuid,
                    deployment_type=deployment_type
                )
                
                logging.info(f"Web UI deployment completed for {project_name}")
                
            except Exception as e:
                error_msg = f"Web UI deployment failed: {str(e)}"
                logging.error(error_msg)
                service.log_deployment_status(
                    project['id'], 
                    'failed', 
                    error_message=error_msg,
                    deployment_type=deployment_type
                )
        
        # Start deployment in background
        deployment_thread = threading.Thread(target=run_deployment)
        deployment_thread.daemon = True
        deployment_thread.start()
        
        if request.is_json:
            return jsonify(success=True, message='Deployment started successfully')
        
        flash('Deployment started successfully!', 'success')
        return redirect(url_for('main.project_detail', project_name=project_name))
        
    except Exception as e:
        error_msg = f"Error starting deployment: {str(e)}"
        logging.error(error_msg)
        
        if request.is_json:
            return jsonify(success=False, error=error_msg), 500
        
        flash('Error starting deployment', 'error')
        return redirect(url_for('main.projects_ui'))


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
            
            # Parse both stdout and stderr for the output markers
            full_output = result.stdout + "\n" + result.stderr
            
            for line in full_output.strip().split('\n'):
                line = line.strip()
                if line.startswith("CONTAINER_ID:"):
                    container_id = line.split(':', 1)[1].strip()
                    logging.info(f"Extracted container ID: {container_id}")
                elif line.startswith("DEPLOYMENT_UUID:"):
                    deployment_uuid = line.split(':', 1)[1].strip()
                    logging.info(f"Extracted deployment UUID: {deployment_uuid}")
            
            # If we can't extract from output, try to get from log file
            if not container_id or not deployment_uuid:
                logging.warning("Could not extract container ID or UUID from script output, checking log file")
                log_file_path = current_dir / "logs" / "deploy.log"
                try:
                    with open(log_file_path, 'r') as log_file:
                        log_lines = log_file.readlines()[-50:]  # Check last 50 lines
                        for line in log_lines:
                            if "Primary container deployed:" in line and not container_id:
                                # Extract container ID from log line
                                parts = line.split("Primary container deployed:")
                                if len(parts) > 1:
                                    container_id = parts[1].strip()
                                    logging.info(f"Extracted container ID from log: {container_id}")
                            elif "Deployment UUID:" in line and not deployment_uuid:
                                # Extract UUID from log line
                                parts = line.split("Deployment UUID:")
                                if len(parts) > 1:
                                    deployment_uuid = parts[1].strip()
                                    logging.info(f"Extracted deployment UUID from log: {deployment_uuid}")
                except Exception as log_e:
                    logging.warning(f"Could not read deploy log: {log_e}")
            
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
    """Redirect to dashboard."""
    return redirect(url_for('main.dashboard'))


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
        
        # Parse both stdout and stderr for the output markers
        full_output = result.stdout + "\n" + result.stderr
        
        for line in full_output.strip().split('\n'):
            line = line.strip()
            if line.startswith("CONTAINER_ID:"):
                container_id = line.split(':', 1)[1].strip()
                logging.info(f"Manual deployment extracted container ID: {container_id}")
            elif line.startswith("DEPLOYMENT_UUID:"):
                deployment_uuid = line.split(':', 1)[1].strip()
                logging.info(f"Manual deployment extracted UUID: {deployment_uuid}")
        
        # If we can't extract from output, try to get from log file
        if not container_id or not deployment_uuid:
            logging.warning("Manual deployment: Could not extract container ID or UUID from script output")
            current_dir = Path(__file__).parent.parent
            log_file_path = current_dir / "logs" / "deploy.log"
            try:
                with open(log_file_path, 'r') as log_file:
                    log_lines = log_file.readlines()[-50:]  # Check last 50 lines
                    for line in log_lines:
                        if "Primary container deployed:" in line and not container_id:
                            parts = line.split("Primary container deployed:")
                            if len(parts) > 1:
                                container_id = parts[1].strip()
                                logging.info(f"Manual deployment extracted container ID from log: {container_id}")
                        elif "Deployment UUID:" in line and not deployment_uuid:
                            parts = line.split("Deployment UUID:")
                            if len(parts) > 1:
                                deployment_uuid = parts[1].strip()
                                logging.info(f"Manual deployment extracted UUID from log: {deployment_uuid}")
            except Exception as log_e:
                logging.warning(f"Manual deployment: Could not read deploy log: {log_e}")
        
        # Log successful deployment
        service.log_deployment_status(
            project['id'], 
            'success',
            container_id=container_id,
            deployment_uuid=deployment_uuid,
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
        
        return render_template('logs_viewer.html', app_logs=app_logs, deploy_logs=deploy_logs)
        
    except Exception as e:
        logging.error(f"Error viewing logs: {str(e)}")
        return jsonify(error="Failed to load logs"), 500
