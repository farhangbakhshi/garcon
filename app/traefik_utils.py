"""
Docker Compose file modification utilities for Traefik integration.
"""
import yaml
import os
import re
import logging
from typing import Dict, Any, Optional


class DockerComposeModifier:
    """Modifies docker-compose.yml files to integrate with Traefik reverse proxy."""
    
    def __init__(self, compose_file_path: str, project_name: str):
        self.compose_file_path = compose_file_path
        self.project_name = project_name
        self.domain_suffix = "localhost"  # Can be configured for production
        self.logger = logging.getLogger(__name__)
        
    def modify_compose_file(self) -> bool:
        """
        Modify the docker-compose.yml file to integrate with Traefik.
        
        Returns:
            bool: True if modification was successful, False otherwise.
        """
        try:
            self.logger.info(f"Starting modification of {self.compose_file_path} for project {self.project_name}")
            
            if not os.path.exists(self.compose_file_path):
                self.logger.error(f"Docker compose file not found: {self.compose_file_path}")
                return False
                
            with open(self.compose_file_path, 'r') as file:
                compose_data = yaml.safe_load(file)
                
            if not compose_data:
                self.logger.error("Empty or invalid docker-compose.yml file")
                return False
                
            # Log original structure
            services_count = len(compose_data.get('services', {}))
            self.logger.debug(f"Original compose file has {services_count} services")
                
            # Modify the compose data
            modified_data = self._add_traefik_configuration(compose_data)
            
            # Write back to file
            with open(self.compose_file_path, 'w') as file:
                yaml.dump(modified_data, file, default_flow_style=False, sort_keys=False)
                
            self.logger.info(f"Successfully modified {self.compose_file_path} for Traefik integration")
            return True
            
        except Exception as e:
            self.logger.error(f"Error modifying docker-compose.yml: {str(e)}", exc_info=True)
            return False
            
    def _add_traefik_configuration(self, compose_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add Traefik configuration to docker-compose data."""
        
        self.logger.debug("Adding Traefik configuration to compose data")
        
        # Ensure services exist
        if 'services' not in compose_data:
            compose_data['services'] = {}
            self.logger.debug("Created empty services section")
            
        # Ensure networks section exists
        if 'networks' not in compose_data:
            compose_data['networks'] = {}
            self.logger.debug("Created empty networks section")
            
        # Add web-proxy network as external
        compose_data['networks']['web-proxy'] = {'external': True}
        self.logger.debug("Added web-proxy external network")
        
        # Process each service
        service_counter = 0
        for service_name, service_config in compose_data['services'].items():
            service_counter += 1
            self.logger.debug(f"Processing service {service_counter}: {service_name}")
            
            self._configure_service_for_traefik(
                service_name, 
                service_config, 
                service_counter
            )
            
        self.logger.info(f"Configured {service_counter} services for Traefik integration")
        return compose_data
        
    def _configure_service_for_traefik(
        self, 
        service_name: str, 
        service_config: Dict[str, Any], 
        service_counter: int
    ) -> None:
        """Configure a single service for Traefik."""
        
        self.logger.debug(f"Configuring service {service_name} for Traefik")
        
        # Add web-proxy network to service
        if 'networks' not in service_config:
            service_config['networks'] = []
        elif isinstance(service_config['networks'], dict):
            # Convert dict format to list format and add web-proxy
            networks_dict = service_config['networks'].copy()
            service_config['networks'] = list(networks_dict.keys()) + ['web-proxy']
        elif isinstance(service_config['networks'], list):
            if 'web-proxy' not in service_config['networks']:
                service_config['networks'].append('web-proxy')
        else:
            service_config['networks'] = ['web-proxy']
        
        self.logger.debug(f"Updated networks for {service_name}: {service_config['networks']}")
            
        # Ensure labels section exists
        if 'labels' not in service_config:
            service_config['labels'] = []
        elif isinstance(service_config['labels'], dict):
            # Convert dict labels to list format
            labels_list = []
            for key, value in service_config['labels'].items():
                labels_list.append(f"{key}={value}")
            service_config['labels'] = labels_list
            self.logger.debug(f"Converted labels from dict to list format for {service_name}")
            
        # Remove ports that would conflict (let Traefik handle routing)
        exposed_ports = self._extract_and_remove_ports(service_config)
        
        # Generate unique subdomain for this service
        subdomain = f"{self.project_name}-{service_name}".lower()
        subdomain = re.sub(r'[^a-z0-9-]', '-', subdomain)
        
        # Add Traefik labels
        traefik_labels = [
            "traefik.enable=true",
            f"traefik.http.routers.{subdomain}.rule=Host(`{subdomain}.{self.domain_suffix}`)",
            f"traefik.http.routers.{subdomain}.entrypoints=web",
            "traefik.docker.network=web-proxy",
            f"project={self.project_name}"  # Add project label for blue-green identification
        ]
        
        # If we found exposed ports, use the first one for Traefik service
        if exposed_ports:
            primary_port = exposed_ports[0]
            traefik_labels.append(
                f"traefik.http.services.{subdomain}.loadbalancer.server.port={primary_port}"
            )
            self.logger.info(f"Service {service_name} will be available at: http://{subdomain}.{self.domain_suffix} (port {primary_port})")
        else:
            # Try to detect common ports or use 80 as default
            detected_port = self._detect_port_from_service(service_config)
            default_port = detected_port if detected_port else 80
                
            traefik_labels.append(
                f"traefik.http.services.{subdomain}.loadbalancer.server.port={default_port}"
            )
            self.logger.info(f"Service {service_name} will be available at: http://{subdomain}.{self.domain_suffix} (using detected/default port {default_port})")
            
        # Add labels to service
        service_config['labels'].extend(traefik_labels)
        self.logger.debug(f"Added {len(traefik_labels)} Traefik labels to {service_name}")
        
    def _extract_and_remove_ports(self, service_config: Dict[str, Any]) -> list:
        """Extract port information and remove ports section to avoid conflicts."""
        exposed_ports = []
        
        if 'ports' in service_config:
            ports = service_config['ports']
            self.logger.debug(f"Found ports configuration: {ports}")
            
            for port_mapping in ports:
                if isinstance(port_mapping, str):
                    # Handle "host:container" or just "port" format
                    if ':' in port_mapping:
                        container_port = port_mapping.split(':')[1]
                    else:
                        container_port = port_mapping
                elif isinstance(port_mapping, int):
                    container_port = str(port_mapping)
                elif isinstance(port_mapping, dict):
                    # Handle long syntax
                    container_port = str(port_mapping.get('target', 80))
                else:
                    continue
                    
                # Extract numeric port
                port_num = re.findall(r'\d+', container_port)
                if port_num:
                    exposed_ports.append(int(port_num[0]))
                    
            # Remove the ports section since Traefik will handle routing
            del service_config['ports']
            self.logger.info(f"Extracted and removed ports {exposed_ports} - Traefik will handle routing")
            
        return exposed_ports
        
    def _detect_port_from_service(self, service_config: Dict[str, Any]) -> Optional[int]:
        """Try to detect the port a service uses from its configuration."""
        
        self.logger.debug("Attempting to detect port from service configuration")
        
        # Check environment variables for common port variables
        if 'environment' in service_config:
            env_vars = service_config['environment']
            port_env_vars = ['PORT', 'HTTP_PORT', 'SERVER_PORT', 'APP_PORT', 'WEB_PORT']
            
            if isinstance(env_vars, list):
                for env_var in env_vars:
                    if isinstance(env_var, str):
                        for port_var in port_env_vars:
                            if env_var.startswith(f"{port_var}="):
                                try:
                                    port = int(env_var.split('=')[1])
                                    self.logger.debug(f"Detected port {port} from environment variable {env_var}")
                                    return port
                                except (ValueError, IndexError):
                                    continue
            elif isinstance(env_vars, dict):
                for port_var in port_env_vars:
                    if port_var in env_vars:
                        try:
                            port = int(env_vars[port_var])
                            self.logger.debug(f"Detected port {port} from environment variable {port_var}")
                            return port
                        except (ValueError, TypeError):
                            continue
                            
        # Check if expose directive exists
        if 'expose' in service_config:
            exposed = service_config['expose']
            if exposed and len(exposed) > 0:
                try:
                    port = int(exposed[0])
                    self.logger.debug(f"Detected port {port} from expose directive")
                    return port
                except (ValueError, TypeError):
                    pass
                    
        # Check image name for common frameworks
        if 'image' in service_config:
            image = service_config['image'].lower()
            if 'nginx' in image:
                self.logger.debug("Detected nginx image, using port 80")
                return 80
            elif 'apache' in image:
                self.logger.debug("Detected apache image, using port 80")
                return 80
            elif 'node' in image or 'express' in image:
                self.logger.debug("Detected node/express image, using port 3000")
                return 3000
            elif 'python' in image or 'flask' in image or 'django' in image:
                self.logger.debug("Detected python/flask/django image, using port 8000")
                return 8000
            elif 'tomcat' in image:
                self.logger.debug("Detected tomcat image, using port 8080")
                return 8080
                
        self.logger.debug("Could not detect port from service configuration")
        return None
