import React from 'react';
import { 
  NexusNode, 
  NodeCategory 
} from '../types';
import { CATEGORY_STYLES } from '../data/nexusGraphData';
import { 
  X, 
  Search, 
  Share2, 
  Zap, 
  Terminal, 
  ExternalLink, 
  ShieldCheck, 
  Clock, 
  Database, 
  Cpu, 
  FileText, 
  Layers, 
  Activity,
  CheckCircle2,
  AlertTriangle,
  Play
} from 'lucide-react';

interface ContextInspectorProps {
  selectedNode: NexusNode | null;
  onClose: () => void;
  onOpenResearchMode: (topic?: string) => void;
  onOpenWorkflowMode: (workflowId?: string) => void;
  onOpenClaudeStudio: (codeSnippet?: string) => void;
}

export const ContextInspector: React.FC<ContextInspectorProps> = ({
  selectedNode,
  onClose,
  onOpenResearchMode,
  onOpenWorkflowMode,
  onOpenClaudeStudio,
}) => {
  if (!selectedNode) {
    return (
      <aside className="w-80 h-full border-l border-cyan-500/10 bg-slate-950/80 backdrop-blur-xl flex flex-col justify-center items-center text-center p-6 text-slate-500 font-mono">
        <Layers className="w-10 h-10 text-slate-700 mb-3 animate-pulse" />
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">
          CONTEXTUAL INSPECTOR
        </h3>
        <p className="text-[11px] text-slate-600 max-w-xs leading-relaxed">
          Select any node in the knowledge universe to inspect its deep research provenance, autonomous workflow traces, or memory synapses.
        </p>
      </aside>
    );
  }

  const style = CATEGORY_STYLES[selectedNode.category] || CATEGORY_STYLES.CONCEPT;

  return (
    <aside className="w-88 h-full border-l border-cyan-500/20 bg-slate-950/90 backdrop-blur-xl flex flex-col text-slate-200 font-mono shadow-2xl overflow-y-auto">
      {/* ── Inspector Header ─────────────────────────────────────────────────── */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="text-[9px] font-bold px-2 py-0.5 rounded-full uppercase"
            style={{
              backgroundColor: `${style.color}20`,
              color: style.color,
              border: `1px solid ${style.color}50`,
            }}
          >
            {selectedNode.category}
          </span>
          <span className="text-[10px] text-emerald-400 font-bold">
            {selectedNode.confidence}% CONF
          </span>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer"
          title="Close Inspector"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-5 space-y-5 flex-1">
        {/* Node Title & Importance Meter */}
        <div>
          <h2 className="text-sm font-bold text-white font-mono leading-snug mb-1.5">
            {selectedNode.name}
          </h2>
          <p className="text-[11px] text-slate-400 leading-relaxed font-sans">
            {selectedNode.description}
          </p>
        </div>

        {/* Confidence & Importance Gauges */}
        <div className="grid grid-cols-2 gap-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-[10px]">
          <div>
            <span className="text-slate-500 uppercase block mb-1">IMPORTANCE</span>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-cyan-400"
                  style={{ width: `${selectedNode.importance}%` }}
                ></div>
              </div>
              <span className="font-bold text-cyan-300">{selectedNode.importance}/100</span>
            </div>
          </div>

          <div>
            <span className="text-slate-500 uppercase block mb-1">CONFIDENCE</span>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-emerald-400"
                  style={{ width: `${selectedNode.confidence}%` }}
                ></div>
              </div>
              <span className="font-bold text-emerald-300">{selectedNode.confidence}%</span>
            </div>
          </div>
        </div>

        {/* ── Category-Specific Dynamic Panels ───────────────────────────────── */}
        {selectedNode.category === 'RESEARCH' && (
          <div className="space-y-3 p-3.5 rounded-2xl bg-cyan-950/20 border border-cyan-500/30">
            <span className="text-[10px] font-bold text-cyan-300 uppercase block flex items-center gap-1.5">
              <Search className="w-3.5 h-3.5 text-cyan-400" />
              <span>Deep Research Inspection</span>
            </span>
            <div className="text-[10px] space-y-1.5 text-slate-300">
              <div><span className="text-slate-500">QUESTION: </span>{selectedNode.name}</div>
              <div><span className="text-slate-500">PROVENANCE: </span>{selectedNode.source || 'ArXiv & IEEE'}</div>
              <div><span className="text-slate-500">EVIDENCE STATUS: </span><span className="text-emerald-400">Verified Consensus</span></div>
            </div>
            <button
              onClick={() => onOpenResearchMode(selectedNode.name)}
              className="w-full mt-2 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs transition-all cursor-pointer flex items-center justify-center gap-1.5"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Open in Research Map</span>
            </button>
          </div>
        )}

        {selectedNode.category === 'WORKFLOW' && (
          <div className="space-y-3 p-3.5 rounded-2xl bg-emerald-950/20 border border-emerald-500/30">
            <span className="text-[10px] font-bold text-emerald-300 uppercase block flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-emerald-400" />
              <span>Autonomous Workflow Inspection</span>
            </span>
            <div className="text-[10px] space-y-1.5 text-slate-300">
              <div><span className="text-slate-500">TRIGGER: </span>GitHub Webhook Push</div>
              <div><span className="text-slate-500">STEPS: </span>5 automated stages</div>
              <div><span className="text-slate-500">EXECUTION: </span><span className="text-emerald-400">Active nominal</span></div>
            </div>
            <button
              onClick={() => onOpenWorkflowMode(selectedNode.id)}
              className="w-full mt-2 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-black font-semibold text-xs transition-all cursor-pointer flex items-center justify-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5 fill-black" />
              <span>Open Workflow Canvas</span>
            </button>
          </div>
        )}

        {selectedNode.category === 'MEMORY' && (
          <div className="space-y-3 p-3.5 rounded-2xl bg-pink-950/20 border border-pink-500/30">
            <span className="text-[10px] font-bold text-pink-300 uppercase block flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-pink-400" />
              <span>Cognitive Memory Synapse</span>
            </span>
            <div className="text-[10px] space-y-1.5 text-slate-300">
              <div><span className="text-slate-500">MEMORY TYPE: </span>Episodic Recall</div>
              <div><span className="text-slate-500">EMBEDDING CLUSTER: </span>HNSW Partition #4</div>
              <div><span className="text-slate-500">LAST CONSOLIDATED: </span>{selectedNode.lastUpdated}</div>
            </div>
          </div>
        )}

        {selectedNode.category === 'CODE' && (
          <div className="space-y-3 p-3.5 rounded-2xl bg-amber-950/20 border border-amber-500/30">
            <span className="text-[10px] font-bold text-amber-300 uppercase block flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5 text-amber-400" />
              <span>Sandbox Code Execution</span>
            </span>
            <div className="text-[10px] space-y-1.5 text-slate-300">
              <div><span className="text-slate-500">SECURITY GATE: </span>Approval Required</div>
              <div><span className="text-slate-500">CONTAINER: </span>Docker Sandbox Isolated</div>
            </div>
            <button
              onClick={() => onOpenClaudeStudio()}
              className="w-full mt-2 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-semibold text-xs transition-all cursor-pointer flex items-center justify-center gap-1.5"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Launch in Claude Studio</span>
            </button>
          </div>
        )}

        {/* Tags Array */}
        {selectedNode.tags && selectedNode.tags.length > 0 && (
          <div>
            <span className="text-[9px] text-slate-500 uppercase block mb-2">METADATA TAGS</span>
            <div className="flex flex-wrap gap-1.5">
              {selectedNode.tags.map((t) => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded-md text-[9px] bg-slate-900 border border-slate-800 text-slate-300"
                >
                  #{t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* System Source & Timestamp */}
        <div className="pt-4 border-t border-slate-800 text-[10px] text-slate-500 space-y-1">
          <div><span className="text-slate-600">ID: </span><span className="text-slate-400">{selectedNode.id}</span></div>
          <div><span className="text-slate-600">SOURCE: </span><span className="text-slate-400">{selectedNode.source || 'Local Brain'}</span></div>
          <div><span className="text-slate-600">LAST UPDATED: </span><span className="text-slate-400">{selectedNode.lastUpdated || 'Recently'}</span></div>
        </div>
      </div>
    </aside>
  );
};
