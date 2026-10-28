import React from 'react';
import {
  OperatingMode,
  AgentStatus,
  ChatCapabilities,
  ModelCatalog
} from '../types';
import { CapabilitiesPanel } from './CapabilitiesPanel';
import { ModelPicker } from './ModelPicker';
import { VoiceSettings } from './VoiceSettings';
import { getModelById } from '../data/modelCatalog';
import type { VoicePreferences } from '../utils/voiceManager';
import { 
  Share2, 
  Search, 
  Zap, 
  Cpu, 
  Terminal, 
  Maximize2, 
  Minimize2, 
  Bell, 
  Settings, 
  User, 
  Activity,
  Layers,
  Sparkles,
  Command,
  Mic,
  ShieldCheck,
  Bot,
  Radio,
  Film,
  Loader2,
  Volume2,
  BarChart3,
  LayoutDashboard,
  History,
  MessageSquareText
} from 'lucide-react';

interface TopBarProps {
  currentMode: OperatingMode;
  onModeChange: (mode: OperatingMode) => void;
  onOpenClaudeStudio: () => void;
  onToggleFullscreen: () => void;
  isFullscreen: boolean;
  onOpenCommandCenter: () => void;
  onOpenVoiceCortex: () => void;
  onOpenAgentsModal: () => void;
  onOpenIntegrationsModal: () => void;
  onOpenNim: () => void;
  agentStatus?: AgentStatus;
  // Chat model changer / capabilities / voice / history entry points
  modelCatalog?: ModelCatalog;
  selectedModelId?: string;
  onModelChange?: (modelId: string) => void;
  capabilities?: ChatCapabilities;
  onCapabilitiesChange?: (capabilities: ChatCapabilities) => void;
  voicePreferences?: VoicePreferences;
  onVoicePreferencesChange?: (preferences: VoicePreferences) => void;
  onAgentStatusChange?: (status: AgentStatus) => void;
  sessionCount?: number;
  onOpenChat?: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  currentMode,
  onModeChange,
  onOpenClaudeStudio,
  onToggleFullscreen,
  isFullscreen,
  onOpenCommandCenter,
  onOpenVoiceCortex,
  onOpenAgentsModal,
  onOpenIntegrationsModal,
  onOpenNim,
  agentStatus = 'idle',
  modelCatalog,
  selectedModelId,
  onModelChange,
  capabilities,
  onCapabilitiesChange,
  voicePreferences,
  onVoicePreferencesChange,
  onAgentStatusChange,
  sessionCount = 0,
  onOpenChat,
}) => {
  const selectedModel = modelCatalog && selectedModelId
    ? getModelById(modelCatalog.models, selectedModelId)
    : null;
  const modes: { id: OperatingMode; label: string; icon: any }[] = [
    { id: 'WORKSPACE', label: 'WORKSPACE', icon: LayoutDashboard },
    { id: 'CLAUDE_CHAT', label: 'CHAT', icon: MessageSquareText },
    { id: 'HUD', label: 'HUD (FUI)', icon: Sparkles },
    { id: 'DASHBOARD', label: 'SWARM DASHBOARD', icon: BarChart3 },
    { id: 'GRAPH', label: 'GRAPH', icon: Share2 },
    { id: 'RESEARCH', label: 'RESEARCH', icon: Search },
    { id: 'WORKFLOW', label: 'WORKFLOW', icon: Zap },
    { id: 'ARCHITECTURE', label: 'ARCHITECTURE', icon: Cpu },
    { id: 'VIDEO', label: 'VIDEO', icon: Film },
  ];

  return (
    <header className="fixed top-3 left-1/2 -translate-x-1/2 z-30 flex min-w-0 items-center justify-between gap-2 px-3 py-2 rounded-2xl glass-obsidian border border-[#00f0ff]/25 bg-[#0a0f1d]/90 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.8),0_0_25px_rgba(0,240,255,0.15)] select-none w-[94vw] max-w-7xl font-mono sm:gap-3 sm:px-4">
      {/* ── Left Quick Triggers ────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-2">
        <button onClick={onOpenNim} title="Open NVIDIA NIM console and configure provider key" className="text-xs font-bold text-white tracking-widest px-2 py-0.5 rounded-lg bg-cyan-950/80 border border-cyan-400/40 text-cyan-400 flex items-center gap-1.5 shadow-[0_0_10px_rgba(0,240,255,0.3)] cursor-pointer">
          <Cpu className="w-3.5 h-3.5" />
          <span>NEXUS</span>
        </button>

        {modelCatalog && selectedModelId && onModelChange && (
          <div className="hidden 2xl:block" title="Model changer">
            <ModelPicker
              catalog={modelCatalog}
              value={selectedModelId}
              onChange={onModelChange}
              compact
              disabled={agentStatus === 'thinking' || agentStatus === 'listening'}
              align="left"
            />
          </div>
        )}

        {/* Dedicated Claude Coding Studio Launcher */}
        <button
          onClick={onOpenClaudeStudio}
          className="flex items-center gap-1.5 px-3 py-1 rounded-xl text-[11px] font-bold text-amber-300 bg-amber-950/70 hover:bg-amber-900 border border-amber-500/50 transition-all shadow-[0_0_10px_rgba(245,158,11,0.25)] cursor-pointer"
          title="Open Claude Coding Studio (Hotkey: C)"
        >
          <Terminal className="w-3.5 h-3.5 text-amber-400" />
          <span className="hidden md:inline">Claude Studio</span>
          <span className="ml-1 hidden rounded bg-amber-900/80 px-1 py-0.2 text-[9px] text-amber-200 lg:inline">C</span>
        </button>

        {/* Autonomous Agents Orchestration Layer Launcher */}
        <button
          onClick={onOpenAgentsModal}
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-[11px] font-bold text-purple-300 bg-purple-950/60 hover:bg-purple-900/80 border border-purple-500/40 transition-all shadow-[0_0_10px_rgba(168,85,247,0.2)] cursor-pointer"
          title="Autonomous Agent Orchestration Layer (10 Active Agents)"
        >
          <Bot className="w-3.5 h-3.5 text-purple-400" />
          <span>AGENTS</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-purple-900/80 text-purple-200 font-mono">10</span>
        </button>

        {/* External Integration Universe Launcher */}
        <button
          onClick={onOpenIntegrationsModal}
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-[11px] font-bold text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-500/40 transition-all shadow-[0_0_10px_rgba(6,182,212,0.2)] cursor-pointer"
          title="External Integration Universe (16 Integrations)"
        >
          <Radio className="w-3.5 h-3.5 text-cyan-400" />
          <span>INTEGRATIONS</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-cyan-900/80 text-cyan-200 font-mono">16</span>
        </button>
      </div>

      {/* ── Center Live Operating Mode Selector ─────────────────────────────── */}
      <nav
        aria-label="Operating mode"
        className="scrollbar-none flex min-w-0 flex-1 items-center gap-1 overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/90 p-1 shadow-inner"
      >
        {modes.map((m) => {
          const Icon = m.icon;
          const isActive = currentMode === m.id;

          return (
            <button
              key={m.id}
              type="button"
              onClick={() => onModeChange(m.id)}
              title={m.label}
              aria-label={`Open ${m.label}`}
              aria-current={isActive ? 'page' : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
              <span className="hidden 2xl:inline">{m.label}</span>
            </button>
          );
        })}
      </nav>

      {/* ── Right Telemetry & Actions ───────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-2">
        {onOpenChat && (
          <button
            type="button"
            onClick={onOpenChat}
            title="Open NEXUS chat and conversation history"
            className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-400/30 bg-cyan-950/50 text-cyan-200 transition-colors hover:border-cyan-300/70 hover:text-white cursor-pointer"
          >
            <History className="h-4 w-4" />
            {sessionCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full border border-cyan-200/70 bg-cyan-400 px-1 text-[8px] font-black text-slate-950">
                {sessionCount > 99 ? '99+' : sessionCount}
              </span>
            )}
          </button>
        )}

        {capabilities && onCapabilitiesChange && (
          <CapabilitiesPanel
            capabilities={capabilities}
            onChange={onCapabilitiesChange}
            selectedModel={selectedModel}
            capabilityLabels={modelCatalog?.capability_labels}
            align="right"
            placement="bottom"
          />
        )}

        {voicePreferences && onVoicePreferencesChange && (
          <VoiceSettings
            preferences={voicePreferences}
            onChange={onVoicePreferencesChange}
            voiceEnabled={capabilities?.voiceReplies}
            onVoiceEnabledChange={
              capabilities && onCapabilitiesChange
                ? (enabled) => onCapabilitiesChange({ ...capabilities, voiceReplies: enabled })
                : undefined
            }
            agentStatus={agentStatus}
            onStatusChange={onAgentStatusChange}
            align="right"
            placement="bottom"
          />
        )}

        {/* Security State Badge (Module 2) */}
        <div 
          className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-[#040914] border border-[#00ff88]/30 text-[9px] text-[#00ff88]"
          title="AST Guard & Sandboxed Execution Active"
        >
          <ShieldCheck className="w-3 h-3 text-[#00ff88]" />
          <span>AST GUARD: OK</span>
        </div>

        {/* MCP & Tool Server Status (Module 2 & 4) */}
        <div 
          className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-[#040914] border border-cyan-400/30 text-[9px] text-cyan-300"
          title="Model Context Protocol (MCP) Server Online"
        >
          <Zap className="w-3 h-3 text-cyan-400" />
          <span>MCP: ONLINE</span>
        </div>

        <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-[9.5px] text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.9)]"></span>
          <span>SYSTEM ONLINE</span>
        </div>

        {/* Dedicated Prominent Voice Cortex Button with Status Feedback */}
        <button
          onClick={onOpenVoiceCortex}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-[11px] font-bold transition-all cursor-pointer group shadow-sm ${
            agentStatus === 'listening'
              ? 'bg-cyan-500 text-black shadow-[0_0_18px_#00f0ff] animate-pulse'
              : agentStatus === 'thinking'
              ? 'bg-purple-950/90 border border-purple-400 text-purple-300 shadow-[0_0_12px_rgba(168,85,247,0.3)]'
              : agentStatus === 'speaking'
              ? 'bg-amber-950/90 border border-amber-400 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.3)]'
              : 'text-cyan-200 bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-400/60 hover:border-cyan-300 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
          }`}
          title={
            agentStatus === 'listening'
              ? 'Voice Cortex is listening... Click to stop'
              : agentStatus === 'thinking'
              ? 'Agent is thinking... Mic locked to prevent echo'
              : agentStatus === 'speaking'
              ? 'Agent is speaking... Mic locked to prevent echo'
              : 'Toggle Hands-Free Voice Cortex (Hotkey: M)'
          }
        >
          {agentStatus === 'thinking' ? (
            <Loader2 className="w-3.5 h-3.5 text-purple-400 animate-spin" />
          ) : agentStatus === 'speaking' ? (
            <Volume2 className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
          ) : (
            <Mic className={`w-3.5 h-3.5 ${agentStatus === 'listening' ? 'text-black' : 'text-cyan-400'} animate-pulse`} />
          )}

          <span className="hidden tracking-wide sm:inline">
            {agentStatus === 'listening'
              ? 'LISTENING'
              : agentStatus === 'thinking'
              ? 'THINKING'
              : agentStatus === 'speaking'
              ? 'SPEAKING'
              : 'VOICE (M)'}
          </span>
        </button>

        {/* Command Center Palette Trigger */}
        <button
          onClick={onOpenCommandCenter}
          className="p-1.5 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
          title="Command Palette (Ctrl+K)"
        >
          <Command className="w-4 h-4" />
        </button>

        {/* Fullscreen Toggle */}
        <button
          onClick={onToggleFullscreen}
          className="p-1.5 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-slate-900 transition-colors cursor-pointer"
          title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      </div>
    </header>
  );
};
