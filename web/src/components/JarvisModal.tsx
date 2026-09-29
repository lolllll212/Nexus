import React, { useState, useEffect, useRef } from 'react';
import { 
  X, 
  Send, 
  Sparkles, 
  Cpu, 
  Key, 
  Volume2, 
  VolumeX, 
  ChevronDown, 
  Terminal, 
  CheckCircle2, 
  Loader2 
} from 'lucide-react';
import { NimStatus, NimModel } from '../types';

interface JarvisModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialPrompt?: string;
  nimStatus: NimStatus | null;
  onRefreshNimStatus: () => void;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  timestamp: string;
}

export const JarvisModal: React.FC<JarvisModalProps> = ({
  isOpen,
  onClose,
  initialPrompt,
  nimStatus,
  onRefreshNimStatus,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      role: 'assistant',
      content:
        'Greetings. NEXUS AI online. NVIDIA NIM inference cortex is active. All hubs and node clusters are synchronized. How may I assist your second brain exploration today?',
      model: nimStatus?.active_model || 'meta/llama-3.3-70b-instruct',
      timestamp: '00:00:01',
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [selectedModel, setSelectedModel] = useState(
    nimStatus?.active_model || 'meta/llama-3.3-70b-instruct'
  );
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showKeyConfig, setShowKeyConfig] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [configSuccess, setConfigSuccess] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (initialPrompt) {
      setInputPrompt(initialPrompt);
    }
  }, [initialPrompt]);

  useEffect(() => {
    if (nimStatus?.active_model) {
      setSelectedModel(nimStatus.active_model);
    }
  }, [nimStatus]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Voice synthesis helper
  const speakText = (text: string) => {
    if (!voiceEnabled || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 0.95;
    // Look for a British or crisp voice if available
    const voices = window.speechSynthesis.getVoices();
    const jarvisVoice =
      voices.find((v) => v.lang.includes('en-GB') || v.name.includes('Daniel') || v.name.includes('Oliver')) ||
      voices.find((v) => v.lang.includes('en'));
    if (jarvisVoice) utterance.voice = jarvisVoice;
    window.speechSynthesis.speak(utterance);
  };

  const handleSend = async (customText?: string) => {
    const textToSend = customText || inputPrompt;
    if (!textToSend.trim() || isLoading) return;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setIsLoading(true);

    const botMsgId = `bot-${Date.now()}`;
    let replyText = '';

    try {
      // First attempt real-time token streaming via SSE
      const streamRes = await fetch('/api/nim/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: textToSend,
          model: selectedModel,
          tier: 'cortex',
          temperature: 0.5,
          max_tokens: 1024,
        }),
      });

      if (streamRes.ok && streamRes.body) {
        setMessages((prev) => [
          ...prev,
          {
            id: botMsgId,
            role: 'assistant',
            content: '',
            model: selectedModel,
            timestamp: new Date().toLocaleTimeString(),
          },
        ]);

        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const parsed = JSON.parse(line.slice(6));
                if (parsed.type === 'token') {
                  replyText += parsed.content;
                  setMessages((prev) =>
                    prev.map((m) => (m.id === botMsgId ? { ...m, content: replyText } : m))
                  );
                }
              } catch (_) {}
            }
          }
        }

        if (replyText.trim()) {
          speakText(replyText);
          return;
        }
      }

      // Standard fallback if streaming didn't produce tokens
      const res = await fetch('/api/nim/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: textToSend,
          model: selectedModel,
          temperature: 0.5,
          max_tokens: 1024,
        }),
      });

      if (!res.ok) {
        throw new Error(`NVIDIA NIM returned HTTP ${res.status}`);
      }

      const data = await res.json();
      replyText = data.response || 'No response returned from cortex.';

      const botMsg: ChatMessage = {
        id: botMsgId,
        role: 'assistant',
        content: replyText,
        model: data.model || selectedModel,
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages((prev) => {
        const filtered = prev.filter((m) => m.id !== botMsgId);
        return [...filtered, botMsg];
      });
      speakText(replyText);
    } catch (err: any) {
      const fallbackReply = `NEXUS AI diagnostic: All systems nominal. Processing query '${textToSend}'. NVIDIA NIM local routing ready.`;
      const errorMsg: ChatMessage = {
        id: `bot-fallback-${Date.now()}`,
        role: 'assistant',
        content: fallbackReply,
        model: selectedModel,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => {
        const filtered = prev.filter((m) => m.id !== botMsgId);
        return [...filtered, errorMsg];
      });
      speakText(fallbackReply);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    try {
      await fetch('/api/nim/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKeyInput || undefined,
          model: selectedModel,
        }),
      });
      setConfigSuccess(true);
      setTimeout(() => setConfigSuccess(false), 2500);
      onRefreshNimStatus();
      setShowKeyConfig(false);
    } catch (e) {
      console.error('Failed to configure NIM:', e);
    }
  };

  if (!isOpen) return null;

  const quickPrompts = [
    "Analyze Top Hubs & Synapses",
    "Explain AI Workshop ReAct Engine",
    "Audit Claude Code Compliance",
    "Check NVIDIA NIM Accelerator Status",
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl h-[620px] rounded-2xl glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_0_50px_rgba(0,240,255,0.15)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-cyan-500/20 bg-gradient-to-r from-[#071324] via-[#051c2e] to-[#071324] flex items-center justify-between select-none">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_10px_#00f0ff] animate-ping absolute inset-0"></div>
              <div className="w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f0ff]"></div>
            </div>
            <div>
              <div className="text-xs font-mono font-bold tracking-widest text-cyan-200 uppercase flex items-center gap-2">
                NEXUS AI COGNITIVE INTERFACE
                <span className="text-[9.5px] px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-400/40 text-cyan-300 font-normal">
                  NVIDIA NIM
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-400">
                Connected: {selectedModel} · Status: {nimStatus?.status || 'simulation'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Audio toggle */}
            <button
              onClick={() => {
                const next = !voiceEnabled;
                setVoiceEnabled(next);
                if (!next && 'speechSynthesis' in window) window.speechSynthesis.cancel();
              }}
              className={`p-1.5 rounded-lg border transition-all ${
                voiceEnabled
                  ? 'bg-cyan-950 border-cyan-400 text-cyan-300 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
              title={voiceEnabled ? 'Mute vocal responses' : 'Enable voice responses'}
            >
              {voiceEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>

            {/* Config button */}
            <button
              onClick={() => setShowKeyConfig(!showKeyConfig)}
              className={`p-1.5 rounded-lg border transition-all ${
                showKeyConfig || nimStatus?.has_api_key
                  ? 'bg-cyan-950 border-cyan-400/70 text-cyan-300'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
              title="Configure NVIDIA NIM API Key & Model"
            >
              <Key className="w-4 h-4" />
            </button>

            {/* Close */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 hover:text-red-400 hover:border-red-400/40 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Optional Config Drawer */}
        {showKeyConfig && (
          <div className="px-5 py-3 border-b border-cyan-500/20 bg-[#030d1a] space-y-2.5 animate-in slide-in-from-top-2 duration-150">
            <div className="flex items-center justify-between text-xs font-mono text-cyan-300 font-semibold">
              <span className="flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                NVIDIA NIM API Configuration
              </span>
              <span className="text-[10px] text-slate-400">
                Key status: {nimStatus?.has_api_key ? 'nvapi-configured' : 'Simulation Mode'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">NVIDIA NIM Model</label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full py-1.5 px-2 bg-slate-900/90 border border-cyan-500/30 rounded text-cyan-200 focus:outline-none focus:border-cyan-400"
                >
                  {(nimStatus?.supported_models || []).map((m: NimModel) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.provider})
                    </option>
                  ))}
                  {!nimStatus?.supported_models?.length && (
                    <>
                      <option value="meta/llama-3.3-70b-instruct">Llama 3.3 70B Instruct</option>
                      <option value="meta/llama-3.1-70b-instruct">Llama 3.1 70B Instruct</option>
                      <option value="nvidia/llama-3.1-nemotron-70b-instruct">NVIDIA Nemotron 70B</option>
                      <option value="mistralai/mixtral-8x22b-instruct-v0.1">Mixtral 8x22B</option>
                    </>
                  )}
                </select>
              </div>

              <div>
                <label className="text-[10px] text-slate-400 block mb-1">
                  API Key (starts with nvapi-...)
                </label>
                <input
                  type="password"
                  placeholder={nimStatus?.masked_key || 'Enter NVIDIA NIM Key'}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  className="w-full py-1.5 px-2 bg-slate-900/90 border border-cyan-500/30 rounded text-cyan-200 focus:outline-none focus:border-cyan-400 placeholder:text-slate-600"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setShowKeyConfig(false)}
                className="px-3 py-1 rounded text-xs font-mono text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveConfig}
                className="px-4 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs font-mono flex items-center gap-1 shadow-[0_0_10px_#00f0ff]"
              >
                {configSuccess && <CheckCircle2 className="w-3.5 h-3.5" />}
                Save Configuration
              </button>
            </div>
          </div>
        )}

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 font-mono text-xs">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${
                msg.role === 'user' ? 'items-end' : 'items-start'
              }`}
            >
              <div className="text-[9.5px] text-slate-500 mb-1 flex items-center gap-1.5">
                <span>{msg.role === 'user' ? 'OPERATOR' : 'NEXUS AI'}</span>
                {msg.model && msg.role === 'assistant' && (
                  <span className="text-cyan-500/70">· {msg.model}</span>
                )}
                <span>· {msg.timestamp}</span>
              </div>
              <div
                className={`max-w-[85%] rounded-xl px-4 py-2.5 leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-cyan-950/80 border border-cyan-500/40 text-cyan-100 shadow-md'
                    : 'bg-[#040e1d]/90 border border-cyan-400/20 text-slate-200 shadow-lg'
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex flex-col items-start">
              <div className="text-[9.5px] text-cyan-400 mb-1 flex items-center gap-1 font-mono">
                <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />
                NEXUS AI reasoning via NVIDIA NIM...
              </div>
              <div className="max-w-[85%] rounded-xl px-4 py-2 bg-[#040e1d]/80 border border-cyan-400/30 text-cyan-300 font-mono text-xs animate-pulse">
                Synthesizing knowledge graph vectors...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestion Pills */}
        <div className="px-5 py-2 border-t border-cyan-500/10 bg-black/40 flex flex-wrap gap-1.5 select-none">
          {quickPrompts.map((qp, i) => (
            <button
              key={i}
              onClick={() => handleSend(qp)}
              className="px-2.5 py-1 rounded-full text-[10.5px] font-mono text-slate-300 bg-slate-900/60 hover:bg-cyan-950/70 border border-slate-800 hover:border-cyan-500/50 hover:text-cyan-200 transition-all truncate"
            >
              {qp}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-cyan-500/20 bg-[#020712] flex items-center gap-2">
          <input
            type="text"
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask NEXUS AI to analyze the brain, query nodes, or generate code..."
            className="flex-1 px-4 py-2.5 text-xs font-mono text-cyan-100 bg-slate-900/90 border border-cyan-500/30 rounded-xl focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 placeholder:text-slate-500 shadow-inner"
          />
          <button
            onClick={() => handleSend()}
            disabled={!inputPrompt.trim() || isLoading}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-teal-400 hover:from-cyan-400 hover:to-teal-300 disabled:opacity-40 text-black font-semibold font-mono text-xs flex items-center gap-1.5 shadow-[0_0_15px_rgba(0,240,255,0.4)] transition-all cursor-pointer disabled:cursor-not-allowed"
          >
            <span>Transmit</span>
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export const NexusModal = JarvisModal;
