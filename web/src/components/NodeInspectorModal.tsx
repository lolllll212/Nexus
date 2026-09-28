import React from 'react';
import { X, Cpu, Globe, Search, Copy, Check, Share2, Sparkles, Network } from 'lucide-react';
import { GraphNode } from '../types';
import { playHudClick, playChime } from '../utils/soundEffects';

interface NodeInspectorModalProps {
  node: GraphNode | null;
  onClose: () => void;
  onAskJarvis: (prompt: string) => void;
  onDeepResearch: (query: string) => void;
}

export const NodeInspectorModal: React.FC<NodeInspectorModalProps> = ({
  node,
  onClose,
  onAskJarvis,
  onDeepResearch,
}) => {
  const [copied, setCopied] = React.useState(false);

  if (!node) return null;

  const handleCopy = () => {
    playHudClick();
    navigator.clipboard.writeText(JSON.stringify(node, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleAsk = () => {
    playChime();
    onAskJarvis(`Provide an architectural and semantic analysis of the Second Brain node: "${node.label}" (Group: ${node.group}, ID: ${node.id}). How does it correlate with other cognitive clusters?`);
    onClose();
  };

  const handleResearch = () => {
    playChime();
    onDeepResearch(node.label);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-lg bg-[#030914] border border-cyan-500/40 rounded-2xl shadow-[0_0_40px_rgba(0,240,255,0.25)] flex flex-col overflow-hidden text-cyan-100">
        {/* Glow Header */}
        <div className="px-5 py-4 border-b border-cyan-500/20 bg-slate-900/60 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div
              className="w-3.5 h-3.5 rounded-full shadow-[0_0_10px_currentColor] animate-pulse"
              style={{
                backgroundColor: node.color || '#00f0ff',
                color: node.color || '#00f0ff',
              }}
            />
            <div>
              <div className="text-[10px] font-mono tracking-widest text-cyan-400 uppercase font-semibold">
                SECOND BRAIN // CONCEPT INSPECTOR
              </div>
              <h3 className="text-sm font-bold font-mono text-white truncate max-w-sm">
                {node.label}
              </h3>
            </div>
          </div>
          <button
            onClick={() => {
              playHudClick();
              onClose();
            }}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-4 text-xs font-mono max-h-[70vh] overflow-y-auto">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-2.5 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
            <div>
              <span className="text-[10px] text-slate-400 uppercase">Node ID</span>
              <p className="text-cyan-200 font-semibold truncate">{node.id}</p>
            </div>
            <div>
              <span className="text-[10px] text-slate-400 uppercase">Category Group</span>
              <p className="text-yellow-300 font-semibold uppercase">{node.group}</p>
            </div>
            <div>
              <span className="text-[10px] text-slate-400 uppercase">Synaptic Weight</span>
              <p className="text-teal-300 font-semibold">{(node.val || 10).toFixed(1)} / 100.0</p>
            </div>
            <div>
              <span className="text-[10px] text-slate-400 uppercase">Status</span>
              <p className="text-emerald-400 font-semibold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                ACTIVE ENTITY
              </p>
            </div>
          </div>

          {/* Description / Summary */}
          <div className="p-3 bg-cyan-950/20 border border-cyan-500/20 rounded-xl space-y-1">
            <span className="text-[10px] text-cyan-400 uppercase font-semibold tracking-wider flex items-center gap-1">
              <Network className="w-3 h-3" />
              Cognitive Context
            </span>
            <p className="text-slate-300 text-[11px] leading-relaxed">
              This entity represents an active neural node within the Second Brain knowledge topology. It forms associative synapses across episodic vector memories and automated agent pipelines.
            </p>
          </div>

          {/* Actions */}
          <div className="pt-2 flex flex-col sm:flex-row gap-2">
            <button
              onClick={handleAsk}
              className="flex-1 py-2.5 px-3 rounded-xl bg-gradient-to-r from-cyan-600 to-teal-500 hover:from-cyan-500 hover:to-teal-400 text-black font-semibold text-xs flex items-center justify-center gap-1.5 shadow-[0_0_15px_rgba(0,240,255,0.3)] transition-all cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Query J.A.R.V.I.S.</span>
            </button>

            <button
              onClick={handleResearch}
              className="flex-1 py-2.5 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-cyan-500/30 text-cyan-200 text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer"
            >
              <Globe className="w-3.5 h-3.5 text-cyan-400" />
              <span>Deep Research</span>
            </button>

            <button
              onClick={handleCopy}
              className="py-2.5 px-3 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700 text-slate-300 text-xs flex items-center justify-center gap-1 transition-all cursor-pointer"
              title="Copy JSON Payload"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
