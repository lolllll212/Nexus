import React, { useState, useEffect, useRef } from 'react';
import {
  Code,
  Terminal,
  Play,
  Copy,
  Check,
  Search,
  Globe,
  GitBranch,
  Sparkles,
  Maximize2,
  Minimize2,
  X,
  ChevronDown,
  ChevronRight,
  Send,
  Plus,
  Trash2,
  ArrowLeft,
  Cpu,
  Layers,
  FileCode,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  MessageSquare,
  Mic,
  MicOff,
  RefreshCw,
  Zap,
} from 'lucide-react';
import { playHudClick, playChime, playSuccessChime, playAlertChime } from '../utils/soundEffects';

interface ToolCallRecord {
  tool: string;
  args: Record<string, any>;
  result: Record<string, any>;
  duration_ms: number;
  status: string;
}

interface Artifact {
  id: string;
  title: string;
  type: string;
  language?: string;
  content: string;
  metadata?: Record<string, any>;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  tools_used?: ToolCallRecord[];
  artifacts?: Artifact[];
  timestamp: string;
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
}

interface ClaudeCodingStudioProps {
  onBackToSecondBrain: () => void;
  onOpenResearch?: (query: string) => void;
}

export const ClaudeCodingStudio: React.FC<ClaudeCodingStudioProps> = ({
  onBackToSecondBrain,
  onOpenResearch,
}) => {
  // Session management
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    return [
      {
        id: 'sess-default',
        title: 'New Coding Session',
        createdAt: new Date().toLocaleTimeString(),
        messages: [
          {
            id: 'msg-welcome',
            role: 'assistant',
            content:
              "Welcome to **NEXUS Coding & Research Studio**. I am equipped with autonomous Python sandboxing, real-time web crawler research, GitHub integration, and Claude-style thinking and artifacts.\n\nAsk me to solve algorithms, debug code, search documentation, or inspect repositories.",
            thinking:
              "System initialization: Sandbox active, LLM provider synchronized with NVIDIA NIM and ReAct executor, artifact rendering pipeline online.",
            timestamp: new Date().toLocaleTimeString(),
          },
        ],
      },
    ];
  });
  const [activeSessionId, setActiveSessionId] = useState<string>('sess-default');

  // Input & state
  const [inputPrompt, setInputPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState('meta/llama-3.3-70b-instruct');
  const [enableWebSearch, setEnableWebSearch] = useState(true);
  const [enableCodeExec, setEnableCodeExec] = useState(true);
  const [enableGithub, setEnableGithub] = useState(true);

  // Artifact & Split-view state
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [artifactTab, setArtifactTab] = useState<'code' | 'preview' | 'test' | 'research'>('code');
  const [isArtifactMaximized, setIsArtifactMaximized] = useState(false);
  const [sandboxOutput, setSandboxOutput] = useState<{ output: string; error?: string; duration?: number } | null>(null);
  const [isRunningCode, setIsRunningCode] = useState(false);

  // UI state
  const [collapsedThinking, setCollapsedThinking] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [templates, setTemplates] = useState<any[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages, isLoading]);

  useEffect(() => {
    fetch('/api/coding/templates')
      .then((res) => res.json())
      .then((data) => {
        if (data.templates) setTemplates(data.templates);
      })
      .catch(() => {});
  }, []);

  const handleNewChat = () => {
    playHudClick();
    const newSess: ChatSession = {
      id: `sess-${Date.now()}`,
      title: 'New Coding Session',
      createdAt: new Date().toLocaleTimeString(),
      messages: [
        {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: 'New coding workspace ready. How can I assist with your architecture, algorithms, or research?',
          timestamp: new Date().toLocaleTimeString(),
        },
      ],
    };
    setSessions((prev) => [newSess, ...prev]);
    setActiveSessionId(newSess.id);
    setActiveArtifact(null);
  };

  const handleSend = async (customPrompt?: string) => {
    const text = (customPrompt || inputPrompt).trim();
    if (!text || isLoading) return;

    playChime();
    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString(),
    };

    // Update session title if first user message
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === activeSessionId) {
          const isFirst = s.messages.filter((m) => m.role === 'user').length === 0;
          return {
            ...s,
            title: isFirst ? text.slice(0, 30) + '...' : s.title,
            messages: [...s.messages, userMsg],
          };
        }
        return s;
      })
    );

    setInputPrompt('');
    setIsLoading(true);

    try {
      const res = await fetch('/api/coding/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: text,
          session_id: activeSessionId,
          model: selectedModel,
          enable_web_search: enableWebSearch,
          enable_code_exec: enableCodeExec,
          enable_github: enableGithub,
          temperature: 0.3,
        }),
      });

      if (!res.ok) {
        throw new Error(`Coding assistant returned HTTP ${res.status}`);
      }

      const data = await res.json();
      const botMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        role: 'assistant',
        content: data.response,
        thinking: data.thinking,
        tools_used: data.tools_used || [],
        artifacts: data.artifacts || [],
        timestamp: new Date().toLocaleTimeString(),
      };

      setSessions((prev) =>
        prev.map((s) => {
          if (s.id === activeSessionId) {
            return {
              ...s,
              messages: [...s.messages, botMsg],
            };
          }
          return s;
        })
      );

      // Auto-open first artifact if produced
      if (data.artifacts && data.artifacts.length > 0) {
        setActiveArtifact(data.artifacts[0]);
        if (data.artifacts[0].type === 'html') {
          setArtifactTab('preview');
        } else if (data.artifacts[0].type === 'research') {
          setArtifactTab('research');
        } else {
          setArtifactTab('code');
        }
        playSuccessChime();
      }
    } catch (err: any) {
      playAlertChime();
      const errorMsg: ChatMessage = {
        id: `bot-err-${Date.now()}`,
        role: 'assistant',
        content: `**Execution Notice**: Error communicating with cortex: ${err.message}. Running in local emergency fallback mode.`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setSessions((prev) =>
        prev.map((s) => (s.id === activeSessionId ? { ...s, messages: [...s.messages, errorMsg] } : s))
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunCodeInSandbox = async (codeToRun: string) => {
    playHudClick();
    setIsRunningCode(true);
    setSandboxOutput(null);

    try {
      const res = await fetch('/api/coding/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: codeToRun }),
      });
      const data = await res.json();
      setSandboxOutput({
        output: data.output || (data.success ? 'Program executed successfully with no stdout.' : ''),
        error: data.error,
        duration: data.execution_time_ms,
      });
      setArtifactTab('test');
      if (data.success) {
        playSuccessChime();
      } else {
        playAlertChime();
      }
    } catch (err: any) {
      setSandboxOutput({ output: '', error: err.message });
      playAlertChime();
    } finally {
      setIsRunningCode(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    playHudClick();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleThinking = (msgId: string) => {
    playHudClick();
    setCollapsedThinking((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-[#111318] text-zinc-100 font-sans select-none overflow-hidden animate-fadeIn">
      {/* ── Top Navigation Bar ─────────────────────────────────────────── */}
      <header className="h-14 border-b border-zinc-800 bg-[#16181f]/90 backdrop-blur-md px-4 flex items-center justify-between shrink-0 z-20">
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              playHudClick();
              onBackToSecondBrain();
            }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-xs font-mono text-cyan-300 border border-zinc-700/80 transition-all cursor-pointer shadow-sm hover:border-cyan-500/50"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Second Brain OS</span>
          </button>

          <div className="h-4 w-px bg-zinc-800" />

          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f0ff] animate-pulse" />
            <span className="font-mono font-bold text-sm text-zinc-100 tracking-wider">
              NEXUS <span className="text-cyan-400">CODING STUDIO</span>
            </span>
            <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-950/70 text-cyan-300 border border-cyan-500/30">
              Claude 3.5 Sonnet / Llama 3.3
            </span>
          </div>
        </div>

        {/* Integration indicators & Model Selector */}
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-2 text-[11px] font-mono text-zinc-400">
            <span
              className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-colors ${
                enableCodeExec ? 'bg-emerald-950/50 border-emerald-500/40 text-emerald-300' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
              }`}
            >
              <Terminal className="w-3 h-3" />
              Python Sandbox
            </span>

            <span
              className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-colors ${
                enableWebSearch ? 'bg-blue-950/50 border-blue-500/40 text-blue-300' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
              }`}
            >
              <Globe className="w-3 h-3" />
              Web Research
            </span>

            <span
              className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-colors ${
                enableGithub ? 'bg-purple-950/50 border-purple-500/40 text-purple-300' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
              }`}
            >
              <GitBranch className="w-3 h-3" />
              GitHub
            </span>
          </div>

          {/* Model picker */}
          <div className="relative">
            <select
              value={selectedModel}
              onChange={(e) => {
                playHudClick();
                setSelectedModel(e.target.value);
              }}
              className="px-3 py-1.5 text-xs font-mono bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-200 focus:outline-none focus:border-cyan-500 cursor-pointer"
            >
              <option value="meta/llama-3.3-70b-instruct">Llama 3.3 70B (Primary)</option>
              <option value="nvidia/nemotron-4-340b-instruct">Nemotron 70B (Heavy Reasoning)</option>
              <option value="meta/llama-3.1-8b-instruct">Llama 3.1 8B (Fast Reflex)</option>
            </select>
          </div>
        </div>
      </header>

      {/* ── Main Workspace Body (Sidebar + Chat + Artifact Split-view) ───── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Sessions & Templates */}
        <aside className="w-64 border-r border-zinc-800 bg-[#14161d] flex flex-col justify-between shrink-0 hidden lg:flex select-none">
          {/* Top: New Chat & Sessions */}
          <div className="p-3 flex flex-col flex-1 overflow-hidden">
            <button
              onClick={handleNewChat}
              className="w-full py-2 px-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-mono text-xs flex items-center justify-between border border-zinc-700/80 transition-all cursor-pointer shadow-sm hover:border-cyan-500/40 mb-3"
            >
              <span className="flex items-center gap-2">
                <Plus className="w-4 h-4 text-cyan-400" />
                New Chat
              </span>
              <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 text-[10px] text-zinc-400 font-mono border border-zinc-800">
                ⌘K
              </kbd>
            </button>

            <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest px-2 mb-1.5 font-semibold">
              Recent Chats
            </div>

            <div className="flex-1 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => {
                    playHudClick();
                    setActiveSessionId(s.id);
                  }}
                  className={`group px-2.5 py-2 rounded-lg text-xs font-mono cursor-pointer flex items-center justify-between transition-all ${
                    s.id === activeSessionId
                      ? 'bg-zinc-800 text-cyan-300 font-semibold border border-zinc-700'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/60'
                  }`}
                >
                  <span className="truncate flex-1 flex items-center gap-2">
                    <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70" />
                    <span className="truncate">{s.title}</span>
                  </span>
                  {sessions.length > 1 && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSessions((prev) => prev.filter((item) => item.id !== s.id));
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Bottom: Quick Templates */}
          <div className="p-3 border-t border-zinc-800/80 bg-zinc-950/40">
            <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-2 font-semibold flex items-center gap-1.5">
              <Sparkles className="w-3 h-3 text-cyan-400" />
              Prompt Templates
            </div>
            <div className="space-y-1.5">
              {templates.slice(0, 3).map((tpl) => (
                <button
                  key={tpl.id}
                  onClick={() => handleSend(tpl.prompt)}
                  className="w-full text-left p-2 rounded-lg bg-zinc-900/80 hover:bg-zinc-800 border border-zinc-800/80 hover:border-cyan-500/30 text-[11px] font-mono text-zinc-300 transition-all truncate block cursor-pointer"
                >
                  <span className="font-semibold text-cyan-300 block truncate">{tpl.title}</span>
                  <span className="text-[10px] text-zinc-500 truncate block">{tpl.category}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* Center: Conversation Stream */}
        <section
          className={`flex-1 flex flex-col h-full bg-[#111318] relative transition-all duration-300 ${
            activeArtifact && !isArtifactMaximized ? 'w-1/2' : 'w-full'
          } ${activeArtifact && isArtifactMaximized ? 'hidden' : 'flex'}`}
        >
          {/* Messages Scroll Area */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 custom-scrollbar">
            {activeSession?.messages.map((msg) => (
              <div key={msg.id} className="max-w-3xl mx-auto space-y-3">
                {/* User Message */}
                {msg.role === 'user' ? (
                  <div className="flex justify-end">
                    <div className="max-w-[85%] px-4 py-3 rounded-2xl bg-zinc-800 border border-zinc-700/80 text-zinc-100 text-sm font-sans shadow-md">
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                      <span className="text-[10px] font-mono text-zinc-500 block text-right mt-1">
                        {msg.timestamp}
                      </span>
                    </div>
                  </div>
                ) : (
                  /* Assistant Message */
                  <div className="space-y-3">
                    {/* 1. Claude Thinking Block Accordion */}
                    {msg.thinking && (
                      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 overflow-hidden text-xs">
                        <button
                          onClick={() => toggleThinking(msg.id)}
                          className="w-full px-3.5 py-2 flex items-center justify-between text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors font-mono cursor-pointer"
                        >
                          <span className="flex items-center gap-2">
                            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                            <span>Thinking Process</span>
                          </span>
                          {collapsedThinking[msg.id] ? (
                            <ChevronRight className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                        </button>
                        {!collapsedThinking[msg.id] && (
                          <div className="px-3.5 py-2.5 text-zinc-400 border-t border-zinc-800/80 font-mono text-[11px] leading-relaxed bg-black/20 whitespace-pre-wrap">
                            {msg.thinking}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 2. Tool Execution Badges */}
                    {msg.tools_used && msg.tools_used.length > 0 && (
                      <div className="space-y-1.5">
                        {msg.tools_used.map((t, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs font-mono text-zinc-300"
                          >
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                            <span className="font-semibold text-emerald-300">Tool Executed: {t.tool}</span>
                            <span className="text-zinc-500 text-[10px]">({t.duration_ms}ms)</span>
                            <span className="ml-auto text-zinc-400 text-[10px]">
                              {JSON.stringify(t.result).slice(0, 45)}...
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 3. Assistant Markdown Content */}
                    <div className="p-4 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 text-zinc-200 text-sm leading-relaxed space-y-3">
                      <div className="whitespace-pre-wrap font-sans">{msg.content}</div>

                      {/* 4. Artifact Action Buttons */}
                      {msg.artifacts && msg.artifacts.length > 0 && (
                        <div className="pt-2 border-t border-zinc-800/80 flex flex-wrap gap-2">
                          {msg.artifacts.map((art) => (
                            <button
                              key={art.id}
                              onClick={() => {
                                playHudClick();
                                setActiveArtifact(art);
                                setArtifactTab(art.type === 'html' ? 'preview' : art.type === 'research' ? 'research' : 'code');
                              }}
                              className="px-3 py-1.5 rounded-xl bg-cyan-950/70 hover:bg-cyan-900/80 border border-cyan-500/40 text-cyan-200 text-xs font-mono flex items-center gap-1.5 transition-all shadow-sm cursor-pointer"
                            >
                              <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                              <span>View Artifact: {art.title}</span>
                              <ExternalLink className="w-3 h-3 text-cyan-400 opacity-60 ml-0.5" />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="max-w-3xl mx-auto flex items-center gap-3 p-4 rounded-xl bg-zinc-900/50 border border-zinc-800">
                <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                <span className="text-xs font-mono text-zinc-400">
                  NEXUS Reasoning & Chaining Tools...
                </span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Box Footer */}
          <div className="p-4 border-t border-zinc-800 bg-[#16181f]/80 backdrop-blur-md">
            <div className="max-w-3xl mx-auto space-y-2">
              <div className="flex items-center justify-between text-xs font-mono px-1">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setEnableCodeExec(!enableCodeExec)}
                    className={`px-2 py-0.5 rounded text-[10.5px] border transition-colors cursor-pointer ${
                      enableCodeExec ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
                    }`}
                  >
                    ⚡ Sandbox
                  </button>
                  <button
                    onClick={() => setEnableWebSearch(!enableWebSearch)}
                    className={`px-2 py-0.5 rounded text-[10.5px] border transition-colors cursor-pointer ${
                      enableWebSearch ? 'bg-blue-950/60 border-blue-500/50 text-blue-300' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
                    }`}
                  >
                    🌐 Web Search
                  </button>
                  <button
                    onClick={() => setEnableGithub(!enableGithub)}
                    className={`px-2 py-0.5 rounded text-[10.5px] border transition-colors cursor-pointer ${
                      enableGithub ? 'bg-purple-950/60 border-purple-500/50 text-purple-300' : 'bg-zinc-900 border-zinc-800 text-zinc-500'
                    }`}
                  >
                    🐙 GitHub
                  </button>
                </div>
                <span className="text-[10px] text-zinc-500">Return to send · Shift+Return for newline</span>
              </div>

              {/* Textarea & Transmit Button */}
              <div className="relative flex items-end gap-2 bg-zinc-900 border border-zinc-700/80 rounded-2xl p-2 focus-within:border-cyan-500/80 focus-within:ring-1 focus-within:ring-cyan-500/50 transition-all shadow-inner">
                <textarea
                  value={inputPrompt}
                  onChange={(e) => setInputPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Ask a coding question, request an algorithm, test code in sandbox, or search docs..."
                  rows={2}
                  className="flex-1 bg-transparent border-0 text-sm font-sans text-zinc-100 placeholder:text-zinc-500 focus:outline-none resize-none px-2 py-1 max-h-36"
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!inputPrompt.trim() || isLoading}
                  className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-teal-400 hover:from-cyan-400 hover:to-teal-300 disabled:opacity-40 text-black font-semibold font-mono text-xs flex items-center gap-1.5 shadow-[0_0_12px_rgba(0,240,255,0.35)] transition-all cursor-pointer disabled:cursor-not-allowed shrink-0"
                >
                  <span>Transmit</span>
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* ── Right Side: Claude Artifacts Split-View Panel ───────────── */}
        {activeArtifact && (
          <aside
            className={`border-l border-zinc-800 bg-[#12141c] flex flex-col h-full transition-all duration-300 z-10 ${
              isArtifactMaximized ? 'w-full' : 'w-full md:w-1/2'
            }`}
          >
            {/* Artifact Top Bar */}
            <div className="h-12 border-b border-zinc-800 px-4 bg-zinc-900/70 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-cyan-400" />
                <span className="font-mono font-bold text-xs text-zinc-200 truncate max-w-xs">
                  {activeArtifact.title}
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 uppercase">
                  {activeArtifact.language || activeArtifact.type}
                </span>
              </div>

              {/* Tab Selector & Controls */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setArtifactTab('code')}
                  className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                    artifactTab === 'code' ? 'bg-zinc-800 text-cyan-300 font-semibold' : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Code
                </button>
                {activeArtifact.type === 'html' && (
                  <button
                    onClick={() => setArtifactTab('preview')}
                    className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                      artifactTab === 'preview' ? 'bg-zinc-800 text-cyan-300 font-semibold' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    Preview
                  </button>
                )}
                <button
                  onClick={() => setArtifactTab('test')}
                  className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                    artifactTab === 'test' ? 'bg-zinc-800 text-cyan-300 font-semibold' : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Sandbox
                </button>

                <div className="h-3 w-px bg-zinc-800 mx-1" />

                <button
                  onClick={() => setIsArtifactMaximized(!isArtifactMaximized)}
                  className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
                  title={isArtifactMaximized ? 'Restore View' : 'Maximize Artifact'}
                >
                  {isArtifactMaximized ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                </button>
                <button
                  onClick={() => setActiveArtifact(null)}
                  className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
                  title="Close Artifact Panel"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Artifact Content Area */}
            <div className="flex-1 overflow-hidden relative flex flex-col">
              {/* Tab 1: Code View */}
              {artifactTab === 'code' && (
                <div className="flex-1 flex flex-col overflow-hidden">
                  <div className="p-2 border-b border-zinc-800/80 bg-zinc-950/60 flex items-center justify-between text-xs font-mono">
                    <span className="text-zinc-500 text-[10px]">
                      {activeArtifact.metadata?.lines || activeArtifact.content.split('\n').length} lines · UTF-8
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleRunCodeInSandbox(activeArtifact.content)}
                        disabled={isRunningCode}
                        className="px-2.5 py-1 rounded-lg bg-emerald-950 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 text-[11px] font-mono flex items-center gap-1 transition-all cursor-pointer shadow-sm"
                      >
                        <Play className="w-3 h-3 text-emerald-400" />
                        <span>Run in Sandbox</span>
                      </button>

                      <button
                        onClick={() => copyToClipboard(activeArtifact.content, activeArtifact.id)}
                        className="px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] font-mono flex items-center gap-1 transition-colors cursor-pointer"
                      >
                        {copiedId === activeArtifact.id ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-400" />
                            <span>Copied!</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                  <pre className="flex-1 p-4 overflow-auto font-mono text-xs text-cyan-100 bg-[#0a0c10] leading-relaxed custom-scrollbar selection:bg-cyan-900">
                    <code>{activeArtifact.content}</code>
                  </pre>
                </div>
              )}

              {/* Tab 2: HTML Live Preview */}
              {artifactTab === 'preview' && (
                <div className="flex-1 bg-white overflow-hidden">
                  <iframe
                    title="Artifact Live Preview"
                    srcDoc={activeArtifact.content}
                    className="w-full h-full border-0"
                    sandbox="allow-scripts"
                  />
                </div>
              )}

              {/* Tab 3: Sandbox Test Runner Output */}
              {artifactTab === 'test' && (
                <div className="flex-1 p-4 bg-[#0a0c10] overflow-y-auto font-mono text-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <span className="text-zinc-400 font-semibold flex items-center gap-1.5">
                      <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                      Sandbox Execution Console
                    </span>
                    <button
                      onClick={() => handleRunCodeInSandbox(activeArtifact.content)}
                      disabled={isRunningCode}
                      className="px-2 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-500/40 text-[11px] flex items-center gap-1 cursor-pointer"
                    >
                      <Play className="w-2.5 h-2.5" />
                      {isRunningCode ? 'Running...' : 'Re-run'}
                    </button>
                  </div>

                  {sandboxOutput ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-[11px]">
                        {sandboxOutput.error ? (
                          <span className="text-red-400 flex items-center gap-1">
                            <AlertCircle className="w-3.5 h-3.5" /> Error Encountered
                          </span>
                        ) : (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Execution Nominal
                          </span>
                        )}
                        {sandboxOutput.duration && (
                          <span className="text-zinc-500">({sandboxOutput.duration}ms)</span>
                        )}
                      </div>

                      {sandboxOutput.output && (
                        <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-200 whitespace-pre-wrap leading-relaxed">
                          {sandboxOutput.output}
                        </div>
                      )}

                      {sandboxOutput.error && (
                        <div className="p-3 rounded-lg bg-red-950/40 border border-red-500/40 text-red-200 whitespace-pre-wrap leading-relaxed">
                          {sandboxOutput.error}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-zinc-500 py-8 text-center">
                      Click "Run in Sandbox" to execute this code inside the isolated Python environment.
                    </div>
                  )}
                </div>
              )}

              {/* Tab 4: Research Report View */}
              {artifactTab === 'research' && (
                <div className="flex-1 p-6 bg-[#0c0e14] overflow-y-auto text-zinc-200 text-xs leading-relaxed space-y-4">
                  <div className="p-4 rounded-xl bg-blue-950/30 border border-blue-500/30 font-mono">
                    <span className="text-blue-300 font-bold block mb-1">Autonomous Research Report</span>
                    <p className="text-zinc-300 text-[11px] whitespace-pre-wrap">{activeArtifact.content}</p>
                  </div>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};
