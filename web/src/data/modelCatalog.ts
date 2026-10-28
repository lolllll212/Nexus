import { nexusJson } from '../api';
import type {
  ChatCapabilities,
  ChatCodingMetadata,
  ChatEffort,
  CodingCapabilityCatalog,
  CodingFocus,
  ModelCapabilityKey,
  ModelCatalog,
  ModelCatalogExecution,
  NexusModel,
} from '../types';

/**
 * Frontend model-changer catalog.
 *
 * The backend `GET /api/models` endpoint is the source of truth. The bundled
 * fallback mirrors the supported NVIDIA NIM catalog so the picker remains
 * usable (clearly marked offline) when the API has not started yet or a
 * static preview is being viewed without the Python backend.
 */

export const AUTO_MODEL_ID = 'auto';
export const MODEL_STORAGE_KEY = 'nexus_model';
export const CAPABILITIES_STORAGE_KEY = 'nexus_capabilities';

export const CHAT_EFFORT_OPTIONS: Array<{
  id: ChatEffort;
  label: string;
  shortLabel: string;
  description: string;
}> = [
  {
    id: 'auto',
    label: 'Auto',
    shortLabel: 'Auto',
    description: 'Nexus chooses speed, depth, model, and repair budget from the task.',
  },
  {
    id: 'fast',
    label: 'Fast',
    shortLabel: 'Fast',
    description: 'Shortest useful path for simple questions and quick drafts.',
  },
  {
    id: 'balanced',
    label: 'Balanced',
    shortLabel: 'Balance',
    description: 'A careful default for everyday work without unnecessary depth.',
  },
  {
    id: 'deep',
    label: 'Deep',
    shortLabel: 'Deep',
    description: 'More evidence, stronger model routing, verification, and up to two answer repairs.',
  },
  {
    id: 'max',
    label: 'Max',
    shortLabel: 'Max',
    description: 'Maximum work budget: flagship routing, cross-checking, verification, and up to three repairs.',
  },
];

export function normalizeChatEffort(value: unknown): ChatEffort {
  return value === 'fast' || value === 'balanced' || value === 'deep' || value === 'max'
    ? value
    : 'auto';
}

export function getChatEffortOption(effort: ChatEffort | string | undefined) {
  return (
    CHAT_EFFORT_OPTIONS.find((option) => option.id === normalizeChatEffort(effort)) ||
    CHAT_EFFORT_OPTIONS[0]
  );
}

export const CODING_FOCUS_OPTIONS: Array<{
  id: CodingFocus;
  label: string;
  shortLabel: string;
  description: string;
}> = [
  {
    id: 'auto',
    label: 'Auto detect',
    shortLabel: 'Code Auto',
    description: 'Nexus detects frontend and language intent from the request and attached files.',
  },
  {
    id: 'frontend',
    label: 'Frontend & clean UI',
    shortLabel: 'Frontend UI',
    description: 'Design-system thinking: hierarchy, tokens, responsive layout, accessibility, states, and build checks.',
  },
  {
    id: 'c',
    label: 'C',
    shortLabel: 'C17',
    description: 'C17 ownership, bounds, checked returns, warnings, CMake/Make, and sanitizer-aware verification.',
  },
  {
    id: 'cpp',
    label: 'C++',
    shortLabel: 'C++20',
    description: 'Modern C++20 RAII, value semantics, const-correctness, CMake, warnings, and tests.',
  },
  {
    id: 'rust',
    label: 'Rust',
    shortLabel: 'Rust',
    description: 'Ownership-first Rust with Result/Option boundaries, Cargo check, Clippy, fmt, and tests.',
  },
  {
    id: 'python',
    label: 'Python',
    shortLabel: 'Python',
    description: 'Typed, testable Python with Ruff, Mypy, pytest, safe I/O, and clear module boundaries.',
  },
  {
    id: 'php',
    label: 'PHP',
    shortLabel: 'PHP 8',
    description: 'Strict PHP 8 with validated input, escaped output, prepared data access, CSRF, and Composer checks.',
  },
  {
    id: 'html5',
    label: 'HTML5',
    shortLabel: 'HTML5',
    description: 'Semantic, accessible HTML5 with landmarks, labels, responsive metadata, and progressive enhancement.',
  },
  {
    id: 'xml',
    label: 'XML',
    shortLabel: 'XML',
    description: 'Well-formed XML/XSD/XSLT with namespace discipline and XXE-safe parsers and validation.',
  },
  {
    id: 'ruby',
    label: 'Ruby',
    shortLabel: 'Ruby',
    description: 'Readable Ruby with small objects, frozen literals where useful, Bundler, Minitest/RSpec, and lint checks.',
  },
];

const CODING_FOCUS_ALIASES: Record<string, CodingFocus> = {
  'c++': 'cpp',
  cplusplus: 'cpp',
  html: 'html5',
  'front-end': 'frontend',
  ui: 'frontend',
  py: 'python',
  rs: 'rust',
  rb: 'ruby',
  coding: 'auto',
  general: 'auto',
};

export function normalizeCodingFocus(value: unknown): CodingFocus {
  if (typeof value !== 'string') return 'auto';
  const normalized = value.trim().toLowerCase().replace(/_/g, '-');
  if (CODING_FOCUS_OPTIONS.some((option) => option.id === normalized)) {
    return normalized as CodingFocus;
  }
  return CODING_FOCUS_ALIASES[normalized] || 'auto';
}

export function getCodingFocusOption(focus: CodingFocus | string | undefined) {
  return (
    CODING_FOCUS_OPTIONS.find((option) => option.id === normalizeCodingFocus(focus)) ||
    CODING_FOCUS_OPTIONS[0]
  );
}

export function codingFocusMode(focus: CodingFocus | string | undefined): string {
  const normalized = normalizeCodingFocus(focus);
  return normalized === 'auto' ? 'general' : normalized;
}

export function formatCodingProfile(coding: ChatCodingMetadata | null | undefined): string | null {
  if (!coding?.is_coding) return null;
  if (coding.is_frontend) {
    const kind = coding.frontend_kind?.replace(/_/g, ' ');
    return kind ? `Frontend · ${kind}` : 'Frontend UI';
  }
  const labels = Array.isArray(coding.language_labels) ? coding.language_labels.filter(Boolean) : [];
  if (labels.length > 0) return labels.slice(0, 3).join(' · ');
  const focus = getCodingFocusOption(coding.focus || coding.requested_focus);
  return focus.id === 'auto' ? 'Coding' : focus.label;
}

export const FALLBACK_CODING_CATALOG: CodingCapabilityCatalog = {
  focuses: CODING_FOCUS_OPTIONS.map((option) => option.id),
  languages: {
    c: { label: 'C', standard: 'ISO C17' },
    cpp: { label: 'C++', standard: 'ISO C++20' },
    rust: { label: 'Rust', standard: 'Rust 2021, stable toolchain' },
    python: { label: 'Python', standard: 'Python 3.11+ with type hints' },
    php: { label: 'PHP', standard: 'PHP 8.2+ with strict types' },
    html5: { label: 'HTML5', standard: 'WHATWG HTML Living Standard' },
    xml: { label: 'XML', standard: 'XML 1.0, XSD 1.0/1.1, XPath, XSLT' },
    ruby: { label: 'Ruby', standard: 'Ruby 3.2+' },
  },
  frontend: {
    kinds: ['app_shell', 'dashboard', 'form', 'landing', 'commerce', 'content', 'game', 'design_system'],
    design_goals: ['visual hierarchy', 'responsive layout', 'accessible interaction', 'visible focus', 'design tokens'],
  },
  tools: ['project_scan', 'code_diagnostics', 'frontend_quality', 'project_checks', 'create_repository'],
  quality_gates: ['accessibility', 'responsive design', 'language safety', 'verification evidence'],
};

export const CAPABILITY_LABELS: Record<ModelCapabilityKey, string> = {
  reasoning: 'Extended thinking',
  tool_use: 'Tool use',
  code: 'Code & artifacts',
  vision: 'Vision (images)',
  long_context: 'Long context',
  research: 'Deep research',
  streaming: 'Streaming replies',
};

export const CAPABILITY_META: Record<
  ModelCapabilityKey,
  { label: string; description: string }
> = {
  reasoning: {
    label: CAPABILITY_LABELS.reasoning,
    description: 'Shows a collapsible, sanitized reasoning summary before the answer.',
  },
  tool_use: {
    label: CAPABILITY_LABELS.tool_use,
    description: 'Can call NEXUS tools and act on their observations.',
  },
  code: {
    label: CAPABILITY_LABELS.code,
    description: 'Optimized for code blocks and reusable artifact-style deliverables.',
  },
  vision: {
    label: CAPABILITY_LABELS.vision,
    description: 'Can reason about images, screenshots, charts and diagrams.',
  },
  long_context: {
    label: CAPABILITY_LABELS.long_context,
    description: 'Handles long conversations and large documents in one request.',
  },
  research: {
    label: CAPABILITY_LABELS.research,
    description: 'Better suited to multi-source synthesis and evidence-led answers.',
  },
  streaming: {
    label: CAPABILITY_LABELS.streaming,
    description: 'Returns progress while NEXUS is thinking and using tools.',
  },
};

export const CAPABILITY_KEYS = Object.keys(CAPABILITY_META) as ModelCapabilityKey[];

export const SPEED_LABELS: Record<string, string> = {
  fastest: 'Fastest',
  fast: 'Fast',
  balanced: 'Balanced',
  deep: 'Deep',
};

export const FALLBACK_MODELS: NexusModel[] = [
  {
    id: AUTO_MODEL_ID,
    name: 'NEXUS Auto',
    provider: 'NEXUS Cortex',
    description:
      'Adaptive cortex routing for general work, clean frontend/UI, and C, C++, Rust, Python, PHP, HTML5, XML, and Ruby—with tools, verification, and repair.',
    tags: ['auto', 'cortex', 'adaptive'],
    context_window: null,
    speed: 'balanced',
    best_for: 'Effort- and coding-aware routing with tools, memory, verification, and answer repair',
    capabilities: ['reasoning', 'tool_use', 'code', 'vision', 'long_context', 'research', 'streaming'],
    is_active: false,
    source: 'nexus-default',
  },
  {
    id: 'nvidia/nemotron-3.5-lightning-30b-a3b',
    name: 'Nemotron 3.5 Lightning 30B (fast)',
    provider: 'NVIDIA NIM',
    description: 'Fastest verified reasoning model - sub-second first token. Default.',
    tags: ['default', 'reasoning', 'fast'],
    context_window: 131072,
    speed: 'fastest',
    best_for: 'Everyday chat, quick questions, voice conversations',
    capabilities: ['reasoning', 'tool_use', 'code', 'long_context', 'streaming'],
    is_active: false,
    source: 'nvidia-nim',
  },
  {
    id: 'nvidia/nemotron-3-ultra-550b-a55b',
    name: 'Nemotron 3 Ultra 550B',
    provider: 'NVIDIA NIM',
    description: 'Largest verified reasoning model - deep multi-step reasoning.',
    tags: ['flagship', 'reasoning'],
    context_window: 262144,
    speed: 'deep',
    best_for: 'Hard reasoning, architecture, long research syntheses',
    capabilities: ['reasoning', 'tool_use', 'code', 'long_context', 'research', 'streaming'],
    is_active: false,
    source: 'nvidia-nim',
  },
  {
    id: 'meta/llama-3.3-70b-instruct',
    name: 'Llama 3.3 70B Instruct',
    provider: 'Meta / NVIDIA NIM',
    description: "Workhorse open model - the container's classic cortex default.",
    tags: ['general', 'balanced'],
    context_window: 131072,
    speed: 'balanced',
    best_for: 'General reasoning, writing, tool-driven workflows',
    capabilities: ['tool_use', 'code', 'long_context', 'research', 'streaming'],
    is_active: true,
    source: 'nvidia-nim',
  },
  {
    id: 'openai/gpt-oss-20b',
    name: 'GPT-OSS 20B',
    provider: 'OpenAI / NVIDIA NIM',
    description: 'Open-weight general model - balanced speed and quality.',
    tags: ['general'],
    context_window: 131072,
    speed: 'balanced',
    best_for: 'General chat and quick drafting',
    capabilities: ['reasoning', 'tool_use', 'code', 'streaming'],
    is_active: false,
    source: 'nvidia-nim',
  },
  {
    id: 'stepfun-ai/step-5-preview',
    name: 'Step 5 Preview',
    provider: 'StepFun / NVIDIA NIM',
    description: 'Fast general assistant model.',
    tags: ['general', 'fast'],
    context_window: 65536,
    speed: 'fastest',
    best_for: 'Snappy answers and short tasks',
    capabilities: ['tool_use', 'code', 'streaming'],
    is_active: false,
    source: 'nvidia-nim',
  },
  {
    id: 'z-ai/glm-5.3',
    name: 'GLM 5.3',
    provider: 'Z.ai / NVIDIA NIM',
    description: 'Strong general model - slower responses, deep answers.',
    tags: ['general', 'deep'],
    context_window: 131072,
    speed: 'deep',
    best_for: 'Deep, thorough written answers',
    capabilities: ['reasoning', 'tool_use', 'code', 'long_context', 'research', 'streaming'],
    is_active: false,
    source: 'nvidia-nim',
  },
  {
    id: 'meta/llama-3.2-90b-vision-instruct',
    name: 'Llama 3.2 90B Vision',
    provider: 'Meta / NVIDIA NIM',
    description: 'Multimodal vision-language model for image understanding.',
    tags: ['vision', 'multimodal'],
    context_window: 131072,
    speed: 'balanced',
    best_for: "Image Q&A, screenshots, charts and diagrams",
    capabilities: ['vision', 'tool_use', 'long_context', 'streaming'],
    is_active: false,
    source: 'nvidia-nim',
  },
];

export const FALLBACK_CATALOG: ModelCatalog = {
  models: FALLBACK_MODELS,
  active_model: 'meta/llama-3.3-70b-instruct',
  default_model: 'meta/llama-3.3-70b-instruct',
  provider_status: 'offline',
  has_api_key: false,
  capability_labels: { ...CAPABILITY_LABELS },
  execution: {
    efforts: CHAT_EFFORT_OPTIONS.map((option) => option.id),
    default_effort: 'auto',
    adaptive_model_routing: false,
    quality_gate_enabled: true,
    native_tool_calling_enabled: true,
    quality_max_repairs: 3,
  },
  coding: FALLBACK_CODING_CATALOG,
};

function cloneCatalog(catalog: ModelCatalog): ModelCatalog {
  return JSON.parse(JSON.stringify(catalog)) as ModelCatalog;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function normalizeModel(raw: unknown): NexusModel | null {
  if (!isRecord(raw) || typeof raw.id !== 'string' || !raw.id.trim()) return null;
  const contextWindow =
    typeof raw.context_window === 'number' && Number.isFinite(raw.context_window)
      ? raw.context_window
      : null;

  return {
    id: raw.id,
    name: stringValue(raw.name, raw.id),
    provider: stringValue(raw.provider, raw.id === AUTO_MODEL_ID ? 'NEXUS Cortex' : 'NVIDIA NIM'),
    description: stringValue(raw.description),
    tags: stringArray(raw.tags),
    context_window: contextWindow,
    speed: stringValue(raw.speed, 'balanced'),
    best_for: stringValue(raw.best_for),
    capabilities: stringArray(raw.capabilities),
    is_active: Boolean(raw.is_active),
    source: stringValue(raw.source, raw.id === AUTO_MODEL_ID ? 'nexus-default' : 'nvidia-nim'),
  };
}

function normalizeExecution(raw: unknown): ModelCatalogExecution {
  const fallback = FALLBACK_CATALOG.execution!;
  if (!isRecord(raw)) return { ...fallback, efforts: [...fallback.efforts] };

  const efforts = Array.isArray(raw.efforts)
    ? raw.efforts
        .map((value) => normalizeChatEffort(value))
        .filter((value, index, values) => values.indexOf(value) === index)
    : [];
  const repairs =
    typeof raw.quality_max_repairs === 'number' && Number.isFinite(raw.quality_max_repairs)
      ? Math.max(0, Math.min(5, Math.round(raw.quality_max_repairs)))
      : fallback.quality_max_repairs;

  return {
    efforts: efforts.length > 0 ? efforts : [...fallback.efforts],
    default_effort: normalizeChatEffort(raw.default_effort),
    adaptive_model_routing: Boolean(raw.adaptive_model_routing),
    quality_gate_enabled:
      typeof raw.quality_gate_enabled === 'boolean'
        ? raw.quality_gate_enabled
        : fallback.quality_gate_enabled,
    native_tool_calling_enabled:
      typeof raw.native_tool_calling_enabled === 'boolean'
        ? raw.native_tool_calling_enabled
        : fallback.native_tool_calling_enabled,
    quality_max_repairs: repairs,
  };
}

function normalizeCodingCatalog(raw: unknown): CodingCapabilityCatalog {
  if (!isRecord(raw)) return { ...FALLBACK_CODING_CATALOG };
  return {
    ...FALLBACK_CODING_CATALOG,
    ...raw,
    focuses: stringArray(raw.focuses).length > 0 ? stringArray(raw.focuses) : FALLBACK_CODING_CATALOG.focuses,
    languages: isRecord(raw.languages)
      ? (raw.languages as CodingCapabilityCatalog['languages'])
      : FALLBACK_CODING_CATALOG.languages,
    frontend: isRecord(raw.frontend)
      ? (raw.frontend as CodingCapabilityCatalog['frontend'])
      : FALLBACK_CODING_CATALOG.frontend,
    tools: stringArray(raw.tools).length > 0 ? stringArray(raw.tools) : FALLBACK_CODING_CATALOG.tools,
    quality_gates:
      stringArray(raw.quality_gates).length > 0
        ? stringArray(raw.quality_gates)
        : FALLBACK_CODING_CATALOG.quality_gates,
  };
}

export function normalizeCatalog(raw: unknown): ModelCatalog {
  if (!isRecord(raw)) return cloneCatalog(FALLBACK_CATALOG);

  const models = Array.isArray(raw.models)
    ? raw.models.map(normalizeModel).filter((model): model is NexusModel => model !== null)
    : [];

  if (models.length === 0) return cloneCatalog(FALLBACK_CATALOG);
  if (!models.some((model) => model.id === AUTO_MODEL_ID)) {
    const auto = FALLBACK_MODELS.find((model) => model.id === AUTO_MODEL_ID);
    if (auto) models.unshift({ ...auto });
  }

  const activeModel = typeof raw.active_model === 'string' ? raw.active_model : null;
  const defaultModel = stringValue(
    raw.default_model,
    activeModel || models.find((model) => model.tags.includes('default'))?.id || AUTO_MODEL_ID,
  );

  return {
    models,
    active_model: activeModel,
    default_model: defaultModel,
    provider_status: stringValue(raw.provider_status, 'simulation'),
    has_api_key: Boolean(raw.has_api_key),
    capability_labels: {
      ...CAPABILITY_LABELS,
      ...(isRecord(raw.capability_labels)
        ? Object.fromEntries(
            Object.entries(raw.capability_labels).filter(
              (entry): entry is [string, string] => typeof entry[1] === 'string',
            ),
          )
        : {}),
    },
    execution: normalizeExecution(raw.execution),
    coding: normalizeCodingCatalog(raw.coding),
  };
}

export async function fetchModelCatalog(): Promise<ModelCatalog> {
  try {
    const raw = await nexusJson<unknown>('/api/models');
    return normalizeCatalog(raw);
  } catch {
    return cloneCatalog(FALLBACK_CATALOG);
  }
}

export function getModelById(models: NexusModel[], modelId: string | null | undefined): NexusModel | null {
  if (!modelId) return null;
  return models.find((model) => model.id === modelId) || null;
}

export function resolveSelectedModelId(catalog: ModelCatalog, preferredId?: string | null): string {
  const preferred = preferredId || getStoredModelId();
  if (getModelById(catalog.models, preferred)) return preferred;
  if (getModelById(catalog.models, AUTO_MODEL_ID)) return AUTO_MODEL_ID;
  return catalog.default_model || catalog.models[0]?.id || AUTO_MODEL_ID;
}

export function modelSupports(model: NexusModel | null | undefined, capability: ModelCapabilityKey): boolean {
  return Boolean(model?.capabilities.includes(capability));
}

export function getCapabilityLabel(
  capability: string,
  labels: Record<string, string> = CAPABILITY_LABELS,
): string {
  return labels[capability] || CAPABILITY_LABELS[capability as ModelCapabilityKey] || capability.replace(/_/g, ' ');
}

export function formatContextWindow(contextWindow: number | null | undefined): string {
  if (!contextWindow) return 'Configured context';
  if (contextWindow >= 1000) return `${Math.round(contextWindow / 1024)}K context`;
  return `${contextWindow.toLocaleString()} context`;
}

export function formatSpeed(speed: string | null | undefined): string {
  if (!speed) return SPEED_LABELS.balanced;
  return SPEED_LABELS[speed] || speed.replace(/_/g, ' ');
}

export function getStoredModelId(): string {
  if (typeof window === 'undefined') return AUTO_MODEL_ID;
  try {
    return window.localStorage.getItem(MODEL_STORAGE_KEY)?.trim() || AUTO_MODEL_ID;
  } catch {
    return AUTO_MODEL_ID;
  }
}

export function saveStoredModelId(modelId: string): string {
  const next = modelId?.trim() || AUTO_MODEL_ID;
  try {
    window.localStorage.setItem(MODEL_STORAGE_KEY, next);
  } catch {
    // Storage may be unavailable in private browsing; selection still works.
  }
  return next;
}

export const DEFAULT_CAPABILITIES: ChatCapabilities = {
  extendedThinking: false,
  artifacts: true,
  deepResearch: false,
  voiceReplies: true,
  memory: true,
  effort: 'auto',
  codingFocus: 'auto',
};

function normalizeCapabilities(raw: unknown): ChatCapabilities {
  if (!isRecord(raw)) return { ...DEFAULT_CAPABILITIES };
  return {
    extendedThinking: typeof raw.extendedThinking === 'boolean' ? raw.extendedThinking : DEFAULT_CAPABILITIES.extendedThinking,
    artifacts: typeof raw.artifacts === 'boolean' ? raw.artifacts : DEFAULT_CAPABILITIES.artifacts,
    deepResearch: typeof raw.deepResearch === 'boolean' ? raw.deepResearch : DEFAULT_CAPABILITIES.deepResearch,
    voiceReplies: typeof raw.voiceReplies === 'boolean' ? raw.voiceReplies : DEFAULT_CAPABILITIES.voiceReplies,
    memory: typeof raw.memory === 'boolean' ? raw.memory : DEFAULT_CAPABILITIES.memory,
    effort: normalizeChatEffort(raw.effort),
    codingFocus: normalizeCodingFocus(raw.codingFocus),
  };
}

export function loadCapabilities(): ChatCapabilities {
  if (typeof window === 'undefined') return { ...DEFAULT_CAPABILITIES };
  try {
    const raw = window.localStorage.getItem(CAPABILITIES_STORAGE_KEY);
    return raw ? normalizeCapabilities(JSON.parse(raw)) : { ...DEFAULT_CAPABILITIES };
  } catch {
    return { ...DEFAULT_CAPABILITIES };
  }
}

export const getStoredCapabilities = loadCapabilities;

export function saveCapabilities(capabilities: ChatCapabilities): ChatCapabilities {
  const next = normalizeCapabilities(capabilities);
  try {
    window.localStorage.setItem(CAPABILITIES_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage failures; React state remains authoritative for the tab.
  }
  return next;
}
