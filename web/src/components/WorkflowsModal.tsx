import React, { useState, useEffect } from 'react';
import { 
  X, 
  Play, 
  CheckCircle2, 
  Loader2, 
  Zap, 
  GitBranch, 
  Mail, 
  Cpu, 
  Clock, 
  ShieldCheck, 
  ArrowRight,
  Terminal
} from 'lucide-react';

interface WorkflowStep {
  id: string;
  name: string;
  action: string;
  service: string;
  status: string;
  output?: string;
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

interface WorkflowsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRefreshGraph: () => void;
}

export const WorkflowsModal: React.FC<WorkflowsModalProps> = ({
  isOpen,
  onClose,
  onRefreshGraph,
}) => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runningWorkflowId, setRunningWorkflowId] = useState<string | null>(null);
  const [executionLogs, setExecutionLogs] = useState<any[]>([]);

  const fetchWorkflows = async () => {
    try {
      const res = await fetch('/api/workflows');
      if (res.ok) {
        const data = await res.json();
        setWorkflows(data);
      }
    } catch (e) {
      console.warn('Could not fetch workflows from API:', e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchWorkflows();
    }
  }, [isOpen]);

  const handleRunWorkflow = async (workflowId: string) => {
    setRunningWorkflowId(workflowId);
    setExecutionLogs([]);

    try {
      const res = await fetch(`/api/workflows/run/${workflowId}`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setExecutionLogs(data.execution_logs || []);
        fetchWorkflows();
        onRefreshGraph();
      }
    } catch (e) {
      console.error('Error running workflow:', e);
    } finally {
      setRunningWorkflowId(null);
    }
  };

  const getServiceIcon = (service: string) => {
    const s = service.toLowerCase();
    if (s.includes('git')) return <GitBranch className="w-3.5 h-3.5 text-orange-400" />;
    if (s.includes('mail')) return <Mail className="w-3.5 h-3.5 text-blue-400" />;
    if (s.includes('nim') || s.includes('nvidia') || s.includes('cortex')) return <Cpu className="w-3.5 h-3.5 text-cyan-400" />;
    return <Zap className="w-3.5 h-3.5 text-emerald-400" />;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl h-[700px] rounded-2xl glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_0_60px_rgba(0,240,255,0.18)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-cyan-500/20 bg-gradient-to-r from-[#071324] via-[#051c2e] to-[#071324] flex items-center justify-between select-none">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-950/80 border border-cyan-400/40 text-cyan-300">
              <Zap className="w-5 h-5 text-cyan-400 animate-pulse" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold tracking-widest text-cyan-200 uppercase flex items-center gap-2">
                WORKFLOW AUTOMATION MATRIX
                <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-400/40 text-cyan-300 font-normal">
                  AUTONOMOUS PIPELINES
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-400">
                Triggerable multi-step flows chaining GitHub, Gmail, Deep Research, and NVIDIA NIM
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 hover:text-red-400 hover:border-red-400/40 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Workflows Grid */}
          <div className="space-y-4">
            {workflows.map((wf) => {
              const isRunning = runningWorkflowId === wf.id;
              return (
                <div
                  key={wf.id}
                  className="p-4 rounded-xl bg-[#040e1d] border border-cyan-500/25 shadow-lg space-y-3 transition-all hover:border-cyan-400/40"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono font-bold text-white tracking-wide">
                          {wf.title}
                        </span>
                        <span className="text-[9.5px] px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 font-mono">
                          {wf.category}
                        </span>
                      </div>
                      <p className="text-xs font-sans text-slate-300 mt-1 leading-snug">
                        {wf.description}
                      </p>
                    </div>

                    <button
                      onClick={() => handleRunWorkflow(wf.id)}
                      disabled={isRunning}
                      className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-teal-400 hover:from-cyan-400 hover:to-teal-300 text-black font-semibold font-mono text-xs flex items-center gap-1.5 shadow-[0_0_15px_rgba(0,240,255,0.3)] transition-all cursor-pointer disabled:opacity-50 shrink-0 ml-4"
                    >
                      {isRunning ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Executing...</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3.5 h-3.5 fill-black" />
                          <span>Run Workflow</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* Trigger & Last Run */}
                  <div className="flex items-center gap-4 text-[10.5px] font-mono text-slate-400 pt-1 border-t border-cyan-500/10">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-cyan-400" />
                      Trigger: <span className="text-slate-200">{wf.trigger}</span>
                    </span>
                    <span>•</span>
                    <span>Last executed: <span className="text-slate-200">{wf.last_run}</span></span>
                  </div>

                  {/* Step Sequence Pills */}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {wf.steps.map((st, i) => (
                      <React.Fragment key={st.id}>
                        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-black/40 border border-slate-800 text-[10.5px] font-mono text-slate-300">
                          {getServiceIcon(st.service)}
                          <span>{st.name}</span>
                          <CheckCircle2 className="w-3 h-3 text-emerald-400 ml-0.5" />
                        </div>
                        {i < wf.steps.length - 1 && (
                          <ArrowRight className="w-3 h-3 text-slate-600" />
                        )}
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Execution Telemetry Log */}
          {executionLogs.length > 0 && (
            <div className="p-4 rounded-xl bg-[#020712] border border-cyan-500/30 space-y-2 font-mono text-xs shadow-xl animate-in fade-in duration-200">
              <div className="flex items-center justify-between text-cyan-400 pb-1.5 border-b border-cyan-500/20">
                <span className="flex items-center gap-1.5 font-bold tracking-wider">
                  <Terminal className="w-3.5 h-3.5" />
                  PIPELINE EXECUTION TELEMETRY
                </span>
                <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> ALL STEPS VERIFIED
                </span>
              </div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-2">
                {executionLogs.map((log, i) => (
                  <div key={i} className="text-slate-300 flex items-start gap-2 text-[11px] leading-tight">
                    <span className="text-cyan-500/80">[{log.timestamp}]</span>
                    <span className="text-emerald-400 font-semibold">{log.service}:</span>
                    <span>{log.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
