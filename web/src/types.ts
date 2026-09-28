export type NodeGroup = 
  | 'Router' 
  | 'Concepts' 
  | 'Suites' 
  | 'Skills' 
  | 'Tools' 
  | 'Worlds' 
  | 'Notes' 
  | 'Files';

export type HubCategory = 
  | 'Skill Suites' 
  | 'Local Businesses' 
  | 'AI Workshop' 
  | 'Claude Code';

export interface GraphNode {
  id: string;
  group: NodeGroup;
  val: number;
  hub?: HubCategory | string;
  desc?: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
  index?: number;
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  value?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface HubItem {
  id: HubCategory;
  label: string;
  color: string;
  count: number;
}

export interface LegendItem {
  id: NodeGroup;
  label: string;
  color: string;
  glowColor: string;
  count: number;
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

export interface ForceSettings {
  repel: number;       // Repel force strength (e.g. -100 to -1000)
  linkLength: number;  // Resting link length (e.g. 40 to 220)
}

export interface NimModel {
  id: string;
  name: string;
  provider: string;
  context_length: number;
  description: string;
  tags: string[];
}

export interface NimStatus {
  enabled: boolean;
  has_api_key: boolean;
  masked_key: string;
  base_url: string;
  active_model: string;
  status: 'ready' | 'connected' | 'simulation' | 'error';
  supported_models: NimModel[];
}
