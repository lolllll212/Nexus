import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { LeftSidebar } from './components/LeftSidebar';
import { RightSidebar } from './components/RightSidebar';
import { CenterCanvas } from './components/CenterCanvas';
import { TopNavigation } from './components/TopNavigation';
import { JarvisModal } from './components/JarvisModal';
import { HoloCubeOverlay } from './components/HoloCubeOverlay';
import { FaceTrackerOverlay } from './components/FaceTrackerOverlay';
import { WatchLoggerOverlay } from './components/WatchLoggerOverlay';
import { ResearchModal } from './components/ResearchModal';
import { WorkflowsModal } from './components/WorkflowsModal';
import { IntegrationsModal } from './components/IntegrationsModal';
import { VisionGesturesModal } from './components/VisionGesturesModal';
import { VoiceCortex } from './components/VoiceCortex';
import { NodeInspectorModal } from './components/NodeInspectorModal';
import { ClaudeCodingStudio } from './components/ClaudeCodingStudio';
import { playHudClick, playChime, playSuccessChime } from './utils/soundEffects';

import { 
  GraphData, 
  GraphNode, 
  NodeGroup, 
  HubCategory, 
  HubItem, 
  LegendItem, 
  ForceSettings, 
  SystemStates, 
  NimStatus 
} from './types';
import { INITIAL_GRAPH_DATA, GROUP_COLORS, HUB_CONFIG } from './data/mockData';

export const App: React.FC = () => {
  // Graph state
  const [graphData, setGraphData] = useState<GraphData>(INITIAL_GRAPH_DATA);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeFilter, setActiveFilter] = useState<NodeGroup | null>(null);
  const [activeHub, setActiveHub] = useState<HubCategory | null>(null);

  // Physics & view controls
  const [forces, setForces] = useState<ForceSettings>({ repel: -420, linkLength: 95 });
  const [isSimulating, setIsSimulating] = useState(true);
  const [showLabels, setShowLabels] = useState(false);
  const [showPulses, setShowPulses] = useState(true);
  const [is3DMode, setIs3DMode] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fitTrigger, setFitTrigger] = useState(1);

  // System States (HUD Toggles)
  const [systemStates, setSystemStates] = useState<SystemStates>({
    ONLINE: true,
    RING: true,
    CUBE: false,
    FACE: false,
    EYES: false,
    WATCH: false,
    HOLO: false,
    FOCUS: false,
  });

  // J.A.R.V.I.S. & NVIDIA NIM State
  const [isJarvisOpen, setIsJarvisOpen] = useState(false);
  const [jarvisPrompt, setJarvisPrompt] = useState<string | undefined>(undefined);
  const [nimStatus, setNimStatus] = useState<NimStatus | null>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(true);

  // Modals state
  const [isCodingStudioOpen, setIsCodingStudioOpen] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get('view') === 'claude' || params.get('view') === 'code';
    }
    return false;
  });
  const [isResearchOpen, setIsResearchOpen] = useState(false);
  const [isWorkflowsOpen, setIsWorkflowsOpen] = useState(false);
  const [isIntegrationsOpen, setIsIntegrationsOpen] = useState(false);
  const [isVisionOpen, setIsVisionOpen] = useState(false);
  const [inspectingNode, setInspectingNode] = useState<GraphNode | null>(null);
  const [gestureToast, setGestureToast] = useState<string | null>(null);

  // Fetch graph data from backend
  const fetchGraphData = useCallback(async () => {
    try {
      const res = await fetch('/api/graph?limit=140');
      if (res.ok) {
        const json = await res.json();
        if (json.nodes && json.nodes.length > 0) {
          setGraphData(json);
        }
      }
    } catch (e) {
      console.warn('Using local Second Brain graph dataset.', e);
    }
  }, []);

  // Fetch NIM status from backend
  const fetchNimStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/nim/status');
      if (res.ok) {
        const json = await res.json();
        setNimStatus(json);
      }
    } catch (e) {
      console.warn('NIM status offline, using simulation.', e);
    }
  }, []);

  useEffect(() => {
    fetchGraphData();
    fetchNimStatus();
  }, [fetchGraphData, fetchNimStatus]);

  // Compute connected neighbors for selected node
  const connectedNeighbors = useMemo(() => {
    if (!selectedNode) return [];
    const nbrMap = new Map<string, GraphNode>();
    const nodeMap = new Map<string, GraphNode>();
    graphData.nodes.forEach((n) => nodeMap.set(n.id, n));

    graphData.links.forEach((l) => {
      const sId = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
      const tId = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;

      if (sId === selectedNode.id && nodeMap.has(tId)) {
        nbrMap.set(tId, nodeMap.get(tId)!);
      } else if (tId === selectedNode.id && nodeMap.has(sId)) {
        nbrMap.set(sId, nodeMap.get(sId)!);
      }
    });

    return Array.from(nbrMap.values());
  }, [selectedNode, graphData]);

  const handleSelectNode = useCallback((node: GraphNode | null) => {
    setSelectedNode(node);
    if (node) {
      setInspectingNode(node);
      playHudClick();
    }
  }, []);

  // Compute Hub counts dynamically
  const hubs: HubItem[] = useMemo(() => {
    const hubNames: HubCategory[] = [
      'Skill Suites',
      'Local Businesses',
      'AI Workshop',
      'Claude Code',
    ];

    const counts: Record<HubCategory, number> = {
      'Skill Suites': 0,
      'Local Businesses': 0,
      'AI Workshop': 0,
      'Claude Code': 0,
    };

    graphData.nodes.forEach((node) => {
      if (node.hub && counts[node.hub as HubCategory] !== undefined) {
        counts[node.hub as HubCategory]++;
      }
    });

    return hubNames.map((name) => ({
      id: name,
      label: name,
      color: HUB_CONFIG[name]?.color || '#00f0ff',
      count: counts[name] || 0,
    }));
  }, [graphData]);

  // Compute Legend counts dynamically
  const legendItems: LegendItem[] = useMemo(() => {
    const groups: NodeGroup[] = [
      'Router',
      'Concepts',
      'Suites',
      'Skills',
      'Tools',
      'Worlds',
      'Notes',
      'Files',
    ];

    const counts: Record<NodeGroup, number> = {
      Router: 0,
      Concepts: 0,
      Suites: 0,
      Skills: 0,
      Tools: 0,
      Worlds: 0,
      Notes: 0,
      Files: 0,
    };

    graphData.nodes.forEach((node) => {
      if (counts[node.group] !== undefined) {
        counts[node.group]++;
      }
    });

    return groups.map((grp) => ({
      id: grp,
      label: grp,
      color: GROUP_COLORS[grp]?.base || '#00f0ff',
      glowColor: GROUP_COLORS[grp]?.glow || 'rgba(0,240,255,0.4)',
      count: counts[grp] || 0,
    }));
  }, [graphData]);

  // Reset to 2D link handler
  const handleReset2D = () => {
    setIs3DMode(false);
    setActiveFilter(null);
    setActiveHub(null);
    setSearchTerm('');
    setFitTrigger((prev) => prev + 1);
  };

  // Toggle single system state
  const handleToggleState = (key: keyof SystemStates) => {
    setSystemStates((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      if (key === 'HOLO' && next.HOLO) {
        setIs3DMode(true);
      }
      return next;
    });
  };

  // Toggle filter in legend
  const handleToggleFilter = (group: NodeGroup) => {
    setActiveFilter((prev) => (prev === group ? null : group));
  };

  // Toggle fullscreen
  const handleToggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  // Open Jarvis modal with optional preloaded prompt
  const handleOpenJarvis = (prompt?: string) => {
    setJarvisPrompt(prompt);
    setIsJarvisOpen(true);
  };

  // Hand gesture detection handler
  const handleGestureDetected = (gesture: string) => {
    setGestureToast(`🖐️ HAND GESTURE DETECTED: ${gesture}`);
    setTimeout(() => setGestureToast(null), 3000);

    if (gesture === 'PEACE SIGN') {
      handleReset2D();
    } else if (gesture === 'OPEN PALM') {
      // Repulsor blast: temporarily scatter nodes
      setForces((prev) => ({ ...prev, repel: -780 }));
      setTimeout(() => setForces((prev) => ({ ...prev, repel: -420 })), 2200);
    } else if (gesture === 'CLOSED FIST') {
      // Magnetic pull: engage focus & tighten links
      setSystemStates((prev) => ({ ...prev, FOCUS: true }));
      setForces((prev) => ({ ...prev, linkLength: 60 }));
      setTimeout(() => setForces((prev) => ({ ...prev, linkLength: 95 })), 2500);
    } else if (gesture === 'PINCH') {
      // Select central AI Workshop node
      const centerNode = graphData.nodes.find((n) => n.id === 'AI Workshop') || graphData.nodes[0];
      if (centerNode) setSelectedNode(centerNode);
    }
  };

  // Voice command dispatcher
  const handleVoiceCommand = (command: string, rawText: string) => {
    if (command === 'RESEARCH') {
      setIsResearchOpen(true);
    } else if (command === 'GITHUB') {
      setIsIntegrationsOpen(true);
    } else if (command === 'GMAIL') {
      setIsIntegrationsOpen(true);
    } else if (command === 'WORKFLOW') {
      setIsWorkflowsOpen(true);
    } else if (command === 'VISION') {
      setIsVisionOpen(true);
    } else if (command === 'FIT') {
      handleReset2D();
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.key === 'Escape') {
        setSelectedNode(null);
        setActiveFilter(null);
        setActiveHub(null);
        setIsJarvisOpen(false);
        setIsResearchOpen(false);
        setIsWorkflowsOpen(false);
        setIsIntegrationsOpen(false);
        setIsVisionOpen(false);
      } else if (e.key === 'c' || e.key === 'C') {
        setIsCodingStudioOpen((prev) => !prev);
      } else if (e.key === 'j' || e.key === 'J') {
        setIsJarvisOpen((prev) => !prev);
      } else if (e.key === 'r' || e.key === 'R') {
        setIsResearchOpen((prev) => !prev);
      } else if (e.key === 'w' || e.key === 'W') {
        setIsWorkflowsOpen((prev) => !prev);
      } else if (e.key === 'i' || e.key === 'I') {
        setIsIntegrationsOpen((prev) => !prev);
      } else if (e.key === 'v' || e.key === 'V') {
        setIsVisionOpen((prev) => !prev);
      } else if (e.key === 'f' || e.key === 'F') {
        setFitTrigger((prev) => prev + 1);
      } else if (e.key === ' ') {
        e.preventDefault();
        setIsSimulating((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#020408] text-slate-100 flex">
      {/* Sci-fi CRT scanline overlay */}
      <div className="scanline"></div>

      {/* 1. Left Sidebar (System Controls & Data) */}
      <LeftSidebar
        nodeCount={graphData.nodes.length}
        connectionCount={graphData.links.length}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        selectedNode={selectedNode}
        onSelectNode={handleSelectNode}
        connectedNeighbors={connectedNeighbors}
        hubs={hubs}
        activeHub={activeHub}
        onSelectHub={setActiveHub}
        forces={forces}
        onForcesChange={setForces}
        onReset2D={handleReset2D}
        onOpenJarvis={handleOpenJarvis}
      />

      {/* 2. Main Center Canvas */}
      <main className="relative flex-1 h-full overflow-hidden">
        {/* Floating Top Navigation */}
        <TopNavigation
          onFit={() => setFitTrigger((prev) => prev + 1)}
          isSimulating={isSimulating}
          onToggleSimulation={() => setIsSimulating((prev) => !prev)}
          showLabels={showLabels}
          onToggleLabels={() => setShowLabels((prev) => !prev)}
          showPulses={showPulses}
          onTogglePulses={() => setShowPulses((prev) => !prev)}
          is3DMode={is3DMode}
          onToggle3D={() => setIs3DMode((prev) => !prev)}
          isFullscreen={isFullscreen}
          onToggleFullscreen={handleToggleFullscreen}
          onOpenJarvis={() => handleOpenJarvis()}
          onOpenResearch={() => setIsResearchOpen(true)}
          onOpenWorkflows={() => setIsWorkflowsOpen(true)}
          onOpenIntegrations={() => setIsIntegrationsOpen(true)}
          onOpenVision={() => setIsVisionOpen(true)}
          onOpenCodingStudio={() => setIsCodingStudioOpen(true)}
        />

        {/* Center Force-Directed Graph */}
        <CenterCanvas
          data={graphData}
          selectedNode={selectedNode}
          onSelectNode={handleSelectNode}
          activeFilter={activeFilter}
          activeHub={activeHub}
          searchTerm={searchTerm}
          forces={forces}
          isSimulating={isSimulating}
          showLabels={showLabels}
          showPulses={showPulses}
          is3DMode={is3DMode}
          systemStates={systemStates}
          fitTrigger={fitTrigger}
        />

        {/* State Overlays */}
        <HoloCubeOverlay active={systemStates.CUBE} />
        <FaceTrackerOverlay
          faceActive={systemStates.FACE}
          eyesActive={systemStates.EYES}
        />
        <WatchLoggerOverlay
          active={systemStates.WATCH}
          selectedNode={selectedNode}
        />

        {/* Gesture Notification Toast */}
        {gestureToast && (
          <div className="fixed top-18 right-80 z-40 px-4 py-2 rounded-xl bg-cyan-950/90 border border-cyan-400 text-xs font-mono text-cyan-200 shadow-[0_0_25px_rgba(0,240,255,0.4)] animate-in slide-in-from-right-2">
            {gestureToast}
          </div>
        )}

        {/* HOLO Mode Notification pill */}
        {systemStates.HOLO && (
          <div className="fixed top-18 left-1/2 -translate-x-1/2 z-30 px-3 py-1.5 rounded-full bg-amber-950/80 border border-amber-400/50 text-[10px] font-mono text-amber-300 flex items-center gap-2 shadow-[0_0_15px_rgba(251,191,36,0.3)] animate-pulse">
            <span>HOLO GESTURE DECK STANDBY</span>
            <a
              href="/holo.html"
              target="_blank"
              rel="noreferrer"
              className="px-2 py-0.5 rounded bg-amber-400 text-black font-semibold hover:bg-amber-300 transition-colors"
            >
              LAUNCH WEBCAM DECK →
            </a>
          </div>
        )}

        {/* Voice Cortex (STT & TTS) Floating Bar */}
        <VoiceCortex
          onCommand={handleVoiceCommand}
          onOpenJarvisWithPrompt={handleOpenJarvis}
          voiceEnabled={voiceEnabled}
          onToggleVoice={() => setVoiceEnabled(!voiceEnabled)}
        />
      </main>

      {/* 3. Right Sidebar & HUD */}
      <RightSidebar
        legendItems={legendItems}
        activeFilter={activeFilter}
        onToggleFilter={handleToggleFilter}
        systemStates={systemStates}
        onToggleState={handleToggleState}
        hasNimKey={!!nimStatus?.has_api_key}
        onOpenJarvis={() => handleOpenJarvis()}
      />

      {/* J.A.R.V.I.S. NVIDIA NIM Dialog Modal */}
      <JarvisModal
        isOpen={isJarvisOpen}
        onClose={() => setIsJarvisOpen(false)}
        initialPrompt={jarvisPrompt}
        nimStatus={nimStatus}
        onRefreshNimStatus={fetchNimStatus}
      />

      {/* Autonomous Deep Research Lab Modal */}
      <ResearchModal
        isOpen={isResearchOpen}
        onClose={() => setIsResearchOpen(false)}
        onRefreshGraph={fetchGraphData}
        onOpenJarvisWithPrompt={handleOpenJarvis}
      />

      {/* Workflows Automation Modal */}
      <WorkflowsModal
        isOpen={isWorkflowsOpen}
        onClose={() => setIsWorkflowsOpen(false)}
        onRefreshGraph={fetchGraphData}
      />

      {/* Integrations (GitHub & Gmail) Modal */}
      <IntegrationsModal
        isOpen={isIntegrationsOpen}
        onClose={() => setIsIntegrationsOpen(false)}
        onRefreshGraph={fetchGraphData}
      />

      {/* Vision, Screen Sharing & Hand Gestures Modal */}
      <VisionGesturesModal
        isOpen={isVisionOpen}
        onClose={() => setIsVisionOpen(false)}
        onGestureDetected={handleGestureDetected}
        onOpenJarvisWithPrompt={handleOpenJarvis}
      />

      {/* Second Brain Concept Inspector Modal */}
      {inspectingNode && (
        <NodeInspectorModal
          node={inspectingNode}
          onClose={() => setInspectingNode(null)}
          onAskJarvis={(prompt) => handleOpenJarvis(prompt)}
          onDeepResearch={(topic) => {
            setIsResearchOpen(true);
          }}
        />
      )}
      {/* Dedicated Claude Coding & Research Studio Overlay */}
      {isCodingStudioOpen && (
        <ClaudeCodingStudio
          onBackToSecondBrain={() => setIsCodingStudioOpen(false)}
          onOpenResearch={(query) => {
            setIsCodingStudioOpen(false);
            setIsResearchOpen(true);
          }}
        />
      )}
    </div>
  );
};
