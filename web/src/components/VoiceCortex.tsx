import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Mic, 
  MicOff, 
  Volume2, 
  VolumeX, 
  Sparkles, 
  Loader2, 
  Volume1,
  Radio
} from 'lucide-react';
import { AgentStatus } from '../types';
import { stopAnySpeaking, speakWithStatus } from '../utils/voiceManager';

interface VoiceCortexProps {
  onCommand: (command: string, rawText: string) => void;
  onOpenJarvisWithPrompt?: (prompt: string) => void;
  onOpenPrompt?: (prompt: string) => void;
  voiceEnabled: boolean;
  onToggleVoice: () => void;
  agentStatus: AgentStatus;
  onStatusChange: (status: AgentStatus) => void;
}

export const VoiceCortex: React.FC<VoiceCortexProps> = ({
  onCommand,
  onOpenJarvisWithPrompt,
  onOpenPrompt,
  voiceEnabled,
  onToggleVoice,
  agentStatus,
  onStatusChange,
}) => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [speechSupported, setSpeechSupported] = useState(false);

  const recognitionRef = useRef<any>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const simTimeoutRef = useRef<any>(null);
  const animFrameRef = useRef<number | null>(null);

  // Keep ref to latest agentStatus and callbacks to prevent stale closures
  const agentStatusRef = useRef<AgentStatus>(agentStatus);
  useEffect(() => {
    agentStatusRef.current = agentStatus;
  }, [agentStatus]);

  const dispatchPrompt = onOpenPrompt || onOpenJarvisWithPrompt || (() => {});

  // ── Bulletproof Cleanup Helper for SpeechRecognition ──────────────────────
  const abortMicrophone = useCallback(() => {
    const rec = recognitionRef.current;
    if (rec) {
      try {
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        rec.onstart = null;
        rec.abort();
      } catch (_) {}
      recognitionRef.current = null;
    }
    if (simTimeoutRef.current) {
      clearTimeout(simTimeoutRef.current);
      simTimeoutRef.current = null;
    }
    setIsListening(false);
    setTranscript('');
  }, []);

  // ── FIX 1: Programmatically disable mic the exact moment agent starts thinking or speaking
  useEffect(() => {
    if (agentStatus === 'thinking' || agentStatus === 'speaking') {
      abortMicrophone();
    }
  }, [agentStatus, abortMicrophone]);

  // ── Voice Command Dispatcher ──────────────────────────────────────────────
  const handleVoiceCommand = useCallback((text: string) => {
    const cleanText = text.trim();
    if (!cleanText) {
      onStatusChange('idle');
      return;
    }

    // 1. Immediately abort mic listener BEFORE any AI processing or speech output
    abortMicrophone();

    // 2. Transition Agent Status to 'thinking'
    onStatusChange('thinking');

    // 3. Dispatch command to AI agent
    const lower = cleanText.toLowerCase();
    if (lower.includes('research') || lower.includes('search')) {
      const topic = lower.replace(/.*(?:research|search for|search)\s+/i, '');
      onCommand('RESEARCH', topic);
    } else if (lower.includes('github') || lower.includes('repo')) {
      onCommand('GITHUB', cleanText);
    } else if (lower.includes('email') || lower.includes('mail') || lower.includes('gmail')) {
      onCommand('GMAIL', cleanText);
    } else if (lower.includes('workflow') || lower.includes('pipeline')) {
      onCommand('WORKFLOW', cleanText);
    } else if (lower.includes('camera') || lower.includes('vision') || lower.includes('gesture')) {
      onCommand('VISION', cleanText);
    } else if (lower.includes('fit') || lower.includes('2d') || lower.includes('recenter')) {
      onCommand('FIT', cleanText);
    } else {
      // Direct prompt question to NEXUS AI
      dispatchPrompt(cleanText);
    }
  }, [abortMicrophone, onStatusChange, onCommand, dispatchPrompt]);

  // ── FIX 2: Single Lifecycle Controller with Full Cleanup Guarantee ────────
  useEffect(() => {
    // Check Web Speech API availability
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      setSpeechSupported(true);
    }

    // Cleanup when component unmounts
    return () => {
      abortMicrophone();
      stopAnySpeaking();
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [abortMicrophone]);

  // ── Start / Stop Listening Controller ─────────────────────────────────────
  const startListeningSession = useCallback(() => {
    // Do NOT allow microphone to start if agent is currently thinking or speaking
    if (agentStatusRef.current === 'thinking' || agentStatusRef.current === 'speaking') {
      return;
    }

    // Abort any prior instances before creating a new one
    abortMicrophone();
    stopAnySpeaking();

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognition.continuous = false; // Single utterance at a time to prevent infinite buffering
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onstart = () => {
          setIsListening(true);
          onStatusChange('listening');
        };

        recognition.onresult = (event: any) => {
          // If agent transitioned to thinking or speaking in the meantime, drop audio immediately
          if (agentStatusRef.current === 'thinking' || agentStatusRef.current === 'speaking') {
            abortMicrophone();
            return;
          }

          let currentTranscript = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            currentTranscript += event.results[i][0].transcript;
          }
          setTranscript(currentTranscript);

          // When utterance is final, execute and kill listener immediately
          const lastResult = event.results[event.results.length - 1];
          if (lastResult.isFinal) {
            handleVoiceCommand(currentTranscript);
          }
        };

        recognition.onerror = (e: any) => {
          console.warn('Speech recognition warning/error:', e?.error || e);
          abortMicrophone();
          onStatusChange('idle');
        };

        recognition.onend = () => {
          // Clean up instance on end
          if (recognitionRef.current === recognition) {
            recognitionRef.current = null;
          }
          setIsListening(false);
          if (agentStatusRef.current === 'listening') {
            onStatusChange('idle');
          }
        };

        recognitionRef.current = recognition;
        recognition.start();
        setIsListening(true);
        onStatusChange('listening');
      } catch (err) {
        console.warn('Could not start speech recognition, using fallback:', err);
        simulateVoiceInput();
      }
    } else {
      simulateVoiceInput();
    }
  }, [abortMicrophone, handleVoiceCommand, onStatusChange]);

  const simulateVoiceInput = useCallback(() => {
    setIsListening(true);
    onStatusChange('listening');
    setTranscript('Listening for vocal command...');

    const simulatedPhrases = [
      'NEXUS, research autonomous AI agent swarms',
      'NEXUS, summarize active second brain synapses',
      'NEXUS, check latest GitHub integration status',
      'NEXUS, fit graph to 2D view',
      'NEXUS, analyze AI Workshop hub architecture',
    ];
    const phrase = simulatedPhrases[Math.floor(Math.random() * simulatedPhrases.length)];

    simTimeoutRef.current = setTimeout(() => {
      setTranscript(phrase);
      simTimeoutRef.current = setTimeout(() => {
        handleVoiceCommand(phrase);
      }, 1200);
    }, 1000);
  }, [handleVoiceCommand, onStatusChange]);

  // ── Toggle Handler ────────────────────────────────────────────────────────
  const toggleListening = () => {
    // Prevent toggling while agent is actively thinking or speaking
    if (agentStatus === 'thinking' || agentStatus === 'speaking') {
      return;
    }

    if (isListening || agentStatus === 'listening') {
      abortMicrophone();
      onStatusChange('idle');
    } else {
      startListeningSession();
    }
  };

  // ── Sinusoidal Wave Animation on Canvas ───────────────────────────────────
  useEffect(() => {
    if (!isListening) {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let step = 0;
    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      step += 0.09;

      ctx.beginPath();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = '#00f0ff';
      ctx.shadowColor = '#00f0ff';
      ctx.shadowBlur = 8;

      const midY = canvas.height / 2;
      for (let x = 0; x < canvas.width; x++) {
        const y = midY + Math.sin(x * 0.08 + step) * 6 * Math.sin(x * 0.02);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      animFrameRef.current = requestAnimationFrame(render);
    };

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [isListening]);

  const isBusy = agentStatus === 'thinking' || agentStatus === 'speaking';

  return (
    <>
      {/* Floating Microphone HUD Button */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3.5 py-2 rounded-full glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_8px_32px_rgba(0,0,0,0.7),0_0_20px_rgba(0,240,255,0.15)] select-none font-mono">
        <button
          onClick={toggleListening}
          disabled={isBusy}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
            agentStatus === 'listening'
              ? 'bg-cyan-500 text-black shadow-[0_0_18px_#00f0ff] animate-pulse font-bold'
              : agentStatus === 'thinking'
              ? 'bg-purple-950/80 border border-purple-500/50 text-purple-300 opacity-90 cursor-not-allowed'
              : agentStatus === 'speaking'
              ? 'bg-amber-950/80 border border-amber-500/50 text-amber-300 opacity-90 cursor-not-allowed'
              : 'bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-400/50 text-cyan-200 shadow-sm'
          }`}
          title={
            agentStatus === 'listening'
              ? 'Listening... Click to stop'
              : agentStatus === 'thinking'
              ? 'Agent is thinking... Mic disabled to prevent echo loop'
              : agentStatus === 'speaking'
              ? 'Agent is speaking... Mic disabled to prevent echo loop'
              : 'Voice STT: Click or speak to NEXUS AI (Hotkey: M)'
          }
        >
          {agentStatus === 'listening' ? (
            <Mic className="w-4 h-4 text-black animate-bounce" />
          ) : agentStatus === 'thinking' ? (
            <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
          ) : agentStatus === 'speaking' ? (
            <Volume2 className="w-4 h-4 text-amber-400 animate-pulse" />
          ) : (
            <Mic className="w-4 h-4 text-cyan-400" />
          )}

          <span>
            {agentStatus === 'listening'
              ? 'LISTENING...'
              : agentStatus === 'thinking'
              ? 'THINKING...'
              : agentStatus === 'speaking'
              ? 'SPEAKING...'
              : 'VOICE CORTEX'}
          </span>
        </button>

        {isListening && (
          <canvas ref={canvasRef} width={76} height={20} className="block mx-1" />
        )}

        <div className="w-[1px] h-4 bg-cyan-500/20 mx-0.5" />

        {/* Vocal TTS Toggle */}
        <button
          onClick={onToggleVoice}
          className={`p-1.5 rounded-full transition-colors cursor-pointer ${
            voiceEnabled
              ? 'text-cyan-400 bg-cyan-950/60 border border-cyan-500/40 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
              : 'text-slate-500 hover:text-slate-300'
          }`}
          title={voiceEnabled ? 'Mute vocal audio responses' : 'Enable spoken voice responses (TTS)'}
        >
          {voiceEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
        </button>
      </div>

      {/* Live Transcript Notification Banner */}
      {isListening && transcript && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-xl bg-black/95 border border-cyan-400/50 shadow-[0_0_20px_rgba(0,240,255,0.3)] text-xs font-mono text-cyan-200 flex items-center gap-2 max-w-lg truncate animate-in slide-in-from-bottom-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
          <span className="text-slate-400">Heard:</span>
          <span className="text-white font-bold truncate">"{transcript}"</span>
        </div>
      )}
    </>
  );
};
