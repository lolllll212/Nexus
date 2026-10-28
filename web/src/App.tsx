import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Sparkles } from 'lucide-react';
import {
  NexusNode,
  NexusLink,
  NodeCategory,
  OperatingMode,
  ResearchClaim,
  AgentStatus,
  ChatCapabilities,
  ChatCodingMetadata,
  ChatExecutionMetadata,
  ChatQualityMetadata,
  ChatSessionRecord,
  ChatSessionSummary,
  ConversationalMessage,
  ModelCatalog,
  TaskDifficulty
} from './types';
import { 
  INITIAL_NEXUS_NODES, 
  INITIAL_NEXUS_LINKS 
} from './data/nexusGraphData';
import { NexusCanvas } from './components/NexusCanvas';
import { WorkspaceView } from './components/workspace/WorkspaceView';
import { DeepResearchView } from './components/DeepResearchView';
import { WorkflowCanvasView } from './components/WorkflowCanvasView';
import { ArchitectureView } from './components/ArchitectureView';
import { LeftSidebar } from './components/LeftSidebar';
import { ContextInspector } from './components/ContextInspector';
import { TopBar } from './components/TopBar';
import { CommandCenter } from './components/CommandCenter';
import { ClaudeCodingStudio } from './components/ClaudeCodingStudio';
import { VoiceCortex } from './components/VoiceCortex';
import { RunwayVideoStudioView } from './components/RunwayVideoStudioView';
import { AgentOrchestrationModal } from './components/AgentOrchestrationModal';
import { IntegrationsModal } from './components/IntegrationsModal';
import { InformationFlowTicker } from './components/InformationFlowTicker';
import { CyberneticOrb } from './components/CyberneticOrb';
import { HudTelemetryFlanks } from './components/HudTelemetryFlanks';
import { MultimodalBridgeModal } from './components/MultimodalBridgeModal';
import { CanvasBuilderModal } from './components/CanvasBuilderModal';
import { CodeCompilerModal } from './components/CodeCompilerModal';
import { ConversationalStream } from './components/ConversationalStream';
  import { JarvisModal, type JarvisAction } from './components/JarvisModal';
  import { JarvisHUD } from './components/JarvisHUD';
import { AnalyticsDashboardView } from './components/AnalyticsDashboardView';
import { SwarmDashboardView } from './components/SwarmDashboardView';
import { MobileCompactCockpit } from './components/MobileCompactCockpit';
import { playHudClick, playChime, playSuccessChime } from './utils/soundEffects';
import {
  FALLBACK_CATALOG,
  codingFocusMode,
  fetchModelCatalog,
  getStoredCapabilities,
  getStoredModelId,
  resolveSelectedModelId,
  saveCapabilities,
  saveStoredModelId,
} from './data/modelCatalog';
import {
  appendChatMessages,
  clearChatSessions,
  conversationalToStored,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  newSessionId,
  renameChatSession,
  storedToConversational,
  summaryFromRecord,
  type HistorySource,
} from './utils/chatHistory';
import {
  getVoicePreferences,
  saveVoicePreferences,
  speakWithStatus,
  stopAnySpeaking,
  type VoicePreferences,
} from './utils/voiceManager';
import { nexusChatStream, nexusJson } from './api';

type CommandActionType = 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH';

interface QueuedCommand {
  id: string;
  query: string;
  actionType: CommandActionType;
  /** The user bubble is added at enqueue time so queued sends are visible. */
  userMessage: ConversationalMessage;
  /** Settings are snapshotted at enqueue time so later UI changes don't mutate queued work. */
  model: string;
  capabilities: ChatCapabilities;
  sessionId: string;
}

function createWelcomeMessage(): ConversationalMessage {
  return {
    id: `init-${Date.now()}`,
    role: 'assistant',
    content: 'NEXUS Autonomous Cognitive OS v2.4 online. All 3 concentric HUD rings synchronized. Standing by for instructions or vocal input [M].',
    timestamp: new Date().toLocaleTimeString(),
    toolsUsed: ['system_boot', 'ast_sandbox_guard'],
    difficulty: 'low',
    actionTriggers: [
      { label: '✦ Transcode Media', action: 'OPEN_MULTIMODAL' },
      { label: '⚡ Code Sandbox', action: 'OPEN_CODE' },
      { label: '◈ Canvas Builder', action: 'OPEN_CANVAS' },
    ],
  };
}

function sanitizeThinking(text: string): string {
  if (!text) return '';
  let cleaned = text.replace(/\r\n/g, '\n');
  const finalAnswerMatch = cleaned.match(/final\s+answer\s*:/i);
  if (finalAnswerMatch?.index !== undefined) {
    cleaned = cleaned.slice(0, finalAnswerMatch.index);
  }
  return cleaned
    .split('\n')
    .filter((line) => !/TOOL_CALL\s*:/i.test(line))
    .join('\n')
    .replace(/^\s*(thought|thinking|reasoning)\s*:\s*/i, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export const App: React.FC = () => {
  // Operating Modes: 'WORKSPACE' | 'GRAPH' | 'RESEARCH' | 'WORKFLOW' | 'ARCHITECTURE' | 'VIDEO'
  // WORKSPACE is the light-canvas Primary Workspace Dashboard — the app's front door.
  const [currentMode, setCurrentMode] = useState<OperatingMode>('WORKSPACE');
  const [dashboardSubView, setDashboardSubView] = useState<'swarm' | 'system'>('swarm');

  // Explicit Agent Status State: 'idle' | 'listening' | 'thinking' | 'speaking'
  const [agentStatus, setAgentStatus] = useState<AgentStatus>('idle');

  // Living Knowledge Graph Data
  const [nodes, setNodes] = useState<NexusNode[]>(INITIAL_NEXUS_NODES);
  const [links, setLinks] = useState<NexusLink[]>(INITIAL_NEXUS_LINKS);
  const [selectedNode, setSelectedNode] = useState<NexusNode | null>(null);

  // Filters & Search
  const [activeFilter, setActiveFilter] = useState<NodeCategory | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Modals & Overlays
  const [isClaudeStudioOpen, setIsClaudeStudioOpen] = useState(false);
  const [isVoiceCortexOpen, setIsVoiceCortexOpen] = useState(false);
  const [isAgentsModalOpen, setIsAgentsModalOpen] = useState(false);
  const [isIntegrationsModalOpen, setIsIntegrationsModalOpen] = useState(false);
  const [isMultimodalBridgeOpen, setIsMultimodalBridgeOpen] = useState(false);
  const [isCanvasBuilderOpen, setIsCanvasBuilderOpen] = useState(false);
  const [isCodeCompilerOpen, setIsCodeCompilerOpen] = useState(false);
  const [isConversationalStreamOpen, setIsConversationalStreamOpen] = useState(true);
  const [taskDifficulty, setTaskDifficulty] = useState<TaskDifficulty>('low');
  const [puffTrigger, setPuffTrigger] = useState<number>(0);
  const [isAccelerated, setIsAccelerated] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isJarvisOpen, setIsJarvisOpen] = useState(false);
  const [jarvisListening, setJarvisListening] = useState(false);
  const [nimStatus, setNimStatus] = useState<any>(null);

  // Model changer, Claude-style capabilities, voice output and chat history.
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog>(FALLBACK_CATALOG);
  const [selectedModelId, setSelectedModelId] = useState<string>(() => getStoredModelId());
  const [capabilities, setCapabilities] = useState<ChatCapabilities>(() => getStoredCapabilities());
  const [voicePreferences, setVoicePreferences] = useState<VoicePreferences>(() => getVoicePreferences());
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [historySource, setHistorySource] = useState<HistorySource>('local');
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => newSessionId());
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const voiceEnabled = capabilities.voiceReplies;

  // Module 2: The Conversational Stream framing AI feedback
  const [conversationalMessages, setConversationalMessages] = useState<ConversationalMessage[]>([
    createWelcomeMessage(),
  ]);

  // Unified Command Queue to prevent state race conditions
  const [queuedCommandCount, setQueuedCommandCount] = useState(0);
  const commandQueueRef = useRef<QueuedCommand[]>([]);
  const isProcessingCommandRef = useRef(false);
  const activeGenerationControllerRef = useRef<AbortController | null>(null);
  const selectedModelIdRef = useRef(selectedModelId);
  const capabilitiesRef = useRef(capabilities);
  const voicePreferencesRef = useRef(voicePreferences);
  const currentSessionIdRef = useRef(currentSessionId);
  const agentStatusRef = useRef(agentStatus);
  const currentModeRef = useRef(currentMode);
  const speechGatesQueueRef = useRef(false);
  const stopSpeakingRef = useRef<() => void>(() => {});

  useEffect(() => {
    selectedModelIdRef.current = selectedModelId;
  }, [selectedModelId]);

  useEffect(() => {
    capabilitiesRef.current = capabilities;
  }, [capabilities]);

  useEffect(() => {
    voicePreferencesRef.current = voicePreferences;
  }, [voicePreferences]);

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    agentStatusRef.current = agentStatus;
    if (agentStatus !== 'speaking') setSpeakingMessageId(null);
  }, [agentStatus]);

  useEffect(() => {
    currentModeRef.current = currentMode;
  }, [currentMode]);

  useEffect(() => () => {
    activeGenerationControllerRef.current?.abort();
  }, []);

  // Deep research initial query state
  const [researchTopic, setResearchTopic] = useState('Recursive Self-Evolution & AST Guard Sandboxes in Autonomous LLMs');

  const refreshNimStatus = useCallback(async () => {
    try {
      const response = await nexusJson<any>('/api/nim/status');
      setNimStatus(response);
    } catch {
      setNimStatus(null);
    }
  }, []);

  useEffect(() => {
    refreshNimStatus();
  }, [refreshNimStatus]);

  const handleModelChange = useCallback((modelId: string) => {
    const saved = saveStoredModelId(modelId);
    selectedModelIdRef.current = saved;
    setSelectedModelId(saved);
  }, []);

  const handleCapabilitiesChange = useCallback((next: ChatCapabilities) => {
    const saved = saveCapabilities(next);
    capabilitiesRef.current = saved;
    setCapabilities(saved);
    if (!saved.voiceReplies && agentStatusRef.current === 'speaking') {
      stopSpeakingRef.current();
    }
  }, []);

  const handleVoicePreferencesChange = useCallback((preferences: VoicePreferences) => {
    const saved = saveVoicePreferences(preferences);
    voicePreferencesRef.current = saved;
    setVoicePreferences(saved);
  }, []);

  const refreshChatHistory = useCallback(async (): Promise<void> => {
    setIsHistoryLoading(true);
    try {
      const result = await listChatSessions('', 100);
      setChatSessions(result.sessions);
      setHistorySource(result.source);
    } finally {
      setIsHistoryLoading(false);
    }
  }, []);

  const upsertChatSessionSummary = useCallback((record: ChatSessionRecord) => {
    const summary = summaryFromRecord(record);
    setChatSessions((prev) =>
      [summary, ...prev.filter((session) => session.id !== summary.id)].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      ),
    );
  }, []);

  const startFreshSession = useCallback((): string => {
    const sessionId = newSessionId();
    currentSessionIdRef.current = sessionId;
    setCurrentSessionId(sessionId);
    setConversationalMessages([createWelcomeMessage()]);
    setSpeakingMessageId(null);
    return sessionId;
  }, []);

  const prepareForSessionSwitch = useCallback((): boolean => {
    if (commandQueueRef.current.length > 0) return false;
    if (agentStatusRef.current === 'thinking' || agentStatusRef.current === 'listening') return false;
    if (isProcessingCommandRef.current && !speechGatesQueueRef.current) return false;
    if (agentStatusRef.current === 'speaking') stopSpeakingRef.current();
    return !isProcessingCommandRef.current;
  }, []);

  const handleNewChat = useCallback(async (): Promise<boolean> => {
    if (!prepareForSessionSwitch()) return false;
    startFreshSession();
    setIsConversationalStreamOpen(true);
    return true;
  }, [prepareForSessionSwitch, startFreshSession]);

  const handleOpenSession = useCallback(async (sessionId: string): Promise<boolean> => {
    if (sessionId === currentSessionIdRef.current && chatSessions.some((s) => s.id === sessionId)) {
      setIsConversationalStreamOpen(true);
      return true;
    }
    if (!prepareForSessionSwitch()) return false;

    setIsHistoryLoading(true);
    try {
      const result = await getChatSession(sessionId);
      if (!result.session) return false;
      setHistorySource(result.source);
      currentSessionIdRef.current = result.session.id;
      setCurrentSessionId(result.session.id);
      setConversationalMessages(result.session.messages.map(storedToConversational));
      setSpeakingMessageId(null);
      setIsConversationalStreamOpen(true);
      return true;
    } finally {
      setIsHistoryLoading(false);
    }
  }, [chatSessions, prepareForSessionSwitch]);

  const handleRenameSession = useCallback(async (sessionId: string, title: string): Promise<boolean> => {
    const result = await renameChatSession(sessionId, title);
    if (!result.session) return false;
    setHistorySource(result.source);
    upsertChatSessionSummary(result.session);
    return true;
  }, [upsertChatSessionSummary]);

  const handleDeleteSession = useCallback(async (sessionId: string): Promise<boolean> => {
    const deletingCurrent = sessionId === currentSessionIdRef.current;
    if (deletingCurrent && !prepareForSessionSwitch()) return false;

    const result = await deleteChatSession(sessionId);
    if (!result.deleted) return false;
    setHistorySource(result.source);
    setChatSessions((prev) => prev.filter((session) => session.id !== sessionId));
    if (deletingCurrent) startFreshSession();
    return true;
  }, [prepareForSessionSwitch, startFreshSession]);

  const handleClearHistory = useCallback(async (): Promise<boolean> => {
    if (!prepareForSessionSwitch()) return false;
    const result = await clearChatSessions();
    setHistorySource(result.source);
    setChatSessions([]);
    startFreshSession();
    return true;
  }, [prepareForSessionSwitch, startFreshSession]);

  useEffect(() => {
    let cancelled = false;
    void fetchModelCatalog().then((catalog) => {
      if (cancelled) return;
      setModelCatalog(catalog);
      const resolved = resolveSelectedModelId(catalog, selectedModelIdRef.current);
      selectedModelIdRef.current = resolved;
      setSelectedModelId(resolved);
      saveStoredModelId(resolved);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    void refreshChatHistory();
  }, [refreshChatHistory]);

  // Keyboard Shortcuts (C for Claude Studio, A for Agents, I for Integrations, 1-4 for Modes, Esc to close)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      // The Claude-style chat is a focused writing/tool surface; global OS
      // hotkeys should not fire modal overlays over it.
      if (currentModeRef.current === 'CLAUDE_CHAT') return;

      if (e.key === 'c' || e.key === 'C') {
        setIsClaudeStudioOpen((prev) => !prev);
        playHudClick();
      } else if (e.key === 'm' || e.key === 'M') {
        setIsVoiceCortexOpen((prev) => !prev);
        playHudClick();
      } else if (e.key === 'a' || e.key === 'A') {
        setIsAgentsModalOpen((prev) => !prev);
        playHudClick();
      } else if (e.key === 'i' || e.key === 'I') {
        setIsIntegrationsModalOpen((prev) => !prev);
        playHudClick();
      } else if (e.key === 'b' || e.key === 'B' || e.key === 'v' || e.key === 'V') {
        setIsMultimodalBridgeOpen((prev) => !prev);
        playHudClick();
      } else if (e.key === 'w' || e.key === 'W') {
        setCurrentMode((prev) => (prev === 'WORKSPACE' ? 'GRAPH' : 'WORKSPACE'));
        playHudClick();
      } else if (e.key === '0' || e.key === 'h' || e.key === 'H') {
        setCurrentMode((prev) => (prev === 'HUD' ? 'GRAPH' : 'HUD'));
        playHudClick();
      } else if (e.key === '1') {
        setCurrentMode('GRAPH');
        playHudClick();
      } else if (e.key === '2') {
        setCurrentMode('RESEARCH');
        playHudClick();
      } else if (e.key === '3') {
        setCurrentMode('WORKFLOW');
        playHudClick();
      } else if (e.key === '4') {
        setCurrentMode('ARCHITECTURE');
        playHudClick();
      } else if (e.key === '5') {
        setCurrentMode('VIDEO');
        playHudClick();
      } else if (e.key === 'Escape') {
        if (isClaudeStudioOpen) setIsClaudeStudioOpen(false);
        else if (isAgentsModalOpen) setIsAgentsModalOpen(false);
        else if (isIntegrationsModalOpen) setIsIntegrationsModalOpen(false);
        else if (isMultimodalBridgeOpen) setIsMultimodalBridgeOpen(false);
        else if (isCanvasBuilderOpen) setIsCanvasBuilderOpen(false);
        else if (isCodeCompilerOpen) setIsCodeCompilerOpen(false);
        else if (selectedNode) setSelectedNode(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isClaudeStudioOpen, isAgentsModalOpen, isIntegrationsModalOpen, isMultimodalBridgeOpen, isCanvasBuilderOpen, isCodeCompilerOpen, selectedNode]);

  // Fullscreen Handler
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
        setIsFullscreen(false);
      }
    }
  }, []);

  // Neighborhood Expansion: Double-click spawns linked knowledge nodes with ripple
  const handleNodeNeighborhoodExpand = useCallback((targetNode: NexusNode) => {
    playSuccessChime();
    const newId1 = `sub-${targetNode.id}-1`;
    const newId2 = `sub-${targetNode.id}-2`;

    const newNode1: NexusNode = {
      id: newId1,
      name: `Synthesized Insight: ${targetNode.name}`,
      category: 'CONCEPT',
      val: 14,
      importance: 82,
      confidence: 96,
      hub: targetNode.hub,
      description: `Discovered connection derived from ${targetNode.name} during subcortex synthesis walk.`,
      source: 'Neo4j Graph Walk',
      lastUpdated: 'Just now',
      tags: ['Derived', 'Synapse', 'Dynamic'],
      pulsing: true,
      x: (targetNode.x || 500) + (Math.random() - 0.5) * 120,
      y: (targetNode.y || 400) + (Math.random() - 0.5) * 120,
    };

    const newNode2: NexusNode = {
      id: newId2,
      name: `Actionable Task: Verify ${targetNode.name}`,
      category: 'TASK',
      val: 12,
      importance: 79,
      confidence: 94,
      hub: targetNode.hub,
      description: `Autonomous task dispatched by NEXUS Planner to evaluate ${targetNode.name}.`,
      source: 'NEXUS Planner',
      lastUpdated: 'Just now',
      tags: ['Autonomous Task', 'Scheduled'],
      x: (targetNode.x || 500) + (Math.random() - 0.5) * 120,
      y: (targetNode.y || 400) + (Math.random() - 0.5) * 120,
    };

    setNodes((prev) => {
      if (prev.some((n) => n.id === newId1)) return prev;
      return [...prev, newNode1, newNode2];
    });

    setLinks((prev) => [
      ...prev,
      { source: targetNode.id, target: newId1, relation: 'SYNTHESIZES', active: true },
      { source: targetNode.id, target: newId2, relation: 'SPAWNS_TASK', active: true },
    ]);
  }, []);

  // Direct execution of single knowledge graph action
  const executeCommandDirect = useCallback(
    (
      query: string,
      actionType: 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH',
      onComplete: () => void
    ) => {
      const newId = `cmd-${Date.now()}`;
      const categoryMap: Record<typeof actionType, NodeCategory> = {
        RESEARCH: 'RESEARCH',
        WORKFLOW: 'WORKFLOW',
        CODE: 'CODE',
        MEMORY: 'MEMORY',
        GRAPH: 'CONCEPT',
      };

      const category = categoryMap[actionType];
      const newNode: NexusNode = {
        id: newId,
        name: query,
        category,
        val: 26,
        importance: 92,
        confidence: 98,
        hub: 'Dynamic Ingestion',
        description: `Injected into Knowledge Universe via Command Center: "${query}".`,
        source: 'User Command Palette',
        lastUpdated: 'Just now',
        tags: [actionType, 'Active Command', 'Real-Time'],
        pulsing: true,
        status: 'executing',
        x: 500 + (Math.random() - 0.5) * 140,
        y: 400 + (Math.random() - 0.5) * 140,
      };

      // Connect to the appropriate central hub
      let targetHub = 'res-core';
      if (actionType === 'CODE') targetHub = 'code-core';
      else if (actionType === 'WORKFLOW') targetHub = 'wf-core';
      else if (actionType === 'MEMORY') targetHub = 'mem-core';

      setNodes((prev) => [newNode, ...prev]);
      setLinks((prev) => [
        { source: targetHub, target: newId, relation: 'DISPATCHED_TO', active: true },
        ...prev,
      ]);
      setSelectedNode(newNode);

      if (actionType === 'RESEARCH') {
        setResearchTopic(query);
      }

      onComplete();
    },
    []
  );

  // FIX 3: Unified Queue Processor preventing state race conditions & Wiring AI Core
  const processNextCommand = useCallback(() => {
    if (commandQueueRef.current.length === 0) {
      isProcessingCommandRef.current = false;
      activeGenerationControllerRef.current = null;
      setQueuedCommandCount(0);
      setAgentStatus('idle');
      setIsAccelerated(false);
      return;
    }

    const next = commandQueueRef.current.shift()!;
    setQueuedCommandCount(commandQueueRef.current.length);
    const generationController = new AbortController();
    activeGenerationControllerRef.current = generationController;
    isProcessingCommandRef.current = true;
    setAgentStatus('thinking');

    // Module 3: Dynamically shift respiration color & accelerate ring rotation
    const lq = next.query.toLowerCase();
    let diff: TaskDifficulty = 'low';
    if (lq.includes('security') || lq.includes('threat') || lq.includes('critical') || lq.includes('hardening')) {
      diff = 'critical';
    } else if (
      next.capabilities.codingFocus !== 'auto' ||
      lq.includes('code') ||
      lq.includes('frontend') ||
      lq.includes('compiler') ||
      lq.includes('sandbox') ||
      lq.includes('ast') ||
      lq.includes('python') ||
      lq.includes('rust') ||
      lq.includes('c++') ||
      lq.includes('html5') ||
      lq.includes('xml') ||
      lq.includes('ruby') ||
      lq.includes('php')
    ) {
      diff = 'high';
    } else if (lq.includes('multimodal') || lq.includes('image') || lq.includes('video') || lq.includes('transcode')) {
      diff = 'medium';
    }
    setTaskDifficulty(diff);
    setIsAccelerated(true);

    // The user turn was appended when the command was queued, so a message
    // sent during another response is visible immediately.
    const userMsg = next.userMessage;

    executeCommandDirect(next.query, next.actionType, async () => {
      // Module 3: Exact millisecond action ripple "puff" effect
      setPuffTrigger((prev) => prev + 1);
      setIsAccelerated(false);

      // Prepare contextual actions; tool labels below come from the backend stream.
      const triggers: Array<{ label: string; action: string; payload?: any }> = [];

      if (diff === 'medium' || lq.includes('image') || lq.includes('video') || lq.includes('multimodal')) {
        triggers.push({ label: '✦ Open Multimodal Bridge', action: 'OPEN_MULTIMODAL' });
        if (currentModeRef.current !== 'CLAUDE_CHAT' && (lq.includes('open') || lq.includes('transcode') || lq.includes('show'))) {
          setIsMultimodalBridgeOpen(true);
        }
      } else if (diff === 'high' || lq.includes('code') || lq.includes('python')) {
        triggers.push({ label: '⚡ Open Code Compiler', action: 'OPEN_CODE' });
        if (currentModeRef.current !== 'CLAUDE_CHAT' && (lq.includes('open') || lq.includes('run') || lq.includes('code'))) {
          setIsCodeCompilerOpen(true);
        }
      } else if (lq.includes('canvas') || lq.includes('diagram') || lq.includes('node')) {
        triggers.push({ label: '◈ Open Canvas Builder', action: 'OPEN_CANVAS' });
        if (currentModeRef.current !== 'CLAUDE_CHAT' && (lq.includes('open') || lq.includes('show'))) {
          setIsCanvasBuilderOpen(true);
        }
      } else if (lq.includes('video') || lq.includes('studio') || lq.includes('render')) {
        triggers.push({ label: '🎬 Open Video Studio', action: 'OPEN_VIDEO' });
      }

      const assistantId = `ai-${Date.now()}`;
      setConversationalMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: 'assistant',
          content: 'Connecting to NEXUS cognitive stream...',
          timestamp: new Date().toLocaleTimeString(),
          toolsUsed: [],
          difficulty: diff,
          actionTriggers: triggers,
          model: next.model,
          modelSource: next.model === 'auto' ? 'nexus-default' : 'nvidia-nim',
          thinking: '',
          status: 'streaming',
        },
      ]);

      let finalAnswer = '';
      let finalModel = next.model;
      let finalModelSource = next.model === 'auto' ? 'nexus-default' : 'nvidia-nim';
      let thinkingTrace = '';
      let streamSucceeded = false;
      let generationStopped = false;
      let finalExecution: ChatExecutionMetadata | undefined;
      let finalQuality: ChatQualityMetadata | undefined;
      const toolsUsed = new Set<string>();

      try {
        let answerReceived = false;
        await nexusChatStream(
          next.query,
          next.actionType === 'CODE' ? 'coding' : 'general',
          (event) => {
            if (event.model) finalModel = event.model;
            if (event.model_source) finalModelSource = event.model_source;
            if (event.execution) finalExecution = event.execution;
            if (event.quality) finalQuality = event.quality;
            if (event.type === 'tool_call' && event.tool_id) toolsUsed.add(event.tool_id);

            if (event.type === 'metadata') {
              setConversationalMessages((prev) =>
                prev.map((item) => item.id === assistantId
                  ? { ...item, execution: finalExecution, quality: finalQuality }
                  : item),
              );
            }

            if (event.type === 'thought' && next.capabilities.extendedThinking && event.content) {
              const piece = sanitizeThinking(event.content);
              if (piece) {
                if (!thinkingTrace || piece.startsWith(thinkingTrace)) {
                  thinkingTrace = piece;
                } else if (!thinkingTrace.includes(piece)) {
                  thinkingTrace = `${thinkingTrace}\n\n${piece}`;
                }
              }
            }

            if (
              event.type === 'start' ||
              event.type === 'thought' ||
              event.type === 'tool_call' ||
              event.type === 'quality_repair'
            ) {
              setConversationalMessages((prev) =>
                prev.map((item) => item.id === assistantId
                  ? {
                      ...item,
                      content:
                        event.type === 'thought'
                          ? 'NEXUS is reasoning...'
                          : event.type === 'quality_repair'
                            ? 'NEXUS is verifying and improving the answer...'
                            : 'NEXUS is processing...',
                      toolsUsed: [...toolsUsed],
                      model: finalModel,
                      modelSource: finalModelSource,
                      thinking: thinkingTrace,
                    }
                  : item),
              );
            }

            if (event.type === 'answer') {
              answerReceived = true;
              finalAnswer = event.content || '';
              setConversationalMessages((prev) =>
                prev.map((item) => item.id === assistantId
                  ? {
                      ...item,
                      content: finalAnswer,
                      toolsUsed: [...toolsUsed],
                      model: finalModel,
                      modelSource: finalModelSource,
                      thinking: thinkingTrace,
                    }
                  : item),
              );
            }
          },
          {
            model: next.model,
            effort: next.capabilities.effort,
            sessionId: next.capabilities.memory ? next.sessionId : undefined,
            extendedThinking: next.capabilities.extendedThinking,
            deepResearch: next.capabilities.deepResearch,
            artifacts: next.capabilities.artifacts,
            signal: generationController.signal,
          },
        );
        if (!answerReceived) throw new Error('NEXUS stream ended without an answer.');
        streamSucceeded = true;
      } catch (error) {
        const aborted =
          generationController.signal.aborted ||
          (error instanceof DOMException && error.name === 'AbortError') ||
          (error instanceof Error && error.name === 'AbortError');
        generationStopped = aborted;
        if (aborted) {
          finalAnswer = finalAnswer.trim()
            ? `${finalAnswer.trim()}\n\n_Generation stopped._`
            : 'Generation stopped before an answer arrived.';
          setConversationalMessages((prev) =>
            prev.map((item) => item.id === assistantId
              ? { ...item, content: finalAnswer, status: 'stopped', thinking: thinkingTrace }
              : item),
          );
        } else {
          const message = error instanceof Error ? error.message : 'Unknown stream error.';
          finalAnswer = '';
          setConversationalMessages((prev) =>
            prev.map((item) => item.id === assistantId
              ? { ...item, content: `NEXUS stream failed: ${message}`, status: 'error' }
              : item),
          );
        }
      } finally {
        if (activeGenerationControllerRef.current === generationController) {
          activeGenerationControllerRef.current = null;
        }
      }

      if (streamSucceeded) {
        setConversationalMessages((prev) =>
          prev.map((item) => item.id === assistantId
            ? { ...item, status: 'complete', execution: finalExecution, quality: finalQuality }
            : item),
        );
      }

      if (streamSucceeded || generationStopped) {
        const finalAssistantMessage: ConversationalMessage = {
          id: assistantId,
          role: 'assistant',
          content: finalAnswer,
          timestamp: new Date().toLocaleTimeString(),
          toolsUsed: [...toolsUsed],
          difficulty: diff,
          actionTriggers: triggers,
          model: finalModel,
          modelSource: finalModelSource,
          thinking: thinkingTrace,
          execution: finalExecution,
          quality: finalQuality,
          status: generationStopped ? 'stopped' : 'complete',
        };
        try {
          const historyResult = await appendChatMessages(
            next.sessionId,
            [conversationalToStored(userMsg), conversationalToStored(finalAssistantMessage)],
            { model: finalModel },
          );
          setHistorySource(historyResult.source);
          if (historyResult.session) upsertChatSessionSummary(historyResult.session);
        } catch {
          // chatHistory already falls back to localStorage; a storage failure
          // must never suppress the completed answer or its voice reply.
        }
      }

      if (streamSucceeded && next.capabilities.voiceReplies && finalAnswer.trim()) {
        // Speak the actual answer (voiceManager strips code/markdown and
        // chunks it) with the saved accent — en-IN by default.
        speechGatesQueueRef.current = true;
        setSpeakingMessageId(assistantId);
        let speechSettled = false;
        const finishSpeech = () => {
          if (speechSettled) return;
          speechSettled = true;
          speechGatesQueueRef.current = false;
          setSpeakingMessageId(null);
          processNextCommand();
        };
        const started = speakWithStatus(
          finalAnswer,
          setAgentStatus,
          finishSpeech,
          voicePreferencesRef.current,
        );
        if (!started) finishSpeech();
      } else {
        setTimeout(() => {
          processNextCommand();
        }, 500);
      }
    });
  }, [executeCommandDirect, upsertChatSessionSummary]);

  // Inject command or research result into the live knowledge graph with queueing
  const handleExecuteCommand = useCallback(
    (query: string, actionType: CommandActionType) => {
      const cleanQuery = query.trim();
      if (!cleanQuery) return;
      playChime();
      const snapshotCapabilities = { ...capabilitiesRef.current };
      const effectiveActionType =
        snapshotCapabilities.deepResearch && actionType === 'GRAPH' ? 'RESEARCH' : actionType;
      const commandId = `cmd-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      const userMessage: ConversationalMessage = {
        id: `usr-${commandId}`,
        role: 'user',
        content: cleanQuery,
        timestamp: new Date().toLocaleTimeString(),
      };
      setConversationalMessages((prev) => [...prev, userMessage]);
      commandQueueRef.current.push({
        id: commandId,
        query: cleanQuery,
        actionType: effectiveActionType,
        userMessage,
        model: selectedModelIdRef.current,
        capabilities: snapshotCapabilities,
        sessionId: currentSessionIdRef.current,
      });
      setQueuedCommandCount(commandQueueRef.current.length);

      if (!isProcessingCommandRef.current) {
        processNextCommand();
      }
    },
    [processNextCommand]
  );

  const handleStopGeneration = useCallback(() => {
    activeGenerationControllerRef.current?.abort();
  }, []);

  const handleStopSpeaking = useCallback(() => {
    const shouldResumeQueue = speechGatesQueueRef.current;
    speechGatesQueueRef.current = false;
    stopAnySpeaking();
    setSpeakingMessageId(null);
    setAgentStatus('idle');
    // stopAnySpeaking suppresses the utterance onFinish callback, so resume
    // a speech-gated command queue explicitly instead of stranding it.
    if (shouldResumeQueue) processNextCommand();
  }, [processNextCommand]);

  useEffect(() => {
    stopSpeakingRef.current = handleStopSpeaking;
  }, [handleStopSpeaking]);

  const handleSpeakMessage = useCallback((message: ConversationalMessage) => {
    if (!message.content.trim()) return;
    const shouldResumeQueue = speechGatesQueueRef.current;
    setSpeakingMessageId(message.id);
    let speechSettled = false;
    const finishSpeech = () => {
      if (speechSettled) return;
      speechSettled = true;
      setSpeakingMessageId(null);
      if (shouldResumeQueue) {
        speechGatesQueueRef.current = false;
        processNextCommand();
      }
    };
    const started = speakWithStatus(
      message.content,
      setAgentStatus,
      finishSpeech,
      voicePreferencesRef.current,
    );
    if (!started) finishSpeech();
  }, [processNextCommand]);

  // Sync Deep Research output into knowledge graph as a new document node
  const handleInjectResearchIntoGraph = useCallback((reportTitle: string, claims: ResearchClaim[]) => {
    playSuccessChime();
    const docId = `doc-research-${Date.now()}`;
    const newDocNode: NexusNode = {
      id: docId,
      name: `Research Artifact: ${reportTitle}`,
      category: 'DOCUMENT',
      val: 28,
      importance: 96,
      confidence: 97,
      hub: 'Research Lab',
      description: `Executive research paper covering ${claims.length} cross-checked empirical claims and verified citations.`,
      source: 'Deep Research Synthesis Engine',
      lastUpdated: 'Just now',
      tags: ['Research Report', 'Synthesized', 'Artifact'],
      pulsing: true,
      x: 520,
      y: 420,
    };

    setNodes((prev) => [newDocNode, ...prev]);
    setLinks((prev) => [
      { source: 'res-core', target: docId, relation: 'PUBLISHES', active: true },
      { source: docId, target: 'mem-core', relation: 'CONSOLIDATES_INTO', active: true },
      ...prev,
    ]);
    setSelectedNode(newDocNode);
    setCurrentMode('GRAPH');
  }, []);

  // Sync Runway Gen-3 Alpha Video into knowledge graph as a new video node
  const handleInjectVideoIntoGraph = useCallback((title: string, prompt: string, metadata: any) => {
    playSuccessChime();
    const vidId = `vid-runway-${Date.now()}`;
    const newVidNode: NexusNode = {
      id: vidId,
      name: `Video: ${title}`,
      category: 'WEBSITE',
      val: 26,
      importance: 92,
      confidence: 97,
      hub: 'AI Workshop',
      description: `Runway Gen-3 Alpha video render: "${prompt}". Aspect Ratio: ${metadata.ratio || '16:9'}, Resolution: ${metadata.resolution || '1080p'}.`,
      source: 'Runway Gen-3 Studio',
      lastUpdated: 'Just now',
      tags: ['Video', 'Gen-3 Alpha', 'Runway', 'Neural Render'],
      pulsing: true,
      metadata,
      x: 480 + (Math.random() - 0.5) * 140,
      y: 400 + (Math.random() - 0.5) * 140,
    };

    setNodes((prev) => [newVidNode, ...prev]);
    setLinks((prev) => [
      { source: 'code-core', target: vidId, relation: 'RENDERS', active: true },
      { source: vidId, target: 'res-core', relation: 'SYNERGIZES_WITH', active: true },
      ...prev,
    ]);
    setSelectedNode(newVidNode);
    setCurrentMode('GRAPH');
  }, []);

  // Spoken commands from the Jarvis console map onto app-level actions.
  const handleJarvisCommand = (action: JarvisAction) => {
    playHudClick();
    switch (action) {
      case 'open-research':
        setCurrentMode('RESEARCH');
        break;
      case 'open-workflow':
        setCurrentMode('WORKFLOW');
        break;
      case 'open-video':
        setCurrentMode('VIDEO');
        break;
      case 'open-dashboard':
        setCurrentMode('DASHBOARD');
        break;
      case 'open-architecture':
        setCurrentMode('ARCHITECTURE');
        break;
      case 'open-studio':
        setIsClaudeStudioOpen(true);
        break;
      case 'open-agents':
        setIsAgentsModalOpen(true);
        break;
      case 'open-integrations':
        setIsIntegrationsModalOpen(true);
        break;
      case 'open-multimodal':
        setIsMultimodalBridgeOpen(true);
        break;
      default:
        // 'stop-speaking' / 'dismiss' are fully handled inside the console.
        break;
    }
  };

  const openClaudeChat = useCallback(() => {
    // Chat now ships as its own Vite entry (`/chat.html`) with a standalone
    // controller. Workplace OS links to it instead of embedding the full
    // Claude-style chat as an internal operating mode.
    playHudClick();
    window.location.assign('/chat.html');
  }, []);

  const handleOperatingModeChange = useCallback(
    (mode: OperatingMode) => {
      if (mode === 'CLAUDE_CHAT') {
        openClaudeChat();
        return;
      }
      setCurrentMode(mode);
      playHudClick();
    },
    [openClaudeChat],
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#030508] text-slate-100 font-sans antialiased select-none">
      {/* ── Minimal Floating Top Bar (hidden on the light Workspace and Claude-style chat surfaces) ──── */}
      {currentMode !== 'WORKSPACE' && currentMode !== 'CLAUDE_CHAT' && (
      <TopBar
        currentMode={currentMode}
        onModeChange={handleOperatingModeChange}
        onOpenClaudeStudio={() => {
          setIsClaudeStudioOpen(true);
          playHudClick();
        }}
        onToggleFullscreen={toggleFullscreen}
        isFullscreen={isFullscreen}
        onOpenCommandCenter={() => {
          const input = document.querySelector('input[placeholder*="Ask NEXUS"]') as HTMLInputElement;
          input?.focus();
        }}
        onOpenVoiceCortex={() => setIsVoiceCortexOpen(true)}
        onOpenAgentsModal={() => setIsAgentsModalOpen(true)}
        onOpenIntegrationsModal={() => setIsIntegrationsModalOpen(true)}
        onOpenNim={() => setIsJarvisOpen(true)}
        agentStatus={agentStatus}
        modelCatalog={modelCatalog}
        selectedModelId={selectedModelId}
        onModelChange={handleModelChange}
        capabilities={capabilities}
        onCapabilitiesChange={handleCapabilitiesChange}
        voicePreferences={voicePreferences}
        onVoicePreferencesChange={handleVoicePreferencesChange}
        onAgentStatusChange={setAgentStatus}
        sessionCount={chatSessions.length}
        onOpenChat={openClaudeChat}
      />
      )}

      <JarvisModal
        isOpen={isJarvisOpen}
        onClose={() => setIsJarvisOpen(false)}
        nimStatus={nimStatus}
        onRefreshNimStatus={refreshNimStatus}
        agentStatus={agentStatus}
        onStatusChange={setAgentStatus}
        onCommand={handleJarvisCommand}
        onListeningChange={setJarvisListening}
      />

      {/* Floating JARVIS orb - always visible, mirrors listening/speaking state */}
      {currentMode !== 'WORKSPACE' && currentMode !== 'CLAUDE_CHAT' && (
      <div className="fixed bottom-5 right-5 z-40 hidden md:block">
        <JarvisHUD
          ringActive
          listening={jarvisListening}
          speaking={agentStatus === 'speaking'}
          hasNimKey={Boolean(nimStatus?.has_api_key)}
          onClick={() => {
            playHudClick();
            setIsJarvisOpen(true);
          }}
        />
      </div>
      )}

      {/* ── Left Sidebar: Workspaces, Search & System Telemetry (hidden on Workspace/Chat) ── */}
      {currentMode !== 'WORKSPACE' && currentMode !== 'CLAUDE_CHAT' && (
      <LeftSidebar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
        onOpenResearchMode={() => setCurrentMode('RESEARCH')}
        onOpenWorkflowMode={() => setCurrentMode('WORKFLOW')}
        onOpenVideoMode={() => setCurrentMode('VIDEO')}
        onOpenAnalyticsMode={() => setCurrentMode('DASHBOARD')}
        onOpenAgentsModal={() => setIsAgentsModalOpen(true)}
        onOpenIntegrationsModal={() => setIsIntegrationsModalOpen(true)}
        onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
      />
      )}

      {/* ── Center Viewport: Mode Dependent ─────────────────────────────────── */}
      <main className="flex-1 h-full relative overflow-hidden bg-[#0a0f1d]">
        {/* ── SCREEN 1+2: Light-canvas NEXUS OS workspace — the full light
             suite (home, graph, research, workflow, architecture, analytics,
             agents) with the floating multi-modal Query Cockpit. The full
             Chat UI is intentionally not mounted here; it has its own
             `/chat.html` entry and standalone controller. */}
        {currentMode === 'WORKSPACE' && <WorkspaceView onOpenIntegrations={() => setIsIntegrationsModalOpen(true)} />}

        {/* Real-time Information Flow Ticker (Cortex vs Subcortex) in Graph Mode */}
        {currentMode === 'GRAPH' && (
          <div className="absolute top-16 right-6 z-20 max-w-lg">
            <InformationFlowTicker />
          </div>
        )}

        {currentMode === 'HUD' && (
          <div className="relative w-full h-full flex flex-col items-center justify-center p-4 bg-[#0a0f1d] overflow-hidden select-none">
            {/* Cyber scanline and background holographic grid */}
            <div className="absolute inset-0 scanline pointer-events-none opacity-30" />
            <div 
              className="absolute inset-0 pointer-events-none opacity-20"
              style={{
                backgroundImage: 'radial-gradient(circle at 50% 50%, rgba(0, 240, 255, 0.15) 0%, transparent 70%), linear-gradient(rgba(0, 240, 255, 0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 240, 255, 0.05) 1px, transparent 1px)',
                backgroundSize: '100% 100%, 40px 40px, 40px 40px',
              }}
            />

            {/* Flanking HUD Telemetry Data Streams */}
            <HudTelemetryFlanks
              onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
              onOpenAgentsModal={() => setIsAgentsModalOpen(true)}
              onOpenIntegrationsModal={() => setIsIntegrationsModalOpen(true)}
            />

            {/* Cybernetic Centerpiece (The Arc Reactor Orb) */}
            <CyberneticOrb
              agentStatus={agentStatus}
              taskDifficulty={taskDifficulty}
              isAccelerated={isAccelerated}
              puffTrigger={puffTrigger}
              onToggleVoice={() => {
                setIsVoiceCortexOpen((prev) => !prev);
                playHudClick();
              }}
              onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
              onOpenCodeCompiler={() => setIsCodeCompilerOpen(true)}
              onOpenCanvasBuilder={() => setIsCanvasBuilderOpen(true)}
              onOpenVideoStudio={() => setCurrentMode('VIDEO')}
              onOpenGraphMode={() => setCurrentMode('GRAPH')}
            />
          </div>
        )}

        {currentMode === 'DASHBOARD' && (
          dashboardSubView === 'swarm' ? (
            <SwarmDashboardView
              agentStatus={agentStatus}
              onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
              onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
              onToggleAnalyticsMode={() => setDashboardSubView('system')}
            />
          ) : (
            <div className="relative w-full h-full">
              <button
                onClick={() => setDashboardSubView('swarm')}
                className="absolute top-4 right-6 z-20 px-3 py-1.5 rounded-xl bg-cyan-950/90 border border-cyan-400/50 text-cyan-300 hover:text-white text-xs font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.3)] cursor-pointer"
              >
                ← BACK TO SWARM COCKPIT
              </button>
              <AnalyticsDashboardView
                agentStatus={agentStatus}
                onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
                onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
              />
            </div>
          )
        )}

        {currentMode === 'GRAPH' && (
          <NexusCanvas
            nodes={nodes}
            links={links}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            activeFilter={activeFilter}
            onFilterChange={setActiveFilter}
            searchQuery={searchQuery}
            onNodeNeighborhoodExpand={handleNodeNeighborhoodExpand}
            onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
            onOpenResearchMode={(topic) => {
              if (topic) setResearchTopic(topic);
              setCurrentMode('RESEARCH');
            }}
            onOpenWorkflowMode={() => setCurrentMode('WORKFLOW')}
          />
        )}

        {currentMode === 'RESEARCH' && (
          <DeepResearchView
            initialTopic={researchTopic}
            onInjectResearchIntoGraph={handleInjectResearchIntoGraph}
            onOpenClaudeStudio={(content) => {
              setIsClaudeStudioOpen(true);
            }}
          />
        )}

        {currentMode === 'WORKFLOW' && (
          <WorkflowCanvasView
            onInjectNewKnowledge={(title, data) => {
              handleExecuteCommand(title, 'MEMORY');
            }}
            onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
          />
        )}

        {currentMode === 'ARCHITECTURE' && (
          <ArchitectureView />
        )}

        {currentMode === 'VIDEO' && (
          <RunwayVideoStudioView
            onInjectVideoIntoGraph={handleInjectVideoIntoGraph}
            onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
          />
        )}
      </main>

      {/* ── Right Dynamic Contextual Inspector ──────────────────────────────── */}
      {currentMode === 'GRAPH' && (
        <ContextInspector
          selectedNode={selectedNode}
          onClose={() => setSelectedNode(null)}
          onOpenResearchMode={(t) => {
            if (t) setResearchTopic(t);
            setCurrentMode('RESEARCH');
          }}
          onOpenWorkflowMode={() => setCurrentMode('WORKFLOW')}
          onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
        />
      )}

      {/* Workspace keeps its light Query Cockpit; this launcher opens the
          full hybrid NEXUS chat (practical solutions, history, Claude-style
          model changer, tools/files, repository builder, and voice). */}
      {currentMode === 'WORKSPACE' && (
        <button
          type="button"
          onClick={openClaudeChat}
          title="Open Nexus Chat — real-life solutions, tools, files, repositories, models, voice and backend history"
          className="fixed bottom-24 right-6 z-50 flex items-center gap-2.5 rounded-full border border-white/70 bg-[#262624]/95 px-4 py-2.5 font-sans text-sm font-semibold text-[#f7f5ef] shadow-[0_16px_40px_rgba(61,57,47,0.30)] backdrop-blur transition-all hover:scale-[1.03] hover:bg-[#34322e] cursor-pointer"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[linear-gradient(135deg,#d97757,#8b7cf6_58%,#2f9e8f)] text-white">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <span>Nexus Chat</span>
          <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium text-[#e6e0d2]">solve · tools · repos</span>
        </button>
      )}

      {/* ── Conversational Stream: compact graph/HUD chat; CLAUDE_CHAT has its own full window ─ */}
      {currentMode !== 'WORKSPACE' && currentMode !== 'CLAUDE_CHAT' && (
      <ConversationalStream
        messages={conversationalMessages}
        isOpen={isConversationalStreamOpen}
        onToggleOpen={() => setIsConversationalStreamOpen((prev) => !prev)}
        onTriggerAction={(action) => {
          if (action === 'OPEN_MULTIMODAL') setIsMultimodalBridgeOpen(true);
          else if (action === 'OPEN_CODE') setIsCodeCompilerOpen(true);
          else if (action === 'OPEN_CANVAS') setIsCanvasBuilderOpen(true);
          else if (action === 'OPEN_VIDEO') setCurrentMode('VIDEO');
          playHudClick();
        }}
        isStreaming={agentStatus === 'thinking'}
        onSendMessage={(q) => handleExecuteCommand(q, 'GRAPH')}
        onStopGeneration={handleStopGeneration}
        queuedCount={queuedCommandCount}
        modelCatalog={modelCatalog}
        selectedModelId={selectedModelId}
        onModelChange={handleModelChange}
        capabilities={capabilities}
        onCapabilitiesChange={handleCapabilitiesChange}
        voicePreferences={voicePreferences}
        onVoicePreferencesChange={handleVoicePreferencesChange}
        agentStatus={agentStatus}
        onAgentStatusChange={setAgentStatus}
        speakingMessageId={speakingMessageId}
        onSpeakMessage={handleSpeakMessage}
        onStopSpeaking={handleStopSpeaking}
        sessions={chatSessions}
        historySource={historySource}
        currentSessionId={currentSessionId}
        isHistoryLoading={isHistoryLoading}
        onRefreshHistory={refreshChatHistory}
        onNewChat={handleNewChat}
        onOpenSession={handleOpenSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onClearHistory={handleClearHistory}
      />
      )}

      {/* ── Bottom Floating Command Center Bar (In Graph or HUD Mode) ───────── */}
      {(currentMode === 'GRAPH' || currentMode === 'HUD') && (
        <CommandCenter
          onExecuteCommand={handleExecuteCommand}
          onStopGeneration={handleStopGeneration}
          queuedCount={queuedCommandCount}
          onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
          onOpenResearchMode={(t) => {
            if (t) setResearchTopic(t);
            setCurrentMode('RESEARCH');
          }}
          onOpenVoiceCortex={() => setIsVoiceCortexOpen(true)}
          agentStatus={agentStatus}
        />
      )}

      {/* ── Dedicated Full-Screen Claude Coding Studio Modal ─────────────────── */}
      {isClaudeStudioOpen && (
        <div className="fixed inset-0 z-50 bg-[#030508]/98 backdrop-blur-2xl">
          <ClaudeCodingStudio
            onBackToSecondBrain={() => setIsClaudeStudioOpen(false)}
            onOpenResearch={(q) => {
              setResearchTopic(q);
              setIsClaudeStudioOpen(false);
              setCurrentMode('RESEARCH');
            }}
          />
        </div>
      )}

      {/* ── Autonomous Agent Orchestration Layer Modal (10 Agents) ─────────── */}
      <AgentOrchestrationModal
        isOpen={isAgentsModalOpen}
        onClose={() => setIsAgentsModalOpen(false)}
        onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
        onOpenResearchMode={(t) => {
          if (t) setResearchTopic(t);
          setCurrentMode('RESEARCH');
        }}
      />

      {/* ── External Integration Universe Modal (16 Integrations) ───────────── */}
      <IntegrationsModal
        isOpen={isIntegrationsModalOpen}
        onClose={() => setIsIntegrationsModalOpen(false)}
        onRefreshGraph={() => {}}
      />

      {/* ── Multimodal Perception Bridge Modal (Image/Video to Non-Vision LLMs) ─ */}
      <MultimodalBridgeModal
        isOpen={isMultimodalBridgeOpen}
        onClose={() => setIsMultimodalBridgeOpen(false)}
        onInjectIntoGraph={(title, summary, meta) => {
          handleExecuteCommand(title, 'MEMORY');
        }}
        onInjectPrompt={(prompt) => {
          const input = document.querySelector('input[placeholder*="Ask NEXUS"]') as HTMLInputElement;
          if (input) {
            input.value = prompt;
            input.focus();
          }
        }}
      />

      {/* ── Contextual Canvas Builder Modal ─────────────────────────────────── */}
      <CanvasBuilderModal
        isOpen={isCanvasBuilderOpen}
        onClose={() => setIsCanvasBuilderOpen(false)}
        onAddNodeToGraph={(title, cat, summary) => {
          handleExecuteCommand(title, 'GRAPH');
        }}
      />

      {/* ── Contextual Code Compiler Modal ──────────────────────────────────── */}
      <CodeCompilerModal
        isOpen={isCodeCompilerOpen}
        onClose={() => setIsCodeCompilerOpen(false)}
      />

      {/* ── Spoken Voice Cortex Assistant (Claude chat has native voice controls) ─ */}
      {currentMode !== 'CLAUDE_CHAT' && (
      <VoiceCortex
        voiceEnabled={voiceEnabled}
        onToggleVoice={() => handleCapabilitiesChange({ ...capabilities, voiceReplies: !capabilities.voiceReplies })}
        agentStatus={agentStatus}
        onStatusChange={setAgentStatus}
        onCommand={(cmd, text) => {
          handleExecuteCommand(text, 'GRAPH');
        }}
        onOpenPrompt={(prompt) => {
          handleExecuteCommand(prompt, 'RESEARCH');
        }}
      />
      )}

      {/* ── Mobile Application UI: High-Velocity Thumb Cockpit ──────────────── */}
      {currentMode !== 'WORKSPACE' && currentMode !== 'CLAUDE_CHAT' && (
      <MobileCompactCockpit
        agentStatus={agentStatus}
        currentMode={currentMode}
        onModeChange={handleOperatingModeChange}
        onToggleVoice={() => {
          setIsVoiceCortexOpen((prev) => !prev);
          playHudClick();
        }}
        onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
        onOpenCodeCompiler={() => setIsCodeCompilerOpen(true)}
        onOpenCanvasBuilder={() => setIsCanvasBuilderOpen(true)}
      />
      )}
    </div>
  );
};
