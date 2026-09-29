import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  NexusNode, 
  NexusLink, 
  NodeCategory, 
  OperatingMode, 
  ResearchClaim,
  AgentStatus 
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
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

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
        else if (selectedNode) setSelectedNode(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isClaudeStudioOpen, isAgentsModalOpen, isIntegrationsModalOpen, selectedNode]);

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

  // FIX 3: Unified Queue Processor preventing state race conditions
  const processNextCommand = useCallback(() => {
    if (commandQueueRef.current.length === 0) {
      isProcessingCommandRef.current = false;
      setAgentStatus('idle');
      return;
    }

    const next = commandQueueRef.current.shift()!;
    isProcessingCommandRef.current = true;
    setAgentStatus('thinking');

    executeCommandDirect(next.query, next.actionType, () => {
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
      />

      {/* ── Center Viewport: Mode Dependent ─────────────────────────────────── */}
      <main className="flex-1 h-full relative overflow-hidden bg-[#05070c]">
        {/* Real-time Information Flow Ticker (Cortex vs Subcortex) in Graph Mode */}
        {currentMode === 'GRAPH' && (
          <div className="absolute top-16 right-6 z-20 max-w-lg">
            <InformationFlowTicker />
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

      {/* ── Bottom Floating Command Center Bar (In Graph Mode) ──────────────── */}
      {currentMode === 'GRAPH' && (
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
