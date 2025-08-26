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
        
    def modify_compose_file(self) -> bool:
        """
        Modify the docker-compose.yml file to integrate with Traefik.
        
        Returns:
            bool: True if modification was successful, False otherwise.
        """
        try:
            if not os.path.exists(self.compose_file_path):
                logging.error(f"Docker compose file not found: {self.compose_file_path}")
                return False
                
            with open(self.compose_file_path, 'r') as file:
                compose_data = yaml.safe_load(file)
                
            if not compose_data:
                logging.error("Empty or invalid docker-compose.yml file")
                return False
                
            # Modify the compose data
            modified_data = self._add_traefik_configuration(compose_data)
            
            # Write back to file
            with open(self.compose_file_path, 'w') as file:
                yaml.dump(modified_data, file, default_flow_style=False, sort_keys=False)
                
            logging.info(f"Successfully modified {self.compose_file_path} for Traefik integration")
            return True
            
        except Exception as e:
            logging.error(f"Error modifying docker-compose.yml: {str(e)}")
            return False
            
    def _add_traefik_configuration(self, compose_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add Traefik configuration to docker-compose data."""
        
        # Ensure services exist
        if 'services' not in compose_data:
            compose_data['services'] = {}
            
        # Ensure networks section exists
        if 'networks' not in compose_data:
            compose_data['networks'] = {}
            
        # Add web-proxy network as external
        compose_data['networks']['web-proxy'] = {'external': True}
        
        # Process each service
        service_counter = 0
        for service_name, service_config in compose_data['services'].items():
            service_counter += 1
            self._configure_service_for_traefik(
                service_name, 
                service_config, 
                service_counter
            )
            
        return compose_data
        
    def _configure_service_for_traefik(
        self, 
        service_name: str, 
        service_config: Dict[str, Any], 
        service_counter: int
    ) -> None:
        """Configure a single service for Traefik."""
        
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
            
        # Ensure labels section exists
        if 'labels' not in service_config:
            service_config['labels'] = []
        elif isinstance(service_config['labels'], dict):
            # Convert dict labels to list format
            labels_list = []
            for key, value in service_config['labels'].items():
                labels_list.append(f"{key}={value}")
            service_config['labels'] = labels_list
            
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
            "traefik.docker.network=web-proxy"
        ]
        
        # If we found exposed ports, use the first one for Traefik service
        if exposed_ports:
            primary_port = exposed_ports[0]
            traefik_labels.append(
                f"traefik.http.services.{subdomain}.loadbalancer.server.port={primary_port}"
            )
            logging.info(f"Service {service_name} will be available at: http://{subdomain}.{self.domain_suffix}")
        else:
            # Try to detect common ports or use 80 as default
            common_ports = [80, 3000, 8080, 5000, 8000, 9000]
            default_port = 80
            
            # Check if any common ports are mentioned in the image or environment
            detected_port = self._detect_port_from_service(service_config)
            if detected_port:
                default_port = detected_port
                
            traefik_labels.append(
                f"traefik.http.services.{subdomain}.loadbalancer.server.port={default_port}"
            )
            logging.info(f"Service {service_name} will be available at: http://{subdomain}.{self.domain_suffix} (using detected/default port {default_port})")
            
        # Add labels to service
        service_config['labels'].extend(traefik_labels)
        
    def _extract_and_remove_ports(self, service_config: Dict[str, Any]) -> list:
        """Extract port information and remove ports section to avoid conflicts."""
        exposed_ports = []
        
        if 'ports' in service_config:
            ports = service_config['ports']
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
            logging.info(f"Removed ports {exposed_ports} from service - Traefik will handle routing")
            
        return exposed_ports
        
    def _detect_port_from_service(self, service_config: Dict[str, Any]) -> Optional[int]:
        """Try to detect the port a service uses from its configuration."""
        
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
                                    return int(env_var.split('=')[1])
                                except (ValueError, IndexError):
                                    continue
            elif isinstance(env_vars, dict):
                for port_var in port_env_vars:
                    if port_var in env_vars:
                        try:
                            return int(env_vars[port_var])
                        except (ValueError, TypeError):
                            continue
                            
        # Check if expose directive exists
        if 'expose' in service_config:
            exposed = service_config['expose']
            if exposed and len(exposed) > 0:
                try:
                    return int(exposed[0])
                except (ValueError, TypeError):
                    pass
                    
        # Check image name for common frameworks
        if 'image' in service_config:
            image = service_config['image'].lower()
            if 'nginx' in image:
                return 80
            elif 'apache' in image:
                return 80
            elif 'node' in image or 'express' in image:
                return 3000
            elif 'python' in image or 'flask' in image or 'django' in image:
                return 8000
            elif 'tomcat' in image:
                return 8080
                
        return None
