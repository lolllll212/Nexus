import React, { useState } from 'react';
import { 
  Zap, 
  Play, 
  Pause, 
  RotateCcw, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  ChevronRight, 
  Layers, 
  Database, 
  ArrowRight,
  Share2,
  ExternalLink,
  Code,
  ShieldAlert,
  Send
} from 'lucide-react';
import { MOCK_WORKFLOW_STEPS } from '../data/nexusGraphData';
import { WorkflowStep } from '../types';

interface WorkflowCanvasViewProps {
  onInjectNewKnowledge: (title: string, data: any) => void;
  onOpenClaudeStudio: () => void;
}

export const WorkflowCanvasView: React.FC<WorkflowCanvasViewProps> = ({
  onInjectNewKnowledge,
  onOpenClaudeStudio,
}) => {
  const [steps, setSteps] = useState<WorkflowStep[]>(MOCK_WORKFLOW_STEPS);
  const [selectedStep, setSelectedStep] = useState<WorkflowStep>(steps[2]);
  const [isRunning, setIsRunning] = useState(false);
  const [executionOutput, setExecutionOutput] = useState<string>(
    'Workflow Pipeline: CI/CD Security Audit & Automated Patching\nStatus: Active Execution\nTotal Run Time: 2,092ms'
  );

  const handleRunWorkflow = () => {
    setIsRunning(true);
    setExecutionOutput('Initiating distributed multi-agent pipeline...\nTrigger: GitHub Push (sha=2b6b81a)\nExecuting Step 1/5: Webhook signature verification...');

    setTimeout(() => {
      setSteps((prev) =>
        prev.map((s, idx) => ({
          ...s,
          status: idx <= 3 ? 'completed' : idx === 4 ? 'running' : 'pending',
        }))
      );
      setExecutionOutput((prev) => prev + '\n✓ Step 1-3 Verified!\nExecuting Step 4: Streaming knowledge nodes to Neo4j...');
      setIsRunning(false);
    }, 2500);
  };

  const handleStepToMemory = () => {
    onInjectNewKnowledge(`Workflow Output: ${selectedStep.name}`, {
      step: selectedStep.name,
      agent: selectedStep.agent,
      tool: selectedStep.tool,
      output: selectedStep.output,
      timestamp: new Date().toISOString(),
    });
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#05070c] text-slate-100 font-mono overflow-hidden">
      {/* ── Top Header Controls ──────────────────────────────────────────────── */}
      <div className="p-4 border-b border-emerald-500/20 bg-slate-950/80 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-emerald-950/80 border border-emerald-400/40 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.25)]">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider">
                AUTONOMOUS WORKFLOW CANVAS
              </span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                PIPELINE #841
              </span>
            </div>
            <h2 className="text-sm font-semibold text-slate-100">
              CI/CD Autonomous Security Hardening & Knowledge Loop
            </h2>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRunWorkflow}
            disabled={isRunning}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-black font-semibold text-xs shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 fill-black" />
            <span>{isRunning ? 'Executing Pipeline...' : 'Run Workflow'}</span>
          </button>

          <button
            onClick={handleStepToMemory}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-cyan-300 border border-cyan-500/30 text-xs transition-all cursor-pointer"
          >
            <Database className="w-3.5 h-3.5 text-cyan-400" />
            <span>Convert Output to Knowledge Node</span>
          </button>
        </div>
      </div>

      {/* ── Main Canvas: Node Pipeline & Live Execution Ticker ───────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Workflow Pipeline Steps Diagram */}
        <div className="flex-1 p-8 overflow-y-auto bg-slate-950/30 flex flex-col justify-center items-center">
          <div className="w-full max-w-2xl space-y-4">
            <div className="text-center mb-6">
              <span className="text-xs text-slate-500 font-bold uppercase tracking-widest">
                Directed Workflow Execution Graph
              </span>
              <p className="text-xs text-slate-400 mt-1">
                Research → Knowledge → Workflow → Action → Memory
              </p>
            </div>

            {steps.map((step, idx) => {
              const isSelected = selectedStep.id === step.id;
              const isLast = idx === steps.length - 1;

              return (
                <div key={step.id} className="relative flex flex-col items-center">
                  <div
                    onClick={() => setSelectedStep(step)}
                    className={`w-full p-4 rounded-2xl border transition-all cursor-pointer flex items-center justify-between gap-4 ${
                      isSelected
                        ? 'bg-slate-900 border-emerald-400 shadow-[0_0_25px_rgba(16,185,129,0.25)]'
                        : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-xs font-bold font-mono text-emerald-400">
                        0{idx + 1}
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-100 font-mono">
                          {step.name}
                        </h4>
                        <div className="flex items-center gap-2 text-[10px] text-slate-400 mt-0.5">
                          <span className="text-purple-400 font-medium">{step.agent}</span>
                          <span>•</span>
                          <span className="text-amber-400">{step.tool}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-slate-500 font-mono">
                        {step.durationMs}ms
                      </span>
                      {step.status === 'completed' && (
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-500/40 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>DONE</span>
                        </span>
                      )}
                      {step.status === 'running' && (
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-500/40 animate-pulse flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <span>RUNNING</span>
                        </span>
                      )}
                      {step.status === 'pending' && (
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-slate-900 text-slate-500 border border-slate-800">
                          PENDING
                        </span>
                      )}
                    </div>
                  </div>

                  {!isLast && (
                    <div className="my-1 flex flex-col items-center">
                      <div className="w-[2px] h-4 bg-emerald-500/30"></div>
                      <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.8)]"></div>
                      <div className="w-[2px] h-4 bg-emerald-500/30"></div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Step Inspector & Terminal Output */}
        <div className="w-96 border-l border-slate-800 p-6 flex flex-col bg-slate-950/80">
          <div className="pb-3 border-b border-slate-800 mb-4 flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
              Step Inspector
            </span>
            <span className="text-[9px] text-slate-500">ID: {selectedStep.id}</span>
          </div>

          <div className="space-y-4 mb-6">
            <div>
              <span className="text-[9px] text-slate-500 uppercase block mb-1">STEP NAME</span>
              <p className="text-xs font-bold text-slate-200">{selectedStep.name}</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-[9px] text-slate-500 uppercase block mb-1">ASSIGNED AGENT</span>
                <p className="text-xs font-semibold text-purple-400">{selectedStep.agent}</p>
              </div>
              <div>
                <span className="text-[9px] text-slate-500 uppercase block mb-1">ACTIVE TOOL</span>
                <p className="text-xs font-semibold text-amber-400">{selectedStep.tool}</p>
              </div>
            </div>

            <div>
              <span className="text-[9px] text-slate-500 uppercase block mb-1">INPUT PAYLOAD</span>
              <div className="p-2.5 rounded-xl bg-black/60 border border-slate-800 text-[10px] text-slate-300 font-mono break-all">
                {selectedStep.input}
              </div>
            </div>

            <div>
              <span className="text-[9px] text-slate-500 uppercase block mb-1">EXECUTION OUTPUT</span>
              <div className="p-2.5 rounded-xl bg-black/60 border border-slate-800 text-[10px] text-emerald-300 font-mono break-all">
                {selectedStep.output}
              </div>
            </div>
          </div>

          {/* Live Pipeline Terminal Output */}
          <div className="mt-auto pt-4 border-t border-slate-800">
            <span className="text-[9px] text-slate-500 uppercase block mb-1.5 flex items-center gap-1.5">
              <Code className="w-3.5 h-3.5 text-cyan-400" />
              <span>Pipeline Live Log Stream</span>
            </span>
            <div className="p-3 rounded-xl bg-black border border-slate-800/80 text-[10px] text-slate-400 font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
              {executionOutput}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
