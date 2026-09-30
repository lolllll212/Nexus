import React, { useState } from 'react';
import { X, Layers, Plus, Sparkles, CheckCircle2, Trash2 } from 'lucide-react';

interface CanvasBuilderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddNodeToGraph?: (title: string, category: string, summary: string) => void;
}

export const CanvasBuilderModal: React.FC<CanvasBuilderModalProps> = ({
  isOpen,
  onClose,
  onAddNodeToGraph,
}) => {
  if (!isOpen) return null;

  const [nodeTitle, setNodeTitle] = useState('');
  const [nodeCategory, setNodeCategory] = useState('CONCEPT');
  const [nodeDescription, setNodeDescription] = useState('');
  const [elements, setElements] = useState([
    { id: '1', title: 'Multimodal Perception Engine', cat: 'AI_MODEL' },
    { id: '2', title: 'Arc Reactor Centerpiece Orb', cat: 'UI_COMPONENT' },
    { id: '3', title: 'Flanking HUD Telemetry Matrix', cat: 'TELEMETRY' },
  ]);

  const handleAdd = () => {
    if (!nodeTitle.trim()) return;
    const newEl = { id: Date.now().toString(), title: nodeTitle.trim(), cat: nodeCategory };
    setElements([...elements, newEl]);
    if (onAddNodeToGraph) {
      onAddNodeToGraph(nodeTitle.trim(), nodeCategory, nodeDescription || 'Contextual Canvas Element');
    }
    setNodeTitle('');
    setNodeDescription('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl animate-fade-in select-none">
      <div className="relative w-full max-w-xl glass-obsidian rounded-3xl border border-[#00f0ff]/30 shadow-[0_0_40px_rgba(0,240,255,0.2)] p-6 font-mono text-slate-200">
        <div className="flex items-center justify-between pb-3 border-b border-[#00f0ff]/20 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-purple-500/20 border border-purple-400/40 flex items-center justify-center text-purple-300">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-white tracking-widest uppercase">CONTEXTUAL CANVAS BUILDER</h3>
              <p className="text-[9px] text-purple-300/80">Draft nodes & inject them into the Second Brain Cosmos</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <label className="text-[9px] text-slate-400 uppercase tracking-widest block mb-1">NODE TITLE</label>
            <input
              type="text"
              value={nodeTitle}
              onChange={(e) => setNodeTitle(e.target.value)}
              placeholder="e.g. Non-Vision LLM Decomposition Schema"
              className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-purple-400"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[9px] text-slate-400 uppercase tracking-widest block mb-1">CATEGORY</label>
              <select
                value={nodeCategory}
                onChange={(e) => setNodeCategory(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-purple-300 focus:outline-none focus:border-purple-400"
              >
                <option value="CONCEPT">CONCEPT</option>
                <option value="AI_MODEL">AI_MODEL</option>
                <option value="UI_COMPONENT">UI_COMPONENT</option>
                <option value="TELEMETRY">TELEMETRY</option>
                <option value="WORKFLOW">WORKFLOW</option>
              </select>
            </div>

            <div>
              <label className="text-[9px] text-slate-400 uppercase tracking-widest block mb-1">DESCRIPTION</label>
              <input
                type="text"
                value={nodeDescription}
                onChange={(e) => setNodeDescription(e.target.value)}
                placeholder="Optional summary..."
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-purple-400"
              />
            </div>
          </div>

          <button
            onClick={handleAdd}
            className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 cursor-pointer transition-all shadow-[0_0_15px_rgba(168,85,247,0.3)]"
          >
            <Plus className="w-4 h-4" />
            <span>ADD & SYNC TO GRAPH</span>
          </button>

          <div className="pt-2 border-t border-slate-800/80">
            <span className="text-[9px] text-slate-400 uppercase tracking-widest block mb-2 font-semibold">ACTIVE CANVAS NODES:</span>
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {elements.map((el) => (
                <div key={el.id} className="p-2 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between text-[10px]">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-purple-400 shadow-[0_0_6px_#c084fc]" />
                    <span className="font-semibold text-white">{el.title}</span>
                  </div>
                  <span className="px-1.5 py-0.5 rounded-md bg-purple-950/80 text-[8.5px] text-purple-300 border border-purple-500/30">
                    {el.cat}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
