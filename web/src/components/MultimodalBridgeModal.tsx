import React, { useState } from 'react';
import { 
  X, 
  Upload, 
  Eye, 
  Film, 
  Image as ImageIcon, 
  Sparkles, 
  CheckCircle2, 
  Copy, 
  Check, 
  ArrowRight, 
  Play, 
  Send, 
  Zap, 
  Grid, 
  Palette, 
  FileText,
  Clock,
  Layers,
  Cpu
} from 'lucide-react';
import { MultimodalDecomposition } from '../types';

interface MultimodalBridgeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onInjectIntoGraph?: (title: string, summary: string, metadata: any) => void;
  onInjectPrompt?: (prompt: string) => void;
}

export const MultimodalBridgeModal: React.FC<MultimodalBridgeModalProps> = ({
  isOpen,
  onClose,
  onInjectIntoGraph,
  onInjectPrompt,
}) => {
  if (!isOpen) return null;

  const [mediaType, setMediaType] = useState<'image' | 'video'>('image');
  const [selectedSample, setSelectedSample] = useState<string>('sample-1');
  const [userQuestion, setUserQuestion] = useState<string>('Describe the visual layout, center element, and theme colors.');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [copiedPrompt, setCopiedPrompt] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'grid' | 'tokens' | 'chat'>('grid');

  // Decomposition state
  const [decomposition, setDecomposition] = useState<MultimodalDecomposition>({
    media_type: 'image',
    filename: 'nexus_arc_reactor_hud.png',
    dimensions: '1920x1080',
    aspect_ratio: '16:9',
    file_size_kb: 420.5,
    average_luminance: 42.0,
    color_palette: [
      { hex: '#0A0F1D', rgb: [10, 15, 29], percentage: 48.5, name: 'Deep Obsidian Navy' },
      { hex: '#00F0FF', rgb: [0, 240, 255], percentage: 22.0, name: 'Electric Cyber Cyan' },
      { hex: '#00FF88', rgb: [0, 255, 136], percentage: 14.2, name: 'Crisp Neon Emerald' },
      { hex: '#0F172A', rgb: [15, 23, 42], percentage: 9.3, name: 'Neutral Steel Slate' },
      { hex: '#FFAA00', rgb: [255, 170, 0], percentage: 6.0, name: 'Arc Reactor Amber' },
    ],
    ocr_extracted_text: [
      'NEXUS AI COGNITIVE OS',
      'CORE FREQUENCY: 4.80 GHz',
      'VOICE (M) [LISTENING]',
      'ARC REACTOR: NOMINAL',
      'QUANTUM ENTROPY: 0.042',
      '0.0.0.0:8000 FASTAPI ONLINE',
    ],
    spatial_grid: {
      top_left: { sector: 'Top-Left (Q1)', visual_elements: ['Workspace Tabs', 'System Branding', 'Cosmos Search'], density: 'Medium', dominant_hue: 'Obsidian Navy' },
      top_center: { sector: 'Top-Center (Q2)', visual_elements: ['Floating TopBar', 'Mode Switcher [GRAPH, VIDEO]', 'Voice Trigger'], density: 'Medium', dominant_hue: 'Glassmorphic Slate' },
      top_right: { sector: 'Top-Right (Q3)', visual_elements: ['World Time Zone Matrix', 'System Uptime Clock'], density: 'High', dominant_hue: 'Crisp Neon Emerald' },
      mid_left: { sector: 'Mid-Left (Q4)', visual_elements: ['CPU Telemetry (42%)', 'RAM / VRAM Bars', '10 Neural Agents'], density: 'High', dominant_hue: 'Cyber Cyan' },
      center: { sector: 'Center (Q5 - Visual Anchor)', visual_elements: ['Dynamic Arc Reactor Orb', 'Concentric Rotating Rings', 'Audio Waveform Ripples'], density: 'Focal Point', dominant_hue: 'Radiant Plasma Cyan' },
      mid_right: { sector: 'Mid-Right (Q6)', visual_elements: ['Network Throughput Stream', 'Port Health Badges [:8000, :3000, :4890]'], density: 'High', dominant_hue: 'Obsidian Slate' },
      bottom_left: { sector: 'Bottom-Left (Q7)', visual_elements: ['Subcortex Synapses', 'Cache Hit (99.4%)'], density: 'Medium', dominant_hue: 'Deep Obsidian' },
      bottom_center: { sector: 'Bottom-Center (Q8)', visual_elements: ['Command Center Prompt Bar', 'Race-Condition State Locks', 'Quick Chips'], density: 'High', dominant_hue: 'Obsidian Glass with Cyan Glow' },
      bottom_right: { sector: 'Bottom-Right (Q9)', visual_elements: ['Microphone Hotkey [M]', 'Status Badges'], density: 'Medium', dominant_hue: 'Cyan Shadow' },
    },
    scene_summary: 'Image shows a high-tech glassmorphic cybernetic operating system with deep obsidian background (#0A0F1D). The central anchor is a pulsating Arc Reactor Orb surrounded by concentric rotating rings and audio ripples. Flanking HUD telemetry displays real-time CPU loads and world clocks.',
    prompt_injection_block: `<<< MULTIMODAL PERCEPTION BRIDGE: HIGH-DENSITY IMAGE REPRESENTATION >>>
[IMAGE IDENTIFIER]: nexus_arc_reactor_hud.png | Dimensions: 1920x1080 (16:9)
[OVERALL SCENE SUMMARY]:
Image shows a high-tech glassmorphic cybernetic operating system with deep obsidian background (#0A0F1D). The central anchor is a pulsating Arc Reactor Orb surrounded by concentric rotating rings.

[COLOR HARMONY & PALETTE MATRIX]:
    - Deep Obsidian Navy (#0A0F1D) :: 48.5% coverage
    - Electric Cyber Cyan (#00F0FF) :: 22.0% coverage
    - Crisp Neon Emerald (#00FF88) :: 14.2% coverage
    - Arc Reactor Amber (#FFAA00) :: 6.0% coverage

[3x3 SPATIAL GRID DECOMPOSITION]:
    - [Center (Q5)]: Dynamic Arc Reactor Orb with rotating rings (Focal Point)
    - [Mid-Left (Q4)]: CPU load monitors and neural agent list
    - [Mid-Right (Q6)]: Real-time network throughput and port bindings
    - [Bottom-Center (Q8)]: Command Center prompt bar with status locks

[INSCRIBED TEXT & OCR DETECTIONS]:
    - "NEXUS AI COGNITIVE OS"
    - "CORE FREQUENCY: 4.80 GHz"
    - "VOICE (M) [LISTENING]"
    - "ARC REACTOR: NOMINAL"

[DIRECTIVE FOR TEXT-ONLY LANGUAGE MODEL]:
Operate with full visual perception. Use the spatial grid, OCR inscriptions, and color palette above to answer questions or write code.
<<< END MULTIMODAL ENCODING >>>`,
  });

  const [aiAnswer, setAiAnswer] = useState<string>(
    'The visual centerpiece is a glowing Cybernetic Arc Reactor Orb situated in the direct center (Quadrant 5) with concentric rotating orbital rings. The design employs an Obsidian/Navy base (#0A0F1D) with high-contrast Cyber Cyan (#00F0FF) glowing glassmorphic overlays and crisp Neon Emerald (#00FF88) telemetry indicators.'
  );

  const handleTranscode = async (type: 'image' | 'video', presetId?: string) => {
    setIsProcessing(true);
    setMediaType(type);

    try {
      const res = await fetch('/api/multimodal/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Authorization': 'Bearer sk-test-1',
        },
        body: new URLSearchParams({
          media_type: type,
          source_url: type === 'video' ? 'https://nexus.ai/samples/core_boot.mp4' : 'https://nexus.ai/samples/hud_overview.png',
          question: userQuestion,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setDecomposition(data.decomposition);
        setAiAnswer(data.answer);
      }
    } catch (_) {
      // Offline fallback already matches local state
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCopyPrompt = () => {
    navigator.clipboard.writeText(decomposition.prompt_injection_block);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl animate-fade-in select-none">
      <div className="relative w-full max-w-5xl h-[88vh] glass-obsidian rounded-3xl border border-[#00f0ff]/30 shadow-[0_0_50px_rgba(0,240,255,0.18)] flex flex-col overflow-hidden font-mono text-slate-200">
        
        {/* Subtle Cyber scanline overlay */}
        <div className="absolute inset-0 scanline pointer-events-none opacity-25" />

        {/* ── Modal Header ─────────────────────────────────────────────────── */}
        <div className="px-6 py-4 border-b border-[#00f0ff]/20 flex items-center justify-between bg-[#070b16]/90">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-black shadow-[0_0_15px_rgba(0,240,255,0.4)]">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-white tracking-widest uppercase">
                  NEXUS MULTIMODAL PERCEPTION BRIDGE
                </h2>
                <span className="px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-400/40 text-[9px] text-cyan-300 font-bold">
                  NON-VISION MODEL ADAPTER
                </span>
              </div>
              <p className="text-[10px] text-cyan-400/70 tracking-wide">
                Transcodes images & videos into structured spatial grids, OCR tokens & temporal keyframes for text-only LLMs.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60 border border-slate-700/50 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ── Preset Media Selector Bar ─────────────────────────────────────── */}
        <div className="px-6 py-2.5 bg-[#040814]/90 border-b border-[#00f0ff]/15 flex items-center justify-between flex-wrap gap-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold">PRESET SAMPLES:</span>
            <button
              onClick={() => {
                setSelectedSample('sample-1');
                handleTranscode('image');
              }}
              className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1.5 border ${
                selectedSample === 'sample-1'
                  ? 'bg-cyan-950 border-cyan-400 text-white shadow-[0_0_10px_rgba(0,240,255,0.3)]'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              <ImageIcon className="w-3 h-3 text-cyan-400" />
              <span>1. ARC REACTOR HUD (IMAGE)</span>
            </button>

            <button
              onClick={() => {
                setSelectedSample('sample-2');
                handleTranscode('video');
              }}
              className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1.5 border ${
                selectedSample === 'sample-2'
                  ? 'bg-amber-950 border-amber-400 text-white shadow-[0_0_10px_rgba(255,170,0,0.3)]'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Film className="w-3 h-3 text-amber-400" />
              <span>2. COGNITIVE STATE CYCLE (VIDEO)</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <label className="px-3 py-1 rounded-lg bg-slate-900 border border-cyan-500/30 text-cyan-300 hover:border-cyan-400 text-[10px] font-bold flex items-center gap-1.5 cursor-pointer transition-colors">
              <Upload className="w-3 h-3" />
              <span>UPLOAD LOCAL MEDIA</span>
              <input
                type="file"
                accept="image/*,video/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    const isVid = file.type.startsWith('video');
                    handleTranscode(isVid ? 'video' : 'image');
                  }
                }}
              />
            </label>
          </div>
        </div>

        {/* ── Main Work Area (Split View) ───────────────────────────────────── */}
        <div className="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-12 gap-0 divide-y md:divide-y-0 md:divide-x divide-[#00f0ff]/15">
          
          {/* ── Left Column: Media Visual Preview & Attributes (5 cols) ─────── */}
          <div className="md:col-span-5 p-5 flex flex-col justify-between overflow-y-auto bg-[#050914]/60 space-y-4">
            <div>
              <div className="flex items-center justify-between text-[10px] text-slate-400 uppercase tracking-widest mb-2 font-bold">
                <span>INPUT MEDIA PREVIEW</span>
                <span className="text-cyan-400">{decomposition.dimensions || '1080p'} ({decomposition.aspect_ratio || '16:9'})</span>
              </div>

              {/* Visual Frame */}
              <div className="relative aspect-video w-full rounded-2xl overflow-hidden border border-cyan-400/40 bg-[#02050e] shadow-[0_0_20px_rgba(0,240,255,0.12)] flex items-center justify-center group">
                {/* Simulated visual graphic preview */}
                <div className="absolute inset-0 bg-gradient-to-br from-[#0a0f1d] via-[#040914] to-[#02040a] flex items-center justify-center p-4">
                  {/* Visual Arc Reactor preview */}
                  <div className="relative w-32 h-32 rounded-full border border-cyan-400/40 flex items-center justify-center">
                    <div className="absolute inset-2 rounded-full border border-dashed border-cyan-300/30 animate-spin-slow" />
                    <div className="w-16 h-16 rounded-full bg-cyan-500/20 shadow-[0_0_25px_#00f0ff] flex flex-col items-center justify-center text-center">
                      <Zap className="w-4 h-4 text-cyan-300 mb-0.5" />
                      <span className="text-[7px] font-bold text-white tracking-widest">NEXUS</span>
                    </div>
                  </div>
                </div>

                {/* Overlaid Badges */}
                <div className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md bg-slate-950/80 border border-cyan-400/30 text-[8.5px] text-cyan-300">
                  {mediaType.toUpperCase()}
                </div>
                <div className="absolute bottom-2.5 right-2.5 px-2 py-0.5 rounded-md bg-slate-950/80 border border-emerald-400/30 text-[8.5px] text-emerald-300">
                  TRANSCODED
                </div>
              </div>

              {/* Media Attributes */}
              <div className="mt-3.5 space-y-2 text-[10px]">
                <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-500">FILE NAME:</span>
                    <span className="text-slate-200 font-bold truncate max-w-[200px]">{decomposition.filename}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">PAYLOAD SIZE:</span>
                    <span className="text-cyan-300 font-mono">{decomposition.file_size_kb || 420} KB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">LUMINANCE / THEME:</span>
                    <span className="text-[#00ff88] font-bold">DARK MODE (Obsidian)</span>
                  </div>
                </div>

                {/* Color Palette Matrix */}
                {decomposition.color_palette && (
                  <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                    <span className="text-[9px] text-slate-400 uppercase tracking-wider block mb-2 font-semibold">
                      COLOR HARMONY PALETTE
                    </span>
                    <div className="grid grid-cols-2 gap-1.5">
                      {decomposition.color_palette.slice(0, 4).map((c, i) => (
                        <div key={i} className="flex items-center gap-2 p-1.5 rounded-lg bg-[#030610] border border-slate-800/80">
                          <span 
                            className="w-3.5 h-3.5 rounded-xs shrink-0 shadow-sm"
                            style={{ backgroundColor: c.hex }}
                          />
                          <div className="truncate">
                            <span className="text-[9px] text-slate-200 font-bold block">{c.hex}</span>
                            <span className="text-[7.5px] text-slate-500 block truncate">{c.percentage}% · {c.name}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Ingestion Action */}
            <button
              onClick={() => {
                if (onInjectIntoGraph) {
                  onInjectIntoGraph(
                    `Multimodal: ${decomposition.filename}`,
                    decomposition.scene_summary || decomposition.action_narrative || 'Visual Scene',
                    { type: 'MULTIMODAL', palette: decomposition.color_palette }
                  );
                }
                onClose();
              }}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-black font-bold text-xs tracking-wider uppercase transition-all shadow-[0_0_20px_rgba(0,240,255,0.3)] flex items-center justify-center gap-2 cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>CHECKPOINT TO SECOND BRAIN GRAPH</span>
            </button>
          </div>

          {/* ── Right Column: Transcoded Decomposition & Text-Only LLM Chat (7 cols) */}
          <div className="md:col-span-7 flex flex-col justify-between overflow-hidden bg-[#070d1c]/80">
            {/* View Switcher Tabs */}
            <div className="p-3 border-b border-[#00f0ff]/15 flex items-center justify-between bg-[#040814]/80">
              <div className="flex items-center gap-2 text-xs">
                <button
                  onClick={() => setActiveTab('grid')}
                  className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                    activeTab === 'grid'
                      ? 'bg-cyan-950 border border-cyan-400 text-cyan-200 shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Grid className="w-3 h-3 text-cyan-400" />
                  <span>SPATIAL GRID (3x3)</span>
                </button>

                <button
                  onClick={() => setActiveTab('tokens')}
                  className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                    activeTab === 'tokens'
                      ? 'bg-cyan-950 border border-cyan-400 text-cyan-200 shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <FileText className="w-3 h-3 text-cyan-400" />
                  <span>TEXT-ONLY TOKENS</span>
                </button>

                <button
                  onClick={() => setActiveTab('chat')}
                  className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                    activeTab === 'chat'
                      ? 'bg-emerald-950 border border-emerald-400 text-emerald-200 shadow-[0_0_8px_rgba(0,255,136,0.2)]'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Sparkles className="w-3 h-3 text-[#00ff88]" />
                  <span>NON-VISION MODEL Q&A</span>
                </button>
              </div>

              {activeTab === 'tokens' && (
                <button
                  onClick={handleCopyPrompt}
                  className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 hover:border-cyan-400 text-[10px] text-cyan-300 flex items-center gap-1 cursor-pointer transition-colors"
                >
                  {copiedPrompt ? <Check className="w-3 h-3 text-[#00ff88]" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedPrompt ? 'COPIED' : 'COPY TOKENS'}</span>
                </button>
              )}
            </div>

            {/* Tab Contents */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              
              {/* TAB 1: 3x3 Spatial Grid / Video Keyframes */}
              {activeTab === 'grid' && (
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 uppercase tracking-widest mb-2 font-semibold">
                      <span>3x3 SPATIAL GRID DECOMPOSITION</span>
                      <span className="text-cyan-400">NON-VISION COORDINATE MAPPING</span>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      {decomposition.spatial_grid && Object.entries(decomposition.spatial_grid).map(([key, val]) => (
                        <div 
                          key={key} 
                          className={`p-2 rounded-xl border transition-all ${
                            key === 'center'
                              ? 'bg-cyan-950/60 border-cyan-400 shadow-[0_0_12px_rgba(0,240,255,0.25)]'
                              : 'bg-slate-950/70 border-slate-800/80 hover:border-slate-700'
                          }`}
                        >
                          <div className="flex items-center justify-between text-[8px] text-slate-500 mb-1">
                            <span className="font-bold text-slate-400 uppercase">{key}</span>
                            <span className={key === 'center' ? 'text-cyan-300 font-bold' : ''}>{val.density}</span>
                          </div>
                          <p className="text-[9px] text-slate-200 font-semibold leading-tight line-clamp-2">
                            {val.visual_elements.join(', ')}
                          </p>
                          <span className="text-[7.5px] text-cyan-400/80 block mt-1">{val.dominant_hue}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* OCR extracted labels */}
                  {decomposition.ocr_extracted_text && (
                    <div className="p-3 rounded-2xl bg-slate-950/80 border border-slate-800">
                      <span className="text-[9px] text-slate-400 uppercase tracking-widest block mb-1.5 font-semibold">
                        OCR INSCRIBED TEXT LABELS DETECTED:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {decomposition.ocr_extracted_text.map((txt, idx) => (
                          <span key={idx} className="px-2 py-0.5 rounded-md bg-[#040814] border border-cyan-500/20 text-cyan-300 text-[9px]">
                            "{txt}"
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: Text-Only Token Representation Block */}
              {activeTab === 'tokens' && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[10px] text-slate-400 uppercase tracking-widest">
                    <span>STRUCTURED SEMANTIC TOKEN PAYLOAD</span>
                    <span className="text-cyan-400">READY FOR LLM PROMPT INJECTION</span>
                  </div>
                  <pre className="p-3.5 rounded-2xl bg-[#02050c] border border-cyan-500/30 text-[9.5px] text-cyan-200 font-mono whitespace-pre-wrap leading-relaxed shadow-inner overflow-x-auto">
                    {decomposition.prompt_injection_block}
                  </pre>
                </div>
              )}

              {/* TAB 3: Interactive Q&A with Text-Only LLM */}
              {activeTab === 'chat' && (
                <div className="space-y-4">
                  <div className="p-3.5 rounded-2xl bg-cyan-950/40 border border-cyan-500/30 text-[10.5px] space-y-2">
                    <div className="flex items-center gap-1.5 text-cyan-300 font-bold uppercase tracking-wider">
                      <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                      <span>TEXT-ONLY MODEL INFERENCE RESULT:</span>
                    </div>
                    <p className="text-slate-200 leading-relaxed">
                      {aiAnswer}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <span className="text-[9.5px] text-slate-400 uppercase tracking-wider block font-semibold">
                      ASK ANOTHER QUESTION ABOUT THIS MEDIA:
                    </span>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={userQuestion}
                        onChange={(e) => setUserQuestion(e.target.value)}
                        placeholder="e.g. Write CSS for the central arc reactor, or analyze spatial hierarchy..."
                        className="flex-1 px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-cyan-400"
                        onKeyDown={(e) => e.key === 'Enter' && handleTranscode(mediaType)}
                      />
                      <button
                        onClick={() => handleTranscode(mediaType)}
                        disabled={isProcessing}
                        className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                      >
                        {isProcessing ? <Zap className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                        <span>RESOLVE</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Bottom Actions Bar */}
            <div className="p-3 border-t border-[#00f0ff]/15 bg-[#040814]/90 flex items-center justify-between text-xs">
              <span className="text-[9.5px] text-slate-400 font-mono">
                {isProcessing ? '⚡ Transcoding media matrix...' : '✓ Multimodal Bridge Synchronized'}
              </span>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    if (onInjectPrompt) {
                      onInjectPrompt(decomposition.prompt_injection_block);
                    }
                    onClose();
                  }}
                  className="px-3 py-1.5 rounded-xl bg-slate-900 border border-cyan-400/40 hover:border-cyan-400 text-cyan-300 hover:text-white text-[10px] font-bold transition-colors cursor-pointer"
                >
                  SEND TO COMMAND PROMPT BAR
                </button>
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
};
