export type NodeCategory = 
  | 'MEMORY' 
  | 'DOCUMENT' 
  | 'WEBSITE' 
  | 'RESEARCH' 
  | 'PROJECT' 
  | 'TASK' 
  | 'AGENT' 
  | 'WORKFLOW' 
  | 'API' 
  | 'TOOL' 
  | 'PERSON' 
  | 'COMPANY' 
  | 'CONCEPT' 
  | 'CODE' 
  | 'DATABASE' 
  | 'CONVERSATION' 
  | 'FILE' 
  | 'SOURCE';

export type OperatingMode = 'GRAPH' | 'RESEARCH' | 'WORKFLOW' | 'ARCHITECTURE';

export type LayoutAlgorithm = 'FORCE' | 'RING' | 'CLUSTER' | 'RADIAL';

export interface NexusNode {
  id: string;
  name: string;
  category: NodeCategory;
  val: number;
  importance: number;      // 0 - 100
  confidence: number;      // 0 - 100
  hub?: string;
  description: string;
  source?: string;
  lastUpdated?: string;
  tags: string[];
  metadata?: Record<string, any>;
  pulsing?: boolean;
  status?: 'active' | 'idle' | 'executing' | 'warning' | 'synced';
  pinned?: boolean;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface NexusLink {
  source: string | NexusNode;
  target: string | NexusNode;
  relation: string;        // 'PRODUCES' | 'CALLS' | 'EXTRACTED_FROM' | 'DEPENDS_ON' | 'SYNTHESIZES' | 'AUTHENTICATES'
  strength?: number;
  active?: boolean;
  traced?: boolean;
}

export interface AutonomousAgent {
  id: string;
  name: string;
  role: 'Researcher' | 'Coder' | 'Planner' | 'Browser' | 'Vision' | 'Data Analyst' | 'Writer' | 'Executor' | 'Memory' | 'Fact Checker';
  status: 'active' | 'thinking' | 'executing' | 'idle';
  task: string;
  model: string;
  tools: string[];
  latency: number;
  tokens: string;
  progress: number;
  avatarColor: string;
  activeContextTokens: number;
}

export interface InterAgentMessage {
  id: string;
  timestamp: string;
  fromAgent: string;
  toAgent: string;
  type: 'TASK_HANDOFF' | 'DATA_PAYLOAD' | 'VERIFICATION_REQUEST' | 'AST_ARTIFACT' | 'SYNAPSE_SIGNAL';
  content: string;
  status: 'delivered' | 'processing' | 'verified';
}

export interface IntegrationService {
  id: string;
  name: string;
  category: 'code' | 'storage' | 'communication' | 'productivity' | 'database' | 'llm' | 'system';
  status: 'connected' | 'active' | 'syncing' | 'ready';
  description: string;
  badge: string;
  metrics: string;
  icon: string;
  endpoint?: string;
  lastSync?: string;
  pingMs?: number;
}

export interface ResearchClaim {
  id: string;
  claim: string;
  status: 'verified' | 'competing' | 'disputed';
  sources: string[];
  confidence: number;
  evidence: string;
}

export interface ResearchSourceItem {
  id: string;
  title: string;
  url: string;
  domain: string;
  relevance: number;
  credibility: 'tier-1' | 'tier-2' | 'preprint';
  date: string;
}

export interface ResearchTraceEvent {
  id: string;
  timestamp: string;
  phase: string;
  message: string;
  status: 'complete' | 'in_progress' | 'warning';
}

export interface WorkflowStep {
  id: string;
  name: string;
  agent: string;
  tool: string;
  status: 'completed' | 'running' | 'pending' | 'failed';
  durationMs: number;
  input: string;
  output: string;
}

export interface HexagonalPort {
  id: string;
  name: string;
  type: string;
  protocol: string;
  activeAdapter: string;
  latencyMs: number;
  status: 'nominal' | 'degraded' | 'standby';
  adapters: string[];
}

export interface SystemTelemetry {
  cortexStatus: 'ONLINE' | 'THINKING' | 'EXECUTING';
  cortexLatency: number;
  cortexTokensPerSec: number;
  subcortexStatus: 'ACTIVE' | 'DREAMING' | 'SYNTHESIZING';
  subcortexConsolidationRate: number;
  activeAgents: number;
  totalTools: number;
  memorySyncRate: number;
  activeWorkflows: number;
}
