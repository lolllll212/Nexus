import React from 'react';
import { Search, X, Sliders, Cpu, Compass, Layers, Sparkles, MessageSquare } from 'lucide-react';
import { GraphNode, HubCategory, HubItem, ForceSettings } from '../types';
import { HUB_CONFIG, GROUP_COLORS } from '../data/mockData';

interface LeftSidebarProps {
  nodeCount: number;
  connectionCount: number;
  searchTerm: string;
  onSearchChange: (value: string) => void;
  selectedNode: GraphNode | null;
  onSelectNode: (node: GraphNode | null) => void;
  connectedNeighbors: GraphNode[];
  hubs: HubItem[];
  activeHub: HubCategory | null;
  onSelectHub: (hub: HubCategory | null) => void;
  forces: ForceSettings;
  onForcesChange: (forces: ForceSettings) => void;
  onReset2D: () => void;
  onOpenJarvis: (prompt?: string) => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  nodeCount,
  connectionCount,
  searchTerm,
  onSearchChange,
  selectedNode,
  onSelectNode,
  connectedNeighbors,
  hubs,
  activeHub,
  onSelectHub,
  forces,
  onForcesChange,
  onReset2D,
  onOpenJarvis,
}) => {
  return (
    <aside className="w-80 h-full flex flex-col z-20 pointer-events-auto border-r border-[rgba(0,240,255,0.14)] glass-panel select-none">
      {/* 1. Header */}
      <div className="p-5 border-b border-[rgba(0,240,255,0.12)] bg-gradient-to-b from-[#061120] to-transparent">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_10px_#00f0ff] animate-pulse"></div>
            <h1 className="text-base font-bold tracking-wider text-cyan-300 font-mono flex items-center gap-1.5">
              AI WORKSHOP OS
            </h1>
          </div>
          <button
            onClick={onReset2D}
            className="text-[11px] font-mono tracking-wide text-cyan-400 hover:text-cyan-200 transition-colors underline decoration-cyan-500/50 hover:decoration-cyan-300 underline-offset-2"
            title="Reset perspective to 2D force view"
          >
            back to 2D
          </button>
        </div>
        <div className="text-[11px] font-mono text-slate-400 tracking-tight flex items-center justify-between">
          <span>{nodeCount} nodes · {connectionCount} connections</span>
          <span className="text-[10px] text-cyan-500/80 uppercase">v7.4 // online</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* 2. Search */}
        <div>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <Search className="w-3.5 h-3.5 text-cyan-400/80" />
            </div>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search the brain..."
              className="w-full pl-9 pr-8 py-2 text-xs font-mono text-cyan-100 bg-[#07111e]/90 border border-[rgba(0,240,255,0.22)] rounded-full focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 shadow-inner placeholder:text-slate-500 transition-all"
            />
            {searchTerm && (
              <button
                onClick={() => onSearchChange('')}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-cyan-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* 3. Inspector Panel */}
        <div className="border border-[rgba(0,240,255,0.16)] rounded-xl bg-[#040c18]/85 p-3.5 shadow-lg relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-16 h-16 bg-cyan-500/5 rounded-full blur-xl pointer-events-none"></div>

          <div className="flex items-center justify-between mb-2">
            <div className="text-[10.5px] font-mono tracking-widest text-cyan-400/90 uppercase font-semibold flex items-center gap-1.5">
              <Compass className="w-3 h-3 text-cyan-400" />
              Inspector
            </div>
            {selectedNode && (
              <button
                onClick={() => onSelectNode(null)}
                className="text-[10px] text-slate-400 hover:text-cyan-300 font-mono"
              >
                Clear
              </button>
            )}
          </div>

          {!selectedNode ? (
            <div className="text-[11px] leading-relaxed text-slate-400 font-mono py-1">
              Click a node to focus it. Drag to rearrange, scroll to zoom. Toggle FOCUS in HUD to isolate synaptic clusters.
            </div>
          ) : (
            <div className="space-y-2.5">
              <div>
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-white font-mono tracking-wide truncate max-w-[190px]">
                    {selectedNode.id}
                  </h3>
                  <span
                    className="text-[9px] px-1.5 py-0.5 rounded font-mono font-medium border"
                    style={{
                      borderColor: GROUP_COLORS[selectedNode.group]?.base || '#00f0ff',
                      color: GROUP_COLORS[selectedNode.group]?.base || '#00f0ff',
                      backgroundColor: `${GROUP_COLORS[selectedNode.group]?.base}15` || 'rgba(0,240,255,0.1)',
                    }}
                  >
                    {selectedNode.group}
                  </span>
                </div>
                {selectedNode.hub && (
                  <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                    Hub: <span className="text-cyan-300 font-medium">{selectedNode.hub}</span>
                  </p>
                )}
              </div>

              {selectedNode.desc && (
                <p className="text-[10.5px] text-slate-300 font-sans leading-snug line-clamp-3 bg-black/30 p-2 rounded border border-white/5">
                  {selectedNode.desc}
                </p>
              )}

              {connectedNeighbors.length > 0 && (
                <div>
                  <div className="text-[9.5px] font-mono text-slate-400 uppercase tracking-wider mb-1">
                    Linked Synapses ({connectedNeighbors.length})
                  </div>
                  <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto pr-1">
                    {connectedNeighbors.slice(0, 8).map((nbr) => (
                      <button
                        key={nbr.id}
                        onClick={() => onSelectNode(nbr)}
                        className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800/80 hover:bg-cyan-950/70 border border-slate-700/60 hover:border-cyan-500/50 text-slate-300 hover:text-cyan-200 transition-colors truncate max-w-[140px]"
                        title={nbr.id}
                      >
                        {nbr.id}
                      </button>
                    ))}
                    {connectedNeighbors.length > 8 && (
                      <span className="text-[9.5px] text-slate-500 self-center font-mono">
                        +{connectedNeighbors.length - 8} more
                      </span>
                    )}
                  </div>
                </div>
              )}

              <button
                onClick={() => onOpenJarvis(`Analyze node '${selectedNode.id}' and its synaptic links in the ${selectedNode.hub || 'AI Workshop'} cluster.`)}
                className="w-full mt-2 py-1.5 px-3 rounded-lg bg-gradient-to-r from-cyan-950/80 to-blue-950/80 hover:from-cyan-900/90 hover:to-blue-900/90 border border-cyan-500/40 hover:border-cyan-400 text-cyan-200 text-[10.5px] font-mono flex items-center justify-center gap-1.5 shadow-[0_0_12px_rgba(0,240,255,0.15)] transition-all"
              >
                <Sparkles className="w-3 h-3 text-cyan-400 animate-spin-slow" />
                Ask J.A.R.V.I.S. (NVIDIA NIM)
              </button>
            </div>
          )}
        </div>

        {/* 4. Top Hubs List */}
        <div>
          <div className="flex items-center justify-between mb-2 px-1">
            <span className="text-[10px] font-mono tracking-widest text-slate-400 uppercase font-semibold flex items-center gap-1.5">
              <Layers className="w-3 h-3 text-cyan-400" />
              Top Hubs
            </span>
            {activeHub && (
              <button
                onClick={() => onSelectHub(null)}
                className="text-[10px] text-cyan-400 hover:text-cyan-200 font-mono"
              >
                Show All
              </button>
            )}
          </div>
          <div className="space-y-1">
            {hubs.map((hub) => {
              const isSelected = activeHub === hub.id;
              const config = HUB_CONFIG[hub.id] || { color: '#00f0ff', dotClass: 'bg-cyan-400 shadow-[0_0_8px_#00f0ff]' };
              return (
                <button
                  key={hub.id}
                  onClick={() => onSelectHub(isSelected ? null : hub.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-mono transition-all border ${
                    isSelected
                      ? 'bg-cyan-950/60 border-cyan-400/60 shadow-[0_0_12px_rgba(0,240,255,0.2)] text-white'
                      : 'bg-slate-900/40 border-slate-800/80 hover:border-slate-700/90 text-slate-300 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`w-2 h-2 rounded-full ${config.dotClass}`}
                      style={{ backgroundColor: config.color }}
                    />
                    <span className="tracking-wide">{hub.label}</span>
                  </div>
                  <span className={`text-[11px] font-semibold ${isSelected ? 'text-cyan-300' : 'text-slate-400'}`}>
                    {hub.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 5. Forces Panel */}
        <div className="border border-[rgba(0,240,255,0.16)] rounded-xl bg-[#040c18]/80 p-3.5 space-y-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[10.5px] font-mono tracking-widest text-cyan-400/90 uppercase font-semibold flex items-center gap-1.5">
              <Sliders className="w-3 h-3 text-cyan-400" />
              Forces
            </span>
            <span className="text-[9.5px] font-mono text-cyan-500/70">PHYSICS ENGINE</span>
          </div>

          {/* Repel Slider */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-mono">
              <label htmlFor="repel-slider" className="text-slate-300">Repel</label>
              <span className="text-cyan-400 font-semibold">{Math.abs(forces.repel)}</span>
            </div>
            <input
              id="repel-slider"
              type="range"
              min="50"
              max="900"
              step="10"
              value={Math.abs(forces.repel)}
              onChange={(e) => onForcesChange({ ...forces, repel: -Number(e.target.value) })}
              className="cyan-slider"
            />
          </div>

          {/* Link length Slider */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-mono">
              <label htmlFor="link-slider" className="text-slate-300">Link length</label>
              <span className="text-cyan-400 font-semibold">{forces.linkLength}px</span>
            </div>
            <input
              id="link-slider"
              type="range"
              min="30"
              max="240"
              step="5"
              value={forces.linkLength}
              onChange={(e) => onForcesChange({ ...forces, linkLength: Number(e.target.value) })}
              className="cyan-slider"
            />
          </div>
        </div>
      </div>

      {/* Footer System Status */}
      <div className="p-3 border-t border-[rgba(0,240,255,0.1)] bg-black/40 flex items-center justify-between text-[10px] font-mono text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
          STARK ENGINE READY
        </span>
        <button
          onClick={() => onOpenJarvis()}
          className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 hover:underline"
        >
          <MessageSquare className="w-3 h-3" />
          TERMINAL
        </button>
      </div>
    </aside>
  );
};
