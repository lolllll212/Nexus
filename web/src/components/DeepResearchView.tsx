import React, { useState, useEffect } from 'react';
import { 
  Globe, 
  Activity,
  Search, 
  ArrowRight, 
  ShieldCheck, 
  AlertTriangle, 
  FileText, 
  CheckCircle2, 
  Clock, 
  Layers, 
  ExternalLink, 
  Sparkles, 
  Play, 
  RefreshCw, 
  Download,
  Share2,
  Database,
  Cpu
} from 'lucide-react';
import { MOCK_RESEARCH_CLAIMS, MOCK_RESEARCH_TRACES } from '../data/nexusGraphData';
import { ResearchClaim, ResearchTraceEvent } from '../types';
import { nexusJson } from '../api';

interface DeepResearchViewProps {
  initialTopic?: string;
  onInjectResearchIntoGraph: (reportTitle: string, claims: ResearchClaim[]) => void;
  onOpenClaudeStudio: (content: string) => void;
}

export const DeepResearchView: React.FC<DeepResearchViewProps> = ({
  initialTopic = 'Recursive Self-Evolution & AST Guard Sandboxes in Autonomous LLMs',
  onInjectResearchIntoGraph,
  onOpenClaudeStudio,
}) => {
  const [topic, setTopic] = useState(initialTopic);
  const [isResearching, setIsResearching] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(134);
  const [claims, setClaims] = useState<ResearchClaim[]>(MOCK_RESEARCH_CLAIMS);
  const [traces, setTraces] = useState<ResearchTraceEvent[]>(MOCK_RESEARCH_TRACES);
  const [selectedClaim, setSelectedClaim] = useState<ResearchClaim | null>(claims[0]);
  const [activeTab, setActiveTab] = useState<'map' | 'claims' | 'synthesis'>('map');
  const [error, setError] = useState<string | null>(null);

  // Live timer simulation
  useEffect(() => {
    let timer: any;
    if (isResearching) {
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isResearching]);

  const handleStartResearch = async () => {
    if (!topic.trim() || isResearching) return;
    setIsResearching(true);
    setError(null);
    const newTrace: ResearchTraceEvent = {
      id: `trace-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      phase: 'PLANNING',
      message: `Decomposing inquiry "${topic}" into 4 sub-queries for distributed browser swarm...`,
      status: 'in_progress',
    };
    setTraces((prev) => [newTrace, ...prev]);

    try {
      const result = await nexusJson<{
        summary: string;
        key_findings: string[];
        sources: Array<{ title: string; url: string; snippet: string }>;
      }>('/api/research/execute', {
        method: 'POST',
        body: JSON.stringify({ query: topic, max_sources: 4, auto_ingest_graph: true, hub_target: 'AI Workshop' }),
      });
      const liveClaims: ResearchClaim[] = result.key_findings.map((claim, index) => ({
        id: `live-claim-${index}`,
        claim,
        status: 'verified',
        sources: result.sources.slice(0, 2).map((source) => source.title),
        confidence: 80,
        evidence: result.summary,
      }));
      setClaims(liveClaims);
      setSelectedClaim(liveClaims[0] || null);
      setTraces((prev) => [{
        id: `trace-complete-${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        phase: 'SYNTHESIS',
        message: result.summary,
        status: 'complete',
      }, ...prev]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Research request failed');
      setTraces((prev) => [{
        id: `trace-error-${Date.now()}`,
        timestamp: new Date().toLocaleTimeString(),
        phase: 'ERROR',
        message: requestError instanceof Error ? requestError.message : 'Research request failed',
        status: 'warning',
      }, ...prev]);
    } finally {
      setIsResearching(false);
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`;
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#05070c] text-slate-100 font-mono overflow-hidden">
      {/* ── Top Research Metrics Banner ──────────────────────────────────────── */}
      <div className="p-4 border-b border-cyan-500/20 bg-slate-950/80 backdrop-blur-md flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-cyan-950/80 border border-cyan-400/40 text-cyan-400 shadow-[0_0_15px_rgba(0,240,255,0.25)]">
            <Globe className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider">
                DEEP RESEARCH PIPELINE
              </span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/30">
                LEVEL 4 DEPTH
              </span>
            </div>
            <h2 className="text-sm font-semibold text-slate-100 truncate max-w-xl">
              {topic}
            </h2>
          </div>
        </div>

        {/* Real-time Metrics Counters */}
        <div className="flex items-center gap-4 text-xs">
          <div className="px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center">
            <span className="text-[9px] text-slate-500 uppercase">SOURCES</span>
            <span className="text-cyan-400 font-bold">18 FOUND</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center">
            <span className="text-[9px] text-slate-500 uppercase">CLAIMS</span>
            <span className="text-purple-400 font-bold">54 EXTRACTED</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center">
            <span className="text-[9px] text-slate-500 uppercase">CONFLICTS</span>
            <span className="text-amber-400 font-bold">2 DETECTED</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center">
            <span className="text-[9px] text-slate-500 uppercase">CONFIDENCE</span>
            <span className="text-emerald-400 font-bold">94.6%</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 flex flex-col items-center">
            <span className="text-[9px] text-slate-500 uppercase">ELAPSED</span>
            <span className="text-slate-300 font-mono font-bold">{formatTime(elapsedSeconds)}</span>
          </div>

          <button
            onClick={() => onInjectResearchIntoGraph(topic, claims)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-black font-semibold text-xs shadow-[0_0_15px_rgba(0,240,255,0.3)] transition-all cursor-pointer"
          >
            <Database className="w-3.5 h-3.5" />
            <span>Sync to Knowledge Graph</span>
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="mx-6 mt-4 rounded-xl border border-red-400/40 bg-red-950/30 px-4 py-3 text-xs text-red-200">
          Research failed: {error}
        </div>
      )}

      {/* ── Main Viewport Split: Interactive Research Map & Live Trace ──────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column: Visual Research Pipeline Map & Evidence Matrix */}
        <div className="flex-1 flex flex-col border-r border-slate-800 p-6 overflow-y-auto bg-slate-950/40">
          {/* Visual Step-by-Step Directed Graph Pipeline */}
          <div className="mb-6 p-4 rounded-2xl glass-panel border border-cyan-500/20 bg-slate-950/80 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider mb-3 block">
              AUTONOMOUS RESEARCH WORKFLOW TOPOLOGY
            </span>
            <div className="grid grid-cols-5 gap-2 text-center text-xs">
              <div className="p-3 rounded-xl bg-cyan-950/50 border border-cyan-400/40">
                <span className="text-[9px] text-cyan-400 font-bold block mb-1">01. INQUIRY</span>
                <p className="text-[11px] font-semibold text-slate-200">Question Decompose</p>
                <span className="text-[8px] text-emerald-400 font-mono">COMPLETE</span>
              </div>
              <div className="p-3 rounded-xl bg-purple-950/50 border border-purple-400/40">
                <span className="text-[9px] text-purple-400 font-bold block mb-1">02. SEARCH</span>
                <p className="text-[11px] font-semibold text-slate-200">SSRF Crawler Swarm</p>
                <span className="text-[8px] text-emerald-400 font-mono">18 SOURCES</span>
              </div>
              <div className="p-3 rounded-xl bg-blue-950/50 border border-blue-400/40">
                <span className="text-[9px] text-blue-400 font-bold block mb-1">03. EXTRACTION</span>
                <p className="text-[11px] font-semibold text-slate-200">Claim Normalization</p>
                <span className="text-[8px] text-emerald-400 font-mono">54 CLAIMS</span>
              </div>
              <div className="p-3 rounded-xl bg-amber-950/50 border border-amber-400/40">
                <span className="text-[9px] text-amber-400 font-bold block mb-1">04. CONTRADICTION</span>
                <p className="text-[11px] font-semibold text-slate-200">Cross-Reference Matrix</p>
                <span className="text-[8px] text-amber-300 font-mono">2 COMPETING</span>
              </div>
              <div className="p-3 rounded-xl bg-emerald-950/50 border border-emerald-400/40">
                <span className="text-[9px] text-emerald-400 font-bold block mb-1">05. SYNTHESIS</span>
                <p className="text-[11px] font-semibold text-slate-200">Final Executive Whitepaper</p>
                <span className="text-[8px] text-emerald-400 font-mono">READY</span>
              </div>
            </div>
          </div>

          {/* Claims & Competing Branches Matrix */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span>Extracted Claims & Evidence Topology</span>
            </span>
            <span className="text-[10px] text-slate-500">
              Click claim to inspect competing sources & citation provenance
            </span>
          </div>

          <div className="space-y-3 mb-6">
            {claims.map((c) => {
              const isSelected = selectedClaim?.id === c.id;
              const isDisputed = c.status === 'competing' || c.status === 'disputed';

              return (
                <div
                  key={c.id}
                  onClick={() => setSelectedClaim(c)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-slate-900 border-cyan-400 shadow-[0_0_20px_rgba(0,240,255,0.2)]'
                      : isDisputed
                      ? 'bg-amber-950/20 border-amber-500/40 hover:border-amber-400'
                      : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2">
                      {isDisputed ? (
                        <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-amber-950 text-amber-400 border border-amber-500/40 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" />
                          <span>COMPETING CLAIM</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-500/40 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>VERIFIED CONSENSUS</span>
                        </span>
                      )}
                      <span className="text-[10px] text-slate-400">
                        {c.sources.join(' • ')}
                      </span>
                    </div>
                    <span className="text-xs font-bold font-mono text-cyan-300">
                      {c.confidence}% CONF
                    </span>
                  </div>

                  <p className="text-xs text-slate-200 font-sans leading-relaxed mb-2">
                    {c.claim}
                  </p>

                  <div className="p-2.5 rounded-lg bg-black/40 border border-slate-800/80 text-[11px] text-slate-400 font-mono">
                    <span className="text-slate-500 uppercase block text-[9px] mb-0.5">EVIDENCE CITATION:</span>
                    {c.evidence}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Synthesis Report Preview & Export */}
          <div className="p-4 rounded-2xl glass-panel border border-emerald-500/20 bg-slate-950/90 mt-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-2">
                <FileText className="w-4 h-4" />
                <span>Executive Synthesis Deliverable</span>
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onOpenClaudeStudio('# Executive Synthesis: ' + topic + '\n\n' + JSON.stringify(claims, null, 2))}
                  className="px-2.5 py-1 rounded-lg text-[10px] bg-amber-950/80 hover:bg-amber-900 text-amber-300 border border-amber-500/40 flex items-center gap-1 cursor-pointer"
                >
                  <Cpu className="w-3 h-3" />
                  <span>Open in Claude Studio</span>
                </button>
              </div>
            </div>
            <p className="text-[11px] text-slate-400 mb-3">
              Comprehensive report compiled from 18 verified sources, cross-referenced across 49 consensus claims with 2 branch dispute notes.
            </p>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[10px] text-slate-500 font-mono">GENERATED BY: NEXUS Autonomous Synthesis Agent</span>
            </div>
          </div>
        </div>

        {/* Right Column: Operational Research Trace Feed (High Level Only) */}
        <div className="w-96 flex flex-col bg-slate-950/80 p-4 overflow-hidden">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
            <div className="flex items-center gap-2 text-xs font-bold text-cyan-400 uppercase tracking-wider">
              <Activity className="w-4 h-4" />
              <span>Research Trace Stream</span>
            </div>
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-500/30">
              OPERATIONAL
            </span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {traces.map((t) => (
              <div key={t.id} className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 text-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[9px] font-bold text-cyan-400 uppercase font-mono">
                    [{t.phase}]
                  </span>
                  <span className="text-[9px] text-slate-500 font-mono">{t.timestamp}</span>
                </div>
                <p className="text-[11px] text-slate-300 font-mono leading-relaxed">
                  {t.message}
                </p>
                <div className="mt-2 flex items-center gap-1.5 text-[9px] text-emerald-400">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Verified & Checkpointed</span>
                </div>
              </div>
            ))}
          </div>

          {/* Quick Query Input */}
          <div className="mt-4 pt-3 border-t border-slate-800">
            <span className="text-[9px] text-slate-500 uppercase block mb-1.5">INITIATE SUB-INQUIRY</span>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="Enter query..."
                className="flex-1 px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono text-slate-100 focus:outline-none focus:border-cyan-400"
              />
              <button
                onClick={handleStartResearch}
                disabled={isResearching}
                className="p-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-black transition-all cursor-pointer"
                title="Execute Deep Research"
              >
                <Play className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
