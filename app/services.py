import logging
import re
import uuid
from datetime import datetime
from .models import DatabaseManager


class Services:
    def __init__(self):
        self.db = DatabaseManager()
        self.logger = logging.getLogger(__name__)
    
    def process_webhook(self, repository_payload):
        """Process the webhook payload and return repository information."""
        self.logger.info("Processing webhook payload")
        self.logger.debug(f"Webhook payload keys: {list(repository_payload.keys())}")
        
        repo_name = repository_payload.get('repository', {}).get('name')
        repo_url = repository_payload.get('repository', {}).get('html_url')
        
        # Extract commit information if available
        commit_hash = None
        if 'head_commit' in repository_payload and repository_payload['head_commit']:
            commit_hash = repository_payload['head_commit'].get('id')
            self.logger.info(f"Webhook triggered by commit: {commit_hash[:8]}...")
        
        self.logger.info(f"Processed webhook for repository: {repo_name}")
        
        return {
            'repo_name': repo_name, 
            'repo_url': repo_url,
            'commit_hash': commit_hash
        }
    
    def get_or_create_project(self, repo_name, repo_url):
        """Get existing project or create a new one."""
        self.logger.debug(f"Looking up project: {repo_name}")
        existing_project = self.db.get_project_by_repo_name(repo_name)
        
        if existing_project:
            self.logger.info(f"Found existing project: {repo_name} (ID: {existing_project.get('id')})")
            return existing_project
        else:
            self.logger.info(f"Creating new project: {repo_name}")
            try:
                project_id = self.db.add_or_update_project(repo_name, repo_url)
                if project_id:
                    self.logger.info(f"Successfully created project {repo_name} with ID: {project_id}")
                    return self.db.get_project_by_repo_name(repo_name)
                else:
                    self.logger.error(f"Failed to create project {repo_name}: no ID returned")
                    return None
            except Exception as e:
                self.logger.error(f"Exception while creating project {repo_name}: {str(e)}", exc_info=True)
                return None
    
    def update_project_deployment_info(self, repo_name, local_path=None, container_id=None, deployment_uuid=None):
        """Update project with deployment information."""
        self.logger.debug(f"Updating deployment info for {repo_name}")
        
        try:
            existing_project = self.db.get_project_by_repo_name(repo_name)
            if existing_project:
                repo_url = existing_project['repo_url']
                self.db.add_or_update_project(repo_name, repo_url, local_path, container_id)
                
                self.logger.info(f"Updated deployment info for {repo_name}")
                if container_id:
                    self.logger.info(f"  Container ID: {container_id}")
                if deployment_uuid:
                    self.logger.info(f"  Deployment UUID: {deployment_uuid}")
                if local_path:
                    self.logger.debug(f"  Local path: {local_path}")
            else:
                self.logger.warning(f"Project {repo_name} not found for deployment info update")
        except Exception as e:
            self.logger.error(f"Failed to update deployment info for {repo_name}: {str(e)}", exc_info=True)
    
    def log_deployment_status(self, project_id, status, commit_hash=None, error_message=None, container_id=None, deployment_uuid=None, deployment_type='blue-green'):
        """Log the deployment status with comprehensive information."""
        self.logger.info(f"Logging deployment status: {status} for project ID: {project_id}")
        
        try:
            self.db.log_deployment(
                project_id, 
                status, 
                commit_hash, 
                error_message, 
                container_id, 
                deployment_uuid, 
                deployment_type
            )
            
            if status == 'success' and container_id:
                self.db.update_project_container_id(project_id, container_id)
                self.logger.info(f"Updated project {project_id} with container ID: {container_id}")
            
            # Additional logging for debugging
            if status == 'started':
                self.logger.info(f"{deployment_type.title()} deployment started for project {project_id}")
                if commit_hash:
                    self.logger.info(f"  Commit hash: {commit_hash}")
            elif status == 'success':
                self.logger.info(f"{deployment_type.title()} deployment succeeded for project {project_id}")
                if container_id:
                    self.logger.info(f"  New container: {container_id}")
                if deployment_uuid:
                    self.logger.info(f"  Deployment UUID: {deployment_uuid}")
            elif status == 'failed':
                self.logger.error(f"{deployment_type.title()} deployment failed for project {project_id}")
                if error_message:
                    self.logger.error(f"  Error: {error_message}")
                    
        except Exception as e:
            self.logger.error(f"Failed to log deployment status: {str(e)}", exc_info=True)
        
    def get_project_urls(self, repo_name):
        """Generate Traefik URLs for a project's services."""
        self.logger.debug(f"Generating URLs for project: {repo_name}")
        
        urls = []
        domain_suffix = "localhost"
        
        # Clean project name for subdomain
        clean_name = re.sub(r'[^a-z0-9-]', '-', repo_name.lower())
        self.logger.debug(f"Clean project name for URLs: {clean_name}")
        
        # For now, we'll assume common service names
        # In a more advanced implementation, this could parse the actual compose file
        common_services = ['web', 'app', 'frontend', 'backend', 'api', 'server']
        
        # Generate potential URLs
        # Primary URL (just project name)
        primary_url = f"http://{clean_name}.{domain_suffix}"
        urls.append(primary_url)
        self.logger.debug(f"Added primary URL: {primary_url}")
        
        # Service-specific URLs
        for service in common_services:
            service_url = f"http://{clean_name}-{service}.{domain_suffix}"
            urls.append(service_url)
            
        self.logger.info(f"Generated {len(urls)} potential URLs for project {repo_name}")
        return urls
    
    def get_deployment_metrics(self, repo_name=None):
        """Get deployment metrics and statistics."""
        try:
            if repo_name:
                project = self.db.get_project_by_repo_name(repo_name)
                if not project:
                    self.logger.warning(f"Project {repo_name} not found for metrics")
                    return None
                
                # Get deployment history for this project
                deployments = self.db.get_deployment_history(project['id'])
                self.logger.info(f"Retrieved {len(deployments)} deployment records for {repo_name}")
                
                return {
                    'project': project,
                    'deployments': deployments,
                    'total_deployments': len(deployments)
                }
            else:
                # Get overall metrics
                projects = self.db.get_all_projects()
                total_deployments = sum(len(self.db.get_deployment_history(p['id'])) for p in projects)
                
                self.logger.info(f"Retrieved metrics: {len(projects)} projects, {total_deployments} total deployments")
                
                return {
                    'total_projects': len(projects),
                    'total_deployments': total_deployments,
                    'projects': projects
                }
        except Exception as e:
            self.logger.error(f"Failed to get deployment metrics: {str(e)}", exc_info=True)
            return None