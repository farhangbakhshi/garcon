import sqlite3
import logging
from datetime import datetime
from pathlib import Path


class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Default to the data/projects.db file
            current_dir = Path(__file__).parent.parent
            data_dir = current_dir / "data"
            data_dir.mkdir(exist_ok=True) # Ensure the directory exists
            db_path = data_dir / "projects.db"
        
        self.db_path = str(db_path)
        self.init_database()
    
    def init_database(self):
        """Initialize the database and create tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create projects table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        repo_name TEXT UNIQUE NOT NULL,
                        repo_url TEXT NOT NULL,
                        local_path TEXT,
                        container_id TEXT,
                        deployment_uuid TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create deployments table to track deployment history
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS deployments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        deploy_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        commit_hash TEXT,
                        error_message TEXT,
                        container_id TEXT,
                        deployment_uuid TEXT,
                        deployment_type TEXT DEFAULT 'blue-green',
                        FOREIGN KEY (project_id) REFERENCES projects (id)
                    )
                ''')
                
                # Add deployment_uuid column to projects table if it doesn't exist
                cursor.execute("PRAGMA table_info(projects)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'deployment_uuid' not in columns:
                    cursor.execute('ALTER TABLE projects ADD COLUMN deployment_uuid TEXT')
                    logging.info("Added deployment_uuid column to projects table")
                
                # Add columns to deployments table if they don't exist
                cursor.execute("PRAGMA table_info(deployments)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'container_id' not in columns:
                    cursor.execute('ALTER TABLE deployments ADD COLUMN container_id TEXT')
                    logging.info("Added container_id column to deployments table")
                if 'deployment_uuid' not in columns:
                    cursor.execute('ALTER TABLE deployments ADD COLUMN deployment_uuid TEXT')
                    logging.info("Added deployment_uuid column to deployments table")
                if 'deployment_type' not in columns:
                    cursor.execute('ALTER TABLE deployments ADD COLUMN deployment_type TEXT DEFAULT "blue-green"')
                    logging.info("Added deployment_type column to deployments table")
                
                conn.commit()
                logging.info("Database initialized successfully")
                
        except sqlite3.Error as e:
            logging.error(f"Database initialization error: {e}")
            raise
    
    def get_project_by_repo_name(self, repo_name):
        """Get project information by repository name."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Enable column access by name
                cursor = conn.cursor()
                
                cursor.execute(
                    'SELECT * FROM projects WHERE repo_name = ?', 
                    (repo_name,)
                )
                result = cursor.fetchone()
                return dict(result) if result else None
                
        except sqlite3.Error as e:
            logging.error(f"Error fetching project {repo_name}: {e}")
            return None
    
    def get_project_by_id(self, project_id):
        """Get project information by project ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Enable column access by name
                cursor = conn.cursor()
                
                cursor.execute(
                    'SELECT * FROM projects WHERE id = ?', 
                    (project_id,)
                )
                result = cursor.fetchone()
                return dict(result) if result else None
                
        except sqlite3.Error as e:
            logging.error(f"Error fetching project with ID {project_id}: {e}")
            return None
    
    def add_or_update_project(self, repo_name, repo_url, local_path=None, container_id=None, deployment_uuid=None):
        """Add a new project or update an existing one."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if project exists
                existing_project = self.get_project_by_repo_name(repo_name)
                
                if existing_project:
                    # Update existing project
                    cursor.execute('''
                        UPDATE projects 
                        SET repo_url = ?, local_path = ?, container_id = ?, 
                            deployment_uuid = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE repo_name = ?
                    ''', (repo_url, local_path, container_id, deployment_uuid, repo_name))
                    project_id = existing_project['id']
                    logging.info(f"Updated existing project: {repo_name}")
                else:
                    # Insert new project
                    cursor.execute('''
                        INSERT INTO projects (repo_name, repo_url, local_path, container_id, deployment_uuid)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (repo_name, repo_url, local_path, container_id, deployment_uuid))
                    project_id = cursor.lastrowid
                    logging.info(f"Added new project: {repo_name}")
                
                conn.commit()
                return project_id
                
        except sqlite3.Error as e:
            logging.error(f"Error adding/updating project {repo_name}: {e}")
            return None
    
    def log_deployment(self, project_id, status, commit_hash=None, error_message=None, container_id=None, deployment_uuid=None, deployment_type='blue-green'):
        """Log a deployment attempt with comprehensive information."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO deployments 
                    (project_id, status, commit_hash, error_message, container_id, deployment_uuid, deployment_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (project_id, status, commit_hash, error_message, container_id, deployment_uuid, deployment_type))
                
                conn.commit()
                logging.info(f"Logged {deployment_type} deployment for project ID {project_id}: {status}")
                
        except sqlite3.Error as e:
            logging.error(f"Error logging deployment: {e}")
    
    def get_deployment_history(self, project_id, limit=50):
        """Get deployment history for a project."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM deployments 
                    WHERE project_id = ? 
                    ORDER BY deploy_time DESC 
                    LIMIT ?
                ''', (project_id, limit))
                
                results = cursor.fetchall()
                return [dict(row) for row in results]
                
        except sqlite3.Error as e:
            logging.error(f"Error fetching deployment history for project {project_id}: {e}")
            return []
    
    def get_recent_deployments(self, limit=20):
        """Get recent deployments across all projects."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT d.*, p.repo_name 
                    FROM deployments d
                    JOIN projects p ON d.project_id = p.id
                    ORDER BY d.deploy_time DESC 
                    LIMIT ?
                ''', (limit,))
                
                results = cursor.fetchall()
                return [dict(row) for row in results]
                
        except sqlite3.Error as e:
            logging.error(f"Error fetching recent deployments: {e}")
            return []
    
    def get_all_projects(self):
        """Get all projects in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('SELECT * FROM projects ORDER BY created_at DESC')
                results = cursor.fetchall()
                return [dict(row) for row in results]
                
        except sqlite3.Error as e:
            logging.error(f"Error fetching all projects: {e}")
            return []

    def get_project_count(self):
        """Get the total count of projects."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM projects')
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logging.error(f"Error fetching project count: {e}")
            return 0

    def get_deployment_count(self):
        """Get the total count of deployments."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM deployments')
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logging.error(f"Error fetching deployment count: {e}")
            return 0

    def update_project_container_id(self, project_id, container_id):
        """Update the container_id for a specific project."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE projects 
                    SET container_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (container_id, project_id))
                
                conn.commit()
                if container_id:
                    logging.info(f"Updated container ID for project ID {project_id}: {container_id}")
                else:
                    logging.info(f"Cleared container ID for project ID {project_id}")
                
        except sqlite3.Error as e:
            logging.error(f"Error updating container ID for project {project_id}: {e}")
    
    def delete_project(self, project_id):
        """Delete a project from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
                deleted_count = cursor.rowcount
                
                conn.commit()
                if deleted_count > 0:
                    logging.info(f"Deleted project with ID {project_id} from database")
                else:
                    logging.warning(f"No project found with ID {project_id} to delete")
                
                return deleted_count > 0
                
        except sqlite3.Error as e:
            logging.error(f"Error deleting project {project_id}: {e}")
            return False
    
    def delete_deployment_history(self, project_id):
        """Delete all deployment history for a project."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM deployments WHERE project_id = ?', (project_id,))
                deleted_count = cursor.rowcount
                
                conn.commit()
                logging.info(f"Deleted {deleted_count} deployment records for project ID {project_id}")
                
                return deleted_count
                
        except sqlite3.Error as e:
            logging.error(f"Error deleting deployment history for project {project_id}: {e}")
            return 0