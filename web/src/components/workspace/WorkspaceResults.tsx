import React from 'react';
import {
  X,
  Telescope,
  ImagePlus,
  Search,
  Music,
  MessageSquareText,
  AlertTriangle,
  ExternalLink,
  Download,
  Brain,
  Lightbulb,
  Globe,
  Layers,
  Clock,
  Sparkles,
  ScanSearch,
  Film,
  AudioLines,
  FileText,
  Type,
  Fingerprint,
  Palette,
} from 'lucide-react';

/** One analyzed attachment from a multimodal perception run. */
export interface MediaResultEntry {
  id: string;
  type: 'image' | 'video' | 'audio' | 'doc';
  filename: string;
  sizeKb: number;
  previewUrl: string | null;
  error?: string;
  /* /api/multimodal/process payload (image / video / doc) */
  answer?: string;
  dimensions?: string;
  format?: string;
  aspectRatio?: string;
  luminance?: number;
  contrast?: number;
  sha256?: string;
  palette?: Array<{ hex: string; name?: string; percentage?: number }>;
  ocrText?: string[];
  sceneSummary?: string;
  entities?: Array<{ name: string; category?: string; coordinates?: string }>;
  keyframes?: Array<{ timestamp: string; scene_name: string; visual_description: string }>;
  videoDuration?: number;
  fps?: number;
  resolution?: string;
  /* /api/audio/stt payload */
  transcript?: string;
  confidence?: number;
  engine?: string;
}

export type WorkspaceResult =
  | {
      kind: 'chat';
      id: string;
      query: string;
      answer: string;
      steps: string[];
      streaming: boolean;
    }
  | {
      kind: 'research';
      id: string;
      query: string;
      summary: string;
      keyFindings: string[];
      concepts: string[];
      sources: Array<{ title: string; url: string; snippet: string }>;
      nodesAdded: number;
      durationSeconds: number;
    }
  | {
      kind: 'image';
      id: string;
      prompt: string;
      svgDataUri: string;
      palette: string[];
      seed: number;
      style: string;
      renderMs: number;
    }
  | {
      kind: 'music';
      id: string;
      prompt: string;
      audioDataUri: string;
      keyName: string;
      scale: string;
      tempo: number;
      durationSeconds: number;
      notesRendered: number;
      renderMs: number;
    }
  | {
      kind: 'search';
      id: string;
      query: string;
      results: Array<{ source: string; title: string; snippet: string; score: number; kind?: string; url?: string }>;
      scannedSources: number;
      durationMs: number;
    }
  | {
      kind: 'media';
      id: string;
      query: string;
      entries: MediaResultEntry[];
    }
  | { kind: 'error'; id: string; query: string; message: string };

interface WorkspaceResultsProps {
  result: WorkspaceResult;
  onClose: () => void;
}

const SOURCE_BADGE: Record<string, { label: string; classes: string }> = {
  memory: { label: 'MEMORY', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  concept: { label: 'GRAPH NODE', classes: 'bg-cyan-50 text-cyan-700 border-cyan-200' },
  research: { label: 'RESEARCH', classes: 'bg-violet-50 text-violet-700 border-violet-200' },
  multimodal: { label: 'MULTIMODAL', classes: 'bg-amber-50 text-amber-700 border-amber-200' },
};

const KIND_ICON: Record<WorkspaceResult['kind'], React.ComponentType<{ className?: string; strokeWidth?: number }>> = {
  chat: MessageSquareText,
  research: Telescope,
  image: ImagePlus,
  search: Search,
  music: Music,
  media: ScanSearch,
  error: AlertTriangle,
};

const KIND_TITLE: Record<WorkspaceResult['kind'], string> = {
  chat: 'Cortex Answer',
  research: 'Deep Research Report',
  image: 'Generated Image',
  search: 'Search Results',
  music: 'Generated Track',
  media: 'Multimodal Perception',
  error: 'Execution Error',
};

const ENTRY_ICON: Record<MediaResultEntry['type'], React.ComponentType<{ className?: string; strokeWidth?: number }>> = {
  image: ImagePlus,
  video: Film,
  audio: AudioLines,
  doc: FileText,
};

function Meta({ icon: Icon, children }: { icon: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-[11px] font-medium text-slate-600">
      <Icon className="w-3 h-3 text-slate-400" />
      {children}
    </span>
  );
}

/**
 * Renders the live result of any cockpit action — every panel is populated
 * straight from a real backend route payload.
 */
export const WorkspaceResults: React.FC<WorkspaceResultsProps> = ({ result, onClose }) => {
  const Icon = KIND_ICON[result.kind];

  return (
    <section
      aria-live="polite"
      className="relative mt-8 rounded-3xl bg-white border border-slate-200/80 shadow-[0_20px_50px_-20px_rgba(16,24,40,0.18)] animate-[nxs-rise_0.35s_cubic-bezier(0.22,1,0.36,1)]"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-slate-100">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
              result.kind === 'error'
                ? 'bg-rose-50 text-rose-600'
                : 'bg-gradient-to-br from-slate-900 to-slate-700 text-white'
            }`}
          >
            <Icon className="w-4 h-4" strokeWidth={2} />
          </span>
          <div className="min-w-0">
            <h3 className="text-[15px] font-bold text-slate-900 leading-tight">{KIND_TITLE[result.kind]}</h3>
            <p className="text-[12px] text-slate-400 truncate mt-0.5">“{result.query}”</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition-all cursor-pointer shrink-0"
          aria-label="Close result"
        >
          <X className="w-4 h-4" strokeWidth={2} />
        </button>
      </div>

      <div className="p-6">
        {/* ── Chat stream answer ─────────────────────────────────────────── */}
        {result.kind === 'chat' && (
          <div className="flex flex-col gap-4">
            {result.steps.length > 0 && (
              <details className="group rounded-2xl border border-slate-200 bg-slate-50/60 overflow-hidden">
                <summary className="cursor-pointer list-none px-4 py-2.5 flex items-center gap-2 text-[12px] font-semibold text-slate-500 select-none">
                  <Brain className="w-3.5 h-3.5 text-cyan-600" />
                  ReAct reasoning trace · {result.steps.length} steps
                  <span className="ml-auto text-slate-400 group-open:rotate-180 transition-transform">▾</span>
                </summary>
                <ol className="px-4 pb-3 space-y-1.5">
                  {result.steps.map((s, i) => (
                    <li key={i} className="flex gap-2 text-[12px] text-slate-500 nxs-mono leading-relaxed">
                      <span className="text-cyan-600 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                      <span className="break-words">{s}</span>
                    </li>
                  ))}
                </ol>
              </details>
            )}
            <p className="text-[14px] leading-relaxed text-slate-700 whitespace-pre-wrap">
              {result.answer || (
                <span className="text-slate-400 italic">Cortex is composing an answer…</span>
              )}
              {result.streaming && (
                <span className="inline-block w-[7px] h-[15px] align-[-2px] ml-0.5 rounded-[2px] bg-cyan-500 animate-[nxs-caret_1s_steps(1)_infinite]" />
              )}
            </p>
          </div>
        )}

        {/* ── Deep research report ───────────────────────────────────────── */}
        {result.kind === 'research' && (
          <div className="flex flex-col gap-5">
            <p className="text-[14px] leading-relaxed text-slate-700">{result.summary}</p>

            {result.keyFindings.length > 0 && (
              <div>
                <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2.5">
                  <Lightbulb className="w-3.5 h-3.5 text-amber-500" /> Key Findings
                </h4>
                <ul className="space-y-2">
                  {result.keyFindings.map((f, i) => (
                    <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-slate-600">
                      <span className="shrink-0 mt-[7px] w-1.5 h-1.5 rounded-full bg-amber-400" />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {result.concepts.length > 0 && (
              <div>
                <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2.5">
                  <Layers className="w-3.5 h-3.5 text-cyan-600" /> Concepts Ingested into Graph
                </h4>
                <div className="flex flex-wrap gap-2">
                  {result.concepts.map((c) => (
                    <span key={c} className="px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-[12px] font-medium text-cyan-800">
                      ◈ {c}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {result.sources.length > 0 && (
              <div>
                <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2.5">
                  <Globe className="w-3.5 h-3.5 text-slate-400" /> Corroborated Sources
                </h4>
                <div className="grid sm:grid-cols-2 gap-2.5">
                  {result.sources.map((s, i) => (
                    <a
                      key={i}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className="group rounded-2xl border border-slate-200 hover:border-cyan-300 hover:shadow-[0_8px_20px_-8px_rgba(6,182,212,0.3)] transition-all p-3.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[13px] font-semibold text-slate-800 leading-snug line-clamp-2">{s.title}</span>
                        <ExternalLink className="w-3.5 h-3.5 text-slate-300 group-hover:text-cyan-500 shrink-0 mt-0.5" />
                      </div>
                      <p className="mt-1.5 text-[12px] text-slate-500 line-clamp-2">{s.snippet}</p>
                    </a>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              <Meta icon={Clock}>{result.durationSeconds.toFixed(1)}s execution</Meta>
              <Meta icon={Layers}>+{result.nodesAdded} graph nodes</Meta>
            </div>
          </div>
        )}

        {/* ── Generated image ────────────────────────────────────────────── */}
        {result.kind === 'image' && (
          <div className="grid md:grid-cols-[minmax(0,300px)_1fr] gap-6 items-start">
            <div className="rounded-2xl overflow-hidden border border-slate-200 shadow-[0_16px_40px_-16px_rgba(16,24,40,0.3)] bg-[#0B0F19]">
              <img src={result.svgDataUri} alt={`Generated art for: ${result.prompt}`} className="w-full h-auto block" />
            </div>
            <div className="flex flex-col gap-4">
              <p className="text-[14px] leading-relaxed text-slate-600">
                Rendered by the procedural art engine — deterministic for this exact prompt, so the same words
                always regenerate the same piece.
              </p>
              <div>
                <h4 className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2">Palette</h4>
                <div className="flex gap-2">
                  {result.palette.map((hex) => (
                    <span key={hex} className="flex flex-col items-center gap-1.5">
                      <span className="w-9 h-9 rounded-xl border border-slate-200 shadow-inner" style={{ backgroundColor: hex }} />
                      <span className="text-[10px] nxs-mono text-slate-400">{hex}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Meta icon={Sparkles}>seed {result.seed}</Meta>
                <Meta icon={ImagePlus}>{result.style} style</Meta>
                <Meta icon={Clock}>{result.renderMs.toFixed(1)} ms render</Meta>
              </div>
              <a
                href={result.svgDataUri}
                download={`nexus-art-${result.seed}.svg`}
                className="inline-flex items-center gap-2 self-start px-4 py-2 rounded-full bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 transition-all"
              >
                <Download className="w-3.5 h-3.5" />
                Download SVG
              </a>
            </div>
          </div>
        )}

        {/* ── Generated music ────────────────────────────────────────────── */}
        {result.kind === 'music' && (
          <div className="flex flex-col gap-5">
            <div className="rounded-2xl bg-gradient-to-br from-[#0B0F19] to-slate-800 p-5 shadow-[0_20px_50px_-20px_rgba(11,15,25,0.6)]">
              <div className="flex items-center gap-3">
                <span className="w-11 h-11 rounded-2xl bg-gradient-to-br from-cyan-400 to-violet-500 flex items-center justify-center shadow-[0_0_24px_rgba(34,211,238,0.4)]">
                  <Music className="w-5 h-5 text-white" />
                </span>
                <div className="min-w-0">
                  <p className="text-white text-[14px] font-bold truncate">{result.prompt}</p>
                  <p className="text-slate-400 text-[11px] nxs-mono mt-0.5">
                    {result.keyName} {result.scale} · {result.tempo} BPM
                  </p>
                </div>
              </div>
              {/* Level visualiser strip */}
              <div className="mt-4 flex items-end gap-[3px] h-10" aria-hidden>
                {Array.from({ length: 48 }).map((_, i) => (
                  <span
                    key={i}
                    className="flex-1 rounded-sm bg-gradient-to-t from-cyan-500/70 to-violet-400/70"
                    style={{
                      height: `${18 + 75 * Math.abs(Math.sin(i * 0.37 + result.seed % 7))}%`,
                      opacity: 0.35 + 0.55 * Math.abs(Math.cos(i * 0.21)),
                    }}
                  />
                ))}
              </div>
              <audio controls src={result.audioDataUri} className="mt-4 w-full" preload="metadata">
                Your browser does not support embedded audio.
              </audio>
            </div>
            <div className="flex flex-wrap gap-2">
              <Meta icon={Music}>{result.notesRendered} notes rendered</Meta>
              <Meta icon={Clock}>{result.durationSeconds.toFixed(0)}s · 22.05 kHz WAV</Meta>
              <Meta icon={Sparkles}>seed {result.seed}</Meta>
            </div>
          </div>
        )}

        {/* ── Search results ─────────────────────────────────────────────── */}
        {result.kind === 'search' && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              <Meta icon={Search}>{result.results.length} hits</Meta>
              <Meta icon={Layers}>{result.scannedSources} sources scanned</Meta>
              <Meta icon={Clock}>{result.durationMs.toFixed(1)} ms</Meta>
            </div>
            {result.results.length === 0 && (
              <p className="text-[13px] text-slate-500 italic py-4">
                No matches across memory, graph concepts, research history, or the multimodal corpus yet — try a
                different phrasing.
              </p>
            )}
            <div className="divide-y divide-slate-100">
              {result.results.map((r, i) => {
                const badge = SOURCE_BADGE[r.source] ?? {
                  label: r.source.toUpperCase(),
                  classes: 'bg-slate-50 text-slate-600 border-slate-200',
                };
                return (
                  <div key={i} className="py-3.5 flex gap-3.5">
                    <span className="shrink-0 mt-1 w-1.5 h-1.5 rounded-full bg-slate-300" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 rounded-md border text-[9px] font-bold tracking-[0.12em] nxs-mono ${badge.classes}`}>
                          {badge.label}
                        </span>
                        {r.kind && <span className="text-[10px] text-slate-400 nxs-mono">{r.kind}</span>}
                        <span className="text-[10px] text-slate-300 nxs-mono ml-auto">score {r.score.toFixed(2)}</span>
                      </div>
                      <p className="mt-1.5 text-[13.5px] font-semibold text-slate-800 leading-snug">{r.title}</p>
                      <p className="mt-1 text-[12.5px] text-slate-500 leading-relaxed line-clamp-2">{r.snippet}</p>
                      {r.url && (
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1.5 inline-flex items-center gap-1 text-[11.5px] font-medium text-cyan-700 hover:text-cyan-900"
                        >
                          <ExternalLink className="w-3 h-3" /> {r.url}
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Multimodal perception dossiers ─────────────────────────────── */}
        {result.kind === 'media' && (
          <div className="flex flex-col gap-4">
            {result.entries.map((entry) => {
              const EntryIcon = ENTRY_ICON[entry.type];
              return (
                <div
                  key={entry.id}
                  className="rounded-2xl border border-slate-200 bg-slate-50/60 overflow-hidden animate-[nxs-fade-in_0.35s_ease-out]"
                >
                  {/* Entry header */}
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200/80 bg-white">
                    <span
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                        entry.error
                          ? 'bg-rose-50 text-rose-600'
                          : 'bg-gradient-to-br from-cyan-500 to-violet-500 text-white'
                      }`}
                    >
                      <EntryIcon className="w-4 h-4" strokeWidth={2} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-slate-800 truncate">{entry.filename}</p>
                      <p className="text-[10.5px] nxs-mono uppercase tracking-wider text-slate-400">
                        {entry.type} · {entry.sizeKb >= 1024 ? `${(entry.sizeKb / 1024).toFixed(1)} MB` : `${entry.sizeKb.toFixed(1)} KB`}
                        {entry.sha256 ? ` · sha ${entry.sha256.slice(0, 8)}` : ''}
                      </p>
                    </div>
                  </div>

                  <div className="p-4 flex flex-col gap-3.5">
                    {entry.error ? (
                      <p className="text-[12.5px] text-rose-600 leading-relaxed">{entry.error}</p>
                    ) : (
                      <>
                        {/* Audio: transcript from the speech-to-text route */}
                        {entry.type === 'audio' && (
                          <>
                            <blockquote className="border-l-[3px] border-cyan-400 pl-3.5 text-[14px] text-slate-700 leading-relaxed italic">
                              “{entry.transcript}”
                            </blockquote>
                            <div className="flex flex-wrap items-center gap-2">
                              {typeof entry.confidence === 'number' && (
                                <span className="inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-[11px] font-medium text-slate-600">
                                  <span className="w-16 h-1.5 rounded-full bg-slate-200 overflow-hidden">
                                    <span
                                      className="block h-full rounded-full bg-gradient-to-r from-cyan-400 to-violet-500"
                                      style={{ width: `${Math.round(entry.confidence * 100)}%` }}
                                    />
                                  </span>
                                  {Math.round(entry.confidence * 100)}% confidence
                                </span>
                              )}
                              {entry.engine && <Meta icon={AudioLines}>{entry.engine}</Meta>}
                            </div>
                            {entry.previewUrl && (
                              <audio controls src={entry.previewUrl} className="w-full h-9" preload="metadata" />
                            )}
                          </>
                        )}

                        {/* Image / doc: preview + real pixel stats */}
                        {(entry.type === 'image' || entry.type === 'doc') && (
                          <>
                            {entry.type === 'image' && entry.previewUrl && (
                              <img
                                src={entry.previewUrl}
                                alt={entry.filename}
                                className="max-h-56 rounded-xl border border-slate-200 object-contain bg-[repeating-conic-gradient(#f1f5f9_0%_25%,#ffffff_0%_50%)] bg-[length:16px_16px]"
                              />
                            )}
                            <div className="flex flex-wrap gap-2">
                              {entry.dimensions && <Meta icon={ImagePlus}>{entry.dimensions}</Meta>}
                              {entry.format && <Meta icon={Layers}>{entry.format}</Meta>}
                              {entry.aspectRatio && <Meta icon={Layers}>{entry.aspectRatio}</Meta>}
                              {typeof entry.luminance === 'number' && <Meta icon={Lightbulb}>luma {entry.luminance}</Meta>}
                              {typeof entry.contrast === 'number' && <Meta icon={Layers}>contrast {(entry.contrast * 100).toFixed(0)}%</Meta>}
                            </div>
                          </>
                        )}

                        {/* Video: keyframe timeline from the temporal decomposition */}
                        {entry.type === 'video' && (
                          <>
                            {entry.previewUrl && (
                              <video controls src={entry.previewUrl} className="w-full max-h-64 rounded-xl border border-slate-200 bg-black" preload="metadata" />
                            )}
                            <div className="flex flex-wrap gap-2">
                              {entry.resolution && <Meta icon={Film}>{entry.resolution}</Meta>}
                              {entry.fps && <Meta icon={Film}>{entry.fps} fps</Meta>}
                              {entry.videoDuration && <Meta icon={Clock}>{entry.videoDuration}s</Meta>}
                            </div>
                            {entry.keyframes && entry.keyframes.length > 0 && (
                              <div>
                                <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2">
                                  <Film className="w-3.5 h-3.5 text-violet-500" /> Keyframe Timeline
                                </h4>
                                <div className="flex flex-col gap-2">
                                  {entry.keyframes.map((kf, i) => (
                                    <div key={i} className="flex gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5">
                                      <span className="shrink-0 text-[11px] nxs-mono text-violet-600 font-semibold pt-0.5">{kf.timestamp}</span>
                                      <div className="min-w-0">
                                        <p className="text-[12.5px] font-semibold text-slate-800">{kf.scene_name}</p>
                                        <p className="text-[12px] text-slate-500 leading-relaxed line-clamp-2">{kf.visual_description}</p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </>
                        )}

                        {/* Palette — real quantized colors from the perception bridge */}
                        {entry.palette && entry.palette.length > 0 && (
                          <div>
                            <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2">
                              <Palette className="w-3.5 h-3.5 text-amber-500" /> Dominant Palette
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {entry.palette.map((c, i) => (
                                <span
                                  key={i}
                                  title={`${c.name ?? c.hex}${c.percentage != null ? ` · ${c.percentage}%` : ''}`}
                                  className="inline-flex items-center gap-2 pl-1 pr-2.5 py-1 rounded-full bg-white border border-slate-200 text-[11px] font-medium text-slate-600"
                                >
                                  <span className="w-4 h-4 rounded-full border border-black/10" style={{ backgroundColor: c.hex }} />
                                  {c.name ?? c.hex}
                                  {c.percentage != null && <span className="text-slate-400 nxs-mono">{c.percentage}%</span>}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* OCR / extracted text */}
                        {entry.ocrText && entry.ocrText.length > 0 && (
                          <div>
                            <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2">
                              <Type className="w-3.5 h-3.5 text-cyan-600" /> Extracted Text
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {entry.ocrText.slice(0, 10).map((t, i) => (
                                <span key={i} className="px-2.5 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-[12px] font-medium text-cyan-800">
                                  {t}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Entities (image scene graph) */}
                        {entry.entities && entry.entities.length > 0 && (
                          <div>
                            <h4 className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 mb-2">
                              <Brain className="w-3.5 h-3.5 text-violet-500" /> Scene Entities
                            </h4>
                            <div className="grid sm:grid-cols-2 gap-2">
                              {entry.entities.map((e, i) => (
                                <div key={i} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                                  <p className="text-[12.5px] font-semibold text-slate-800">{e.name}</p>
                                  <p className="text-[11px] text-slate-400 nxs-mono">
                                    {e.category} {e.coordinates ? `· ${e.coordinates}` : ''}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Scene summary */}
                        {entry.sceneSummary && (
                          <div className="flex gap-2.5 rounded-xl bg-white border border-slate-200 px-3.5 py-3">
                            <Sparkles className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" strokeWidth={2} />
                            <p className="text-[12.5px] text-slate-600 leading-relaxed">{entry.sceneSummary}</p>
                          </div>
                        )}

                        {/* The bridge answer */}
                        {entry.answer && (
                          <div className="flex gap-2.5 rounded-xl bg-gradient-to-br from-slate-900 to-slate-700 text-white px-3.5 py-3">
                            <Fingerprint className="w-4 h-4 text-cyan-300 shrink-0 mt-0.5" strokeWidth={2} />
                            <p className="text-[12.5px] leading-relaxed text-slate-100 whitespace-pre-line">{entry.answer}</p>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Error ──────────────────────────────────────────────────────── */}
        {result.kind === 'error' && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 flex gap-3">
            <AlertTriangle className="w-4.5 h-4.5 text-rose-500 shrink-0 mt-0.5" strokeWidth={2} />
            <div>
              <p className="text-[13px] font-semibold text-rose-800">The backend route reported a failure</p>
              <p className="mt-1 text-[12.5px] text-rose-600 leading-relaxed break-words">{result.message}</p>
              <p className="mt-2 text-[11.5px] text-rose-400 nxs-mono">
                Check that the NEXUS API server is running and your key is configured.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
