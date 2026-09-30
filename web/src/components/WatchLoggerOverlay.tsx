import React, { useState, useEffect } from 'react';
import { Terminal, Shield } from 'lucide-react';
import { GraphNode } from '../types';

interface WatchLoggerOverlayProps {
  active: boolean;
  selectedNode: GraphNode | null;
}

export const WatchLoggerOverlay: React.FC<WatchLoggerOverlayProps> = ({
  active,
  selectedNode,
}) => {
  const [logs, setLogs] = useState<string[]>([
    "INITIALIZING TELEMETRY STREAM...",
    "SYNAPSE CLUSTERS 1..4 SYNCHRONIZED",
    "NVIDIA NIM INFERENCE THREAD READY",
  ]);

  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => {
      const messages = [
        "SYNAPSE RES: [AI Workshop <-> NVIDIA NIM] latency 8.2ms",
        "REDIS BUS: Dream session consolidator tick (12 nodes pruned)",
        "QDRANT: 1536d vector memory similarity search completed (0.94)",
        "NIM CORTEX: Llama 3.3 70B cognitive buffer refreshed",
        "AST LINTER: Claude Code auto-patch check nominal",
        "STARK HUD: Bio-telemetry link verified @ 120 FPS",
      ];
      const randomMsg = messages[Math.floor(Math.random() * messages.length)];
      const timestamp = new Date().toLocaleTimeString();
      setLogs((prev) => [`[${timestamp}] ${randomMsg}`, ...prev.slice(0, 4)]);
    }, 3200);

    return () => clearInterval(interval);
  }, [active]);

  useEffect(() => {
    if (selectedNode) {
      const timestamp = new Date().toLocaleTimeString();
      setLogs((prev) => [
        `[${timestamp}] FOCUS LOCK: '${selectedNode.id}' [Group: ${selectedNode.group}]`,
        ...prev.slice(0, 4),
      ]);
    }
  }, [selectedNode]);

  if (!active) return null;

  return (
    <div className="fixed bottom-4 left-84 z-20 pointer-events-none p-3 rounded-xl glass-panel-subtle border border-cyan-500/20 max-w-md select-none text-[10px] font-mono shadow-2xl">
      <div className="flex items-center justify-between text-cyan-400 mb-1.5 pb-1 border-b border-cyan-500/20">
        <span className="flex items-center gap-1 font-semibold tracking-wider">
          <Terminal className="w-3 h-3" />
          SYSTEM WATCH MONITOR
        </span>
        <span className="text-[9px] text-emerald-400 flex items-center gap-1">
          <Shield className="w-2.5 h-2.5" /> STREAMING
        </span>
      </div>
      <div className="space-y-1 text-slate-400">
        {logs.map((log, i) => (
          <div key={i} className="truncate leading-tight font-mono">
            {log}
          </div>
        ))}
      </div>
    </div>
  );
};
