/**
 * Shared Workflow Diagram Component
 * 
 * Provides functionality for:
 * - Loading workflow diagrams from the API
 * - Auto-refreshing diagrams during execution
 * - Handling task selection in diagrams
 * 
 * Usage:
 *   // Initialize all diagram components on the page
 *   WorkflowDiagram.initAll();
 *   
 *   // Or initialize a specific element
 *   const diagram = new WorkflowDiagram(element);
 *   diagram.start();
 *   
 *   // Manual refresh
 *   diagram.refresh();
 *   
 *   // Stop auto-refresh
 *   diagram.stop();
 */

class WorkflowDiagram {
    constructor(element) {
        this.container = element;
        this.runId = element.dataset.runId;
        this.autoRefresh = element.dataset.autoRefresh === 'true';
        this.refreshInterval = parseInt(element.dataset.refreshInterval) || 2000;
        
        this.svgContainer = element.querySelector('.workflow-diagram-svg');
        this.nameBadge = element.querySelector('.workflow-name-badge');
        this.loadingIndicator = element.querySelector('.diagram-loading');
        
        this.intervalId = null;
        this.isRunning = false;
        this.lastTaskCount = 0;
    }
    
    /**
     * Start the diagram - load initial state and begin auto-refresh if enabled
     */
    start() {
        if (this.isRunning) return;
        this.isRunning = true;
        
        // Initial load
        this.refresh();
        
        // Start auto-refresh if enabled
        if (this.autoRefresh) {
            this.intervalId = setInterval(() => this.refresh(), this.refreshInterval);
        }
    }
    
    /**
     * Stop auto-refresh
     */
    stop() {
        this.isRunning = false;
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        // Do one final refresh to show complete state
        this.refresh();
    }
    
    /**
     * Refresh the diagram from the API
     */
    async refresh() {
        if (!this.runId) return;
        
        try {
            const response = await fetch(`/api/runs/${this.runId}/diagram/`);
            
            if (!response.ok) {
                // If 400/404, the workflow might not be selected yet
                if (response.status === 400 || response.status === 404) {
                    return;
                }
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.svg) {
                // Update SVG
                this.svgContainer.innerHTML = data.svg;
                
                // Update workflow name badge if present
                if (this.nameBadge && data.workflow_name) {
                    this.nameBadge.textContent = data.workflow_name;
                }
                
                // Hide loading indicator
                if (this.loadingIndicator) {
                    this.loadingIndicator.style.display = 'none';
                }
                
                // Check if run is complete and stop auto-refresh
                if (data.completed && this.autoRefresh) {
                    this.stop();
                }
                
                // Track task count for change detection
                this.lastTaskCount = data.task_count || 0;
            }
        } catch (err) {
            console.error('Failed to refresh diagram:', err);
        }
    }
    
    /**
     * Update the run ID (useful when a new run starts)
     */
    setRunId(runId) {
        this.runId = runId;
        this.container.dataset.runId = runId;
    }
    
    /**
     * Show the diagram container
     */
    show() {
        this.container.style.display = '';
        this.container.classList.remove('hidden');
    }
    
    /**
     * Hide the diagram container
     */
    hide() {
        this.container.style.display = 'none';
        this.container.classList.add('hidden');
    }
    
    /**
     * Initialize all workflow diagram components on the page
     */
    static initAll() {
        const diagrams = [];
        document.querySelectorAll('.workflow-diagram-component').forEach(element => {
            const diagram = new WorkflowDiagram(element);
            diagram.start();
            diagrams.push(diagram);
        });
        return diagrams;
    }
    
    /**
     * Find a diagram instance by run ID
     */
    static findByRunId(runId) {
        const element = document.querySelector(`.workflow-diagram-component[data-run-id="${runId}"]`);
        if (element && element._workflowDiagram) {
            return element._workflowDiagram;
        }
        return null;
    }
}

// Store instance on element for later access
const originalConstructor = WorkflowDiagram;
WorkflowDiagram = function(element) {
    const instance = new originalConstructor(element);
    element._workflowDiagram = instance;
    return instance;
};
WorkflowDiagram.prototype = originalConstructor.prototype;
WorkflowDiagram.initAll = originalConstructor.initAll;
WorkflowDiagram.findByRunId = originalConstructor.findByRunId;

// Also handle task selection from diagram clicks
function selectTask(taskId) {
    // Scroll to the task panel if it exists
    const panel = document.getElementById('task-panel-' + taskId);
    if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // Trigger Alpine.js to expand the panel and set it as selected
        setTimeout(() => {
            const expandButton = panel.querySelector('[x-data]');
            if (expandButton && expandButton._x_dataStack) {
                expandButton._x_dataStack[0].expanded = true;
            }
            // Update selected task in parent scope
            const container = document.querySelector('[x-data*="selectedTask"]');
            if (container && container._x_dataStack) {
                container._x_dataStack[0].selectedTask = taskId;
            }
        }, 100);
    }
}

// Export for module systems if available
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WorkflowDiagram, selectTask };
}
