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
                        FOREIGN KEY (project_id) REFERENCES projects (id)
                    )
                ''')
                
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
    
    def add_or_update_project(self, repo_name, repo_url, local_path=None, container_id=None):
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
                            updated_at = CURRENT_TIMESTAMP
                        WHERE repo_name = ?
                    ''', (repo_url, local_path, container_id, repo_name))
                    project_id = existing_project['id']
                    logging.info(f"Updated existing project: {repo_name}")
                else:
                    # Insert new project
                    cursor.execute('''
                        INSERT INTO projects (repo_name, repo_url, local_path, container_id)
                        VALUES (?, ?, ?, ?)
                    ''', (repo_name, repo_url, local_path, container_id))
                    project_id = cursor.lastrowid
                    logging.info(f"Added new project: {repo_name}")
                
                conn.commit()
                return project_id
                
        except sqlite3.Error as e:
            logging.error(f"Error adding/updating project {repo_name}: {e}")
            return None
    
    def log_deployment(self, project_id, status, commit_hash=None, error_message=None):
        """Log a deployment attempt."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO deployments (project_id, status, commit_hash, error_message)
                    VALUES (?, ?, ?, ?)
                ''', (project_id, status, commit_hash, error_message))
                
                conn.commit()
                logging.info(f"Logged deployment for project ID {project_id}: {status}")
                
        except sqlite3.Error as e:
            logging.error(f"Error logging deployment: {e}")
    
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
                logging.info(f"Updated container ID for project ID {project_id}")
                
        except sqlite3.Error as e:
            logging.error(f"Error updating container ID for project {project_id}: {e}")