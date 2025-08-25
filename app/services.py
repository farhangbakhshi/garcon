import logging
from .models import DatabaseManager


class Services:
    def __init__(self):
        self.db = DatabaseManager()
    
    def process_webhook(self, repository_payload):
        """Process the webhook payload and return repository information."""
        repo_name = repository_payload.get('repository', {}).get('name')
        repo_url = repository_payload.get('repository', {}).get('html_url')
        
        # Extract commit information if available
        commit_hash = None
        if 'head_commit' in repository_payload and repository_payload['head_commit']:
            commit_hash = repository_payload['head_commit'].get('id')
        
        return {
            'repo_name': repo_name, 
            'repo_url': repo_url,
            'commit_hash': commit_hash
        }
    
    def get_or_create_project(self, repo_name, repo_url):
        """Get existing project or create a new one."""
        existing_project = self.db.get_project_by_repo_name(repo_name)
        
        if existing_project:
            logging.info(f"Found existing project: {repo_name}")
            return existing_project
        else:
            logging.info(f"Creating new project: {repo_name}")
            project_id = self.db.add_or_update_project(repo_name, repo_url)
            if project_id:
                return self.db.get_project_by_repo_name(repo_name)
            return None
    
    def update_project_deployment_info(self, repo_name, local_path=None, container_id=None):
        """Update project with deployment information."""
        existing_project = self.db.get_project_by_repo_name(repo_name)
        if existing_project:
            repo_url = existing_project['repo_url']
            self.db.add_or_update_project(repo_name, repo_url, local_path, container_id)
            logging.info(f"Updated deployment info for {repo_name}")
    
    def log_deployment_status(self, project_id, status, commit_hash=None, error_message=None):
        """Log the deployment status."""
        self.db.log_deployment(project_id, status, commit_hash, error_message)