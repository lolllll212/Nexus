import React, { useState } from 'react';
import { 
  Cpu, 
  Layers, 
  CheckCircle2, 
  ShieldCheck, 
  Zap, 
  RefreshCw, 
  Sliders, 
  Info,
  Server,
  ArrowRight,
  Database,
  Radio
} from 'lucide-react';
import { HEXAGONAL_PORTS } from '../data/nexusGraphData';
import { HexagonalPort } from '../types';

export const ArchitectureView: React.FC = () => {
  const [ports, setPorts] = useState<HexagonalPort[]>(HEXAGONAL_PORTS);
  const [selectedPort, setSelectedPort] = useState<HexagonalPort>(ports[0]);

  const handleSwitchAdapter = (portId: string, adapterName: string) => {
    setPorts((prev) =>
      prev.map((p) => (p.id === portId ? { ...p, activeAdapter: adapterName } : p))
    );
    if (selectedPort.id === portId) {
      setSelectedPort((prev) => ({ ...prev, activeAdapter: adapterName }));
    }
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#05070c] text-slate-100 font-mono overflow-hidden">
      {/* ── Top Architecture Header ─────────────────────────────────────────── */}
      <div className="p-4 border-b border-cyan-500/20 bg-slate-950/80 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-purple-950/80 border border-purple-400/40 text-purple-400 shadow-[0_0_15px_rgba(168,85,247,0.25)]">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider">
                PORTS & ADAPTERS (HEXAGONAL ARCHITECTURE)
              </span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/30">
                STRICT DOMAIN ISOLATION
              </span>
            </div>
            <h2 className="text-sm font-semibold text-slate-100">
              NEXUS Autonomous Core ⇄ Interchangeable Infrastructure Adapters
            </h2>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]"></span>
            <span>100% Provider Agnostic</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(0,240,255,0.8)]"></span>
            <span>Hot-Swappable Ports</span>
          </div>
        </div>
      </div>

      {/* ── Main Architectural Map: NEXUS CORE Center + Hexagonal Ports Ring ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Spatial Architecture Diagram */}
        <div className="flex-1 p-8 overflow-y-auto flex flex-col justify-center items-center relative">
          {/* Subtle Background Radial Aura */}
          <div className="absolute w-[500px] h-[500px] rounded-full bg-purple-500/5 blur-3xl pointer-events-none"></div>

          {/* Central NEXUS Core Entity */}
          <div className="relative z-10 w-44 h-44 rounded-3xl p-4 glass-panel border-2 border-purple-400/60 bg-slate-950/90 shadow-[0_0_50px_rgba(168,85,247,0.35)] flex flex-col items-center justify-center text-center mb-8">
            <div className="w-12 h-12 rounded-2xl bg-purple-950 border border-purple-400/50 flex items-center justify-center text-purple-300 mb-2 shadow-[0_0_20px_rgba(168,85,247,0.4)]">
              <Cpu className="w-6 h-6 animate-spin-slow" />
            </div>
            <h3 className="text-xs font-bold font-mono text-purple-300 tracking-wider">
              NEXUS CORE
            </h3>
            <span className="text-[9px] text-slate-400 mt-0.5">
              Pure Domain Logic & Cortex
            </span>
            <div className="mt-2 text-[8px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold">
              ZERO EXT DEPS
            </div>
          </div>

          {/* Circular Hexagonal Ports Ring */}
          <div className="grid grid-cols-5 gap-3 w-full max-w-4xl z-10">
            {ports.map((port) => {
              const isSelected = selectedPort.id === port.id;

              return (
                <div
                  key={port.id}
                  onClick={() => setSelectedPort(port)}
                  className={`p-3.5 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? 'bg-slate-900 border-cyan-400 shadow-[0_0_20px_rgba(0,240,255,0.25)]'
                      : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[9px] font-mono text-cyan-400 font-bold uppercase truncate">
                        {port.name.replace(' Port', '')}
                      </span>
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.8)]"></span>
                    </div>
                    <span className="text-[8px] text-slate-500 block mb-1">{port.type}</span>
                    <p className="text-[11px] font-semibold text-slate-200 truncate">
                      {port.activeAdapter}
                    </p>
                  </div>

                  <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[9px] text-slate-400">
                    <span>{port.latencyMs}ms</span>
                    <span className="text-cyan-400 font-mono">{port.adapters.length} adapters</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Port Adapter Configuration & Fault Isolation Panel */}
        <div className="w-96 border-l border-slate-800 p-6 flex flex-col bg-slate-950/80">
          <div className="pb-3 border-b border-slate-800 mb-4 flex items-center justify-between">
            <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">
              Port Configuration
            </span>
            <span className="text-[9px] text-emerald-400 font-mono">NOMINAL</span>
          </div>

          <div className="space-y-4 mb-6">
            <div>
              <span className="text-[9px] text-slate-500 uppercase block mb-1">SELECTED PORT</span>
              <h3 className="text-sm font-bold text-slate-100">{selectedPort.name}</h3>
              <p className="text-[10px] text-slate-400 mt-0.5">{selectedPort.type}</p>
            </div>

            <div>
              <span className="text-[9px] text-slate-500 uppercase block mb-1">PORT PROTOCOL</span>
              <div className="p-2.5 rounded-xl bg-black/60 border border-slate-800 text-[10px] text-cyan-300 font-mono break-all">
                {selectedPort.protocol}
              </div>
            </div>

            {/* Interchangeable Adapters List */}
            <div>
              <span className="text-[9px] text-slate-500 uppercase block mb-2">
                INTERCHANGEABLE ADAPTERS (HOT-SWAPPABLE)
              </span>
              <div className="space-y-2">
                {selectedPort.adapters.map((adapter) => {
                  const isActive = selectedPort.activeAdapter.includes(adapter) || adapter.includes(selectedPort.activeAdapter);

                  return (
                    <div
                      key={adapter}
                      onClick={() => handleSwitchAdapter(selectedPort.id, adapter)}
                      className={`p-2.5 rounded-xl border flex items-center justify-between text-xs transition-all cursor-pointer ${
                        isActive
                          ? 'bg-cyan-950/50 border-cyan-400 text-cyan-200 shadow-[0_0_12px_rgba(0,240,255,0.2)]'
                          : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      <span className="font-semibold">{adapter}</span>
                      {isActive ? (
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold">
                          ACTIVE
                        </span>
                      ) : (
                        <span className="text-[9px] text-slate-500 hover:text-slate-300">
                          Click to Bind
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Architectural Guarantees */}
            <div className="p-3.5 rounded-2xl bg-slate-900/40 border border-slate-800 text-[10px] text-slate-400 space-y-1.5">
              <span className="text-slate-300 font-bold uppercase block text-[9px]">
                ARCHITECTURAL GUARANTEES:
              </span>
              <div className="flex items-center gap-1.5 text-emerald-400">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Domain Independence (Zero external imports in core)</span>
              </div>
              <div className="flex items-center gap-1.5 text-cyan-400">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Fault Isolation (Adapter failure cannot crash Cortex)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
