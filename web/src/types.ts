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

export type OperatingMode = 'WORKSPACE' | 'CLAUDE_CHAT' | 'HUD' | 'GRAPH' | 'RESEARCH' | 'WORKFLOW' | 'ARCHITECTURE' | 'VIDEO' | 'DASHBOARD';

export type UiVariety = 'TACTICAL_HUD' | 'ANALYTICS_DASHBOARD' | 'MOBILE_COMPACT';

export type AgentStatus = 'idle' | 'listening' | 'thinking' | 'speaking';

export type TaskDifficulty = 'low' | 'medium' | 'high' | 'critical';

export type ChatEffort = 'auto' | 'fast' | 'balanced' | 'deep' | 'max';

export type CodingFocus =
  | 'auto'
  | 'frontend'
  | 'c'
  | 'cpp'
  | 'rust'
  | 'python'
  | 'php'
  | 'html5'
  | 'xml'
  | 'ruby';

export interface ChatCodingMetadata {
  requested_focus?: CodingFocus | string;
  focus?: CodingFocus | string;
  is_coding?: boolean;
  is_frontend?: boolean;
  languages?: string[];
  language_labels?: string[];
  standards?: string[];
  frontend_kind?: string | null;
  design_goals?: string[];
  expected_tools?: string[];
  verification_checks?: string[];
  weak_model_risk?: string;
  [key: string]: unknown;
}

export interface CodingCapabilityCatalog {
  focuses?: string[];
  languages?: Record<string, { label?: string; standard?: string; [key: string]: unknown }>;
  frontend?: {
    kinds?: string[];
    design_goals?: string[];
    [key: string]: unknown;
  };
  tools?: string[];
  quality_gates?: string[];
  project_checks?: string[];
  repository_templates?: string[];
  [key: string]: unknown;
}

export interface ChatExecutionMetadata {
  requested_effort?: ChatEffort | string;
  effective_effort?: Exclude<ChatEffort, 'auto'> | string;
  complexity?: number;
  mode?: string;
  intent?: string;
  operation_level?: string;
  workstreams?: string[];
  expected_tools?: string[];
  coding?: ChatCodingMetadata | null;
  coding_languages?: string[];
  frontend_kind?: string | null;
  [key: string]: unknown;
}

export interface ChatQualityIssue {
  code: string;
  severity: 'critical' | 'major' | 'minor' | string;
  detail?: string;
  repair_instruction?: string;
}

export interface ChatQualityMetadata {
  score: number;
  passed: boolean;
  status: 'verified' | 'degraded' | 'needs_repair' | 'guardrail_blocked' | 'not_run' | string;
  issues?: ChatQualityIssue[];
  checks?: string[];
  word_count?: number;
  tools_used?: string[];
  repair_attempts_used?: number;
}

export interface ConversationalMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  toolsUsed?: string[];
  actionTriggers?: Array<{ label: string; action: string; payload?: any }>;
  difficulty?: TaskDifficulty;
  /** Model that produced this turn (model changer), e.g. a NIM model id. */
  model?: string;
  /** Where the model came from: 'nexus-default' | 'nvidia-nim'. */
  modelSource?: string;
  /** Sanitized reasoning trace for the Extended Thinking accordion. */
  thinking?: string;
  /** Adaptive effort/evidence profile used for this answer. */
  execution?: ChatExecutionMetadata;
  /** Deterministic final-answer quality verdict from the cortex. */
  quality?: ChatQualityMetadata;
  /** Frontend/polyglot specialist profile used for this answer. */
  coding?: ChatCodingMetadata;
  /** Lifecycle marker used to label partial/stopped streamed answers honestly. */
  status?: 'streaming' | 'complete' | 'stopped' | 'error';
}

// ── Model changer + Claude-style capabilities ──────────────────────────────
export type ModelCapabilityKey =
  | 'reasoning'
  | 'tool_use'
  | 'code'
  | 'vision'
  | 'long_context'
  | 'research'
  | 'streaming';

export interface NexusModel {
  id: string;
  name: string;
  provider: string;
  description: string;
  tags: string[];
  context_window: number | null;
  speed: string; // 'fastest' | 'balanced' | 'deep'
  best_for: string;
  capabilities: string[];
  is_active?: boolean;
  source?: string; // 'nexus-default' | 'nvidia-nim'
}

export interface ModelCatalogExecution {
  efforts: ChatEffort[];
  default_effort: ChatEffort;
  adaptive_model_routing: boolean;
  quality_gate_enabled: boolean;
  native_tool_calling_enabled: boolean;
  quality_max_repairs: number;
}

export interface ModelCatalog {
  models: NexusModel[];
  active_model: string | null;
  default_model: string;
  provider_status: string; // 'live' | 'simulation' | 'offline'
  has_api_key: boolean;
  capability_labels: Record<string, string>;
  execution?: ModelCatalogExecution;
  coding?: CodingCapabilityCatalog;
}

export interface ChatCapabilities {
  extendedThinking: boolean;
  artifacts: boolean;
  deepResearch: boolean;
  voiceReplies: boolean;
  memory: boolean;
  effort: ChatEffort;
  codingFocus: CodingFocus;
}

export type ChatCapabilityToggleKey = Exclude<keyof ChatCapabilities, 'effort' | 'codingFocus'>;

// ── Tool registry (Claude-style chat workspace Tools/Code panel) ───────────
export interface NexusToolSchema {
  type?: string;
  properties?: Record<string, { type?: string; description?: string; [key: string]: any }>;
  required?: string[];
  description?: string;
}

export interface NexusTool {
  id: string;
  name: string;
  description: string;
  status: string;
  use_count: number;
  success_rate: number;
  is_self_generated: boolean;
  endpoint: string | null;
  input_schema: NexusToolSchema;
  output_schema: NexusToolSchema;
  requires_approval: boolean;
  category: string;
}

export interface NexusToolApproval {
  tool_id: string;
  action: string;
  approved: boolean;
}

// ── Upgrade Spaces (shared status catalog across Nexus websites) ──────────
export interface UpgradeSpace {
  id: number;
  name: string;
  priority: string;
  owner: string;
  summary: string;
  status: string;
  evidence: string[];
  runtime_note: string;
}

export interface AgentTelemetrySnapshot {
  enabled: boolean;
  metrics_backend?: string;
  tracer_backend?: string;
  counters?: Record<string, number>;
  heal_success_rate?: number | null;
}

export interface UpgradeSpacesResponse {
  spaces: UpgradeSpace[];
  summary: {
    total: number;
    landed: number;
    pending: number;
  };
  generated_at: string;
  tools_count: number;
  telemetry: AgentTelemetrySnapshot;
}

// ── Chat history (server-backed sessions) ──────────────────────────────────
export interface StoredChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  model?: string;
  tools_used?: string[];
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  model: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
}

export interface ChatSessionRecord {
  id: string;
  title: string;
  model: string | null;
  created_at: string;
  updated_at: string;
  messages: StoredChatMessage[];
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
