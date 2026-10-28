import React, { useCallback, useEffect, useRef, useState } from 'react';
import { nexusJson, nexusChatStream } from '../../api';
import { WorkspaceNavRail, type WorkspaceNavRoute } from './WorkspaceNavRail';
import { UpgradeSpacesPanel } from '../UpgradeSpacesPanel';
import { WorkspaceHome, BootstrapData } from './WorkspaceHome';
import { LightKnowledgeGraph } from './LightKnowledgeGraph';
import { DeepResearchLight } from './DeepResearchLight';
import { WorkflowLight } from './WorkflowLight';
import { ArchitectureLight } from './ArchitectureLight';
import { AnalyticsLight } from './AnalyticsLight';
import { AgentsLight } from './AgentsLight';
import { QueryConsole, ConsoleMode, ConsoleStatus, MediaAttachment } from './QueryConsole';
import { WorkspaceResults, WorkspaceResult, MediaResultEntry } from './WorkspaceResults';

/* ────────────────────────────────────────────────────────────────────────────
 * NEXUS OS — the light-mode workspace shell.
 *
 * One rail, one floating cockpit, seven surfaces:
 *   HOME        Primary Workspace Dashboard (greeting, hero, feature matrix)
 *   GRAPH       Light Knowledge Graph            ← GET  /api/graph/graph
 *   RESEARCH    Deep Research Lab                ← POST /api/research/execute
 *   WORKFLOW    Workflow Canvas                  ← GET  /api/workflows
 *                                              ← POST /api/workflows/run/{id}
 *   ARCHITECTURE Hexagonal Ports & Adapters      ← GET  /openapi.json
 *   ANALYTICS   System Intelligence              ← GET  /api/system/telemetry
 *   AGENTS      Agent Orchestration              ← GET  /v1/agents
 *
 * The floating graphite cockpit stays docked across every route, and its
 * results surface as a bottom sheet above it — no legacy dark pages open.
 * ──────────────────────────────────────────────────────────────────────────── */

const CONSOLE_DRAFT_KEY = 'nexus-workspace-console-draft';

function loadConsoleDraft(): string {
  try {
    return window.sessionStorage.getItem(CONSOLE_DRAFT_KEY) || '';
  } catch {
    return '';
  }
}

const FALLBACK_BOOTSTRAP: BootstrapData = {
  greeting: {
    user: 'Nixtio',
    headline: 'Hi Nixtio, Ready to Achieve Great Things?',
    subline: 'Your cognitive copilot is online. Search, research, create, and ship — all from one canvas.',
  },
  hero: {
    companion: 'NIX-7',
    message: 'Hey there! Need a boost?',
    suggestions: [
      'Explain quantum computing in simple terms',
      'Research the state of autonomous agents',
      'Generate an aurora over a neural skyline',
      'Compose a focus track for deep work',
    ],
  },
  cards: [
    {
      id: 'fast-start',
      title: 'Fast Start',
      description: 'Spin up quick tasks and contribution loops. Zero-friction execution, instant feedback.',
      accent: 'orange',
      action: 'FAST_START',
      stat: 'Ready when you are',
    },
    {
      id: 'collaborate',
      title: 'Collaborate with Team',
      description: 'Background multi-agent orchestrations — researcher, coder, planner and swarm run in parallel.',
      accent: 'multicolor',
      action: 'OPEN_AGENTS',
      stat: 'Swarm standing by',
    },
    {
      id: 'planning',
      title: 'Planning',
      description: 'Track priorities and workflows on a living calendar. Deadlines become DAG steps.',
      accent: 'blue',
      action: 'OPEN_WORKFLOWS',
      stat: 'Roadmap synced',
    },
  ],
  telemetry: {
    uptime_seconds: 0,
    agents_online: 0,
    agents: [],
    recent_memories: [],
    nim_online: false,
    nim_model: null,
  },
};

const RESEARCH_STAGES = [
  'Decomposing query',
  'Searching the web',
  'Browsing sources',
  'Corroborating claims',
  'Synthesising findings',
  'Ingesting into graph',
];
const IMAGE_STAGES = ['Seeding palette', 'Composing geometry', 'Rendering vectors'];
const MUSIC_STAGES = ['Choosing key & scale', 'Arranging progression', 'Rendering waveform'];
const MEDIA_STAGES = [
  'Uploading stream',
  'Decoding bytes',
  'Spatial decomposition',
  'Querying cortex',
];

const DEFAULT_MEDIA_QUESTION = 'Describe this visual scene and identify key elements';

/* Payload shapes of the multimodal perception routes (verified live). */
interface ProcessDecomposition {
  dimensions?: string;
  format?: string;
  aspect_ratio?: string;
  average_luminance?: number;
  contrast_score?: number;
  sha256?: string;
  color_palette?: Array<{ hex: string; name?: string; percentage?: number }>;
  ocr_extracted_text?: string[];
  scene_summary?: string;
  entities?: Array<{ name?: string; category?: string; coordinates?: string }>;
  keyframes?: Array<{ timestamp?: string; scene_name?: string; visual_description?: string }>;
  duration_seconds?: number;
  fps?: number;
  resolution?: string;
}
interface ProcessPayload {
  status?: string;
  media_type?: string;
  filename?: string;
  decomposition?: ProcessDecomposition;
  answer?: string;
}
interface SttPayload {
  text?: string;
  confidence?: number;
  engine?: string;
}

interface WorkspaceViewProps {
  onOpenIntegrations: () => void;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ onOpenIntegrations }) => {
  const [route, setRoute] = useState<WorkspaceNavRoute>('HOME');
  const [bootstrap, setBootstrap] = useState<BootstrapData>(FALLBACK_BOOTSTRAP);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const [consoleValue, setConsoleValue] = useState(() => loadConsoleDraft());
  const [consoleMode, setConsoleMode] = useState<ConsoleMode>('chat');
  const [consoleStatus, setConsoleStatus] = useState<ConsoleStatus>('idle');
  const [statusDetail, setStatusDetail] = useState('');
  const [result, setResult] = useState<WorkspaceResult | null>(null);
  const [heroDismissed, setHeroDismissed] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const stageTimerRef = useRef<number | null>(null);
  const sheetRef = useRef<HTMLDivElement | null>(null);
  const activeRunControllerRef = useRef<AbortController | null>(null);

  const isBusy = consoleStatus !== 'idle';

  /* ── Live bootstrap pull ──────────────────────────────────────────────── */
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const data = await nexusJson<BootstrapData>('/api/workspace/bootstrap', {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setBootstrap(data);
          setBackendOnline(true);
        }
      } catch {
        if (!controller.signal.aborted) setBackendOnline(false);
      }
    })();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    try {
      if (consoleValue) window.sessionStorage.setItem(CONSOLE_DRAFT_KEY, consoleValue);
      else window.sessionStorage.removeItem(CONSOLE_DRAFT_KEY);
    } catch {
      // Draft persistence is best-effort in restricted browser contexts.
    }
  }, [consoleValue]);

  /* ── Stage ticker: visualises the background execution stream ─────────── */
  const startStages = useCallback((stages: string[]) => {
    let i = 0;
    if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
    setStatusDetail(stages[0]);
    stageTimerRef.current = window.setInterval(() => {
      i = Math.min(i + 1, stages.length - 1);
      setStatusDetail(stages[i]);
    }, 2100);
  }, []);

  const stopStages = useCallback(() => {
    if (stageTimerRef.current) {
      window.clearInterval(stageTimerRef.current);
      stageTimerRef.current = null;
    }
  }, []);

  useEffect(
    () => () => {
      activeRunControllerRef.current?.abort();
      stopStages();
    },
    [stopStages],
  );

  const cancelActiveRun = useCallback(() => {
    activeRunControllerRef.current?.abort();
    stopStages();
    setStatusDetail('Stopping…');
  }, [stopStages]);

  /* Bring the result sheet into view when a fresh result lands */
  useEffect(() => {
    if (result) sheetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [result?.id]);

  /* ── The cockpit executor — every mode maps to a real backend route ───── */
  const runQuery = useCallback(
    async (rawQuery: string, mode: ConsoleMode) => {
      const query = rawQuery.trim();
      if (!query || consoleStatus !== 'idle') return;

      const controller = new AbortController();
      activeRunControllerRef.current = controller;
      setConsoleValue('');
      setResult(null);
      setConsoleStatus('thinking');
      setStatusDetail(
        mode === 'research' ? 'Background research stream' : mode === 'chat' ? 'Cortex ReAct loop' : 'Dispatching'
      );

      const id = `res-${Date.now()}`;
      let stagesStarted = false;

      try {
        if (mode === 'chat') {
          const steps: string[] = [];
          let answer = '';
          let sawAnswer = false;

          await nexusChatStream(query, 'general', (ev) => {
            if (ev.type === 'thought' && ev.content) {
              steps.push(ev.content.slice(0, 180));
            } else if (ev.type === 'tool_call') {
              steps.push(`→ tool call: ${ev.tool_id ?? 'tool'}`);
            } else if (ev.type === 'observation' && ev.content) {
              steps.push(`← ${ev.content.slice(0, 140)}`);
            } else if ((ev.type === 'answer' || ev.type === 'content') && ev.content) {
              if (!sawAnswer) {
                sawAnswer = true;
                setConsoleStatus('streaming');
                setStatusDetail('Answer streaming');
              }
              answer += ev.content;
              setResult({ kind: 'chat', id, query, answer, steps, streaming: true });
            }
          }, { signal: controller.signal });

          setResult((prev) =>
            prev && prev.kind === 'chat' && prev.id === id
              ? { ...prev, streaming: false }
              : {
                  kind: 'chat',
                  id,
                  query,
                  answer:
                    answer ||
                    'The cortex completed the loop without returning an answer. The configured LLM endpoint may be unreachable — check /api/nim/status and resend.',
                  steps,
                  streaming: false,
                }
          );
        } else if (mode === 'research') {
          stagesStarted = true;
          startStages(RESEARCH_STAGES);
          const data = await nexusJson<any>('/api/research/execute', {
            method: 'POST',
            body: JSON.stringify({ query, max_sources: 3 }),
            signal: controller.signal,
          });
          setResult({
            kind: 'research',
            id,
            query,
            summary: data.summary ?? 'Research complete.',
            keyFindings: data.key_findings ?? [],
            concepts: data.extracted_concepts ?? [],
            sources: (data.sources ?? []).map((s: any) => ({ title: s.title, url: s.url, snippet: s.snippet })),
            nodesAdded: data.nodes_added_to_graph ?? 0,
            durationSeconds: data.duration_seconds ?? 0,
          });
        } else if (mode === 'image') {
          stagesStarted = true;
          startStages(IMAGE_STAGES);
          const data = await nexusJson<any>('/api/workspace/image', {
            method: 'POST',
            body: JSON.stringify({ prompt: query }),
            signal: controller.signal,
          });
          setResult({
            kind: 'image',
            id,
            prompt: query,
            svgDataUri: data.svg_data_uri,
            palette: data.palette ?? [],
            seed: data.seed,
            style: data.style,
            renderMs: data.render_ms ?? 0,
          });
        } else if (mode === 'search') {
          stagesStarted = true;
          startStages(['Scanning memory', 'Walking graph', 'Merging corpora']);
          const data = await nexusJson<any>('/api/workspace/search', {
            method: 'POST',
            body: JSON.stringify({ query, limit: 8 }),
            signal: controller.signal,
          });
          setResult({
            kind: 'search',
            id,
            query,
            results: data.results ?? [],
            scannedSources: data.scanned_sources ?? 0,
            durationMs: data.duration_ms ?? 0,
          });
        } else if (mode === 'music') {
          stagesStarted = true;
          startStages(MUSIC_STAGES);
          const data = await nexusJson<any>('/api/workspace/music', {
            method: 'POST',
            body: JSON.stringify({ prompt: query }),
            signal: controller.signal,
          });
          setResult({
            kind: 'music',
            id,
            prompt: query,
            audioDataUri: data.audio_data_uri,
            keyName: data.key,
            scale: data.scale,
            tempo: data.tempo,
            durationSeconds: data.duration_seconds,
            notesRendered: data.notes_rendered,
            renderMs: data.render_ms ?? 0,
          });
        }
      } catch (err: any) {
        const stopped = controller.signal.aborted || err?.name === 'AbortError';
        if (stopped) {
          setResult((prev) =>
            prev && prev.kind === 'chat' && prev.id === id
              ? {
                  ...prev,
                  streaming: false,
                  answer: prev.answer
                    ? `${prev.answer.trim()}\n\n_Generation stopped._`
                    : 'Generation stopped before an answer arrived.',
                }
              : {
                  kind: 'error',
                  id,
                  query,
                  message: 'Run stopped. A server-side task may still finish in the background; check its result surface before retrying.',
                },
          );
        } else {
          setResult({
            kind: 'error',
            id,
            query,
            message: err?.message ?? 'The backend route failed to respond.',
          });
        }
      } finally {
        if (activeRunControllerRef.current === controller) activeRunControllerRef.current = null;
        if (stagesStarted) stopStages();
        setConsoleStatus('idle');
        setStatusDetail('');
      }
    },
    [consoleStatus, startStages, stopStages]
  );

  /* ── The multimodal executor — attachments → perception routes ──────────
   * Every attachment is really uploaded: images / video / docs go to the
   * perception bridge (POST /api/multimodal/process, multipart), audio goes
   * to the transcriber (POST /api/audio/stt). Failures are per-attachment. */
  const runMedia = useCallback(
    async (attachments: MediaAttachment[], question: string) => {
      if (consoleStatus !== 'idle' || attachments.length === 0) return;

      const controller = new AbortController();
      activeRunControllerRef.current = controller;
      setConsoleValue('');
      setConsoleStatus('thinking');
      setStatusDetail('Uploading stream');
      startStages(MEDIA_STAGES);

      const id = `res-${Date.now()}`;
      const entries: MediaResultEntry[] = [];
      let stopped = false;

      for (const att of attachments) {
        if (controller.signal.aborted) {
          stopped = true;
          break;
        }
        const sizeKb = Math.round(att.file.size / 102.4) / 10;
        try {
          if (att.kind === 'audio') {
            const fd = new FormData();
            fd.append('audio_file', att.file, att.file.name);
            const stt = await nexusJson<SttPayload>('/api/audio/stt', {
              method: 'POST',
              body: fd,
              signal: controller.signal,
            });
            entries.push({
              id: `${att.id}-stt`,
              type: 'audio',
              filename: att.file.name,
              sizeKb,
              previewUrl: att.previewUrl,
              transcript: stt.text ?? '',
              confidence: stt.confidence,
              engine: stt.engine,
            });
          } else {
            const fd = new FormData();
            fd.append('file', att.file, att.file.name);
            fd.append('question', question || DEFAULT_MEDIA_QUESTION);
            fd.append('media_type', att.kind === 'video' ? 'video' : 'auto');
            const data = await nexusJson<ProcessPayload>('/api/multimodal/process', {
              method: 'POST',
              body: fd,
              signal: controller.signal,
            });
            const dec = data.decomposition ?? {};
            entries.push({
              id: `${att.id}-proc`,
              type: att.kind === 'video' ? 'video' : att.kind === 'image' ? 'image' : 'doc',
              filename: att.file.name,
              sizeKb,
              previewUrl: att.previewUrl,
              answer: data.answer,
              dimensions: dec.dimensions,
              format: dec.format,
              aspectRatio: dec.aspect_ratio,
              luminance: dec.average_luminance,
              contrast: dec.contrast_score,
              sha256: dec.sha256,
              palette: dec.color_palette ?? [],
              ocrText: dec.ocr_extracted_text ?? [],
              sceneSummary: dec.scene_summary,
              entities: (dec.entities ?? []).map((e) => ({
                name: e.name ?? 'entity',
                category: e.category,
                coordinates: e.coordinates,
              })),
              keyframes: (dec.keyframes ?? []).map((k) => ({
                timestamp: k.timestamp ?? '',
                scene_name: k.scene_name ?? '',
                visual_description: k.visual_description ?? '',
              })),
              videoDuration: dec.duration_seconds,
              fps: dec.fps,
              resolution: dec.resolution,
            });
          }
        } catch (err: any) {
          if (controller.signal.aborted || err?.name === 'AbortError') {
            stopped = true;
            break;
          }
          entries.push({
            id: `${att.id}-err`,
            type: att.kind,
            filename: att.file.name,
            sizeKb,
            previewUrl: att.previewUrl,
            error: err?.message ?? 'The perception route failed to respond.',
          });
        }
      }

      if (activeRunControllerRef.current === controller) activeRunControllerRef.current = null;
      stopStages();
      setConsoleStatus('idle');
      setStatusDetail('');
      if (stopped && entries.length === 0) {
        setResult({
          kind: 'error',
          id,
          query: question,
          message: 'Media run stopped before any attachment completed. A server-side upload may still finish in the background.',
        });
      } else {
        if (stopped) {
          entries.push({
            id: `${id}-stopped`,
            type: 'doc',
            filename: 'Run stopped',
            sizeKb: 0,
            previewUrl: null,
            error: 'Stopped before all attachments were processed.',
          });
        }
        setResult({ kind: 'media', id, query: question, entries });
      }
    },
    [consoleStatus, startStages, stopStages]
  );

  /* ── Handoffs from the suite views into the cockpit ───────────────────── */
  const handleResearchTopic = useCallback((topic: string) => {    setConsoleMode('research');
    setConsoleValue(topic);
    textareaRef.current?.focus();
  }, []);

  const handleSuggestion = useCallback((s: string) => {
    setConsoleValue(s);
    textareaRef.current?.focus();
  }, []);

  const handleBoost = useCallback(() => {
    runQuery(
      'Give me a boost: suggest one high-impact task I can complete in the next hour, and why it matters.',
      'chat'
    );
  }, [runQuery]);

  return (
    <div className="nxs-workspace fixed inset-0 z-40 bg-[#F9FAFB] overflow-y-auto antialiased text-slate-900">
      <WorkspaceNavRail activeRoute={route} onRouteChange={setRoute} onOpenIntegrations={onOpenIntegrations} />

      <div className="pl-[72px] min-h-full flex flex-col">
        {route === 'HOME' && (
          <WorkspaceHome
            bootstrap={bootstrap}
            backendOnline={backendOnline}
            isBusy={isBusy}
            heroDismissed={heroDismissed}
            onDismissHero={() => setHeroDismissed((d) => !d)}
            onRouteChange={setRoute}
            onOpenSpaces={() => setRoute('SPACES')}
            onFastStart={handleSuggestion}
            onSuggestion={handleSuggestion}
            onBoost={handleBoost}
          />
        )}
        {route === 'GRAPH' && <LightKnowledgeGraph onResearchTopic={handleResearchTopic} />}
        {route === 'RESEARCH' && <DeepResearchLight />}
        {route === 'WORKFLOW' && <WorkflowLight />}
        {route === 'ARCHITECTURE' && <ArchitectureLight />}
        {route === 'ANALYTICS' && <AnalyticsLight />}
        {route === 'AGENTS' && <AgentsLight />}
        {route === 'SPACES' && <UpgradeSpacesPanel />}
      </div>

      {/* ── Result sheet — floats above the cockpit on every route ───────── */}
      {result && (
        <div className="fixed inset-x-0 bottom-[9.5rem] z-40 pl-[72px] pointer-events-none">
          <div ref={sheetRef} className="max-w-[880px] mx-auto px-6 pointer-events-auto">
            <div className="max-h-[46vh] overflow-y-auto nxs-scroll rounded-3xl shadow-[0_28px_70px_-20px_rgba(16,24,40,0.4)]">
              <WorkspaceResults result={result} onClose={() => setResult(null)} />
            </div>
          </div>
        </div>
      )}

      {/* ── The floating graphite cockpit (all routes) ────────────────────── */}
      <div className="fixed inset-x-0 bottom-6 z-40 pl-[72px] pointer-events-none">
        <div className="max-w-[880px] mx-auto px-6 pointer-events-auto">
          <QueryConsole
            value={consoleValue}
            onChange={setConsoleValue}
            onSubmit={runQuery}
            onSubmitMedia={runMedia}
            onCancel={cancelActiveRun}
            status={consoleStatus}
            statusDetail={statusDetail}
            activeMode={consoleMode}
            onModeChange={setConsoleMode}
            textareaRef={textareaRef}
          />
        </div>
      </div>
    </div>
  );
};
