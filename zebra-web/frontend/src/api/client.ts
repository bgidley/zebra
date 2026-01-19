import type {
  ProcessDefinition,
  ProcessDefinitionListItem,
  ProcessInstance,
  ProcessInstanceDetail,
  ProcessInstanceListItem,
  TaskInstance,
  HealthResponse,
  CreateDefinitionRequest,
  StartProcessRequest,
  CompleteTaskRequest,
} from './types';

const API_BASE = '/api';

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.message || `HTTP ${response.status}`);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Health
export async function getHealth(): Promise<HealthResponse> {
  return fetchApi('/health/');
}

// Definitions
export async function getDefinitions(): Promise<ProcessDefinitionListItem[]> {
  return fetchApi('/definitions/');
}

export async function getDefinition(id: string): Promise<ProcessDefinition> {
  return fetchApi(`/definitions/${id}/`);
}

export async function createDefinition(
  request: CreateDefinitionRequest
): Promise<ProcessDefinition> {
  return fetchApi('/definitions/', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function deleteDefinition(id: string): Promise<void> {
  return fetchApi(`/definitions/${id}/`, {
    method: 'DELETE',
  });
}

// Processes
export interface ProcessListParams {
  definition_id?: string;
  include_completed?: boolean;
  state?: string;
}

export async function getProcesses(
  params: ProcessListParams = {}
): Promise<ProcessInstanceListItem[]> {
  const searchParams = new URLSearchParams();
  if (params.definition_id) searchParams.set('definition_id', params.definition_id);
  if (params.include_completed) searchParams.set('include_completed', 'true');
  if (params.state) searchParams.set('state', params.state);
  
  const query = searchParams.toString();
  return fetchApi(`/processes/${query ? `?${query}` : ''}`);
}

export async function getProcess(id: string): Promise<ProcessInstanceDetail> {
  return fetchApi(`/processes/${id}/`);
}

export async function startProcess(
  request: StartProcessRequest
): Promise<ProcessInstance> {
  return fetchApi('/processes/', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function deleteProcess(id: string): Promise<void> {
  return fetchApi(`/processes/${id}/`, {
    method: 'DELETE',
  });
}

export async function pauseProcess(id: string): Promise<ProcessInstance> {
  return fetchApi(`/processes/${id}/pause/`, {
    method: 'POST',
  });
}

export async function resumeProcess(id: string): Promise<ProcessInstance> {
  return fetchApi(`/processes/${id}/resume/`, {
    method: 'POST',
  });
}

// Tasks
export async function getProcessTasks(processId: string): Promise<TaskInstance[]> {
  return fetchApi(`/processes/${processId}/tasks/`);
}

export async function getPendingTasks(): Promise<TaskInstance[]> {
  return fetchApi('/tasks/');
}

export async function getTask(id: string): Promise<TaskInstance> {
  return fetchApi(`/tasks/${id}/`);
}

export async function completeTask(
  id: string,
  request: CompleteTaskRequest
): Promise<TaskInstance> {
  return fetchApi(`/tasks/${id}/complete/`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
