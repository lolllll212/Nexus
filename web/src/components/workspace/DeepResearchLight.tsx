import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Telescope,
  Play,
  RefreshCw,
  Globe,
  Lightbulb,
  Layers,
  Clock,
  ChevronRight,
  Sparkles,
  History,
} from 'lucide-react';
import { nexusJson } from '../../api';
import { PageHeader, ViewShell, LiveChip, useLiveFetch } from './shared';

/* ────────────────────────────────────────────────────────────────────────────
 * Light Deep Research — the autonomous research lab.
 * Runs POST /api/research/execute with a staged execution timeline, renders
 * the full dossier (summary, findings, concepts, corroborated sources), and
 * keeps GET /api/research/history as a replayable archive.
 * ──────────────────────────────────────────────────────────────────────────── */

interface ResearchReport {
  query: string;
  summary: string;
  key_findings: string[];
  extracted_concepts: string[];
  sources: Array<{ title: string; url: string; snippet: string; key_takeaway?: string }>;
  nodes_added_to_graph: number;
  duration_seconds: number;
  status: string;
}

const STAGES = [
  'Decomposing the query',
  'Searching the web',
  'Browsing & extracting sources',
  'Corroborating claims',
  'Synthesising the dossier',
  'Ingesting into the knowledge graph',
];

const SUGGESTED_TOPICS = [
  'The state of autonomous agent frameworks',
  'Vector databases vs knowledge graphs for memory',
  'Latest breakthroughs in fusion energy',
  'How hexagonal architecture scales LLM systems',
];

export const DeepResearchLight: React.FC = () => {
  const history = useLiveFetch<ResearchReport[]>('/api/research/history');
  const [topic, setTopic] = useState('');
  const [running, setRunning] = useState(false);
  const [stageIndex, setStageIndex] = useState(-1);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reportRef = useRef<HTMLDivElement | null>(null);

  // Stage ticker while the backend researches
  useEffect(() => {
    if (!running) return;
    setStageIndex(0);
    const id = window.setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, STAGES.length - 1));
    }, 2000);
    return () => window.clearInterval(id);
  }, [running]);

  const runResearch = useCallback(
    async (query: string) => {
      const q = query.trim();
      if (!q || running) return;
      setRunning(true);
      setError(null);
      setReport(null);
      setTopic(q);
      try {
        const data = await nexusJson<ResearchReport>('/api/research/execute', {
          method: 'POST',
          body: JSON.stringify({ query: q, max_sources: 3 }),
        });
        setReport(data);
        history.reload();
        requestAnimationFrame(() => reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
      } catch (err: any) {
        setError(err?.message ?? 'Research execution failed.');
      } finally {
        setRunning(false);
        setStageIndex(-1);
      }
    },
    [running, history]
  );

  return (
    <ViewShell>
      <PageHeader
        route="RESEARCH"
        right={
          <LiveChip loading={history.loading} offline={!!history.error} label={history.error ? 'History offline' : 'Lab online'} />
        }
      />

      <div className="mt-6 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
        <div className="space-y-4">
          {/* Runner */}
          <div className="rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
            <label htmlFor="research-topic" className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">
              Research topic
            </label>
            <div className="mt-2.5 flex flex-col sm:flex-row gap-2.5">
              <input
                id="research-topic"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runResearch(topic)}
                placeholder="e.g. How do autonomous research agents verify claims?"
                className="flex-1 px-4 py-3 rounded-2xl bg-slate-50 border border-slate-200 text-[14px] text-slate-800 placeholder:text-slate-400 outline-none focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 transition-all"
              />
              <button
                onClick={() => runResearch(topic)}
                disabled={running || !topic.trim()}
                className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-2xl bg-violet-600 text-white text-[13.5px] font-bold hover:bg-violet-500 shadow-[0_10px_24px_-10px_rgba(139,92,246,0.6)] transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                {running ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Researching…
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" /> Run deep research
                  </>
                )}
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTED_TOPICS.map((t) => (
                <button
                  key={t}
                  disabled={running}
                  onClick={() => runResearch(t)}
                  className="px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[12px] font-medium text-slate-600 hover:border-violet-300 hover:text-violet-700 transition-all disabled:opacity-50 cursor-pointer"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Staged execution timeline */}
          {running && (
            <div className="rounded-3xl bg-white border border-violet-200/70 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(139,92,246,0.25)]">
              <div className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.16em] text-violet-600">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse" />
                Background execution stream
              </div>
              <ol className="mt-4 space-y-3">
                {STAGES.map((stage, i) => (
                  <li key={stage} className="flex items-center gap-3">
                    <span
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold border transition-all ${
                        i < stageIndex
                          ? 'bg-violet-600 border-violet-600 text-white'
                          : i === stageIndex
                            ? 'bg-white border-violet-400 text-violet-600 animate-pulse'
                            : 'bg-white border-slate-200 text-slate-300'
                      }`}
                    >
                      {i < stageIndex ? '✓' : i + 1}
                    </span>
                    <span className={`text-[13px] ${i <= stageIndex ? 'text-slate-800 font-semibold' : 'text-slate-400'}`}>
                      {stage}
                    </span>
                    {i === stageIndex && <span className="text-[11px] nxs-mono text-violet-500">running…</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {error && (
            <div className="rounded-3xl border border-rose-200 bg-rose-50 p-5 text-[13px] text-rose-700">{error}</div>
          )}

          {/* Report */}
          <div ref={reportRef}>
            {report ? (
              <ResearchReportCard report={report} />
            ) : (
              !running && (
                <div className="rounded-3xl bg-white border border-dashed border-slate-300 p-10 text-center">
                  <Telescope className="w-9 h-9 text-slate-300 mx-auto" />
                  <p className="mt-3 text-[14px] font-bold text-slate-700">No dossier yet</p>
                  <p className="mt-1.5 text-[12.5px] text-slate-400 max-w-md mx-auto leading-relaxed">
                    Enter a topic and the lab will crawl, corroborate and synthesise — every finding is ingested into the
                    knowledge graph as live nodes.
                  </p>
                </div>
              )
            )}
          </div>
        </div>

        {/* History */}
        <aside className="rounded-3xl bg-white border border-slate-200/80 p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.16em] text-slate-400">
              <History className="w-3.5 h-3.5" /> Research archive
            </h3>
            <button
              onClick={history.reload}
              className="w-7 h-7 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 cursor-pointer"
              aria-label="Refresh history"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="mt-3 space-y-2 max-h-[560px] overflow-y-auto nxs-scroll pr-1">
            {(history.data ?? []).length === 0 && (
              <p className="py-6 text-center text-[12px] text-slate-400 leading-relaxed">
                Past dossiers land here.<br />GET /api/research/history
              </p>
            )}
            {(history.data ?? []).map((h, i) => (
              <button
                key={`${h.query}-${i}`}
                onClick={() => {
                  setReport(h);
                  setTopic(h.query);
                }}
                className={`w-full text-left p-3.5 rounded-2xl border transition-all cursor-pointer ${
                  report?.query === h.query
                    ? 'border-violet-300 bg-violet-50/60'
                    : 'border-slate-200 bg-white hover:border-violet-200'
                }`}
              >
                <p className="text-[12.5px] font-bold text-slate-800 leading-snug line-clamp-2">{h.query}</p>
                <div className="mt-2 flex items-center gap-2 text-[10.5px] nxs-mono text-slate-400">
                  <Clock className="w-3 h-3" /> {h.duration_seconds?.toFixed(1)}s
                  <span className="text-slate-300">·</span> {h.sources?.length ?? 0} sources
                  <span className="text-slate-300">·</span> +{h.nodes_added_to_graph ?? 0} nodes
                </div>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </ViewShell>
  );
};

const ResearchReportCard: React.FC<{ report: ResearchReport }> = ({ report }) => (
  <section className="rounded-3xl bg-white border border-slate-200/80 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] animate-[nxs-rise_0.35s_cubic-bezier(0.22,1,0.36,1)]">
    <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-slate-100">
      <div className="flex items-center gap-3 min-w-0">
        <span className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 text-white flex items-center justify-center shrink-0">
          <Telescope className="w-4 h-4" />
        </span>
        <div className="min-w-0">
          <h3 className="text-[15px] font-bold text-slate-900 leading-tight">Research dossier</h3>
          <p className="text-[12px] text-slate-400 truncate mt-0.5">“{report.query}”</p>
        </div>
      </div>
      <span
        className={`shrink-0 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${
          report.status === 'completed' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-500'
        }`}
      >
        {report.status}
      </span>
    </div>

    <div className="p-6 space-y-6">
      <p className="text-[14px] leading-relaxed text-slate-700">{report.summary}</p>

      {report.key_findings?.length > 0 && (
        <div>
          <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2.5">
            <Lightbulb className="w-3.5 h-3.5 text-amber-500" /> Key findings
          </h4>
          <ul className="space-y-2">
            {report.key_findings.map((f, i) => (
              <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-slate-600">
                <span className="shrink-0 mt-[7px] w-1.5 h-1.5 rounded-full bg-amber-400" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.extracted_concepts?.length > 0 && (
        <div>
          <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2.5">
            <Layers className="w-3.5 h-3.5 text-cyan-600" /> Ingested concepts
          </h4>
          <div className="flex flex-wrap gap-2">
            {report.extracted_concepts.map((c) => (
              <span key={c} className="px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-[12px] font-medium text-cyan-800">
                ◈ {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {report.sources?.length > 0 && (
        <div>
          <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2.5">
            <Globe className="w-3.5 h-3.5 text-slate-400" /> Corroborated sources
          </h4>
          <div className="grid sm:grid-cols-2 gap-2.5">
            {report.sources.map((s, i) => (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="group rounded-2xl border border-slate-200 hover:border-violet-300 hover:shadow-[0_8px_20px_-8px_rgba(139,92,246,0.3)] transition-all p-3.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[13px] font-semibold text-slate-800 leading-snug line-clamp-2">{s.title}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 group-hover:text-violet-500 shrink-0 mt-0.5" />
                </div>
                <p className="mt-1.5 text-[12px] text-slate-500 line-clamp-2">{s.snippet}</p>
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-[11px] font-medium text-slate-600">
          <Clock className="w-3 h-3 text-slate-400" /> {report.duration_seconds?.toFixed(1)}s execution
        </span>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-[11px] font-medium text-slate-600">
          <Layers className="w-3 h-3 text-slate-400" /> +{report.nodes_added_to_graph} graph nodes
        </span>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-[11px] font-medium text-slate-600">
          <Sparkles className="w-3 h-3 text-slate-400" /> {report.sources?.length ?? 0} sources verified
        </span>
      </div>
    </div>
  </section>
);
