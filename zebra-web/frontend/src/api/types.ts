// API types matching the Django REST Framework serializers

export interface TaskDefinition {
  id: string;
  name: string;
  auto: boolean;
  synchronized: boolean;
  action: string | null;
  properties: Record<string, unknown>;
}

export interface RoutingDefinition {
  id: string;
  source_task_id: string;
  dest_task_id: string;
  parallel: boolean;
  condition: string | null;
}

export interface ProcessDefinition {
  id: string;
  name: string;
  version: number;
  description: string | null;
  first_task_id: string;
  tasks: Record<string, TaskDefinition>;
  routings: RoutingDefinition[];
}

export interface ProcessDefinitionListItem {
  id: string;
  name: string;
  version: number;
  description: string | null;
  task_count: number;
}

export interface TaskInstance {
  id: string;
  process_id: string;
  task_definition_id: string;
  state: string;
  foe_id: string;
  properties: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  // Extra fields added for pending tasks
  process_definition_name?: string;
  task_definition_name?: string;
}

export interface FlowOfExecution {
  id: string;
  process_id: string;
  parent_foe_id: string | null;
  created_at: string;
}

export interface ProcessInstance {
  id: string;
  definition_id: string;
  state: string;
  properties: Record<string, unknown>;
  parent_process_id: string | null;
  parent_task_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ProcessInstanceDetail extends ProcessInstance {
  tasks: TaskInstance[];
  foes: FlowOfExecution[];
  definition: ProcessDefinition;
}

export interface ProcessInstanceListItem {
  id: string;
  definition_id: string;
  definition_name: string;
  state: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface HealthResponse {
  status: string;
  engine: string;
}

export interface ApiError {
  error: boolean;
  message: string;
  status_code: number;
  details: Record<string, unknown> | null;
}

// Request types
export interface CreateDefinitionRequest {
  yaml_content: string;
}

export interface StartProcessRequest {
  definition_id: string;
  properties?: Record<string, unknown>;
}

export interface CompleteTaskRequest {
  result?: Record<string, unknown>;
  next_route?: string;
}
