import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Play,
  Zap,
  GitBranch,
  CheckCircle2,
  Loader2,
  Circle,
  Clock,
  Terminal,
  ChevronRight,
  Workflow as WorkflowIcon,
} from 'lucide-react';
import { nexusJson } from '../../api';
import { PageHeader, ViewShell, LiveChip, useLiveFetch } from './shared';

/* ────────────────────────────────────────────────────────────────────────────
 * Light Workflow Canvas — visual DAG orchestrators with live execution.
 * Lists GET /api/workflows, renders each pipeline as a connected step chain,
 * and runs POST /api/workflows/run/{id}, replaying the execution logs as an
 * animated step-by-step telemetry stream.
 * ──────────────────────────────────────────────────────────────────────────── */

interface WorkflowStep {
  id: string;
  name: string;
  action: string;
  service: string;
  status: string;
  output?: string | null;
}

interface Workflow {
  id: string;
  title: string;
  description: string;
  category: string;
  trigger: string;
  status: string;
  last_run: string;
  steps: WorkflowStep[];
}

interface RunLog {
  step_id: string;
  name: string;
  service: string;
  status: string;
  message: string;
  timestamp: string;
}

const CATEGORY_STYLES: Record<string, string> = {
  Research: 'bg-violet-50 text-violet-700 border-violet-200',
  DevOps: 'bg-blue-50 text-blue-700 border-blue-200',
  'Daily Routine': 'bg-amber-50 text-amber-700 border-amber-200',
  Security: 'bg-rose-50 text-rose-700 border-rose-200',
};

export const WorkflowLight: React.FC = () => {
  const { data, error, loading, reload } = useLiveFetch<Workflow[]>('/api/workflows');
  const workflows = useMemo(() => data ?? [], [data]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stepStatus, setStepStatus] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<RunLog[]>([]);
  const [running, setRunning] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  const selected = workflows.find((w) => w.id === selectedId) ?? workflows[0] ?? null;

  useEffect(() => {
    if (!selectedId && workflows.length > 0) setSelectedId(workflows[0].id);
  }, [workflows, selectedId]);

  // Reset local step statuses when switching workflows
  useEffect(() => {
    setStepStatus({});
    setLogs([]);
  }, [selectedId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [logs]);

  const runWorkflow = useCallback(
    async (workflow: Workflow) => {
      if (running || !workflow) return;
      setRunning(true);
      setLogs([]);
      setStepStatus(Object.fromEntries(workflow.steps.map((s) => [s.id, 'pending'])));
      try {
        const result = await nexusJson<{ execution_logs: RunLog[] }>(`/api/workflows/run/${workflow.id}`, {
          method: 'POST',
        });
        // Replay the backend's execution logs as an animated telemetry stream
        for (let i = 0; i < workflow.steps.length; i++) {
          const step = workflow.steps[i];
          setStepStatus((prev) => ({ ...prev, [step.id]: 'running' }));
          await new Promise((r) => setTimeout(r, 450));
          const log = result.execution_logs?.[i];
          if (log) {
            setLogs((prev) => [...prev, log]);
            setStepStatus((prev) => ({ ...prev, [step.id]: 'completed' }));
          }
        }
        reload();
      } catch (err: any) {
        setLogs((prev) => [
          ...prev,
          {
            step_id: 'error',
            name: 'Execution',
            service: 'api',
            status: 'error',
            message: err?.message ?? 'Workflow run failed.',
            timestamp: new Date().toLocaleTimeString(),
          },
        ]);
        setStepStatus((prev) =>
          Object.fromEntries(Object.entries(prev).map(([k, v]) => [k, v === 'running' ? 'failed' : v]))
        );
      } finally {
        setRunning(false);
      }
    },
    [running, reload]
  );

  return (
    <ViewShell>
      <PageHeader
        route="WORKFLOW"
        right={
          <LiveChip loading={loading} offline={!!error} label={error ? 'Workflows offline' : 'Orchestrator online'} />
        }
      />

      {loading && (
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="h-40 rounded-3xl bg-white border border-slate-200/80 animate-pulse" />
          <div className="h-40 rounded-3xl bg-white border border-slate-200/80 animate-pulse" />
        </div>
      )}

      {error && (
        <div className="mt-6 rounded-3xl border border-amber-200 bg-amber-50 p-6 text-[13px] text-amber-800">
          Workflow API unreachable — {error}. <button onClick={reload} className="underline font-semibold cursor-pointer">Retry</button>
        </div>
      )}

      {!loading && !error && (
        <div className="mt-6 grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
          {/* Workflow list */}
          <div className="space-y-2.5">
            {workflows.map((w) => (
              <button
                key={w.id}
                onClick={() => setSelectedId(w.id)}
                className={`w-full text-left rounded-3xl border p-5 transition-all cursor-pointer ${
                  selected?.id === w.id
                    ? 'bg-white border-emerald-300 shadow-[0_16px_36px_-18px_rgba(16,185,129,0.4)]'
                    : 'bg-white border-slate-200/80 hover:border-slate-300 shadow-[0_1px_2px_rgba(16,24,40,0.04)]'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`px-2 py-0.5 rounded-md border text-[9.5px] font-bold uppercase tracking-wider ${
                      CATEGORY_STYLES[w.category] ?? 'bg-slate-50 text-slate-600 border-slate-200'
                    }`}
                  >
                    {w.category}
                  </span>
                  <span className="flex items-center gap-1.5 text-[10px] nxs-mono text-slate-400">
                    <Clock className="w-3 h-3" /> {w.last_run}
                  </span>
                </div>
                <h3 className="mt-2.5 text-[14px] font-bold text-slate-900 leading-snug">{w.title}</h3>
                <p className="mt-1.5 text-[12px] leading-relaxed text-slate-500 line-clamp-2">{w.description}</p>
                <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-400">
                  <GitBranch className="w-3.5 h-3.5" /> {w.steps.length} steps
                  <span className="text-slate-300">·</span>
                  <Zap className="w-3 h-3" /> {w.trigger}
                </div>
              </button>
            ))}
          </div>

          {/* Detail: DAG + runner + logs */}
          {selected && (
            <div className="space-y-4">
              <div className="rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)]">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <h3 className="text-[16px] font-bold text-slate-900">{selected.title}</h3>
                    <p className="mt-1 text-[12.5px] text-slate-500 leading-relaxed max-w-lg">{selected.description}</p>
                  </div>
                  <button
                    onClick={() => runWorkflow(selected)}
                    disabled={running}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-emerald-600 text-white text-[13px] font-bold hover:bg-emerald-500 shadow-[0_10px_24px_-10px_rgba(16,185,129,0.6)] transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shrink-0"
                  >
                    {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    {running ? 'Executing…' : 'Run workflow'}
                  </button>
                </div>

                {/* DAG chain */}
                <div className="mt-6 overflow-x-auto nxs-scroll pb-2">
                  <div className="flex items-stretch gap-0 min-w-max">
                    {selected.steps.map((step, i) => {
                      const status = stepStatus[step.id] ?? step.status ?? 'pending';
                      const isRunning = running && status === 'running';
                      return (
                        <React.Fragment key={step.id}>
                          {i > 0 && (
                            <div className="flex items-center px-1">
                              <div
                                className={`w-8 h-[2px] rounded-full ${
                                  isRunning ? 'bg-emerald-400 nxs-flow' : status === 'completed' ? 'bg-emerald-400' : 'bg-slate-200'
                                }`}
                              />
                              <ChevronRight className={`w-3.5 h-3.5 ${isRunning ? 'text-emerald-400' : 'text-slate-300'}`} />
                            </div>
                          )}
                          <div
                            className={`w-[168px] rounded-2xl border p-3.5 transition-all ${
                              status === 'completed'
                                ? 'border-emerald-300 bg-emerald-50/50'
                                : isRunning
                                  ? 'border-emerald-400 bg-white shadow-[0_0_0_4px_rgba(16,185,129,0.12)]'
                                  : 'border-slate-200 bg-white'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[9.5px] font-bold nxs-mono text-slate-400">STEP {i + 1}</span>
                              {status === 'completed' ? (
                                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                              ) : isRunning ? (
                                <Loader2 className="w-4 h-4 text-emerald-500 animate-spin" />
                              ) : (
                                <Circle className="w-3.5 h-3.5 text-slate-300" />
                              )}
                            </div>
                            <p className="mt-2 text-[12px] font-bold text-slate-800 leading-snug">{step.name}</p>
                            <p className="mt-1 text-[10.5px] text-slate-400 line-clamp-2">{step.action}</p>
                            <span className="mt-2 inline-block px-2 py-0.5 rounded-md bg-slate-50 border border-slate-200 text-[9.5px] font-bold text-slate-500 uppercase tracking-wider">
                              {step.service}
                            </span>
                          </div>
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Execution telemetry */}
              <div className="rounded-3xl bg-[#0B0F19] border border-white/10 p-5 shadow-[0_20px_50px_-20px_rgba(11,15,25,0.6)]">
                <div className="flex items-center justify-between">
                  <h4 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-emerald-300">
                    <Terminal className="w-3.5 h-3.5" /> Execution telemetry
                  </h4>
                  <span className="text-[10px] nxs-mono text-slate-500">
                    {logs.length > 0 ? `${logs.length} / ${selected.steps.length} steps` : 'idle'}
                  </span>
                </div>
                <div ref={logRef} className="mt-3 h-44 overflow-y-auto nxs-scroll space-y-1.5 pr-1">
                  {logs.length === 0 && (
                    <p className="text-[12px] text-slate-500 nxs-mono leading-relaxed py-6 text-center">
                      Press “Run workflow” — each step hands off to the next through the agent mesh.
                    </p>
                  )}
                  {logs.map((log, i) => (
                    <div key={i} className="flex gap-2.5 text-[11.5px] nxs-mono leading-relaxed animate-[nxs-bus-in_0.3s_ease-out]">
                      <span className="text-slate-600 shrink-0">{log.timestamp}</span>
                      <span className="text-emerald-400 shrink-0">✓</span>
                      <span className="text-slate-300 break-words">
                        <span className="text-emerald-300 font-bold">{log.name}</span>
                        <span className="text-slate-500"> · {log.service} · </span>
                        {log.message}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && !error && workflows.length === 0 && (
        <div className="mt-6 rounded-3xl bg-white border border-dashed border-slate-300 p-10 text-center">
          <WorkflowIcon className="w-9 h-9 text-slate-300 mx-auto" />
          <p className="mt-3 text-[14px] font-bold text-slate-700">No workflows registered</p>
        </div>
      )}
    </ViewShell>
  );
};
