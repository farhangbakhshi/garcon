// Garcon Frontend JavaScript

// Global variables
let deploymentSocket = null;

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    initializeTooltips();
    initializeModals();
    initializeDeploymentButtons();
    initializeDeleteConfirmation();
    initializeWebSocket();
});

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize Bootstrap modals
function initializeModals() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
}

// Initialize deployment buttons
function initializeDeploymentButtons() {
    const deployButtons = document.querySelectorAll('.deploy-btn');
    deployButtons.forEach(button => {
        button.addEventListener('click', handleDeployment);
    });
    
    // Add event listener for confirm deploy button using event delegation
    document.addEventListener('click', function(event) {
        if (event.target.id === 'confirmDeploy' || event.target.closest('#confirmDeploy')) {
            event.preventDefault();
            const modal = document.getElementById('deployModal');
            const projectId = parseInt(modal.dataset.projectId);
            const deploymentType = document.getElementById('deploymentType').value;
            
            // Hide modal
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) {
                bsModal.hide();
            }
            
            // Start deployment
            startDeployment(projectId, deploymentType);
        }
    });
}

// Handle deployment button clicks
function handleDeployment(event) {
    const button = event.target.closest('.deploy-btn');
    const projectId = button.dataset.projectId;
    const projectName = button.dataset.project;
    const deploymentType = button.dataset.deploymentType || 'blue-green';
    
    // Show confirmation modal
    showDeploymentModal(projectId, projectName, deploymentType);
}

// Show deployment confirmation modal
function showDeploymentModal(projectId, projectName, deploymentType) {
    const modal = document.getElementById('deployModal');
    
    // Update modal content
    document.getElementById('deploy-project-name').textContent = projectName;
    document.getElementById('deploymentType').value = deploymentType;
    
    // Store project ID for later use
    modal.dataset.projectId = projectId;
    
    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Start deployment process
function startDeployment(projectId, deploymentType) {
    // Show loading notification
    showNotification('Starting deployment...', 'info');
    
    // Make deployment request
    fetch('/deploy', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
            project_id: projectId,
            deployment_type: deploymentType
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Deployment started successfully!', 'success');
            // Refresh page after a delay to show updated status
            setTimeout(() => location.reload(), 2000);
        } else {
            showNotification(data.error || 'Deployment failed', 'danger');
        }
    })
    .catch(error => {
        console.error('Deployment error:', error);
        showNotification('Network error during deployment', 'danger');
    });
}

// Show notification toast
function showNotification(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    // Remove toast element after it's hidden
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

// Create toast container if it doesn't exist
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '11';
    document.body.appendChild(container);
    return container;
}

// Initialize WebSocket connection for real-time updates
function initializeWebSocket() {
    // Only initialize on pages that need real-time updates
    if (!document.body.classList.contains('needs-websocket')) {
        return;
    }
    
    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        deploymentSocket = new WebSocket(wsUrl);
        
        deploymentSocket.onopen = function(event) {
            console.log('WebSocket connected');
        };
        
        deploymentSocket.onmessage = function(event) {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        };
        
        deploymentSocket.onclose = function(event) {
            console.log('WebSocket disconnected');
            // Attempt to reconnect after 5 seconds
            setTimeout(initializeWebSocket, 5000);
        };
        
        deploymentSocket.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    } catch (error) {
        console.error('WebSocket initialization failed:', error);
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'deployment_status':
            updateDeploymentStatus(data.project_id, data.status);
            break;
        case 'deployment_complete':
            showNotification(`Deployment completed for ${data.project_name}`, 'success');
            updateProjectStatus(data.project_id, 'running');
            break;
        case 'deployment_failed':
            showNotification(`Deployment failed for ${data.project_name}: ${data.error}`, 'danger');
            updateProjectStatus(data.project_id, 'stopped');
            break;
        default:
            console.log('Unknown WebSocket message type:', data.type);
    }
}

// Update deployment status in UI
function updateDeploymentStatus(projectId, status) {
    const statusElement = document.querySelector(`[data-project-id="${projectId}"] .project-status`);
    if (statusElement) {
        statusElement.className = `badge status-${status}`;
        statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        
        // Add pulse animation for deploying status
        if (status === 'deploying') {
            statusElement.classList.add('deploying');
        } else {
            statusElement.classList.remove('deploying');
        }
    }
}

// Update project status
function updateProjectStatus(projectId, status) {
    updateDeploymentStatus(projectId, status);
    
    // Update any deployment buttons
    const deployButton = document.querySelector(`[data-project-id="${projectId}"].deploy-btn`);
    if (deployButton) {
        deployButton.disabled = status === 'deploying';
    }
}

// Utility functions
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    } else if (seconds < 3600) {
        return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Form validation
function validateProjectForm(form) {
    const name = form.querySelector('[name="name"]').value.trim();
    const gitUrl = form.querySelector('[name="git_url"]').value.trim();
    const domain = form.querySelector('[name="domain"]').value.trim();
    
    if (!name || !gitUrl || !domain) {
        showNotification('Please fill in all required fields', 'warning');
        return false;
    }
    
    // Basic URL validation
    const urlPattern = /^https?:\/\/.+/;
    if (!urlPattern.test(gitUrl)) {
        showNotification('Please enter a valid Git URL', 'warning');
        return false;
    }
    
    // Basic domain validation
    const domainPattern = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$/;
    if (!domainPattern.test(domain)) {
        showNotification('Please enter a valid domain name', 'warning');
        return false;
    }
    
    return true;
}

// Add event listeners for forms
document.addEventListener('submit', function(event) {
    const form = event.target;
    
    if (form.id === 'addProjectForm') {
        if (!validateProjectForm(form)) {
            event.preventDefault();
        }
    }
});

// Add confirmation for destructive actions
document.addEventListener('click', function(event) {
    const element = event.target;
    
    if (element.classList.contains('btn-danger') || element.dataset.confirm) {
        const message = element.dataset.confirm || 'Are you sure you want to perform this action?';
        if (!confirm(message)) {
            event.preventDefault();
        }
    }
});

// Auto-refresh functionality for logs page
let logAutoRefresh = null;

function toggleLogAutoRefresh() {
    const button = document.getElementById('autoRefreshBtn');
    const status = document.getElementById('autoRefreshStatus');
    
    if (logAutoRefresh) {
        clearInterval(logAutoRefresh);
        logAutoRefresh = null;
        status.textContent = 'Off';
        button.classList.remove('btn-success');
        button.classList.add('btn-outline-info');
    } else {
        logAutoRefresh = setInterval(() => {
            location.reload();
        }, 10000);
        status.textContent = 'On (10s)';
        button.classList.remove('btn-outline-info');
        button.classList.add('btn-success');
    }
}

// Initialize delete confirmation
function initializeDeleteConfirmation() {
    const deleteConfirmationInput = document.getElementById('deleteConfirmation');
    const confirmDeleteBtn = document.getElementById('confirmDelete');
    
    if (deleteConfirmationInput && confirmDeleteBtn) {
        const projectName = deleteConfirmationInput.dataset.projectName;
        
        deleteConfirmationInput.addEventListener('input', function() {
            const enteredText = this.value.trim();
            confirmDeleteBtn.disabled = enteredText !== projectName;
        });
        
        confirmDeleteBtn.addEventListener('click', function() {
            deleteProject(projectName);
        });
    }
}

// Delete project function
function deleteProject(projectName) {
    // Show loading state
    const confirmBtn = document.getElementById('confirmDelete');
    const originalText = confirmBtn.innerHTML;
    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Deleting...';
    confirmBtn.disabled = true;
    
    // Make delete request
    fetch(`/projects/${projectName}/delete`, {
        method: 'DELETE',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Project deleted successfully!', 'success');
            // Redirect to projects page after a delay
            setTimeout(() => {
                window.location.href = '/projects_ui';
            }, 2000);
        } else {
            showNotification(data.error || 'Failed to delete project', 'danger');
        }
    })
    .catch(error => {
        console.error('Delete error:', error);
        showNotification('Network error during project deletion', 'danger');
    })
    .finally(() => {
        // Restore button state
        confirmBtn.innerHTML = originalText;
        confirmBtn.disabled = false;
    });
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (deploymentSocket) {
        deploymentSocket.close();
    }
    if (logAutoRefresh) {
        clearInterval(logAutoRefresh);
    }
});
