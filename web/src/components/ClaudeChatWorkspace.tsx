import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ArrowUp,
  Asterisk,
  AudioLines,
  Blocks,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Cloud,
  Code2,
  Copy,
  Database,
  Download,
  Eye,
  FilePenLine,
  FilePlus2,
  FileText,
  FolderGit2,
  FolderKanban,
  FolderOpen,
  FolderPlus,
  GitBranch,
  GraduationCap,
  HardDrive,
  LayoutGrid,
  Lightbulb,
  Loader2,
  Lock,
  Mic,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Rocket,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  SquarePen,
  Telescope,
  Trash2,
  Unlock,
  Volume2,
  VolumeX,
  WandSparkles,
  Wrench,
  X,
} from 'lucide-react';
import {
  executeNexusTool,
  fetchNexusTools,
  fetchToolApprovals,
  grantToolApprovals,
} from '../api';
import {
  CHAT_EFFORT_OPTIONS,
  getChatEffortOption,
  getModelById,
} from '../data/modelCatalog';
import { ChatModelPicker } from './ChatModelPicker';
import { NexusAuroraBackground } from './NexusAuroraBackground';
import {
  formatSessionUpdatedAt,
  groupChatSessions,
  type HistorySource,
} from '../utils/chatHistory';
import {
  VOICE_ACCENTS,
  getAccentMeta,
  speakText,
  type VoiceAccentId,
  type VoicePreferences,
} from '../utils/voiceManager';
import type {
  AgentStatus,
  ChatCapabilities,
  ChatCapabilityToggleKey,
  ChatEffort,
  ChatSessionSummary,
  ConversationalMessage,
  ModelCatalog,
  NexusTool,
} from '../types';

type MaybePromise<T> = T | Promise<T>;
type WorkspaceView = 'chat' | 'projects' | 'artifacts' | 'code' | 'customize';
type ComposerMode = 'chat' | 'code';
type ToolParamValue = string | boolean;

interface ClaudeChatWorkspaceProps {
  messages: ConversationalMessage[];
  isStreaming?: boolean;
  onClose: () => void;
  onSendMessage: (message: string, actionType?: 'GRAPH' | 'CODE' | 'RESEARCH') => void;
  onStopGeneration?: () => void;
  queuedCount?: number;

  modelCatalog: ModelCatalog;
  selectedModelId: string;
  onModelChange: (modelId: string) => void;

  capabilities: ChatCapabilities;
  onCapabilitiesChange: (capabilities: ChatCapabilities) => void;

  voicePreferences: VoicePreferences;
  onVoicePreferencesChange: (preferences: VoicePreferences) => void;
  agentStatus: AgentStatus;
  onAgentStatusChange: (status: AgentStatus) => void;
  speakingMessageId?: string | null;
  onSpeakMessage?: (message: ConversationalMessage) => void;
  onStopSpeaking?: () => void;

  sessions: ChatSessionSummary[];
  historySource: HistorySource;
  currentSessionId: string | null;
  isHistoryLoading?: boolean;
  onRefreshHistory: () => MaybePromise<void>;
  onNewChat: () => MaybePromise<boolean | void>;
  onOpenSession: (sessionId: string) => MaybePromise<boolean | void>;
  onRenameSession: (sessionId: string, title: string) => MaybePromise<boolean | void>;
  onDeleteSession: (sessionId: string) => MaybePromise<boolean | void>;
  onClearHistory?: () => MaybePromise<boolean | void>;
}

interface ArtifactItem {
  id: string;
  title: string;
  language: string;
  code: string;
  messageId: string;
}

type ContentSegment =
  | { type: 'text'; text: string }
  | { type: 'code'; language: string; code: string };

const FILE_TOOL_IDS = [
  'write_file',
  'edit_file',
  'delete_file',
  'create_directory',
  'write_files',
  'batch_edit_files',
  'move_path',
  'copy_path',
  'delete_directory',
];
const WORKSPACE_TOOL_IDS = [...FILE_TOOL_IDS, 'create_repository'];

const QUICK_TOOL_PRESETS: Array<{
  id: string;
  label: string;
  detail: string;
  preset: Record<string, ToolParamValue>;
}> = [
  { id: 'release_readiness', label: 'Release readiness', detail: 'Ship/no-ship gate', preset: { path: '.', include_checks: false, fail_on_dirty: true } },
  { id: 'secret_scan', label: 'Secret scan', detail: 'Redacted leak check', preset: { path: '.', max_findings: '100', include_tests: true } },
  { id: 'changelog_draft', label: 'Changelog draft', detail: 'Notes from Git history', preset: { repo_path: '.', max_commits: '50', include_uncommitted: true } },
  { id: 'project_scan', label: 'Scan project', detail: 'Map the whole repo', preset: { path: '.' } },
  { id: 'code_search_semantic', label: 'Semantic code search', detail: 'Find concepts fast', preset: { path: 'src', k: '5', alpha: '0.7' } },
  { id: 'dependency_audit', label: 'Dependency audit', detail: 'Imports vs manifests', preset: { source_path: 'src' } },
  { id: 'web_search', label: 'Web search', detail: 'Titles, URLs, snippets', preset: { max_results: '5' } },
  { id: 'web_fetch', label: 'Fetch a page', detail: 'Readable text + links', preset: { url: 'https://example.com', max_chars: '8000' } },
  { id: 'json_query', label: 'Query JSON', detail: 'Dot/bracket paths', preset: { json_str: '{"users":[{"name":"Nexus"}]}', key_path: 'users[-1].name' } },
];

function draftStorageKey(sessionId: string | null): string {
  return `nexus-chat-draft:${sessionId || 'new-session'}`;
}

function loadComposerDraft(sessionId: string | null): string {
  try {
    return window.sessionStorage.getItem(draftStorageKey(sessionId)) || '';
  } catch {
    return '';
  }
}
const REPOSITORY_TEMPLATES = [
  {
    id: 'python-fastapi',
    label: 'Python FastAPI',
    description: 'API starter with tests, Docker, and health/item endpoints.',
  },
  {
    id: 'react-vite',
    label: 'React + Vite',
    description: 'Interactive web app starter with TypeScript and a task dashboard.',
  },
  {
    id: 'node-api',
    label: 'Node API',
    description: 'Dependency-light JSON API using built-in Node HTTP and tests.',
  },
  {
    id: 'python-cli',
    label: 'Python CLI',
    description: 'Installable command-line package with pytest coverage.',
  },
  {
    id: 'static-site',
    label: 'Static site',
    description: 'Fast HTML/CSS/JS starter that can deploy to GitHub Pages.',
  },
  {
    id: 'empty',
    label: 'Empty repo',
    description: 'README, license, and .gitignore only—bring your own stack.',
  },
] as const;

type RepositoryTemplateId = (typeof REPOSITORY_TEMPLATES)[number]['id'];
const LONG_PARAM_NAMES = new Set([
  'content',
  'code',
  'command',
  'sql',
  'old_text',
  'new_text',
  'json_str',
  'expression',
  'text',
]);

function slugifyRepositoryName(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-._]+|[-._]+$/g, '')
    .slice(0, 100)
    .replace(/[-._]+$/g, '');
}

function greetingForNow(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function isWelcomeMessage(message: ConversationalMessage): boolean {
  return message.id.startsWith('init-') || Boolean(message.toolsUsed?.includes('system_boot'));
}

function parseContentSegments(content: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  const fencePattern = /```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', text: content.slice(lastIndex, match.index) });
    }
    segments.push({
      type: 'code',
      language: (match[1] || '').trim() || 'code',
      code: (match[2] || '').replace(/\n$/, ''),
    });
    lastIndex = fencePattern.lastIndex;
    if (match[0].length === 0) fencePattern.lastIndex += 1;
  }
  if (lastIndex < content.length) segments.push({ type: 'text', text: content.slice(lastIndex) });
  return segments.filter((segment) => segment.type === 'code' || segment.text.trim().length > 0);
}

function extractArtifacts(messages: ConversationalMessage[]): ArtifactItem[] {
  const artifacts: ArtifactItem[] = [];
  messages.forEach((message) => {
    if (message.role !== 'assistant') return;
    parseContentSegments(message.content).forEach((segment, index) => {
      if (segment.type !== 'code') return;
      artifacts.push({
        id: `${message.id}-artifact-${index}`,
        title: `${segment.language || 'code'} artifact`,
        language: segment.language || 'code',
        code: segment.code,
        messageId: message.id,
      });
    });
  });
  return artifacts;
}

function renderInline(text: string, keyPrefix: string) {
  const tokenPattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/|mailto:)[^)\s]+\)|\*[^*]+\*)/g;
  return text.split(tokenPattern).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) return <em key={key}>{part.slice(1, -1)}</em>;
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={key} className="rounded bg-[#efede6] px-1.5 py-0.5 font-mono text-[0.86em] text-[#7a3f21]">
          {part.slice(1, -1)}
        </code>
      );
    }
    const link = part.match(/^\[([^\]]+)\]\(((?:https?:\/\/|mailto:)[^)\s]+)\)$/);
    if (link) {
      return (
        <a key={key} href={link[2]} target="_blank" rel="noreferrer" className="font-medium text-[#b85c38] underline underline-offset-2">
          {link[1]}
        </a>
      );
    }
    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

function renderFormattedText(text: string, keyPrefix: string) {
  return text.split('\n').map((line, lineIndex) => {
    const key = `${keyPrefix}-${lineIndex}`;
    const trimmed = line.trim();
    if (!trimmed) return <div key={key} className="h-3" />;
    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      return (
        <div key={key} className={`mb-2 mt-5 font-semibold text-[#262624] ${heading[1].length === 1 ? 'text-2xl' : heading[1].length === 2 ? 'text-xl' : 'text-lg'}`}>
          {renderInline(heading[2], key)}
        </div>
      );
    }
    const bullet = trimmed.match(/^[-*+]\s+(.+)$/);
    if (bullet) {
      return (
        <div key={key} className="my-1 flex gap-3 pl-2">
          <span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-[#8a867d]" />
          <span>{renderInline(bullet[1], key)}</span>
        </div>
      );
    }
    const numbered = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
    if (numbered) {
      return (
        <div key={key} className="my-1 flex gap-3 pl-2">
          <span className="shrink-0 font-medium text-[#6f6c64]">{numbered[1]}.</span>
          <span>{renderInline(numbered[2], key)}</span>
        </div>
      );
    }
    if (trimmed.startsWith('>')) {
      return (
        <blockquote key={key} className="my-3 border-l-2 border-[#d97757] pl-4 text-[#55534d]">
          {renderInline(trimmed.replace(/^>\s?/, ''), key)}
        </blockquote>
      );
    }
    return <div key={key}>{renderInline(line, key)}</div>;
  });
}

function cleanThinkingText(thinking: string | undefined, content: string): string {
  if (!thinking) return '';
  let cleaned = thinking.replace(/\r\n/g, '\n');
  const finalAnswer = cleaned.match(/final\s+answer\s*:/i);
  if (finalAnswer?.index !== undefined) cleaned = cleaned.slice(0, finalAnswer.index);
  cleaned = cleaned
    .split('\n')
    .filter((line) => !/TOOL_CALL\s*:/i.test(line))
    .join('\n')
    .replace(/^\s*(thought|thinking|reasoning)\s*:\s*/i, '')
    .trim();
  return cleaned === content.trim() ? '' : cleaned;
}

function extensionForLanguage(language: string): string {
  const normalized = language.toLowerCase().replace(/[^a-z0-9+#-]/g, '');
  const extensions: Record<string, string> = {
    typescript: 'ts',
    tsx: 'tsx',
    javascript: 'js',
    jsx: 'jsx',
    python: 'py',
    markdown: 'md',
    shell: 'sh',
    bash: 'sh',
    json: 'json',
    html: 'html',
    css: 'css',
  };
  return extensions[normalized] || normalized || 'txt';
}

function defaultParamValue(toolId: string, name: string, schema: { type?: string }): ToolParamValue {
  if (schema.type === 'boolean') {
    if (name === 'parents') return true;
    if (toolId === 'list_directory' && name === 'include_hidden') return true;
    if (toolId === 'secret_scan' && name === 'include_tests') return true;
    if (toolId === 'release_readiness' && name === 'fail_on_dirty') return true;
    if (toolId === 'changelog_draft' && name === 'include_uncommitted') return true;
    if (toolId === 'create_repository') {
      return ['initialize_git', 'initial_commit', 'include_ci'].includes(name);
    }
    return false;
  }
  if (toolId === 'create_repository') {
    if (name === 'name') return 'my-new-project';
    if (name === 'template') return 'python-fastapi';
    if (name === 'license') return 'MIT';
    if (name === 'description') return 'A useful new project created with Nexus.';
  }
  if (name === 'path') {
    if (toolId === 'write_file') return 'notes/new-file.txt';
    if (toolId === 'create_directory') return 'new-folder';
    if (toolId === 'code_search_semantic') return 'src';
    if (['list_directory', 'grep', 'find_databases', 'project_scan', 'directory_tree', 'code_diagnostics', 'project_checks'].includes(toolId)) return '.';
    return '';
  }
  if (name === 'source_path' && toolId === 'dependency_audit') return 'src';
  if (name === 'requirements_path') return 'requirements.in';
  if (name === 'pyproject_path') return 'pyproject.toml';
  if (name === 'repo_path') return '.';
  if (name === 'target' && toolId === 'pytest_runner') return 'tests/unit';
  if (name === 'options' && toolId === 'pytest_runner') return '-q';
  if (name === 'include' && toolId === 'grep') return '*.py';
  if (name === 'expression' && toolId === 'calculator') return '2 + 2';
  if (name === 'url' && ['web_fetch', 'http_request'].includes(toolId)) return 'https://example.com';
  if (name === 'method' && toolId === 'http_request') return 'GET';
  if (name === 'json_str' && toolId === 'json_query') return '{"users":[{"name":"Nexus"}]}';
  if (name === 'key_path' && toolId === 'json_query') return 'users[-1].name';
  if (name === 'timezone' && toolId === 'current_datetime') return 'Asia/Kolkata';
  if (name === 'timeout') return '30';
  if (name === 'max_chars') return toolId === 'web_fetch' ? '8000' : '5000';
  if (name === 'max_results') return '5';
  if (name === 'max_entries') return '200';
  if (name === 'start_line') return '1';
  if (name === 'alpha') return '0.7';
  if (name === 'k') return '5';
  if (name === 'depth') return '2';
  return '';
}

function buildDefaultParams(
  tool: NexusTool | null,
  preset: Record<string, ToolParamValue> = {},
): Record<string, ToolParamValue> {
  if (!tool) return { ...preset };
  const values: Record<string, ToolParamValue> = {};
  Object.entries(tool.input_schema.properties || {}).forEach(([name, schema]) => {
    values[name] = defaultParamValue(tool.id, name, schema);
  });
  return { ...values, ...preset };
}

const Toggle: React.FC<{
  enabled: boolean;
  label: string;
  onToggle: () => void;
}> = ({ enabled, label, onToggle }) => (
  <button
    type="button"
    role="switch"
    aria-checked={enabled}
    aria-label={label}
    onClick={onToggle}
    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${enabled ? 'bg-[#262624]' : 'bg-[#d8d3c7] hover:bg-[#c9c3b4]'}`}
  >
    <span className={`absolute top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow transition-all ${enabled ? 'left-[22px]' : 'left-[2px]'}`} />
  </button>
);

const NavItem: React.FC<{
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  badge?: string;
  onClick: () => void;
}> = ({ icon, label, active = false, badge, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[15px] transition-colors ${
      active
        ? 'border border-white/80 bg-white/85 font-medium text-[#262624] shadow-[0_8px_22px_rgba(73,63,45,0.08)] ring-1 ring-[#e9dfd0]'
        : 'border border-transparent text-[#4d4b46] hover:bg-white/45'
    }`}
  >
    <span className="flex h-5 w-5 items-center justify-center text-[#6f6c64]">{icon}</span>
    <span className="min-w-0 flex-1 truncate">{label}</span>
    {badge && <span className="rounded-full bg-[#e7e2d6] px-2 py-0.5 text-[11px] font-medium text-[#6f6c64]">{badge}</span>}
  </button>
);

export const ClaudeChatWorkspace: React.FC<ClaudeChatWorkspaceProps> = ({
  messages,
  isStreaming = false,
  onClose,
  onSendMessage,
  onStopGeneration,
  queuedCount = 0,
  modelCatalog,
  selectedModelId,
  onModelChange,
  capabilities,
  onCapabilitiesChange,
  voicePreferences,
  onVoicePreferencesChange,
  agentStatus,
  onAgentStatusChange,
  speakingMessageId,
  onSpeakMessage,
  onStopSpeaking,
  sessions,
  historySource,
  currentSessionId,
  isHistoryLoading = false,
  onRefreshHistory,
  onNewChat,
  onOpenSession,
  onRenameSession,
  onDeleteSession,
  onClearHistory,
}) => {
  const [view, setView] = useState<WorkspaceView>('chat');
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window === 'undefined' || window.innerWidth >= 900);
  const [input, setInput] = useState(() => loadComposerDraft(currentSessionId));
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [composerMode, setComposerMode] = useState<ComposerMode>('chat');
  const [plusOpen, setPlusOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmClearHistory, setConfirmClearHistory] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedThinkingIds, setExpandedThinkingIds] = useState<Set<string>>(() => new Set());
  const [isDictating, setIsDictating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const [tools, setTools] = useState<NexusTool[]>([]);
  const [isLoadingTools, setIsLoadingTools] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<Record<string, boolean>>({});
  const [approvalsError, setApprovalsError] = useState<string | null>(null);
  const [isGrantingApprovals, setIsGrantingApprovals] = useState(false);
  const [selectedToolId, setSelectedToolId] = useState('edit_file');
  const [toolSearch, setToolSearch] = useState('');
  const [toolCategory, setToolCategory] = useState('all');
  const [paramValues, setParamValues] = useState<Record<string, ToolParamValue>>({});
  const [isRunningTool, setIsRunningTool] = useState(false);
  const [toolResult, setToolResult] = useState<Record<string, any> | null>(null);
  const [toolRunError, setToolRunError] = useState<string | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [repoName, setRepoName] = useState('school-fee-tracker');
  const [repoTemplate, setRepoTemplate] = useState<RepositoryTemplateId>('python-fastapi');
  const [repoDescription, setRepoDescription] = useState('Track school fees, receipts, and pending balances.');
  const [repoPath, setRepoPath] = useState('');
  const [repoLicense, setRepoLicense] = useState('MIT');
  const [repoGitHubRemote, setRepoGitHubRemote] = useState('');
  const [repoInitializeGit, setRepoInitializeGit] = useState(true);
  const [repoInitialCommit, setRepoInitialCommit] = useState(true);
  const [repoIncludeCi, setRepoIncludeCi] = useState(true);
  const [repoOverwrite, setRepoOverwrite] = useState(false);
  const [isCreatingRepository, setIsCreatingRepository] = useState(false);
  const [repositoryError, setRepositoryError] = useState<string | null>(null);
  const [repositoryResult, setRepositoryResult] = useState<Record<string, any> | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const plusRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const toolRunControllerRef = useRef<AbortController | null>(null);
  const repositoryRunControllerRef = useRef<AbortController | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const lastAutoScrolledMessageIdRef = useRef<string | null>(null);
  const draftSessionIdRef = useRef(currentSessionId);

  const selectedModel = useMemo(
    () => getModelById(modelCatalog.models, selectedModelId) || modelCatalog.models[0] || null,
    [modelCatalog.models, selectedModelId],
  );
  const visibleMessages = useMemo(() => messages.filter((message) => !isWelcomeMessage(message)), [messages]);
  const hasConversation = visibleMessages.length > 0;
  const artifacts = useMemo(() => extractArtifacts(visibleMessages), [visibleMessages]);
  const selectedArtifact = artifacts.find((artifact) => artifact.id === selectedArtifactId) || artifacts[0] || null;
  const currentSession = sessions.find((session) => session.id === currentSessionId) || null;
  const filteredSessions = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return sessions;
    return sessions.filter((session) =>
      [session.title, session.preview, session.model || '', session.id].join(' ').toLowerCase().includes(query),
    );
  }, [searchQuery, sessions]);
  const groupedSessions = useMemo(() => groupChatSessions(filteredSessions), [filteredSessions]);

  const selectedTool = tools.find((tool) => tool.id === selectedToolId) || null;
  const toolCategories = useMemo(
    () => ['all', ...Array.from(new Set(tools.map((tool) => tool.category || 'general'))).sort()],
    [tools],
  );
  const filteredTools = useMemo(() => {
    const query = toolSearch.trim().toLowerCase();
    return tools.filter((tool) => {
      if (toolCategory !== 'all' && tool.category !== toolCategory) return false;
      if (!query) return true;
      return [tool.id, tool.name, tool.description, tool.category].join(' ').toLowerCase().includes(query);
    });
  }, [toolCategory, toolSearch, tools]);
  const repositoryApproved = Boolean(approvals.create_repository);
  const workspaceToolsApproved = WORKSPACE_TOOL_IDS.every((toolId) => approvals[toolId]);
  const repositorySlug = slugifyRepositoryName(repoName);
  const repositoryTargetPreview = repoPath.trim() || `projects/${repositorySlug || 'my-new-project'}`;
  const isBusy = agentStatus === 'thinking' || isStreaming;
  const slashQuery = input.startsWith('/') && !input.includes(' ') ? input.slice(1).toLowerCase() : null;
  const slashTools = slashQuery === null
    ? []
    : tools.filter((tool) => tool.id.toLowerCase().includes(slashQuery) || tool.name.toLowerCase().includes(slashQuery)).slice(0, 8);

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const element = scrollRef.current;
    if (!element) return;
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    element.scrollTo({ top: element.scrollHeight, behavior });
  }, []);

  const handleMessageScroll = () => {
    const element = scrollRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    const nearBottom = distance < 140;
    shouldStickToBottomRef.current = nearBottom;
    setIsNearBottom(nearBottom);
  };

  const loadTools = useCallback(async (showLoading = true) => {
    if (showLoading) setIsLoadingTools(true);
    try {
      const loaded = await fetchNexusTools();
      setTools(loaded);
      setToolsError(null);
      setSelectedToolId((current) => (loaded.some((tool) => tool.id === current) ? current : loaded[0]?.id || current));
    } catch (error) {
      setToolsError(error instanceof Error ? error.message : 'Could not load the tool registry.');
    } finally {
      if (showLoading) setIsLoadingTools(false);
    }
  }, []);

  const loadApprovals = useCallback(async () => {
    try {
      const loaded = await fetchToolApprovals();
      setApprovals(Object.fromEntries(loaded.map((item) => [item.tool_id, item.approved])));
      setApprovalsError(null);
    } catch (error) {
      setApprovalsError(
        error instanceof Error
          ? error.message
          : 'Tool approval status is unavailable. Direct tool execution requires an admin key.',
      );
    }
  }, []);

  useEffect(() => {
    void onRefreshHistory();
    void loadTools();
    void loadApprovals();
  }, [loadApprovals, loadTools, onRefreshHistory]);

  useEffect(() => {
    if (!selectedTool) return;
    setParamValues((current) => {
      const defaults = buildDefaultParams(selectedTool);
      const next: Record<string, ToolParamValue> = {};
      Object.keys(defaults).forEach((key) => {
        next[key] = key in current ? current[key] : defaults[key];
      });
      return next;
    });
  }, [selectedTool]);

  useEffect(() => {
    if (draftSessionIdRef.current !== currentSessionId) {
      draftSessionIdRef.current = currentSessionId;
      setInput(loadComposerDraft(currentSessionId));
      shouldStickToBottomRef.current = true;
      setIsNearBottom(true);
      return;
    }
    try {
      const key = draftStorageKey(currentSessionId);
      if (input) window.sessionStorage.setItem(key, input);
      else window.sessionStorage.removeItem(key);
    } catch {
      // Draft persistence is best-effort in restricted browser contexts.
    }
  }, [currentSessionId, input]);

  useEffect(() => {
    if (view !== 'chat') return;
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    const frame = window.requestAnimationFrame(() => scrollToLatest('auto'));
    return () => window.cancelAnimationFrame(frame);
  }, [currentSessionId, scrollToLatest, view]);

  useEffect(() => {
    if (view !== 'chat' || !scrollRef.current) return;
    const latest = visibleMessages[visibleMessages.length - 1];
    const latestId = latest?.id || null;
    const userJustSent =
      latest?.role === 'user' && latestId !== lastAutoScrolledMessageIdRef.current;
    if (userJustSent || shouldStickToBottomRef.current) {
      const frame = window.requestAnimationFrame(() => scrollToLatest('auto'));
      lastAutoScrolledMessageIdRef.current = latestId;
      return () => window.cancelAnimationFrame(frame);
    }
    lastAutoScrolledMessageIdRef.current = latestId;
    return undefined;
  }, [expandedThinkingIds, scrollToLatest, view, visibleMessages]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [input, view]);

  useEffect(() => {
    if (!plusOpen) return undefined;
    const handlePointerDown = (event: MouseEvent) => {
      if (plusRef.current && !plusRef.current.contains(event.target as Node)) setPlusOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPlusOpen(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [plusOpen]);

  useEffect(() => () => {
    try {
      recognitionRef.current?.abort?.();
    } catch {
      // Browser recognition cleanup is best-effort.
    }
    toolRunControllerRef.current?.abort();
    repositoryRunControllerRef.current?.abort();
  }, []);

  const showNotice = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice((current) => (current === message ? null : current)), 6000);
  };

  const copyText = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
      } finally {
        document.body.removeChild(textarea);
      }
    }
    setCopiedId(id);
    window.setTimeout(() => setCopiedId((current) => (current === id ? null : current)), 2000);
  };

  const downloadArtifact = (artifact: ArtifactItem) => {
    const blob = new Blob([artifact.code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `nexus-artifact.${extensionForLanguage(artifact.language)}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const downloadJsonResult = (filename: string, value: unknown) => {
    const blob = new Blob([JSON.stringify(value, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const closeSidebarOnMobile = () => {
    if (window.innerWidth < 900) setSidebarOpen(false);
  };

  const handleNewChat = async () => {
    const result = await onNewChat();
    if (result === false) {
      showNotice('NEXUS is still working. Wait for the current response before starting a new chat.');
      return;
    }
    setView('chat');
    closeSidebarOnMobile();
    window.setTimeout(() => textareaRef.current?.focus(), 50);
  };

  const handleOpenSession = async (sessionId: string) => {
    if (sessionId === currentSessionId) {
      setView('chat');
      closeSidebarOnMobile();
      return;
    }
    const result = await onOpenSession(sessionId);
    if (result === false) {
      showNotice('That chat could not be opened while NEXUS is busy or saved history is unavailable.');
      return;
    }
    setView('chat');
    closeSidebarOnMobile();
  };

  const saveSessionRename = async (sessionId: string) => {
    const title = draftTitle.trim();
    if (!title) return;
    const result = await onRenameSession(sessionId, title);
    if (result !== false) setEditingSessionId(null);
  };

  const handleDeleteSession = async (sessionId: string) => {
    const result = await onDeleteSession(sessionId);
    if (result !== false) setConfirmDeleteId(null);
  };

  const insertPrompt = (prompt: string, mode: ComposerMode = 'chat') => {
    setComposerMode(mode);
    setView('chat');
    setInput(prompt);
    window.setTimeout(() => textareaRef.current?.focus(), 50);
  };

  const handleSend = (event?: React.FormEvent) => {
    event?.preventDefault();
    const query = input.trim();
    if (!query) return;
    shouldStickToBottomRef.current = true;
    setIsNearBottom(true);
    onSendMessage(query, composerMode === 'code' ? 'CODE' : 'GRAPH');
    setInput('');
    setPlusOpen(false);
    setView('chat');
  };

  const handleAttachFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const truncated = text.length > 30000;
      const content = truncated ? text.slice(0, 30000) : text;
      setInput((current) => `${current ? `${current}\n\n` : ''}[Attached file: ${file.name}]\n\n\`\`\`\n${content}\n\`\`\``);
      showNotice(truncated ? `${file.name} attached and truncated to 30,000 characters.` : `${file.name} attached to the message.`);
      setPlusOpen(false);
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    } catch {
      showNotice('That file could not be read as text.');
    }
  };

  const toggleDictation = () => {
    if (isDictating) {
      try {
        recognitionRef.current?.stop?.();
      } catch {
        // Ignore browser-specific stop errors.
      }
      setIsDictating(false);
      if (agentStatus === 'listening') onAgentStatusChange('idle');
      return;
    }

    const RecognitionCtor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!RecognitionCtor) {
      showNotice('Voice dictation is not supported in this browser. Voice replies still work where speech synthesis is available.');
      return;
    }
    const recognition = new RecognitionCtor();
    recognitionRef.current = recognition;
    recognition.lang = voicePreferences.accent;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onresult = (speechEvent: any) => {
      let finalTranscript = '';
      for (let index = speechEvent.resultIndex; index < speechEvent.results.length; index += 1) {
        const result = speechEvent.results[index];
        if (result.isFinal) finalTranscript += result[0]?.transcript || '';
      }
      if (finalTranscript.trim()) {
        setInput((current) => `${current ? `${current.replace(/\s+$/, '')} ` : ''}${finalTranscript.trim()}`);
      }
    };
    recognition.onerror = () => {
      setIsDictating(false);
      onAgentStatusChange('idle');
      showNotice('Voice dictation stopped. Check microphone permission and try again.');
    };
    recognition.onend = () => {
      setIsDictating(false);
      onAgentStatusChange('idle');
      textareaRef.current?.focus();
    };
    try {
      recognition.start();
      setIsDictating(true);
      onAgentStatusChange('listening');
    } catch {
      showNotice('Voice dictation could not start in this browser.');
    }
  };

  const handleSpeakToggle = (message: ConversationalMessage) => {
    if (speakingMessageId === message.id && onStopSpeaking) {
      onStopSpeaking();
      return;
    }
    if (onSpeakMessage) {
      onSpeakMessage(message);
      return;
    }
    speakText(message.content, {
      accent: voicePreferences.accent,
      voiceURI: voicePreferences.voiceURI,
      rate: voicePreferences.rate,
      pitch: voicePreferences.pitch,
      onStatusChange: onAgentStatusChange,
    });
  };

  const testVoice = () => {
    if (agentStatus === 'speaking' && onStopSpeaking) {
      onStopSpeaking();
      return;
    }
    speakText(getAccentMeta(voicePreferences.accent).sample, {
      accent: voicePreferences.accent,
      voiceURI: voicePreferences.voiceURI,
      rate: voicePreferences.rate,
      pitch: voicePreferences.pitch,
      onStatusChange: onAgentStatusChange,
    });
  };

  const grantApprovals = async (toolIds: string[]) => {
    setIsGrantingApprovals(true);
    try {
      const granted = await grantToolApprovals(toolIds);
      setApprovals((current) => ({
        ...current,
        ...Object.fromEntries(granted.map((item) => [item.tool_id, item.approved])),
      }));
      setApprovalsError(null);
      showNotice(`Approved ${granted.map((item) => item.tool_id).join(', ')} for this tenant.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not grant tool approval.';
      setApprovalsError(message);
      showNotice(message);
    } finally {
      setIsGrantingApprovals(false);
    }
  };

  const selectTool = (toolId: string, preset: Record<string, ToolParamValue> = {}) => {
    const tool = tools.find((item) => item.id === toolId) || null;
    setSelectedToolId(toolId);
    setParamValues(buildDefaultParams(tool, preset));
    setToolResult(null);
    setToolRunError(null);
  };

  const openTool = (toolId: string, preset: Record<string, ToolParamValue> = {}) => {
    selectTool(toolId, preset);
    setView('code');
    closeSidebarOnMobile();
  };

  const insertToolInstruction = (tool: NexusTool) => {
    const templates: Record<string, string> = {
      write_file: 'Use write_file to create ',
      edit_file: 'Use edit_file to change ',
      delete_file: 'Use delete_file to delete ',
      create_directory: 'Use create_directory to create the folder ',
      create_repository: 'Use create_repository to create a local Git-ready repository for ',
      read_file: 'Use read_file to read ',
      list_directory: 'Use list_directory to list ',
      run_shell: 'Use run_shell to run ',
      pytest_runner: 'Use pytest_runner to run the tests in ',
      web_search: 'Use web_search to find current, citable sources for ',
      web_fetch: 'Use web_fetch to read and summarize ',
      http_request: 'Use http_request to call ',
      code_search_semantic: 'Use code_search_semantic to find where the codebase handles ',
      dependency_audit: 'Use dependency_audit to compare imports with the manifests in ',
      secret_scan: 'Use secret_scan to scan this project for leaked secrets in ',
      release_readiness: 'Use release_readiness to check if this project is ready to release: ',
      changelog_draft: 'Use changelog_draft to draft release notes for ',
      project_scan: 'Use project_scan to map ',
      json_query: 'Use json_query to extract a value from ',
      current_datetime: 'Use current_datetime for the Asia/Kolkata time and ',
    };
    insertPrompt(
      templates[tool.id] || `Use the ${tool.id} tool to `,
      ['code', 'files', 'projects'].includes(tool.category) ? 'code' : 'chat',
    );
  };

  const buildToolParams = (): Record<string, any> => {
    if (!selectedTool) return {};
    const params: Record<string, any> = {};
    const required = new Set(selectedTool.input_schema.required || []);
    Object.entries(selectedTool.input_schema.properties || {}).forEach(([name, rawSchema]) => {
      const schema = rawSchema as { type?: string };
      const raw = paramValues[name];
      if (schema.type === 'boolean') {
        params[name] = Boolean(raw);
        return;
      }
      const value = typeof raw === 'string' ? raw : '';
      if (value === '' && !required.has(name)) return;
      if (schema.type === 'integer' || schema.type === 'number') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) params[name] = schema.type === 'integer' ? Math.trunc(parsed) : parsed;
        return;
      }
      if (schema.type === 'array' || schema.type === 'object' || schema.type === 'any') {
        try {
          params[name] = JSON.parse(value);
        } catch {
          params[name] = value;
        }
        return;
      }
      params[name] = value;
    });
    return params;
  };

  const runSelectedTool = async () => {
    if (!selectedTool || isRunningTool) return;
    const controller = new AbortController();
    toolRunControllerRef.current = controller;
    setIsRunningTool(true);
    setToolRunError(null);
    try {
      const response = await executeNexusTool(
        selectedTool.id,
        buildToolParams(),
        controller.signal,
      );
      setToolResult(response.result);
      if (response.result?.approval_required) {
        setToolRunError('This tool is approval-gated. Grant it above, then run it again.');
      } else if (response.result?.error) {
        setToolRunError(String(response.result.error));
      }
      void loadTools(false);
      void loadApprovals();
    } catch (error) {
      setToolResult(null);
      if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
        setToolRunError('Stopped waiting for this tool result. A server-side task may still finish in the background.');
      } else {
        setToolRunError(error instanceof Error ? error.message : 'Tool execution failed.');
      }
    } finally {
      if (toolRunControllerRef.current === controller) toolRunControllerRef.current = null;
      setIsRunningTool(false);
    }
  };

  const stopWaitingForTool = () => {
    toolRunControllerRef.current?.abort();
  };

  const buildRepositoryParams = (): Record<string, any> => {
    const params: Record<string, any> = {
      name: repositorySlug,
      template: repoTemplate,
      description: repoDescription.trim() || `A new ${repositorySlug} project created with Nexus.`,
      license: repoLicense,
      initialize_git: repoInitializeGit,
      initial_commit: repoInitializeGit && repoInitialCommit,
      include_ci: repoIncludeCi,
      overwrite: repoOverwrite,
    };
    if (repoPath.trim()) params.path = repoPath.trim();
    if (repoGitHubRemote.trim()) params.github_remote = repoGitHubRemote.trim();
    return params;
  };

  const createRepositoryDirect = async () => {
    if (!repositorySlug) {
      setRepositoryError('Give the repository a name with at least one letter or number.');
      return;
    }
    if (!repositoryApproved) {
      setRepositoryError('Approve create_repository first. Nexus will not write project files without that permission.');
      return;
    }
    const controller = new AbortController();
    repositoryRunControllerRef.current = controller;
    setIsCreatingRepository(true);
    setRepositoryError(null);
    setRepositoryResult(null);
    try {
      const response = await executeNexusTool(
        'create_repository',
        buildRepositoryParams(),
        controller.signal,
      );
      const result = (response.result || {}) as Record<string, any>;
      setRepositoryResult(result);
      if (result.approval_required) {
        setRepositoryError('Repository creation is approval-gated. Approve create_repository, then try again.');
      } else if (result.error) {
        setRepositoryError(String(result.error));
      } else if (result.created) {
        showNotice(`Created ${String(result.name || repositorySlug)} at ${String(result.relative_path || result.path || repositoryTargetPreview)}.`);
      }
      void loadTools(false);
      void loadApprovals();
    } catch (error) {
      if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
        setRepositoryError('Stopped waiting for repository creation. Check the target folder before retrying, because the server may have finished it.');
      } else {
        setRepositoryError(error instanceof Error ? error.message : 'Repository creation failed.');
      }
    } finally {
      if (repositoryRunControllerRef.current === controller) repositoryRunControllerRef.current = null;
      setIsCreatingRepository(false);
    }
  };

  const stopWaitingForRepository = () => {
    repositoryRunControllerRef.current?.abort();
  };

  const askAgentToCreateRepository = () => {
    const name = repositorySlug || 'my-new-project';
    const description = repoDescription.trim() || 'a useful real-world project';
    insertPrompt(
      `Create a local Git-ready ${repoTemplate} repository called ${name} for ${description}. Use create_repository, verify the result, then tell me the exact path, files created, run/test commands, and optional GitHub push commands. Do not claim a GitHub repo was created or pushed.`,
      'code',
    );
  };

  const openRepositoryBuilderTool = () => {
    openTool('create_repository', {
      name: repositorySlug || 'my-new-project',
      path: repoPath.trim(),
      template: repoTemplate,
      description: repoDescription.trim(),
      license: repoLicense,
      github_remote: repoGitHubRemote.trim(),
      initialize_git: repoInitializeGit,
      initial_commit: repoInitializeGit && repoInitialCommit,
      include_ci: repoIncludeCi,
      overwrite: repoOverwrite,
    });
  };

  const toggleCapability = (key: ChatCapabilityToggleKey) => {
    onCapabilitiesChange({ ...capabilities, [key]: !capabilities[key] });
  };

  const setEffort = (effort: ChatEffort) => {
    onCapabilitiesChange({ ...capabilities, effort });
  };

  const selectedEffort = getChatEffortOption(capabilities.effort);

  const toggleThinking = (messageId: string) => {
    setExpandedThinkingIds((current) => {
      const next = new Set(current);
      if (next.has(messageId)) next.delete(messageId);
      else next.add(messageId);
      return next;
    });
  };

  const renderCodeBlock = (segment: Extract<ContentSegment, { type: 'code' }>, id: string) => (
    <div key={id} className="my-4 overflow-hidden rounded-2xl border border-[#34322e] bg-[#211f1d] shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-[#d8d2c4]">
          <Code2 className="h-4 w-4 text-[#d97757]" />
          {segment.language} artifact
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void copyText(id, segment.code)}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-[#d8d2c4] transition-colors hover:bg-white/10 hover:text-white"
          >
            {copiedId === id ? <Check className="h-3.5 w-3.5 text-emerald-300" /> : <Copy className="h-3.5 w-3.5" />}
            {copiedId === id ? 'Copied' : 'Copy'}
          </button>
          <button
            type="button"
            onClick={() => downloadArtifact({ id, title: segment.language, language: segment.language, code: segment.code, messageId: id })}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-[#d8d2c4] transition-colors hover:bg-white/10 hover:text-white"
          >
            <Download className="h-3.5 w-3.5" />
            Download
          </button>
        </div>
      </div>
      <pre className="max-h-[460px] overflow-auto p-4 font-mono text-[13px] leading-6 text-[#f1eee7]">
        <code>{segment.code}</code>
      </pre>
    </div>
  );

  const renderMessage = (message: ConversationalMessage) => {
    if (message.role === 'user') {
      return (
        <div key={message.id} className="flex justify-end">
          <div className="max-w-[82%] whitespace-pre-wrap rounded-[24px] rounded-br-lg border border-white/70 bg-[linear-gradient(135deg,rgba(233,230,220,0.96),rgba(238,243,255,0.88))] px-5 py-3.5 text-[16px] leading-7 text-[#262624] shadow-[0_8px_24px_rgba(73,63,45,0.06)] sm:max-w-[72%]">
            {message.content}
          </div>
        </div>
      );
    }
    if (message.role === 'system') {
      return (
        <div key={message.id} className="flex justify-center">
          <div className="rounded-full bg-[#efede6] px-3 py-1.5 text-xs text-[#77736a]">{message.content}</div>
        </div>
      );
    }

    const isProcessing =
      isBusy &&
      /^(Connecting to NEXUS|NEXUS is (processing|reasoning|verifying)|Nexus is (working|reasoning|verifying))/.test(
        message.content,
      );
    const thinking = capabilities.extendedThinking ? cleanThinkingText(message.thinking, message.content) : '';
    const modelName = message.model ? getModelById(modelCatalog.models, message.model)?.name || message.model.split('/').pop() : null;
    const visibleTools = (message.toolsUsed || []).filter((tool) => tool !== 'system_boot' && tool !== 'ast_sandbox_guard');
    const effectiveEffort = message.execution?.effective_effort
      ? getChatEffortOption(String(message.execution.effective_effort)).label
      : null;
    const qualityIssues = message.quality?.issues?.map((issue) => issue.code).filter(Boolean) || [];

    return (
      <article key={message.id} className="flex gap-3 sm:gap-4">
        <div
          title="NEXUS"
          className="nexus-gradient-orb mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl text-white shadow-[0_8px_20px_rgba(124,108,240,0.22)] ring-2 ring-white/80"
        >
          <Sparkles className="h-[18px] w-[18px]" />
        </div>
        <div className="min-w-0 flex-1 text-[16px] leading-7 text-[#35332f]">
          {isProcessing ? (
            <div className="flex items-center gap-3 py-2 text-[#77736a]">
              <span className="flex gap-1">
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#d97757] [animation-delay:-0.2s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#8b7cf6] [animation-delay:-0.1s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#2f9e8f]" />
              </span>
              <span>{message.content.replace('Connecting to NEXUS cognitive stream...', 'NEXUS is working…')}</span>
              {visibleTools.length > 0 && <span className="text-sm">Using {visibleTools.join(', ')}</span>}
            </div>
          ) : (
            <>
              {thinking && (
                <div className="mb-4 overflow-hidden rounded-2xl border border-[#ded8f0] bg-[linear-gradient(135deg,rgba(255,246,238,0.9),rgba(243,240,255,0.88),rgba(235,250,246,0.82))] shadow-sm">
                  <button
                    type="button"
                    onClick={() => toggleThinking(message.id)}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm font-medium text-[#6f6c64]"
                  >
                    <Brain className="h-4 w-4 text-[#d97757]" />
                    Extended thinking
                    <ChevronRight className={`ml-auto h-4 w-4 transition-transform ${expandedThinkingIds.has(message.id) ? 'rotate-90' : ''}`} />
                  </button>
                  {expandedThinkingIds.has(message.id) && (
                    <div className="whitespace-pre-wrap border-t border-[#e3ded2] px-4 py-3 text-sm leading-6 text-[#625f58]">{thinking}</div>
                  )}
                </div>
              )}
              {parseContentSegments(message.content).map((segment, index) =>
                segment.type === 'code'
                  ? renderCodeBlock(segment, `${message.id}-${index}`)
                  : <div key={`${message.id}-${index}`}>{renderFormattedText(segment.text, `${message.id}-${index}`)}</div>,
              )}
            </>
          )}

          {(visibleTools.length > 0 ||
            modelName ||
            effectiveEffort ||
            message.quality ||
            message.status === 'stopped' ||
            message.status === 'error') && (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[#85817a]">
              {message.status === 'stopped' && (
                <span className="rounded-full bg-amber-100 px-2.5 py-1 font-semibold text-amber-800">Stopped</span>
              )}
              {message.status === 'error' && (
                <span className="rounded-full bg-red-100 px-2.5 py-1 font-semibold text-red-800">Stream error</span>
              )}
              {visibleTools.map((tool) => (
                <button
                  key={tool}
                  type="button"
                  onClick={() => openTool(tool)}
                  title={`Open ${tool} in the Tools panel`}
                  className="flex items-center gap-1.5 rounded-full border border-[#ddd8cc] bg-white/85 px-2.5 py-1 font-medium text-[#625f58] shadow-sm backdrop-blur transition-colors hover:border-[#d97757]/50 hover:text-[#9a4b2f]"
                >
                  <Wrench className="h-3 w-3" />
                  {tool}
                </button>
              ))}
              {modelName && <span className="rounded-full bg-[#efede6] px-2.5 py-1">{modelName}</span>}
              {effectiveEffort && (
                <span
                  title="Effective execution effort selected by Nexus for this answer"
                  className="flex items-center gap-1 rounded-full bg-violet-100 px-2.5 py-1 font-semibold text-violet-800"
                >
                  <Rocket className="h-3 w-3" />
                  {effectiveEffort} effort
                </span>
              )}
              {message.quality && (
                <span
                  title={
                    qualityIssues.length > 0
                      ? `Objective quality checks: ${qualityIssues.join(', ')}`
                      : 'Passed Nexus objective completeness and evidence checks'
                  }
                  className={`flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ${
                    message.quality.passed
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  <ShieldCheck className="h-3 w-3" />
                  {message.quality.status === 'guardrail_blocked'
                    ? 'Guardrail checked'
                    : `${message.quality.passed ? 'Verified' : 'Quality'} · ${Math.round(message.quality.score)}`}
                  {message.quality.repair_attempts_used
                    ? ` · ${message.quality.repair_attempts_used} repair${message.quality.repair_attempts_used === 1 ? '' : 's'}`
                    : ''}
                </span>
              )}
              <span>{message.timestamp}</span>
            </div>
          )}

          {!isProcessing && (
            <div className="mt-2 flex items-center gap-1 text-[#85817a]">
              <button
                type="button"
                onClick={() => void copyText(message.id, message.content)}
                title="Copy response"
                className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors hover:bg-[#efede6] hover:text-[#262624]"
              >
                {copiedId === message.id ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                {copiedId === message.id ? 'Copied' : 'Copy'}
              </button>
              <button
                type="button"
                onClick={() => handleSpeakToggle(message)}
                title={speakingMessageId === message.id ? 'Stop voice reply' : `Listen in ${voicePreferences.accent}`}
                className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors hover:bg-[#efede6] hover:text-[#262624]"
              >
                {speakingMessageId === message.id ? <Square className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                {speakingMessageId === message.id ? 'Stop' : 'Listen'}
              </button>
            </div>
          )}
        </div>
      </article>
    );
  };

  const renderPlusMenu = () => (
    <div className="absolute bottom-[calc(100%+10px)] left-0 z-30 w-[300px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-[#e0dbce] bg-white shadow-[0_18px_50px_rgba(38,38,36,0.16)]">
      <div className="p-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-[#35332f] hover:bg-[#f3f0e8]"
        >
          <Paperclip className="h-4 w-4 text-[#77736a]" />
          <span className="flex-1">Attach a text or code file</span>
        </button>
        <button
          type="button"
          onClick={() => {
            setPlusOpen(false);
            setView('code');
          }}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-[#35332f] hover:bg-[#f3f0e8]"
        >
          <Wrench className="h-4 w-4 text-[#77736a]" />
          <span className="flex-1">Tools & file actions</span>
          <span className="rounded-full bg-[#efede6] px-2 py-0.5 text-[11px] text-[#77736a]">{tools.length || '—'}</span>
        </button>
        <button
          type="button"
          onClick={() => {
            setPlusOpen(false);
            setView('projects');
          }}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-[#35332f] hover:bg-[#f3f0e8]"
        >
          <FolderGit2 className="h-4 w-4 text-[#d97757]" />
          <span className="flex-1">Create a repository</span>
          <span className="rounded-full bg-[#f6e4db] px-2 py-0.5 text-[11px] font-medium text-[#9a4b2f]">New</span>
        </button>
        <button
          type="button"
          onClick={() => insertPrompt('/', composerMode)}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-[#35332f] hover:bg-[#f3f0e8]"
        >
          <Code2 className="h-4 w-4 text-[#77736a]" />
          <span className="flex-1">Insert a tool with /</span>
        </button>
      </div>
      <div className="space-y-1 border-t border-[#efede6] p-2">
        <div className="px-3 pb-2 pt-1">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9a968d]">
            <Rocket className="h-3.5 w-3.5 text-[#d97757]" />
            Execution effort
          </div>
          <div className="mt-2 grid grid-cols-5 gap-1" role="group" aria-label="Execution effort">
            {CHAT_EFFORT_OPTIONS.map((option) => {
              const selected = capabilities.effort === option.id;
              return (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={selected}
                  title={`${option.label}: ${option.description}`}
                  onClick={() => setEffort(option.id)}
                  className={`rounded-full px-1 py-1.5 text-[11px] font-semibold transition-colors ${
                    selected
                      ? 'bg-[#262624] text-white shadow-sm'
                      : 'bg-[#efede6] text-[#625f58] hover:bg-[#e5dfd2] hover:text-[#262624]'
                  }`}
                >
                  {option.shortLabel}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] leading-4 text-[#85817a]">{selectedEffort.description}</p>
        </div>
        {(
          [
            ['extendedThinking', 'Extended thinking', Brain],
            ['deepResearch', 'Deep research', Telescope],
            ['artifacts', 'Artifacts', Blocks],
            ['voiceReplies', 'Voice replies', AudioLines],
            ['memory', 'Conversation memory', Database],
          ] as Array<[ChatCapabilityToggleKey, string, React.ComponentType<{ className?: string }>]>
        ).map(([key, label, Icon]) => (
          <div key={key} className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-[#35332f] hover:bg-[#f7f5ef]">
            <Icon className="h-4 w-4 text-[#77736a]" />
            <span className="flex-1">{label}</span>
            <Toggle enabled={capabilities[key]} label={label} onToggle={() => toggleCapability(key)} />
          </div>
        ))}
      </div>
    </div>
  );

  const renderComposer = () => (
    <form onSubmit={handleSend} className="relative w-full">
      {(isBusy || queuedCount > 0) && (
        <div
          aria-live="polite"
          className="mb-2 flex flex-wrap items-center gap-2 rounded-full border border-[#e4dcc9] bg-white/85 px-3 py-2 text-xs text-[#625f58] shadow-sm backdrop-blur"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#d97757]" />
          <span className="font-medium">
            {isBusy ? 'Nexus is working…' : 'Nexus will continue shortly…'}
            {queuedCount > 0 ? ` ${queuedCount} message${queuedCount === 1 ? '' : 's'} queued.` : ''}
          </span>
          <span className="hidden text-[#9a968d] sm:inline">You can type the next message now.</span>
          {onStopGeneration && (
            <button
              type="button"
              disabled={!isBusy}
              onClick={onStopGeneration}
              className="ml-auto flex items-center gap-1.5 rounded-full bg-[#262624] px-3 py-1.5 font-semibold text-white transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Square className="h-3 w-3" />
              Stop generating
            </button>
          )}
        </div>
      )}
      <div ref={plusRef} className="relative">
        {plusOpen && renderPlusMenu()}
        {slashQuery !== null && slashTools.length > 0 && (
          <div className="absolute bottom-[calc(100%+10px)] left-0 z-30 max-h-[320px] w-[360px] max-w-[calc(100vw-2rem)] overflow-y-auto rounded-2xl border border-[#e0dbce] bg-white p-2 shadow-[0_18px_50px_rgba(38,38,36,0.16)]">
            <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#9a968d]">Tools</div>
            {slashTools.map((tool) => (
              <button
                key={tool.id}
                type="button"
                onClick={() => insertToolInstruction(tool)}
                className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-[#f3f0e8]"
              >
                <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-[#d97757]" />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-[#262624]">{tool.id}</span>
                  <span className="block truncate text-xs text-[#85817a]">{tool.description}</span>
                </span>
                {tool.requires_approval && <Lock className="ml-auto h-3.5 w-3.5 shrink-0 text-[#b0aa9d]" />}
              </button>
            ))}
          </div>
        )}

        <div className="nexus-composer-glow rounded-[28px] border border-[#ddd8cc]/95 bg-white/[0.94] shadow-[0_14px_44px_rgba(61,57,47,0.11)] backdrop-blur-xl transition-shadow focus-within:border-[#c9b8a5] focus-within:shadow-[0_18px_52px_rgba(61,57,47,0.15)]">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              const nativeEvent = event.nativeEvent as KeyboardEvent;
              if (
                event.key === 'Enter'
                && !event.shiftKey
                && !nativeEvent.isComposing
                && nativeEvent.keyCode !== 229
              ) {
                event.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            placeholder={
              isBusy
                ? 'Nexus is working — type to queue the next message…'
                : composerMode === 'code'
                  ? 'Describe code, files, or a repository to create…  (type / for tools)'
                  : 'Ask for a real-life plan, a fix, a decision, or research…'
            }
            className="max-h-[220px] w-full resize-none bg-transparent px-5 pb-2 pt-4 text-[17px] leading-7 text-[#262624] outline-none placeholder:text-[#aaa69d]"
          />
          <div className="flex flex-wrap items-center gap-1.5 px-3 pb-3 sm:gap-2">
            <button
              type="button"
              onClick={() => setPlusOpen((current) => !current)}
              title="Add files, tools, and capabilities"
              className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors ${plusOpen ? 'bg-[#262624] text-white' : 'text-[#55534d] hover:bg-[#f0eee6]'}`}
            >
              <Plus className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title="Attach a text or code file"
              className="hidden h-9 w-9 items-center justify-center rounded-full text-[#55534d] transition-colors hover:bg-[#f0eee6] sm:flex"
            >
              <Paperclip className="h-[18px] w-[18px]" />
            </button>

            <div className="flex rounded-full bg-[#f0eee6] p-1" aria-label="Chat mode">
              <button
                type="button"
                onClick={() => setComposerMode('chat')}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-all ${composerMode === 'chat' ? 'bg-white text-[#262624] shadow-sm' : 'text-[#77736a] hover:text-[#262624]'}`}
              >
                Chat
              </button>
              <button
                type="button"
                onClick={() => setComposerMode('code')}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-all ${composerMode === 'code' ? 'bg-white text-[#262624] shadow-sm' : 'text-[#77736a] hover:text-[#262624]'}`}
              >
                Code
              </button>
            </div>

            <div className="ml-auto flex min-w-0 items-center gap-1 sm:gap-1.5">
              <ChatModelPicker
                catalog={modelCatalog}
                value={selectedModelId}
                onChange={onModelChange}
                variant="composer"
                placement="up"
                align="right"
                className="hidden md:block"
              />

              <button
                type="button"
                onClick={toggleDictation}
                title={isDictating ? 'Stop dictation' : `Dictate in ${voicePreferences.accent}`}
                className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors ${isDictating ? 'animate-pulse bg-[#d97757] text-white' : 'text-[#55534d] hover:bg-[#f0eee6]'}`}
              >
                <Mic className="h-[18px] w-[18px]" />
              </button>
              <button
                type="button"
                onClick={() => toggleCapability('voiceReplies')}
                title={capabilities.voiceReplies ? `Voice replies on (${voicePreferences.accent})` : 'Voice replies off'}
                className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors ${capabilities.voiceReplies ? 'text-[#262624] hover:bg-[#f0eee6]' : 'text-[#b0aa9d] hover:bg-[#f0eee6]'}`}
              >
                {capabilities.voiceReplies ? <AudioLines className="h-5 w-5" /> : <VolumeX className="h-5 w-5" />}
              </button>

              {input.trim() ? (
                <button
                  type="submit"
                  title={isBusy ? 'Queue message' : 'Send message'}
                  className="nexus-gradient-orb flex h-9 w-9 items-center justify-center rounded-full text-white shadow-[0_8px_20px_rgba(124,108,240,0.24)] transition-all hover:scale-[1.04] hover:shadow-[0_10px_26px_rgba(217,119,87,0.28)]"
                >
                  <ArrowUp className="h-5 w-5" />
                </button>
              ) : isBusy ? (
                <button
                  type="button"
                  disabled={!onStopGeneration}
                  onClick={onStopGeneration}
                  title="Stop generating"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[#262624] text-white transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Square className="h-4 w-4" />
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,.md,.py,.js,.jsx,.ts,.tsx,.json,.csv,.html,.css,.xml,.yaml,.yml,.toml,.sql,.sh,text/*"
        className="hidden"
        onChange={handleAttachFile}
      />
    </form>
  );

  const renderStarterChips = () => (
    <div className="mt-6 grid w-full gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
      {[
        {
          label: 'Solve a real problem',
          detail: 'Best first move, checklist & fallback',
          icon: Lightbulb,
          prompt: 'Help me solve this real-life problem step by step: ',
          mode: 'chat' as ComposerMode,
          tile: 'bg-orange-100 text-[#b85c38]',
        },
        {
          label: 'Fix something safely',
          detail: 'Diagnose first, then repair',
          icon: Wrench,
          prompt: 'Help me troubleshoot this safely. The exact symptom is: ',
          mode: 'chat' as ComposerMode,
          tile: 'bg-teal-100 text-teal-700',
        },
        {
          label: 'Make a decision',
          detail: 'Compare costs, risks & trade-offs',
          icon: Scale,
          prompt: 'Help me decide between these options. My budget, deadline, and options are: ',
          mode: 'chat' as ComposerMode,
          tile: 'bg-violet-100 text-violet-700',
        },
        {
          label: 'Create a repository',
          detail: 'Runnable template + Git + tests',
          icon: FolderGit2,
          prompt: '',
          mode: 'code' as ComposerMode,
          tile: 'bg-[#f6e4db] text-[#b85c38]',
          action: 'repository' as const,
        },
        {
          label: 'Plan study or work',
          detail: 'A realistic schedule you can finish',
          icon: GraduationCap,
          prompt: 'Make a realistic step-by-step plan for: ',
          mode: 'chat' as ComposerMode,
          tile: 'bg-sky-100 text-sky-700',
        },
        {
          label: 'Turn idea into action',
          detail: 'Business, career or project launch',
          icon: Rocket,
          prompt: 'Turn this idea into a practical 7-day action plan: ',
          mode: 'chat' as ComposerMode,
          tile: 'bg-rose-100 text-rose-700',
        },
      ].map((card) => {
        const Icon = card.icon;
        return (
          <button
            key={card.label}
            type="button"
            onClick={() => {
              if ('action' in card && card.action === 'repository') {
                setView('projects');
                return;
              }
              insertPrompt(card.prompt, card.mode);
            }}
            className="nexus-suggestion-card group flex min-h-[104px] items-start gap-3 rounded-[22px] border border-[#e0dbce]/90 bg-white/70 p-4 text-left shadow-[0_8px_26px_rgba(73,63,45,0.05)] backdrop-blur hover:border-[#cbb99f] hover:bg-white/95"
          >
            <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${card.tile}`}>
              <Icon className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold leading-5 text-[#262624]">{card.label}</span>
              <span className="mt-1 block text-xs leading-5 text-[#85817a]">{card.detail}</span>
            </span>
            <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-[#c0bbac] transition-all group-hover:translate-x-0.5 group-hover:text-[#8a867d]" />
          </button>
        );
      })}
    </div>
  );

  const renderChatView = () => {
    if (!hasConversation) {
      return (
        <div className="nxs-scroll relative z-[1] min-h-0 flex-1 overflow-y-auto px-4">
          <div className="mx-auto flex min-h-full w-full max-w-[900px] flex-col items-center justify-center py-10 sm:py-12">
            <div className="mb-8 text-center">
              <div className="nexus-gradient-orb nexus-sparkle-float mx-auto flex h-14 w-14 items-center justify-center rounded-[20px] text-white shadow-[0_16px_38px_rgba(124,108,240,0.26)] ring-4 ring-white/70">
                <Sparkles className="h-7 w-7" />
              </div>
              <p className="mt-5 text-[11px] font-bold uppercase tracking-[0.22em] text-[#9a8f7d]">
                Nexus hybrid workspace
              </p>
              <h1 className="mt-3 font-serif text-[42px] font-normal leading-[1.04] tracking-[-0.025em] text-[#3d392f] sm:text-[62px]">
                {greetingForNow()}.
                <span className="nexus-gradient-text block pb-2">What shall we solve or build?</span>
              </h1>
              <p className="mx-auto mt-3 max-w-xl text-[15px] leading-6 text-[#77736a]">
                Practical answers first — with real steps, tools, files, repositories, and verification when you need action.
              </p>
            </div>
            {renderComposer()}
            {renderStarterChips()}
            <div className="mt-7 flex flex-wrap items-center justify-center gap-2 text-xs text-[#7c786f]">
              <span className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/65 px-3 py-1.5 shadow-sm backdrop-blur">
                <Sparkles className="h-3.5 w-3.5 text-[#8b7cf6]" />
                {selectedModel?.name || 'NEXUS Auto'} · {modelCatalog.provider_status}
              </span>
              <span className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/65 px-3 py-1.5 shadow-sm backdrop-blur">
                <Wrench className="h-3.5 w-3.5 text-[#2f9e8f]" /> {tools.length ? `${tools.length} tools connected` : 'Tools loading'}
              </span>
              <span className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/65 px-3 py-1.5 shadow-sm backdrop-blur">
                {workspaceToolsApproved ? <Unlock className="h-3.5 w-3.5 text-emerald-600" /> : <Lock className="h-3.5 w-3.5 text-[#b85c38]" />}
                {workspaceToolsApproved ? 'Files + repo builder approved' : 'Files + repos approval-gated'}
              </span>
              <span className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/65 px-3 py-1.5 shadow-sm backdrop-blur">
                <AudioLines className="h-3.5 w-3.5 text-[#d97757]" /> Voice: {voicePreferences.accent}
              </span>
              <span className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/65 px-3 py-1.5 shadow-sm backdrop-blur">
                {historySource === 'backend' ? <Cloud className="h-3.5 w-3.5" /> : <HardDrive className="h-3.5 w-3.5" />}
                {historySource === 'backend' ? 'Backend history' : 'Local history fallback'}
              </span>
            </div>
          </div>
        </div>
      );
    }

    return (
      <>
        <div
          ref={scrollRef}
          onScroll={handleMessageScroll}
          className="nxs-scroll relative z-[1] min-h-0 flex-1 overflow-y-auto px-4"
        >
          <div className="mx-auto w-full max-w-[820px] space-y-9 py-8 sm:py-10">
            {visibleMessages.map(renderMessage)}
          </div>
        </div>
        <div className="relative z-[1] shrink-0 bg-[linear-gradient(to_top,rgba(247,245,239,0.94)_0%,rgba(247,245,239,0.74)_62%,transparent_100%)] px-4 pb-4 pt-3">
          {!isNearBottom && (
            <button
              type="button"
              onClick={() => scrollToLatest()}
              className="absolute -top-12 right-4 z-10 flex items-center gap-1.5 rounded-full border border-[#ddd8cc] bg-white/95 px-3.5 py-2 text-xs font-semibold text-[#55534d] shadow-[0_10px_28px_rgba(61,57,47,0.14)] backdrop-blur transition-all hover:-translate-y-0.5 hover:text-[#262624]"
            >
              Jump to latest
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          )}
          <div className="mx-auto w-full max-w-[820px]">
            {renderComposer()}
            <p className="mt-2 text-center text-[11px] text-[#aaa69d]">
              NEXUS can use workspace tools and make mistakes. Check important file changes and test results.
            </p>
          </div>
        </div>
      </>
    );
  };

  const renderToolParamField = (name: string, schema: { type?: string; description?: string; enum?: string[] }) => {
    const required = selectedTool?.input_schema.required?.includes(name);
    const value = paramValues[name];
    const label = (
      <span className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.1em] text-[#85817a]">
        {name}
        {required && <span className="rounded-full bg-[#f6e4db] px-1.5 py-0.5 text-[9px] text-[#9a4b2f]">required</span>}
        <span className="font-normal normal-case tracking-normal text-[#b0aa9d]">{schema.type || 'any'}</span>
      </span>
    );

    if (schema.type === 'boolean') {
      return (
        <div key={name} className="flex items-center justify-between gap-3 rounded-2xl border border-[#e5e0d3] bg-[#fbfaf7] px-4 py-3">
          <div>
            {label}
            {name === 'confirm' && <p className="text-xs text-[#9a968d]">Required safety confirmation for deletion.</p>}
          </div>
          <Toggle
            enabled={Boolean(value)}
            label={name}
            onToggle={() => setParamValues((current) => ({ ...current, [name]: !Boolean(current[name]) }))}
          />
        </div>
      );
    }

    const isLong = LONG_PARAM_NAMES.has(name) || schema.type === 'array' || schema.type === 'object' || schema.type === 'any';
    const commonClass = 'w-full rounded-2xl border border-[#ddd8cc] bg-white px-4 py-3 text-sm text-[#262624] outline-none transition-colors placeholder:text-[#b0aa9d] focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15';

    if (Array.isArray(schema.enum) && schema.enum.length > 0) {
      return (
        <label key={name} className="block">
          {label}
          <select
            value={typeof value === 'string' && value ? value : schema.enum[0]}
            onChange={(event) => setParamValues((current) => ({ ...current, [name]: event.target.value }))}
            className={commonClass}
          >
            {schema.enum.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          {schema.description && <span className="mt-1.5 block text-xs leading-5 text-[#9a968d]">{schema.description}</span>}
        </label>
      );
    }

    return (
      <label key={name} className="block">
        {label}
        {isLong ? (
          <textarea
            value={typeof value === 'string' ? value : ''}
            onChange={(event) => setParamValues((current) => ({ ...current, [name]: event.target.value }))}
            rows={name === 'content' || name === 'code' ? 7 : 4}
            placeholder={schema.description || `Enter ${name}`}
            className={`${commonClass} resize-y font-mono text-[13px] leading-6`}
          />
        ) : (
          <input
            type={schema.type === 'integer' || schema.type === 'number' ? 'number' : 'text'}
            value={typeof value === 'string' ? value : ''}
            onChange={(event) => setParamValues((current) => ({ ...current, [name]: event.target.value }))}
            placeholder={schema.description || `Enter ${name}`}
            className={commonClass}
          />
        )}
      </label>
    );
  };

  const renderCodeView = () => (
    <div className="nxs-scroll relative z-[1] min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
      <div className="mx-auto w-full max-w-[1180px]">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-serif text-4xl font-normal text-[#3d392f]">Code & tools</h2>
            <p className="mt-2 max-w-2xl text-[15px] leading-6 text-[#77736a]">
              Every registered NEXUS tool is available to the chat agent, including the Git-ready repository builder. Admins can also run a tool directly here; file and repo changes stay workspace-confined and approval-gated.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setView('chat')}
            className="rounded-full border border-[#ddd8cc] bg-white px-4 py-2 text-sm font-medium text-[#55534d] hover:text-[#262624]"
          >
            Back to chat
          </button>
        </div>

        {(toolsError || approvalsError) && (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            {toolsError || approvalsError}
          </div>
        )}

        <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
          <section className="overflow-hidden rounded-[24px] border border-[#e0dbce] bg-white shadow-sm">
            <div className="border-b border-[#efede6] p-4">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#aaa69d]" />
                  <input
                    value={toolSearch}
                    onChange={(event) => setToolSearch(event.target.value)}
                    placeholder="Search tools…"
                    className="w-full rounded-full border border-[#ddd8cc] bg-[#fbfaf7] py-2.5 pl-9 pr-3 text-sm outline-none focus:border-[#c9a189]"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    void loadTools();
                    void loadApprovals();
                  }}
                  title="Refresh tools"
                  className="flex h-10 w-10 items-center justify-center rounded-full border border-[#ddd8cc] text-[#77736a] hover:bg-[#f3f0e8]"
                >
                  <RefreshCw className={`h-4 w-4 ${isLoadingTools ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <select
                value={toolCategory}
                onChange={(event) => setToolCategory(event.target.value)}
                className="mt-3 w-full rounded-full border border-[#ddd8cc] bg-[#fbfaf7] px-3 py-2.5 text-sm capitalize outline-none"
              >
                {toolCategories.map((category) => (
                  <option key={category} value={category}>{category === 'all' ? 'All categories' : category}</option>
                ))}
              </select>
            </div>

            <div className="border-b border-[#efede6] bg-[#fbfaf7] p-4">
              <div className="flex items-start gap-3">
                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${workspaceToolsApproved ? 'bg-emerald-100 text-emerald-700' : 'bg-[#f6e4db] text-[#9a4b2f]'}`}>
                  {workspaceToolsApproved ? <ShieldCheck className="h-5 w-5" /> : <Lock className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-[#262624]">Workspace files & repositories</div>
                  <p className="mt-1 text-xs leading-5 text-[#85817a]">
                    {workspaceToolsApproved
                      ? 'Create, edit, delete, folders, and local repositories are approved for this tenant.'
                      : 'Approval is required before the agent or direct runner can mutate files or scaffold a repo.'}
                  </p>
                  {!workspaceToolsApproved && (
                    <button
                      type="button"
                      disabled={isGrantingApprovals}
                      onClick={() => void grantApprovals(WORKSPACE_TOOL_IDS)}
                      className="mt-3 flex items-center gap-2 rounded-full bg-[#262624] px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {isGrantingApprovals ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unlock className="h-3.5 w-3.5" />}
                      Approve workspace tools
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <button type="button" onClick={() => openTool('write_file')} className="flex items-center gap-2 rounded-2xl border border-[#e5e0d3] bg-white px-3 py-2.5 text-left text-xs font-medium hover:border-[#c9a189]"><FilePlus2 className="h-4 w-4 text-[#d97757]" /> Create file</button>
                <button type="button" onClick={() => openTool('edit_file')} className="flex items-center gap-2 rounded-2xl border border-[#e5e0d3] bg-white px-3 py-2.5 text-left text-xs font-medium hover:border-[#c9a189]"><FilePenLine className="h-4 w-4 text-[#d97757]" /> Edit file</button>
                <button type="button" onClick={() => openTool('delete_file', { confirm: false })} className="flex items-center gap-2 rounded-2xl border border-[#e5e0d3] bg-white px-3 py-2.5 text-left text-xs font-medium hover:border-red-300"><Trash2 className="h-4 w-4 text-red-500" /> Delete file</button>
                <button type="button" onClick={() => openTool('create_directory')} className="flex items-center gap-2 rounded-2xl border border-[#e5e0d3] bg-white px-3 py-2.5 text-left text-xs font-medium hover:border-[#c9a189]"><FolderPlus className="h-4 w-4 text-[#d97757]" /> New folder</button>
                <button type="button" onClick={() => openRepositoryBuilderTool()} className="col-span-2 flex items-center justify-center gap-2 rounded-2xl border border-[#ddc7ff] bg-[linear-gradient(135deg,#fff6f0,#f3f0ff_55%,#e9fbf5)] px-3 py-3 text-left text-xs font-semibold text-[#3d392f] shadow-sm hover:border-[#c9a8ff]"><FolderGit2 className="h-4 w-4 text-[#7c6cf0]" /> New repository <GitBranch className="h-3.5 w-3.5 text-[#2f9e8f]" /></button>
              </div>

              <div className="mt-5">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-bold uppercase tracking-[0.14em] text-[#9a968d]">Fast tool presets</div>
                  <span className="rounded-full bg-[#eefaf6] px-2 py-0.5 text-[10px] font-semibold text-emerald-700">Upgraded</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {QUICK_TOOL_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => openTool(preset.id, preset.preset)}
                      className="rounded-2xl border border-[#e5e0d3] bg-white px-3 py-2.5 text-left transition-colors hover:border-[#8b7cf6]/60 hover:bg-[#f7f5ff]"
                    >
                      <span className="flex items-center gap-1.5 text-xs font-semibold text-[#35332f]">
                        <Sparkles className="h-3.5 w-3.5 text-[#8b7cf6]" />
                        {preset.label}
                      </span>
                      <span className="mt-1 block text-[11px] leading-4 text-[#9a968d]">{preset.detail}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="max-h-[520px] overflow-y-auto p-2">
              {isLoadingTools && tools.length === 0 ? (
                <div className="flex items-center gap-2 px-3 py-6 text-sm text-[#85817a]"><Loader2 className="h-4 w-4 animate-spin" /> Loading tools…</div>
              ) : filteredTools.length === 0 ? (
                <div className="px-3 py-6 text-sm text-[#85817a]">No tools match that search.</div>
              ) : filteredTools.map((tool) => (
                <button
                  key={tool.id}
                  type="button"
                  onClick={() => selectTool(tool.id)}
                  className={`mb-1 flex w-full items-start gap-3 rounded-2xl px-3 py-3 text-left transition-colors ${selectedToolId === tool.id ? 'bg-[#f3f0e8]' : 'hover:bg-[#fbfaf7]'}`}
                >
                  <Wrench className={`mt-0.5 h-4 w-4 shrink-0 ${selectedToolId === tool.id ? 'text-[#d97757]' : 'text-[#aaa69d]'}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-[#262624]">{tool.id}</span>
                    <span className="mt-0.5 block line-clamp-2 text-xs leading-5 text-[#85817a]">{tool.description}</span>
                  </span>
                  {tool.requires_approval && (
                    approvals[tool.id]
                      ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                      : <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[#c0bbac]" />
                  )}
                </button>
              ))}
            </div>
          </section>

          <section className="overflow-hidden rounded-[24px] border border-[#e0dbce] bg-white shadow-sm">
            {selectedTool ? (
              <>
                <div className="border-b border-[#efede6] p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-xl font-semibold text-[#262624]">{selectedTool.id}</h3>
                        <span className="rounded-full bg-[#efede6] px-2.5 py-1 text-[11px] font-medium capitalize text-[#77736a]">{selectedTool.category}</span>
                        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">{selectedTool.status}</span>
                        {selectedTool.requires_approval && (
                          <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${approvals[selectedTool.id] ? 'bg-emerald-50 text-emerald-700' : 'bg-[#f6e4db] text-[#9a4b2f]'}`}>
                            {approvals[selectedTool.id] ? 'Approved' : 'Approval required'}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[#77736a]">{selectedTool.description}</p>
                      <p className="mt-2 text-xs text-[#aaa69d]">Used {selectedTool.use_count} times · {(selectedTool.success_rate * 100).toFixed(0)}% success</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => insertToolInstruction(selectedTool)}
                      className="rounded-full border border-[#ddd8cc] px-3.5 py-2 text-xs font-semibold text-[#55534d] hover:bg-[#f3f0e8]"
                    >
                      Ask agent to use it
                    </button>
                  </div>
                </div>

                <div className="space-y-4 p-5">
                  {Object.entries(selectedTool.input_schema.properties || {}).length === 0 ? (
                    <p className="rounded-2xl bg-[#fbfaf7] px-4 py-3 text-sm text-[#85817a]">This tool takes no parameters.</p>
                  ) : (
                    Object.entries(selectedTool.input_schema.properties || {}).map(([name, schema]) => renderToolParamField(name, schema))
                  )}

                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <button
                      type="button"
                      disabled={isRunningTool}
                      onClick={() => void runSelectedTool()}
                      className="flex items-center gap-2 rounded-full bg-[#262624] px-5 py-2.5 text-sm font-semibold text-white transition-opacity disabled:opacity-50"
                    >
                      {isRunningTool ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                      Run tool
                    </button>
                    {isRunningTool && (
                      <button
                        type="button"
                        onClick={stopWaitingForTool}
                        title="Stop waiting for this direct tool result"
                        className="flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-100"
                      >
                        <Square className="h-4 w-4" />
                        Stop waiting
                      </button>
                    )}
                    {selectedTool.requires_approval && !approvals[selectedTool.id] && (
                      <button
                        type="button"
                        disabled={isGrantingApprovals}
                        onClick={() => void grantApprovals([selectedTool.id])}
                        className="flex items-center gap-2 rounded-full border border-[#d9a488] bg-[#fff7f2] px-4 py-2.5 text-sm font-semibold text-[#9a4b2f] disabled:opacity-50"
                      >
                        <Unlock className="h-4 w-4" />
                        Approve {selectedTool.id}
                      </button>
                    )}
                    <span className="text-xs text-[#aaa69d]">Direct execution is admin-only; the chat agent uses the same executor gates.</span>
                  </div>

                  {toolRunError && (
                    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{toolRunError}</div>
                  )}
                  {toolResult && (
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-[#85817a]">Result</div>
                        <div className="ml-auto flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => void copyText('direct-tool-result', JSON.stringify(toolResult, null, 2))}
                            className="flex items-center gap-1.5 rounded-full border border-[#ddd8cc] bg-white px-3 py-1.5 text-xs font-semibold text-[#55534d] hover:bg-[#f3f0e8] hover:text-[#262624]"
                          >
                            {copiedId === 'direct-tool-result' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                            {copiedId === 'direct-tool-result' ? 'Copied' : 'Copy JSON'}
                          </button>
                          <button
                            type="button"
                            onClick={() => downloadJsonResult(`${selectedTool.id}-result.json`, toolResult)}
                            className="flex items-center gap-1.5 rounded-full border border-[#ddd8cc] bg-white px-3 py-1.5 text-xs font-semibold text-[#55534d] hover:bg-[#f3f0e8] hover:text-[#262624]"
                          >
                            <Download className="h-3.5 w-3.5" />
                            Download
                          </button>
                        </div>
                      </div>
                      <pre className="max-h-[420px] overflow-auto rounded-2xl bg-[#211f1d] p-4 font-mono text-xs leading-6 text-[#f1eee7]">
                        {JSON.stringify(toolResult, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-8 text-sm text-[#85817a]">Select a tool to inspect its schema and run it.</div>
            )}
          </section>
        </div>
      </div>
    </div>
  );

  const renderRepositoryBuilder = () => {
    const result = repositoryResult;
    const resultFiles = Array.isArray(result?.files) ? result.files.map(String) : [];
    const runCommands = Array.isArray(result?.run_commands) ? result.run_commands.map(String) : [];
    const pushCommands = Array.isArray(result?.github?.push_commands)
      ? result.github.push_commands.map(String)
      : [];
    const nextSteps = Array.isArray(result?.next_steps) ? result.next_steps.map(String) : [];
    const git = (result?.git || {}) as Record<string, any>;
    const selectedTemplate = REPOSITORY_TEMPLATES.find((template) => template.id === repoTemplate);
    const resultPath = String(result?.relative_path || result?.path || '');

    return (
      <section className="relative mb-5 overflow-hidden rounded-[30px] border border-[#e0dbce] bg-white/[0.92] shadow-[0_20px_55px_rgba(73,63,45,0.09)] backdrop-blur">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-[linear-gradient(90deg,#d97757,#8b7cf6,#2f9e8f)]" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-violet-300/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 -left-20 h-64 w-64 rounded-full bg-orange-300/20 blur-3xl" />

        <div className="relative p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="nexus-gradient-orb flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-white shadow-[0_12px_28px_rgba(124,108,240,0.24)]">
                <FolderGit2 className="h-6 w-6" />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-xl font-semibold text-[#262624]">Repository builder</h3>
                  <span className="rounded-full bg-[#f3f0ff] px-2.5 py-1 text-[11px] font-semibold text-violet-700">
                    Local & Git-ready
                  </span>
                  <span
                    className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      repositoryApproved ? 'bg-emerald-50 text-emerald-700' : 'bg-[#f6e4db] text-[#9a4b2f]'
                    }`}
                  >
                    {repositoryApproved ? <ShieldCheck className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
                    {repositoryApproved ? 'Approved' : 'Approval needed'}
                  </span>
                </div>
                <p className="mt-1.5 max-w-2xl text-sm leading-6 text-[#77736a]">
                  Scaffold a runnable project with source, tests, README, license, optional CI, Git initialization, and an initial commit.
                  Nexus creates it locally only—it never silently creates or pushes a GitHub repository.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={openRepositoryBuilderTool}
              className="flex items-center gap-2 rounded-full border border-[#ddd8cc] bg-white px-3.5 py-2 text-xs font-semibold text-[#55534d] shadow-sm hover:border-[#c9a189] hover:text-[#262624]"
            >
              <Wrench className="h-3.5 w-3.5" />
              Open schema runner
            </button>
          </div>

          {!repositoryApproved && (
            <div className="mt-5 flex flex-wrap items-center gap-3 rounded-2xl border border-[#f0c9b8] bg-[#fff7f2] px-4 py-3 text-sm text-[#7a4a34]">
              <Lock className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1 leading-6">
                <strong>One permission first:</strong> approve <code>create_repository</code> for this tenant. Paths remain inside the workspace and unknown files are never deleted.
              </span>
              <button
                type="button"
                disabled={isGrantingApprovals}
                onClick={() => void grantApprovals(['create_repository'])}
                className="flex items-center gap-2 rounded-full bg-[#262624] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
              >
                {isGrantingApprovals ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unlock className="h-3.5 w-3.5" />}
                Approve repo builder
              </button>
            </div>
          )}

          <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.11em] text-[#85817a]">Repository name</span>
                  <input
                    value={repoName}
                    onChange={(event) => setRepoName(event.target.value)}
                    placeholder="school-fee-tracker"
                    className="mt-2 w-full rounded-2xl border border-[#ddd8cc] bg-white px-4 py-3 text-sm font-medium outline-none transition-all placeholder:text-[#b0aa9d] focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15"
                  />
                  <span className="mt-1.5 block truncate text-xs text-[#9a968d]">
                    Target: <code className="rounded bg-[#f0eee6] px-1.5 py-0.5 text-[#625f58]">{repositoryTargetPreview}</code>
                  </span>
                </label>

                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.11em] text-[#85817a]">License</span>
                  <select
                    value={repoLicense}
                    onChange={(event) => setRepoLicense(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-[#ddd8cc] bg-white px-4 py-3 text-sm outline-none focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15"
                  >
                    <option value="MIT">MIT — simple & permissive</option>
                    <option value="BSD-3-Clause">BSD-3-Clause</option>
                    <option value="Unlicense">Unlicense — public domain</option>
                    <option value="none">No license file</option>
                  </select>
                  <span className="mt-1.5 block text-xs text-[#9a968d]">You can change ownership details in LICENSE later.</span>
                </label>
              </div>

              <label className="mt-4 block">
                <span className="text-xs font-semibold uppercase tracking-[0.11em] text-[#85817a]">What will this project do?</span>
                <textarea
                  value={repoDescription}
                  onChange={(event) => setRepoDescription(event.target.value)}
                  rows={2}
                  placeholder="Track fees, receipts, and pending balances for a small school."
                  className="mt-2 w-full resize-y rounded-2xl border border-[#ddd8cc] bg-white px-4 py-3 text-sm leading-6 outline-none transition-all placeholder:text-[#b0aa9d] focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15"
                />
              </label>

              <div className="mt-5">
                <div className="text-xs font-semibold uppercase tracking-[0.11em] text-[#85817a]">Starter template</div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {REPOSITORY_TEMPLATES.map((template) => {
                    const selected = repoTemplate === template.id;
                    return (
                      <button
                        key={template.id}
                        type="button"
                        onClick={() => setRepoTemplate(template.id)}
                        aria-pressed={selected}
                        className={`rounded-2xl border px-4 py-3 text-left transition-all ${
                          selected
                            ? 'border-[#c9a8ff] bg-[linear-gradient(135deg,#fff6f0,#f3f0ff_58%,#e9fbf5)] shadow-[0_10px_26px_rgba(124,108,240,0.12)]'
                            : 'border-[#e5e0d3] bg-[#fbfaf7] hover:border-[#c9c2b2] hover:bg-white'
                        }`}
                      >
                        <span className="flex items-center justify-between gap-2 text-sm font-semibold text-[#262624]">
                          {template.label}
                          {selected && <Check className="h-4 w-4 text-violet-600" />}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-[#85817a]">{template.description}</span>
                        <span className="mt-2 block font-mono text-[10px] uppercase tracking-wide text-[#aaa69d]">{template.id}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.11em] text-[#85817a]">Custom path <span className="font-normal normal-case">(optional)</span></span>
                  <input
                    value={repoPath}
                    onChange={(event) => setRepoPath(event.target.value)}
                    placeholder={`projects/${repositorySlug || 'my-new-project'}`}
                    className="mt-2 w-full rounded-2xl border border-[#ddd8cc] bg-white px-4 py-3 font-mono text-sm outline-none placeholder:text-[#b0aa9d] focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-semibold uppercase tracking-[0.11em] text-[#85817a]">Existing GitHub remote <span className="font-normal normal-case">(optional)</span></span>
                  <input
                    value={repoGitHubRemote}
                    onChange={(event) => setRepoGitHubRemote(event.target.value)}
                    placeholder="https://github.com/you/repo.git"
                    className="mt-2 w-full rounded-2xl border border-[#ddd8cc] bg-white px-4 py-3 font-mono text-sm outline-none placeholder:text-[#b0aa9d] focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15"
                  />
                </label>
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {(
                  [
                    ['Initialize Git', 'Create a main-branch repo inside the new folder.', repoInitializeGit, () => setRepoInitializeGit((current) => !current)],
                    ['Initial commit', 'Commit the scaffold with a Nexus identity.', repoInitialCommit && repoInitializeGit, () => repoInitializeGit && setRepoInitialCommit((current) => !current)],
                    ['Include CI', 'Add a GitHub Actions test/build workflow.', repoIncludeCi, () => setRepoIncludeCi((current) => !current)],
                    ['Allow non-empty folder', 'Overwrite template files only; unknown files stay.', repoOverwrite, () => setRepoOverwrite((current) => !current)],
                  ] as Array<[string, string, boolean, () => void]>
                ).map(([label, description, enabled, onToggle]) => (
                  <div key={label} className={`flex items-center gap-3 rounded-2xl border border-[#e5e0d3] bg-[#fbfaf7] px-4 py-3 ${label === 'Initial commit' && !repoInitializeGit ? 'opacity-50' : ''}`}>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-[#262624]">{label}</div>
                      <div className="mt-0.5 text-xs leading-5 text-[#9a968d]">{description}</div>
                    </div>
                    <Toggle enabled={enabled} label={label} onToggle={onToggle} />
                  </div>
                ))}
              </div>

              {repositoryError && (
                <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800">
                  {repositoryError}
                </div>
              )}

              <div className="mt-5 flex flex-wrap items-center gap-2.5">
                <button
                  type="button"
                  disabled={isCreatingRepository || !repositorySlug}
                  onClick={() => void createRepositoryDirect()}
                  className="nexus-gradient-orb flex items-center gap-2 rounded-full px-5 py-3 text-sm font-semibold text-white shadow-[0_12px_28px_rgba(124,108,240,0.24)] transition-all hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
                >
                  {isCreatingRepository ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                  {isCreatingRepository ? 'Creating repository…' : 'Create repository'}
                </button>
                {isCreatingRepository && (
                  <button
                    type="button"
                    onClick={stopWaitingForRepository}
                    className="flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 hover:bg-red-100"
                  >
                    <Square className="h-4 w-4" />
                    Stop waiting
                  </button>
                )}
                <button
                  type="button"
                  onClick={askAgentToCreateRepository}
                  className="flex items-center gap-2 rounded-full border border-[#ddd8cc] bg-white px-4 py-3 text-sm font-semibold text-[#55534d] hover:border-[#c9a189] hover:text-[#262624]"
                >
                  <WandSparkles className="h-4 w-4 text-[#8b7cf6]" />
                  Ask Nexus in chat
                </button>
                <span className="text-xs leading-5 text-[#aaa69d]">Direct creation is admin-only and uses the same backend executor gates as chat.</span>
              </div>
            </div>

            <aside className="h-fit rounded-[24px] border border-[#e5e0d3] bg-[#fbfaf7]/90 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#262624]">
                <GitBranch className="h-4 w-4 text-[#2f9e8f]" />
                What you get
              </div>
              <ul className="mt-3 space-y-2.5 text-sm leading-6 text-[#625f58]">
                {[
                  `${selectedTemplate?.label || 'Starter'} source you can run immediately`,
                  'Starter test or build check',
                  'README with exact run commands',
                  repoLicense === 'none' ? 'No license file (your choice)' : `${repoLicense} license`,
                  repoIncludeCi ? 'GitHub Actions CI workflow' : 'No CI workflow',
                  repoInitializeGit ? `Git on main${repoInitialCommit ? ' + initial commit' : ''}` : 'Plain folder (no Git metadata)',
                ].map((item) => (
                  <li key={item} className="flex gap-2">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-emerald-600" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-4 rounded-2xl bg-[#262624] px-4 py-3 font-mono text-xs leading-6 text-[#f1eee7]">
                <span className="text-[#a9a294]">$ cd</span> {repositoryTargetPreview}
                <br />
                <span className="text-[#a9a294]">$</span>{' '}
                {repoTemplate === 'react-vite'
                  ? 'npm install && npm run dev'
                  : repoTemplate === 'node-api'
                    ? 'npm test && npm run dev'
                    : repoTemplate === 'static-site'
                      ? 'python -m http.server 4173'
                      : 'follow README.md'}
              </div>
              <div className="mt-4 border-t border-[#efede6] pt-4 text-xs leading-5 text-[#85817a]">
                <strong className="text-[#625f58]">Safety boundary:</strong> Nexus refuses protected app folders and non-empty targets unless you explicitly allow template overwrite. Publishing stays a deliberate GitHub step.
              </div>
            </aside>
          </div>

          {result?.created && (
            <div className="mt-6 overflow-hidden rounded-[24px] border border-emerald-200 bg-emerald-50/70">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-emerald-100 px-5 py-4">
                <div>
                  <div className="flex items-center gap-2 font-semibold text-emerald-900">
                    <ShieldCheck className="h-5 w-5" />
                    Created {String(result.name || repositorySlug)}
                  </div>
                  <div className="mt-1 break-all font-mono text-xs text-emerald-800/75">{resultPath}</div>
                </div>
                <div className="flex flex-wrap gap-1.5 text-[11px] font-medium text-emerald-800">
                  <span className="rounded-full bg-white/80 px-2.5 py-1">{String(result.template || repoTemplate)}</span>
                  <span className="rounded-full bg-white/80 px-2.5 py-1">{resultFiles.length} files</span>
                  {git.branch && <span className="rounded-full bg-white/80 px-2.5 py-1">branch: {String(git.branch)}</span>}
                  {git.commit && <span className="rounded-full bg-white/80 px-2.5 py-1">commit: {String(git.commit)}</span>}
                  {git.clean !== null && git.clean !== undefined && (
                    <span className="rounded-full bg-white/80 px-2.5 py-1">{git.clean ? 'working tree clean' : 'has uncommitted changes'}</span>
                  )}
                </div>
              </div>

              <div className="grid gap-4 p-5 lg:grid-cols-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.11em] text-emerald-800/70">Files created</div>
                  <div className="nxs-scroll mt-2 max-h-56 overflow-y-auto rounded-2xl bg-white/80 p-3 font-mono text-[11px] leading-5 text-[#4d4b46]">
                    {resultFiles.length ? resultFiles.map((file) => <div key={file}>{file}</div>) : 'See tool result in Code & tools.'}
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase tracking-[0.11em] text-emerald-800/70">Run it</span>
                    <button type="button" onClick={() => void copyText('repo-run-commands', runCommands.join('\n'))} className="flex items-center gap-1 text-[11px] font-semibold text-emerald-800 hover:text-emerald-950">
                      {copiedId === 'repo-run-commands' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedId === 'repo-run-commands' ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <pre className="mt-2 max-h-56 overflow-auto rounded-2xl bg-[#211f1d] p-3 font-mono text-[11px] leading-5 text-[#f1eee7]">{runCommands.join('\n')}</pre>
                </div>
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase tracking-[0.11em] text-emerald-800/70">Publish later</span>
                    <button type="button" onClick={() => void copyText('repo-push-commands', pushCommands.join('\n'))} className="flex items-center gap-1 text-[11px] font-semibold text-emerald-800 hover:text-emerald-950">
                      {copiedId === 'repo-push-commands' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedId === 'repo-push-commands' ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <pre className="mt-2 max-h-56 overflow-auto rounded-2xl bg-[#211f1d] p-3 font-mono text-[11px] leading-5 text-[#f1eee7]">{pushCommands.join('\n')}</pre>
                  <p className="mt-2 text-[11px] leading-4 text-emerald-800/70">Create an empty GitHub repo first. Nexus did not create or push it.</p>
                </div>
              </div>

              {nextSteps.length > 0 && (
                <div className="border-t border-emerald-100 px-5 py-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.11em] text-emerald-800/70">Next steps</div>
                  <ol className="mt-2 grid gap-1.5 text-sm leading-6 text-emerald-950/80 sm:grid-cols-2">
                    {nextSteps.map((step, index) => (
                      <li key={step}><strong>{index + 1}.</strong> {step}</li>
                    ))}
                  </ol>
                </div>
              )}

              <div className="flex flex-wrap gap-2 border-t border-emerald-100 px-5 py-4">
                <button
                  type="button"
                  onClick={() => insertPrompt(`Open the new repository at ${resultPath}. First inspect it with list_directory/read_file, run its starter verification if appropriate, then help me build the first real feature: `, 'code')}
                  className="flex items-center gap-2 rounded-full bg-[#262624] px-4 py-2.5 text-xs font-semibold text-white"
                >
                  <Sparkles className="h-3.5 w-3.5" /> Build first feature
                </button>
                <button
                  type="button"
                  onClick={() => openTool('git_info', { repo_path: resultPath })}
                  className="flex items-center gap-2 rounded-full border border-emerald-200 bg-white/85 px-4 py-2.5 text-xs font-semibold text-emerald-900"
                >
                  <GitBranch className="h-3.5 w-3.5" /> Check Git status
                </button>
                <button
                  type="button"
                  onClick={() => insertPrompt(`Use list_directory to show me the structure of ${resultPath}, then explain where I should add my first feature.`, 'code')}
                  className="flex items-center gap-2 rounded-full border border-emerald-200 bg-white/85 px-4 py-2.5 text-xs font-semibold text-emerald-900"
                >
                  <FolderOpen className="h-3.5 w-3.5" /> Explore structure
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    );
  };

  const renderProjectsView = () => (
    <div className="nxs-scroll relative z-[1] min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
      <div className="mx-auto w-full max-w-[1120px]">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#9a8f7d]">Build locally · publish deliberately</p>
            <h2 className="mt-2 font-serif text-4xl font-normal text-[#3d392f]">Projects</h2>
            <p className="mt-2 text-[15px] text-[#77736a]">Your local NEXUS workspace, repository builder, connected tools, and recent work.</p>
          </div>
          <span className="nexus-glass-light flex items-center gap-2 rounded-full px-3.5 py-2 text-xs font-medium text-[#625f58]">
            <FolderGit2 className="h-4 w-4 text-[#7c6cf0]" />
            New repos default to <code>projects/&lt;name&gt;</code>
          </span>
        </div>

        <div className="mt-6">
          {renderRepositoryBuilder()}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#f6e4db] text-[#d97757]"><FolderKanban className="h-5 w-5" /></span>
              <div>
                <h3 className="font-semibold text-[#262624]">NEXUS workspace</h3>
                <p className="text-xs text-[#85817a]">Workspace-confined file and repository tools</p>
              </div>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-2xl bg-[#fbfaf7] p-3"><div className="text-xl font-semibold">{tools.length || '—'}</div><div className="mt-1 text-[11px] uppercase tracking-wider text-[#aaa69d]">Tools</div></div>
              <div className="rounded-2xl bg-[#fbfaf7] p-3"><div className="text-xl font-semibold">{sessions.length}</div><div className="mt-1 text-[11px] uppercase tracking-wider text-[#aaa69d]">Chats</div></div>
              <div className="rounded-2xl bg-[#fbfaf7] p-3"><div className="text-xl font-semibold">{artifacts.length}</div><div className="mt-1 text-[11px] uppercase tracking-wider text-[#aaa69d]">Artifacts</div></div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => insertPrompt('Use list_directory to explore the workspace root and summarize the project structure.', 'code')} className="rounded-full bg-[#262624] px-4 py-2 text-xs font-semibold text-white">Explore files</button>
              <button type="button" onClick={() => setView('code')} className="rounded-full border border-[#ddd8cc] px-4 py-2 text-xs font-semibold text-[#55534d]">Open tools</button>
              <button type="button" onClick={() => openTool('pytest_runner')} className="rounded-full border border-[#ddd8cc] px-4 py-2 text-xs font-semibold text-[#55534d]">Run tests</button>
              <button type="button" onClick={() => openTool('git_info')} className="rounded-full border border-[#ddd8cc] px-4 py-2 text-xs font-semibold text-[#55534d]">Git status</button>
              <button type="button" onClick={() => openRepositoryBuilderTool()} className="flex items-center gap-1.5 rounded-full border border-[#ddc7ff] bg-[#f3f0ff] px-4 py-2 text-xs font-semibold text-violet-800"><FolderGit2 className="h-3.5 w-3.5" /> Repo schema</button>
            </div>
          </section>

          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold text-[#262624]">Workspace capabilities</h3>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${workspaceToolsApproved ? 'bg-emerald-50 text-emerald-700' : 'bg-[#f6e4db] text-[#9a4b2f]'}`}>{workspaceToolsApproved ? 'Approved' : 'Locked'}</span>
            </div>
            <div className="mt-4 space-y-2">
              {WORKSPACE_TOOL_IDS.map((toolId) => (
                <button key={toolId} type="button" onClick={() => openTool(toolId)} className="flex w-full items-center gap-3 rounded-2xl border border-[#efede6] px-3 py-2.5 text-left hover:bg-[#fbfaf7]">
                  {toolId === 'create_repository' ? <FolderGit2 className="h-4 w-4 text-[#7c6cf0]" /> : <FileText className="h-4 w-4 text-[#d97757]" />}
                  <span className="flex-1 text-sm font-medium">{toolId}</span>
                  {toolId === 'create_repository' && <span className="rounded-full bg-[#f3f0ff] px-2 py-0.5 text-[10px] font-semibold text-violet-700">repo</span>}
                  {approvals[toolId] ? <ShieldCheck className="h-4 w-4 text-emerald-600" /> : <Lock className="h-4 w-4 text-[#b0aa9d]" />}
                </button>
              ))}
            </div>
            {!workspaceToolsApproved && (
              <button type="button" disabled={isGrantingApprovals} onClick={() => void grantApprovals(WORKSPACE_TOOL_IDS)} className="mt-4 w-full rounded-full bg-[#262624] py-2.5 text-sm font-semibold text-white disabled:opacity-50">
                Approve workspace tools
              </button>
            )}
          </section>
        </div>

        <section className="mt-4 rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
          <h3 className="font-semibold text-[#262624]">Recent chats</h3>
          <div className="mt-3 divide-y divide-[#efede6]">
            {sessions.slice(0, 6).map((session) => (
              <button key={session.id} type="button" onClick={() => void handleOpenSession(session.id)} className="flex w-full items-center gap-3 py-3 text-left">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-[#262624]">{session.title}</span>
                  <span className="mt-0.5 block truncate text-xs text-[#85817a]">{session.preview || 'No preview yet'}</span>
                </span>
                <span className="text-xs text-[#aaa69d]">{formatSessionUpdatedAt(session.updated_at)}</span>
              </button>
            ))}
            {sessions.length === 0 && <p className="py-4 text-sm text-[#85817a]">No saved chats yet. Your first completed conversation will appear here.</p>}
          </div>
        </section>
      </div>
    </div>
  );

  const renderArtifactsView = () => (
    <div className="nxs-scroll relative z-[1] min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
      <div className="mx-auto w-full max-w-[1080px]">
        <h2 className="font-serif text-4xl font-normal text-[#3d392f]">Artifacts</h2>
        <p className="mt-2 text-[15px] text-[#77736a]">Code and structured outputs created in this conversation.</p>
        {artifacts.length === 0 ? (
          <div className="mt-8 rounded-[28px] border border-dashed border-[#d8d3c7] bg-white/60 px-6 py-16 text-center">
            <Blocks className="mx-auto h-10 w-10 text-[#c9c2b2]" />
            <h3 className="mt-4 font-medium text-[#262624]">No artifacts yet</h3>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#85817a]">Ask NEXUS to write code or enable Artifacts, and generated code blocks will be collected here for copying or download.</p>
            <button type="button" onClick={() => insertPrompt('Create a small Python artifact that ', 'code')} className="mt-5 rounded-full bg-[#262624] px-5 py-2.5 text-sm font-semibold text-white">Create an artifact</button>
          </div>
        ) : (
          <div className="mt-6 grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
            <div className="space-y-2">
              {artifacts.map((artifact) => (
                <button
                  key={artifact.id}
                  type="button"
                  onClick={() => setSelectedArtifactId(artifact.id)}
                  className={`w-full rounded-2xl border px-4 py-3 text-left ${selectedArtifact?.id === artifact.id ? 'border-[#d9a488] bg-white shadow-sm' : 'border-[#e0dbce] bg-white/60 hover:bg-white'}`}
                >
                  <span className="flex items-center gap-2 text-sm font-medium text-[#262624]"><Code2 className="h-4 w-4 text-[#d97757]" />{artifact.title}</span>
                  <span className="mt-1 block text-xs text-[#85817a]">{artifact.code.split('\n').length} lines</span>
                </button>
              ))}
            </div>
            {selectedArtifact && (
              <div>
                {renderCodeBlock({ type: 'code', language: selectedArtifact.language, code: selectedArtifact.code }, selectedArtifact.id)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  const renderCustomizeView = () => (
    <div className="nxs-scroll relative z-[1] min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
      <div className="mx-auto w-full max-w-[880px]">
        <h2 className="font-serif text-4xl font-normal text-[#3d392f]">Customize</h2>
        <p className="mt-2 text-[15px] text-[#77736a]">Model, practical-answer capabilities, Indian-English voice defaults, repository permissions, and backend history for this hybrid NEXUS chat.</p>

        <div className="mt-6 space-y-4">
          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 font-semibold text-[#262624]"><Brain className="h-5 w-5 text-[#d97757]" /> Model</h3>
            <ChatModelPicker
              catalog={modelCatalog}
              value={selectedModelId}
              onChange={onModelChange}
              variant="settings"
              placement="down"
              align="left"
              className="mt-4"
            />
            {selectedModel && (
              <>
                <p className="mt-3 text-sm leading-6 text-[#77736a]">{selectedModel.description}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[modelCatalog.provider_status, selectedModel.best_for, ...selectedModel.capabilities].filter(Boolean).map((label) => (
                    <span key={label} className="rounded-full bg-[#efede6] px-2.5 py-1 text-[11px] font-medium text-[#77736a]">{label}</span>
                  ))}
                </div>
              </>
            )}
          </section>

          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 font-semibold text-[#262624]"><Rocket className="h-5 w-5 text-[#d97757]" /> Execution effort</h3>
            <p className="mt-2 text-sm leading-6 text-[#77736a]">
              Control how hard Nexus works before it calls an answer final. Auto adapts to each task; Deep and Max spend more effort on evidence, stronger routing, verification, and bounded answer repair.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5" role="group" aria-label="Execution effort">
              {CHAT_EFFORT_OPTIONS.map((option) => {
                const selected = capabilities.effort === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setEffort(option.id)}
                    className={`rounded-2xl border px-3 py-2.5 text-sm font-semibold transition-colors ${
                      selected
                        ? 'border-[#262624] bg-[#262624] text-white shadow-sm'
                        : 'border-[#ddd8cc] bg-[#fbfaf7] text-[#625f58] hover:border-[#c9a189] hover:text-[#262624]'
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
            <div className="mt-3 rounded-2xl bg-[#f7f5ef] px-4 py-3 text-sm leading-6 text-[#625f58]">
              <span className="font-semibold text-[#262624]">{selectedEffort.label}:</span>{' '}
              {selectedEffort.description}
              {modelCatalog.execution?.adaptive_model_routing && (
                <span className="ml-1">Adaptive NVIDIA NIM model routing is active on this server.</span>
              )}
              {modelCatalog.execution && (
                <span className="ml-1">
                  Quality gate: {modelCatalog.execution.quality_gate_enabled ? 'on' : 'off'} · Native tools:{' '}
                  {modelCatalog.execution.native_tool_calling_enabled ? 'on' : 'off'}.
                </span>
              )}
            </div>
          </section>

          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 font-semibold text-[#262624]"><Eye className="h-5 w-5 text-[#d97757]" /> Capabilities</h3>
            <div className="mt-3 divide-y divide-[#efede6]">
              {(
                [
                  ['extendedThinking', 'Extended thinking', 'Show a sanitized reasoning summary when the model provides one.'],
                  ['deepResearch', 'Deep research', 'Bias answers toward broader investigation and evidence gathering.'],
                  ['artifacts', 'Artifacts', 'Collect code blocks as copyable, downloadable artifacts.'],
                  ['voiceReplies', 'Voice replies', 'Speak completed answers with the selected accent.'],
                  ['memory', 'Conversation memory', 'Send the current session id for continuity and backend history.'],
                ] as Array<[ChatCapabilityToggleKey, string, string]>
              ).map(([key, label, description]) => (
                <div key={key} className="flex items-center gap-4 py-3.5">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[#262624]">{label}</div>
                    <div className="mt-0.5 text-xs leading-5 text-[#85817a]">{description}</div>
                  </div>
                  <Toggle enabled={capabilities[key]} label={label} onToggle={() => toggleCapability(key)} />
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 font-semibold text-[#262624]"><Volume2 className="h-5 w-5 text-[#d97757]" /> Voice</h3>
            <label className="mt-4 block text-xs font-semibold uppercase tracking-[0.1em] text-[#85817a]">Accent</label>
            <select
              value={voicePreferences.accent}
              onChange={(event) => onVoicePreferencesChange({ ...voicePreferences, accent: event.target.value as VoiceAccentId, voiceURI: null })}
              className="mt-2 w-full rounded-2xl border border-[#ddd8cc] bg-[#fbfaf7] px-4 py-3 text-sm outline-none focus:border-[#c9a189]"
            >
              {VOICE_ACCENTS.map((accent) => (
                <option key={accent.id} value={accent.id}>{accent.label} ({accent.id})</option>
              ))}
            </select>
            <p className="mt-2 text-xs leading-5 text-[#85817a]">{getAccentMeta(voicePreferences.accent).description} Actual audio depends on a matching voice installed in your browser or operating system.</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#85817a]">Rate · {voicePreferences.rate.toFixed(2)}×</span>
                <input
                  type="range"
                  min="0.5"
                  max="1.5"
                  step="0.05"
                  value={voicePreferences.rate}
                  onChange={(event) => onVoicePreferencesChange({ ...voicePreferences, rate: Number(event.target.value) })}
                  className="mt-2 w-full accent-[#262624]"
                />
              </label>
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-[#85817a]">Pitch · {voicePreferences.pitch.toFixed(2)}×</span>
                <input
                  type="range"
                  min="0.5"
                  max="1.5"
                  step="0.05"
                  value={voicePreferences.pitch}
                  onChange={(event) => onVoicePreferencesChange({ ...voicePreferences, pitch: Number(event.target.value) })}
                  className="mt-2 w-full accent-[#262624]"
                />
              </label>
            </div>
            <button type="button" onClick={testVoice} className="mt-4 flex items-center gap-2 rounded-full bg-[#262624] px-4 py-2.5 text-sm font-semibold text-white">
              {agentStatus === 'speaking' ? <Square className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
              {agentStatus === 'speaking' ? 'Stop test' : 'Test voice'}
            </button>
          </section>

          <section className="rounded-[24px] border border-[#e0dbce] bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 font-semibold text-[#262624]"><ShieldCheck className="h-5 w-5 text-[#d97757]" /> Tool permissions & history</h3>
            <p className="mt-2 text-sm leading-6 text-[#77736a]">
              {workspaceToolsApproved
                ? 'File create/edit/delete/folder and local repository tools are approved for this tenant. Paths remain confined to the workspace, sensitive files stay blocked, and GitHub publishing is never automatic.'
                : 'File and repository mutations are locked until an admin approves them. Read-only tools remain available to the agent.'}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {!workspaceToolsApproved && (
                <button type="button" disabled={isGrantingApprovals} onClick={() => void grantApprovals(WORKSPACE_TOOL_IDS)} className="rounded-full bg-[#262624] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">Approve workspace tools</button>
              )}
              <button type="button" onClick={() => setView('projects')} className="flex items-center gap-2 rounded-full border border-[#ddc7ff] bg-[#f3f0ff] px-4 py-2.5 text-sm font-semibold text-violet-800"><FolderGit2 className="h-4 w-4" /> Repository builder</button>
              <button type="button" onClick={() => setView('code')} className="rounded-full border border-[#ddd8cc] px-4 py-2.5 text-sm font-semibold text-[#55534d]">Open all tools</button>
              {onClearHistory && sessions.length > 0 && (
                confirmClearHistory ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void (async () => {
                        const result = await onClearHistory();
                        if (result !== false) setConfirmClearHistory(false);
                      })()}
                      className="rounded-full bg-red-600 px-4 py-2.5 text-sm font-semibold text-white"
                    >
                      Confirm clear history
                    </button>
                    <button type="button" onClick={() => setConfirmClearHistory(false)} className="rounded-full border border-[#ddd8cc] px-4 py-2.5 text-sm font-semibold text-[#55534d]">Cancel</button>
                  </>
                ) : (
                  <button type="button" onClick={() => setConfirmClearHistory(true)} className="rounded-full border border-red-200 px-4 py-2.5 text-sm font-semibold text-red-700">Clear history</button>
                )
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );

  const activeViewTitle = view === 'chat'
    ? (currentSession?.title || (hasConversation ? 'Conversation' : 'New chat'))
    : view === 'code'
      ? 'Code & tools'
      : view.charAt(0).toUpperCase() + view.slice(1);

  return (
    <div
      className="nexus-hybrid-chat relative flex h-full w-full overflow-hidden bg-[#f7f5ef] text-[#262624]"
      style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}
    >
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/20 md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[284px] shrink-0 overflow-hidden border-r border-[#e5e1d6]/90 bg-[linear-gradient(180deg,rgba(243,239,230,0.98),rgba(238,242,249,0.94))] shadow-[12px_0_36px_rgba(73,63,45,0.05)] backdrop-blur-xl transition-all duration-200 md:static ${
          sidebarOpen ? 'translate-x-0 md:w-[276px]' : '-translate-x-full md:w-0 md:translate-x-0 md:border-r-0'
        }`}
      >
        <div className="flex h-full w-[276px] flex-col">
          <div className="flex items-center gap-2 px-4 pb-2 pt-4">
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              title="Collapse sidebar"
              className="flex h-9 w-9 items-center justify-center rounded-xl text-[#77736a] hover:bg-[#e5e1d6] hover:text-[#262624]"
            >
              <PanelLeftClose className="h-5 w-5" />
            </button>
            <button type="button" onClick={() => setView('chat')} className="group flex min-w-0 items-center gap-2 text-left" title="Nexus hybrid chat">
              <span className="nexus-gradient-orb flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-white shadow-[0_8px_20px_rgba(124,108,240,0.22)] transition-transform group-hover:scale-105">
                <Sparkles className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-1 font-serif text-[24px] leading-none text-[#262624]">
                  Nexus
                  <ChevronDown className="mt-0.5 h-3.5 w-3.5 text-[#85817a]" />
                </span>
                <span className="nexus-gradient-text mt-1 block text-[9px] font-bold uppercase tracking-[0.18em]">Solve · Build · Create</span>
              </span>
            </button>
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-white/70 px-2 py-1 text-[10px] font-medium text-[#85817a]">
              <span className={`h-1.5 w-1.5 rounded-full ${modelCatalog.provider_status === 'live' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
              {modelCatalog.provider_status}
            </span>
          </div>

          <nav className="space-y-0.5 px-3 pt-2">
            <NavItem
              icon={<span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#d97757] text-white"><Plus className="h-3.5 w-3.5" /></span>}
              label="New"
              onClick={() => void handleNewChat()}
            />
            <NavItem
              icon={<Search className="h-5 w-5" />}
              label="Search"
              onClick={() => {
                setSidebarOpen(true);
                window.setTimeout(() => searchInputRef.current?.focus(), 50);
              }}
            />
            <NavItem icon={<FolderKanban className="h-5 w-5" />} label="Projects" active={view === 'projects'} onClick={() => { setView('projects'); closeSidebarOnMobile(); }} />
            <NavItem icon={<Blocks className="h-5 w-5" />} label="Artifacts" badge={artifacts.length ? String(artifacts.length) : undefined} active={view === 'artifacts'} onClick={() => { setView('artifacts'); closeSidebarOnMobile(); }} />
            <NavItem icon={<Code2 className="h-5 w-5" />} label="Code" badge={tools.length ? String(tools.length) : undefined} active={view === 'code'} onClick={() => { setView('code'); closeSidebarOnMobile(); }} />
            <NavItem icon={<SlidersHorizontal className="h-5 w-5" />} label="Customize" active={view === 'customize'} onClick={() => { setView('customize'); closeSidebarOnMobile(); }} />
          </nav>

          <div className="px-4 pb-2 pt-5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[13px] font-medium text-[#85817a]">Chats and tasks</div>
              <button
                type="button"
                onClick={() => void onRefreshHistory()}
                title="Refresh saved chats"
                className="rounded-lg p-1.5 text-[#aaa69d] hover:bg-[#e5e1d6] hover:text-[#262624]"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isHistoryLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
            <div className="relative mt-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#aaa69d]" />
              <input
                ref={searchInputRef}
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search chats"
                className="w-full rounded-full border border-transparent bg-white/60 py-2 pl-9 pr-3 text-sm text-[#262624] outline-none placeholder:text-[#aaa69d] focus:border-[#d8d3c7] focus:bg-white"
              />
            </div>
          </div>

          <div className="nxs-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-3">
            {currentSessionId && !sessions.some((session) => session.id === currentSessionId) && !searchQuery && (
              <button
                type="button"
                onClick={() => setView('chat')}
                className="mb-1 flex w-full items-center gap-2 rounded-xl bg-white/80 px-3 py-2.5 text-left text-sm font-medium text-[#262624]"
              >
                <SquarePen className="h-4 w-4 text-[#d97757]" />
                <span className="flex-1 truncate">New conversation</span>
                <span className="text-[11px] font-normal text-[#aaa69d]">Unsaved</span>
              </button>
            )}

            {groupedSessions.length === 0 ? (
              <div className="px-3 py-4 text-sm leading-6 text-[#9a968d]">
                {isHistoryLoading ? 'Loading saved chats…' : searchQuery ? 'No chats match that search.' : 'Completed chats will appear here.'}
              </div>
            ) : groupedSessions.map((group) => (
              <div key={group.label} className="mb-3">
                <div className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#aaa69d]">{group.label}</div>
                {group.sessions.map((session) => {
                  const isActive = session.id === currentSessionId;
                  if (editingSessionId === session.id) {
                    return (
                      <div key={session.id} className="mb-1 flex items-center gap-1 rounded-xl bg-white p-1.5 shadow-sm">
                        <input
                          value={draftTitle}
                          onChange={(event) => setDraftTitle(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') void saveSessionRename(session.id);
                            if (event.key === 'Escape') setEditingSessionId(null);
                          }}
                          autoFocus
                          className="min-w-0 flex-1 rounded-lg bg-transparent px-2 py-1.5 text-sm outline-none"
                        />
                        <button type="button" onClick={() => void saveSessionRename(session.id)} className="rounded-lg p-1.5 text-emerald-700 hover:bg-emerald-50"><Check className="h-4 w-4" /></button>
                        <button type="button" onClick={() => setEditingSessionId(null)} className="rounded-lg p-1.5 text-[#85817a] hover:bg-[#f0eee6]"><X className="h-4 w-4" /></button>
                      </div>
                    );
                  }
                  if (confirmDeleteId === session.id) {
                    return (
                      <div key={session.id} className="mb-1 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5">
                        <div className="truncate text-sm font-medium text-red-900">Delete “{session.title}”?</div>
                        <div className="mt-2 flex gap-2">
                          <button type="button" onClick={() => void handleDeleteSession(session.id)} className="rounded-full bg-red-600 px-3 py-1.5 text-xs font-semibold text-white">Delete</button>
                          <button type="button" onClick={() => setConfirmDeleteId(null)} className="rounded-full border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-700">Cancel</button>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div
                      key={session.id}
                      className={`group relative mb-0.5 flex items-center rounded-xl transition-colors ${isActive ? 'bg-white/85 shadow-[0_1px_2px_rgba(38,38,36,0.05)]' : 'hover:bg-[#e9e6dc]'}`}
                    >
                      <button
                        type="button"
                        onClick={() => void handleOpenSession(session.id)}
                        className="min-w-0 flex-1 px-3 py-2.5 text-left"
                      >
                        <span className={`block truncate text-[15px] ${isActive ? 'font-medium text-[#262624]' : 'text-[#4d4b46]'}`}>{session.title}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-[#aaa69d]">{formatSessionUpdatedAt(session.updated_at)} · {session.message_count} messages</span>
                      </button>
                      <span className="mr-1 hidden shrink-0 items-center group-hover:flex">
                        <button
                          type="button"
                          title="Rename chat"
                          onClick={() => {
                            setEditingSessionId(session.id);
                            setDraftTitle(session.title);
                          }}
                          className="rounded-lg p-1.5 text-[#85817a] hover:bg-white hover:text-[#262624]"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          title="Delete chat"
                          onClick={() => setConfirmDeleteId(session.id)}
                          className="rounded-lg p-1.5 text-[#85817a] hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </span>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          <div className="border-t border-[#e5e1d6] p-3">
            <button
              type="button"
              onClick={() => {
                setView('customize');
                closeSidebarOnMobile();
              }}
              className="flex w-full items-center gap-3 rounded-2xl px-2 py-2 text-left transition-colors hover:bg-[#e9e6dc]"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#7c6a55] text-sm font-semibold text-white">N</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-[#262624]">NEXUS local workspace</span>
                <span className="block truncate text-xs text-[#85817a]">{historySource === 'backend' ? 'Backend history · Admin tools' : 'Local fallback history'}</span>
              </span>
              <Settings className="h-4 w-4 shrink-0 text-[#85817a]" />
            </button>
          </div>
        </div>
      </aside>

      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <NexusAuroraBackground active={isBusy || isCreatingRepository || isDictating || agentStatus === 'speaking'} />
        <header className="relative z-[3] flex h-14 shrink-0 items-center gap-2 px-3 sm:px-4">
          {!sidebarOpen && (
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              title="Open sidebar"
              className="flex h-9 w-9 items-center justify-center rounded-xl text-[#77736a] hover:bg-[#efede6] hover:text-[#262624]"
            >
              <PanelLeftOpen className="h-5 w-5" />
            </button>
          )}
          <div className="min-w-0 max-w-[38%] truncate text-sm font-medium text-[#77736a]">{activeViewTitle}</div>

          <div className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-2 lg:flex">
            <ChatModelPicker
              catalog={modelCatalog}
              value={selectedModelId}
              onChange={onModelChange}
              variant="header"
              placement="down"
              align="right"
            />
            <span className="hidden items-center gap-1.5 rounded-full border border-white/70 bg-white/60 px-3 py-2 text-[11px] font-medium text-[#77736a] shadow-sm backdrop-blur xl:flex">
              <Wrench className="h-3.5 w-3.5 text-[#2f9e8f]" />
              {tools.length ? `${tools.length} tools` : 'tools…'}
            </span>
            <span className="hidden items-center gap-1.5 rounded-full border border-white/70 bg-white/60 px-3 py-2 text-[11px] font-medium text-[#77736a] shadow-sm backdrop-blur 2xl:flex">
              <AudioLines className="h-3.5 w-3.5 text-[#d97757]" />
              {voicePreferences.accent}
            </span>
          </div>

          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setView('code')}
              className="flex items-center gap-2 rounded-full px-3 py-2 text-sm font-medium text-[#77736a] transition-colors hover:bg-[#efede6] hover:text-[#262624]"
            >
              <Wrench className="h-4 w-4" />
              <span className="hidden sm:inline">Tools</span>
              {tools.length > 0 && <span className="rounded-full bg-[#efede6] px-1.5 py-0.5 text-[10px]">{tools.length}</span>}
            </button>
            <button
              type="button"
              onClick={onClose}
              title="Return to the NEXUS workspace"
              className="flex items-center gap-2 rounded-full border border-[#e0dbce] bg-white/80 px-3.5 py-2 text-sm font-medium text-[#55534d] transition-colors hover:bg-white hover:text-[#262624]"
            >
              <LayoutGrid className="h-4 w-4" />
              <span className="hidden sm:inline">NEXUS OS</span>
            </button>
          </div>
        </header>

        {notice && (
          <div className="relative z-[2] mx-4 mb-2 flex shrink-0 items-center gap-3 rounded-2xl border border-[#ead9ce] bg-[#fff8f3]/95 px-4 py-3 text-sm text-[#7a4a34] shadow-sm backdrop-blur">
            <Asterisk className="h-4 w-4 shrink-0 text-[#d97757]" />
            <span className="min-w-0 flex-1">{notice}</span>
            <button type="button" onClick={() => setNotice(null)} className="rounded-lg p-1 hover:bg-white"><X className="h-4 w-4" /></button>
          </div>
        )}

        {view === 'chat' && renderChatView()}
        {view === 'projects' && renderProjectsView()}
        {view === 'artifacts' && renderArtifactsView()}
        {view === 'code' && renderCodeView()}
        {view === 'customize' && renderCustomizeView()}
      </main>
    </div>
  );
};
