// Garcon Frontend JavaScript

// Initialize application
document.addEventListener('DOMContentLoaded', function () {
    initializeTooltips();
    initializeModals();
    initializeDeploymentButtons();
    initializeDeleteConfirmation();
});

// Initialize tooltips (no longer using Bootstrap tooltips)
function initializeTooltips() {
    // No longer using Bootstrap tooltips, using native title attributes
    // This function is kept for backward compatibility
}

// Initialize modals and alerts
function initializeModals() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.mb-4.p-4.rounded-lg.border-l-4');
    alerts.forEach(alert => {
        setTimeout(() => {
            const closeBtn = alert.querySelector('button');
            if (closeBtn) {
                alert.style.transition = 'opacity 0.5s ease-out';
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 500);
            }
        }, 5000);
    });
}

// Initialize deployment buttons
function initializeDeploymentButtons() {
    // Event delegation for deploy buttons
    document.addEventListener('click', function (event) {
        const deployBtn = event.target.closest('.deploy-btn');
        if (deployBtn) {
            handleDeployment(deployBtn);
        }

        // Handle confirm deploy button
        if (event.target.id === 'confirmDeploy' || event.target.closest('#confirmDeploy')) {
            event.preventDefault();
            confirmDeployment();
        }
    });
}

// Handle deployment button clicks
function handleDeployment(button) {
    const projectId = button.dataset.projectId;
    const projectName = button.dataset.project;
    const deploymentType = button.dataset.deploymentType || 'blue-green';

    // Show confirmation modal
    showDeploymentModal(projectId, projectName, deploymentType);
}

// Show deployment confirmation modal
function showDeploymentModal(projectId, projectName, deploymentType) {
    const modal = document.getElementById('deployModal');
    if (!modal) return;

    // Update modal content
    const projectNameElement = document.getElementById('deploy-project-name');
    const deploymentTypeSelect = document.getElementById('deploymentType');

    if (projectNameElement) projectNameElement.textContent = projectName;
    if (deploymentTypeSelect) deploymentTypeSelect.value = deploymentType;

    // Store project ID for later use
    modal.dataset.projectId = projectId;

    // Show modal
    modal.classList.remove('hidden');
}

// Confirm deployment
function confirmDeployment() {
    const modal = document.getElementById('deployModal');
    if (!modal) return;

    const projectId = parseInt(modal.dataset.projectId);
    const deploymentType = document.getElementById('deploymentType')?.value || 'blue-green';

    // Hide modal
    modal.classList.add('hidden');

    // Start deployment
    startDeployment(projectId, deploymentType);
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

// Show notification toast using Tailwind classes
function showNotification(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();

    const toast = document.createElement('div');
    const bgColor = type === 'success' ? 'bg-green-500' :
        type === 'danger' ? 'bg-red-500' :
            type === 'warning' ? 'bg-yellow-500' : 'bg-blue-500';

    toast.className = `${bgColor} text-white px-6 py-4 rounded-lg shadow-lg mb-3 transition-all duration-300 transform translate-x-full`;

    toast.innerHTML = `
        <div class="flex items-center justify-between">
            <div class="flex items-center">
                <i class="bi bi-${type === 'success' ? 'check-circle' : type === 'danger' ? 'x-circle' : 'info-circle'} mr-3"></i>
                <span>${message}</span>
            </div>
            <button type="button" class="ml-4 text-white hover:text-gray-200" onclick="this.parentElement.parentElement.remove()">
                <i class="bi bi-x-lg"></i>
            </button>
        </div>
    `;

    toastContainer.appendChild(toast);

    // Animate in
    setTimeout(() => {
        toast.classList.remove('translate-x-full');
    }, 100);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.classList.add('translate-x-full');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// Create toast container if it doesn't exist
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'fixed top-4 right-4 z-50 space-y-2';
    document.body.appendChild(container);
    return container;
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
    const name = form.querySelector('[name="name"]')?.value.trim();
    const gitUrl = form.querySelector('[name="git_url"]')?.value.trim();
    const domain = form.querySelector('[name="domain"]')?.value.trim();

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
document.addEventListener('submit', function (event) {
    const form = event.target;

    if (form.id === 'addProjectForm') {
        if (!validateProjectForm(form)) {
            event.preventDefault();
        }
    }
});

// Add confirmation for destructive actions
document.addEventListener('click', function (event) {
    const element = event.target.closest('[data-confirm]');

    if (element) {
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
        button.classList.remove('bg-cyan-600', 'text-white');
        button.classList.add('border-cyan-600', 'text-cyan-600', 'hover:bg-cyan-50', 'dark:border-cyan-400', 'dark:text-cyan-400', 'dark:hover:bg-cyan-900/50');
    } else {
        logAutoRefresh = setInterval(() => {
            location.reload();
        }, 10000);
        status.textContent = 'On (10s)';
        button.classList.remove('border-cyan-600', 'text-cyan-600', 'hover:bg-cyan-50', 'dark:border-cyan-400', 'dark:text-cyan-400', 'dark:hover:bg-cyan-900/50');
        button.classList.add('bg-cyan-600', 'text-white');
    }
}

// Initialize delete confirmation
function initializeDeleteConfirmation() {
    const deleteConfirmationInput = document.getElementById('deleteConfirmation');
    const confirmDeleteBtn = document.getElementById('confirmDelete');

    if (deleteConfirmationInput && confirmDeleteBtn) {
        const projectName = deleteConfirmationInput.dataset.projectName;

        deleteConfirmationInput.addEventListener('input', function () {
            const enteredText = this.value.trim();
            confirmDeleteBtn.disabled = enteredText !== projectName;

            if (enteredText === projectName) {
                confirmDeleteBtn.classList.remove('bg-gray-300', 'cursor-not-allowed');
                confirmDeleteBtn.classList.add('bg-red-600', 'hover:bg-red-700');
            } else {
                confirmDeleteBtn.classList.add('bg-gray-300', 'cursor-not-allowed');
                confirmDeleteBtn.classList.remove('bg-red-600', 'hover:bg-red-700');
            }
        });

        confirmDeleteBtn.addEventListener('click', function () {
            if (!this.disabled) {
                deleteProject(projectName);
            }
        });
    }
}

// Delete project function
function deleteProject(projectName) {
    // Show loading state
    const confirmBtn = document.getElementById('confirmDelete');
    const originalText = confirmBtn.innerHTML;
    confirmBtn.innerHTML = '<i class="bi bi-hourglass-split animate-spin mr-2"></i>Deleting...';
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
window.addEventListener('beforeunload', function () {
    if (logAutoRefresh) {
        clearInterval(logAutoRefresh);
    }
});

// Global modal close functions for compatibility
window.closeModal = function () {
    const modals = document.querySelectorAll('[id$="Modal"]');
    modals.forEach(modal => modal.classList.add('hidden'));
};

window.closeErrorModal = function () {
    const modal = document.getElementById('errorModal');
    if (modal) modal.classList.add('hidden');
};

window.closeDeleteModal = function () {
    const modal = document.getElementById('deleteModal');
    if (modal) modal.classList.add('hidden');
};

window.closeDeployModal = function () {
    const modal = document.getElementById('deployModal');
    if (modal) modal.classList.add('hidden');
};
