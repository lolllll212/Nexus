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
