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

export type OperatingMode = 'HUD' | 'GRAPH' | 'RESEARCH' | 'WORKFLOW' | 'ARCHITECTURE' | 'VIDEO' | 'DASHBOARD';

export type UiVariety = 'TACTICAL_HUD' | 'ANALYTICS_DASHBOARD' | 'MOBILE_COMPACT';

export type AgentStatus = 'idle' | 'listening' | 'thinking' | 'speaking';

export type TaskDifficulty = 'low' | 'medium' | 'high' | 'critical';

export interface ConversationalMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  toolsUsed?: string[];
  actionTriggers?: Array<{ label: string; action: string; payload?: any }>;
  difficulty?: TaskDifficulty;
}

export interface McpToolSpec {
  name: string;
  description: string;
  parameters: Record<string, any>;
  category: 'perception' | 'code' | 'system' | 'workflow';
}

export interface MultimodalDecomposition {
  media_type: 'image' | 'video';
  filename: string;
  dimensions?: string;
  aspect_ratio?: string;
  duration_seconds?: number;
  file_size_kb?: number;
  average_luminance?: number;
  color_palette?: Array<{ hex: string; rgb: number[]; percentage: number; name: string }>;
  ocr_extracted_text?: string[];
  spatial_grid?: Record<string, { sector: string; visual_elements: string[]; density: string; dominant_hue: string }>;
  keyframes?: Array<{ timestamp: string; frame_index: number; scene_name: string; visual_description: string; motion_vector: string; audio_cue: string }>;
  audio_transcript?: Array<{ start: string; end: string; speaker: string; text: string }>;
  action_narrative?: string;
  scene_summary?: string;
  prompt_injection_block: string;
}

export type LayoutAlgorithm = 'FORCE' | 'RING' | 'CLUSTER' | 'RADIAL';

export type VideoAspectRatio = '16:9' | '9:16' | '1:1' | '21:9';
export type VideoResolution = '720p' | '1080p' | '4K';

export interface CameraMotionParams {
  pan: number;          // -10 to +10 (horizontal sweep)
  tilt: number;         // -10 to +10 (vertical angle)
  zoom: number;         // -10 to +10 (in / out)
  roll: number;         // -10 to +10 (dutch roll)
  speed: number;        // 0.2 to 2.5
  motionBrush: number;  // 0 to 10 intensity
  motionVectors: boolean;
}

export interface TimelineClip {
  id: string;
  title: string;
  start: number;       // seconds
  duration: number;    // seconds
  color: string;
  thumbnail?: string;
  type?: 'video' | 'audio' | 'keyframe' | 'effect';
}

export interface TimelineTrack {
  id: string;
  name: string;
  type: 'video' | 'audio' | 'keyframes' | 'effects';
  clips: TimelineClip[];
  muted?: boolean;
  locked?: boolean;
}

export interface VideoRenderTask {
  id: string;
  prompt: string;
  model: string;
  ratio: VideoAspectRatio;
  resolution: VideoResolution;
  status: 'queued' | 'rendering' | 'completed' | 'failed';
  progress: number;
  durationSec: number;
  videoUrl?: string;
  thumbnailUrl?: string;
  timestamp: string;
}

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

// ── Legacy types (used by CenterCanvas, RightSidebar, mockData) ───────────
export type NodeGroup = 'Router' | 'Concepts' | 'Suites' | 'Skills' | 'Tools' | 'Worlds' | 'Notes' | 'Files';
export type HubCategory = 'Skill Suites' | 'Local Businesses' | 'AI Workshop' | 'Claude Code';

export interface GraphNode {
  id: string;
  group: NodeGroup;
  val: number;
  hub: HubCategory;
  desc: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface GraphLink {
  source: string;
  target: string;
  value?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface ForceSettings {
  charge: number;
  distance: number;
  center: number;
  collision: number;
}

export interface SystemStates {
  ONLINE: boolean;
  RING: boolean;
  CUBE: boolean;
  FACE: boolean;
  EYES: boolean;
  WATCH: boolean;
  HOLO: boolean;
  FOCUS: boolean;
}

export interface LegendItem {
  id: NodeGroup;
  label: string;
  color: string;
  count: number;
}

export interface HubItem {
  id: HubCategory;
  label: string;
  color: string;
}

// ── NIM provider types (used by JarvisModal) ──────────────────────────────
export interface NimModel {
  id: string;
  name?: string;
  owned_by?: string;
  provider?: string;
}

export interface NimStatus {
  provider: string;
  base_url: string;
  has_key: boolean;
  models: NimModel[];
}
