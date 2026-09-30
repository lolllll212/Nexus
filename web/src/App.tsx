import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  NexusNode, 
  NexusLink, 
  NodeCategory, 
  OperatingMode, 
  ResearchClaim,
  AgentStatus,
  ConversationalMessage,
  TaskDifficulty
} from './types';
import { 
  INITIAL_NEXUS_NODES, 
  INITIAL_NEXUS_LINKS 
} from './data/nexusGraphData';
import { NexusCanvas } from './components/NexusCanvas';
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
import { playHudClick, playChime, playSuccessChime } from './utils/soundEffects';
import { speakWithStatus, stopAnySpeaking } from './utils/voiceManager';

export const App: React.FC = () => {
  // Operating Modes: 'GRAPH' | 'RESEARCH' | 'WORKFLOW' | 'ARCHITECTURE' | 'VIDEO'
  const [currentMode, setCurrentMode] = useState<OperatingMode>('GRAPH');

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
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Module 2: The Conversational Stream framing AI feedback
  const [conversationalMessages, setConversationalMessages] = useState<ConversationalMessage[]>([
    {
      id: 'init-1',
      role: 'assistant',
      content: 'NEXUS Autonomous Cognitive OS v2.4 online. All 3 concentric HUD rings synchronized. Standing by for instructions or vocal input [M].',
      timestamp: '00:00:01',
      toolsUsed: ['system_boot', 'ast_sandbox_guard'],
      difficulty: 'low',
      actionTriggers: [
        { label: '✦ Transcode Media', action: 'OPEN_MULTIMODAL' },
        { label: '⚡ Code Sandbox', action: 'OPEN_CODE' },
        { label: '◈ Canvas Builder', action: 'OPEN_CANVAS' },
      ],
    },
  ]);

  // Unified Command Queue to prevent state race conditions
  const commandQueueRef = useRef<{
    id: string;
    query: string;
    actionType: 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH';
  }[]>([]);
  const isProcessingCommandRef = useRef(false);

  // Deep research initial query state
  const [researchTopic, setResearchTopic] = useState('Recursive Self-Evolution & AST Guard Sandboxes in Autonomous LLMs');

  // Keyboard Shortcuts (C for Claude Studio, A for Agents, I for Integrations, 1-4 for Modes, Esc to close)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

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
      setAgentStatus('idle');
      setIsAccelerated(false);
      return;
    }

    const next = commandQueueRef.current.shift()!;
    isProcessingCommandRef.current = true;
    setAgentStatus('thinking');

    // Module 3: Dynamically shift respiration color & accelerate ring rotation
    const lq = next.query.toLowerCase();
    let diff: TaskDifficulty = 'low';
    if (lq.includes('security') || lq.includes('threat') || lq.includes('critical') || lq.includes('hardening')) {
      diff = 'critical';
    } else if (lq.includes('code') || lq.includes('compiler') || lq.includes('sandbox') || lq.includes('ast') || lq.includes('python')) {
      diff = 'high';
    } else if (lq.includes('multimodal') || lq.includes('image') || lq.includes('video') || lq.includes('transcode')) {
      diff = 'medium';
    }
    setTaskDifficulty(diff);
    setIsAccelerated(true);

    // Add user turn to Conversational Stream
    const userMsg: ConversationalMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: next.query,
      timestamp: new Date().toLocaleTimeString(),
    };
    setConversationalMessages((prev) => [...prev, userMsg]);

    executeCommandDirect(next.query, next.actionType, () => {
      // Module 3: Exact millisecond action ripple "puff" effect
      setPuffTrigger((prev) => prev + 1);
      setIsAccelerated(false);

      // Determine AI response, MCP tools, and contextual action triggers (Module 4)
      const tools: string[] = [];
      const triggers: Array<{ label: string; action: string; payload?: any }> = [];
      let reply = `Command executed successfully. Synapse checkpointed to Knowledge Cosmos.`;

      if (diff === 'medium' || lq.includes('image') || lq.includes('video') || lq.includes('multimodal')) {
        tools.push('process_multimodal_media');
        triggers.push({ label: '✦ Open Multimodal Bridge', action: 'OPEN_MULTIMODAL' });
        reply = `Decomposed media payload into 3x3 spatial grid and OCR inscriptions. Non-vision LLM prompt block prepared.`;
        if (lq.includes('open') || lq.includes('transcode') || lq.includes('show')) {
          setIsMultimodalBridgeOpen(true);
        }
      } else if (diff === 'high' || lq.includes('code') || lq.includes('python')) {
        tools.push('execute_sandbox_code');
        triggers.push({ label: '⚡ Open Code Compiler', action: 'OPEN_CODE' });
        reply = `Python sandbox initialized with AST safety constraints. Ready for live execution.`;
        if (lq.includes('open') || lq.includes('run') || lq.includes('code')) {
          setIsCodeCompilerOpen(true);
        }
      } else if (lq.includes('canvas') || lq.includes('diagram') || lq.includes('node')) {
        tools.push('canvas_builder');
        triggers.push({ label: '◈ Open Canvas Builder', action: 'OPEN_CANVAS' });
        reply = `Visual diagramming workspace prepared. Ready to draft and connect new nodes.`;
        if (lq.includes('open') || lq.includes('show')) {
          setIsCanvasBuilderOpen(true);
        }
      } else if (lq.includes('video') || lq.includes('studio') || lq.includes('render')) {
        tools.push('runway_video_studio');
        triggers.push({ label: '🎬 Open Video Studio', action: 'OPEN_VIDEO' });
        reply = `Runway-style creative video studio activated with 6-axis camera trajectory controls.`;
      } else {
        tools.push('cortex_eval');
      }

      const aiMsg: ConversationalMessage = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        content: reply,
        timestamp: new Date().toLocaleTimeString(),
        toolsUsed: tools,
        difficulty: diff,
        actionTriggers: triggers,
      };
      setConversationalMessages((prev) => [...prev, aiMsg]);

      if (voiceEnabled) {
        // Spoken confirmation - voice synthesis coordinates agentStatus to 'speaking'
        const spokenConfirmation = `NEXUS processed: ${next.query.slice(0, 42)}`;
        speakWithStatus(spokenConfirmation, setAgentStatus, () => {
          processNextCommand();
        });
      } else {
        setTimeout(() => {
          processNextCommand();
        }, 500);
      }
    });
  }, [voiceEnabled, executeCommandDirect]);

  // Inject command or research result into the live knowledge graph with queueing
  const handleExecuteCommand = useCallback(
    (query: string, actionType: 'RESEARCH' | 'WORKFLOW' | 'CODE' | 'MEMORY' | 'GRAPH') => {
      playChime();
      commandQueueRef.current.push({
        id: `cmd-${Date.now()}-${Math.random()}`,
        query,
        actionType,
      });

      if (!isProcessingCommandRef.current) {
        processNextCommand();
      }
    },
    [processNextCommand]
  );

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

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#030508] text-slate-100 font-sans antialiased select-none">
      {/* ── Minimal Floating Top Bar ─────────────────────────────────────────── */}
      <TopBar
        currentMode={currentMode}
        onModeChange={(mode) => {
          setCurrentMode(mode);
          playHudClick();
        }}
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
        agentStatus={agentStatus}
      />

      {/* ── Left Sidebar: Workspaces, Search & System Telemetry ─────────────── */}
      <LeftSidebar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        onOpenClaudeStudio={() => setIsClaudeStudioOpen(true)}
        onOpenResearchMode={() => setCurrentMode('RESEARCH')}
        onOpenWorkflowMode={() => setCurrentMode('WORKFLOW')}
        onOpenVideoMode={() => setCurrentMode('VIDEO')}
        onOpenAgentsModal={() => setIsAgentsModalOpen(true)}
        onOpenIntegrationsModal={() => setIsIntegrationsModalOpen(true)}
        onOpenMultimodalBridge={() => setIsMultimodalBridgeOpen(true)}
      />

      {/* ── Center Viewport: Mode Dependent ─────────────────────────────────── */}
      <main className="flex-1 h-full relative overflow-hidden bg-[#0a0f1d]">
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

      {/* ── Conversational Stream: Framing AI Feedback & Actions (Module 2 & 4) ─ */}
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
      />

      {/* ── Bottom Floating Command Center Bar (In Graph or HUD Mode) ───────── */}
      {(currentMode === 'GRAPH' || currentMode === 'HUD') && (
        <CommandCenter
          onExecuteCommand={handleExecuteCommand}
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

      {/* ── Spoken Voice Cortex Assistant ───────────────────────────────────── */}
      <VoiceCortex
        voiceEnabled={voiceEnabled}
        onToggleVoice={() => setVoiceEnabled(!voiceEnabled)}
        agentStatus={agentStatus}
        onStatusChange={setAgentStatus}
        onCommand={(cmd, text) => {
          handleExecuteCommand(text, 'GRAPH');
        }}
        onOpenPrompt={(prompt) => {
          handleExecuteCommand(prompt, 'RESEARCH');
        }}
      />
    </div>
  );
};
