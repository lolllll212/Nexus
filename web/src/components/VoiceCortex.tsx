import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Volume2, VolumeX, Sparkles, AudioWaveform as Waveform } from 'lucide-react';

interface VoiceCortexProps {
  onCommand: (command: string, rawText: string) => void;
  onOpenJarvisWithPrompt: (prompt: string) => void;
  voiceEnabled: boolean;
  onToggleVoice: () => void;
}

export const VoiceCortex: React.FC<VoiceCortexProps> = ({
  onCommand,
  onOpenJarvisWithPrompt,
  voiceEnabled,
  onToggleVoice,
}) => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [speechSupported, setSpeechSupported] = useState(false);

  const recognitionRef = useRef<any>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    // Check Web Speech Recognition support
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      setSpeechSupported(true);
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event: any) => {
        let currentTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          currentTranscript += event.results[i][0].transcript;
        }
        setTranscript(currentTranscript);

        // Check if final
        const lastResult = event.results[event.results.length - 1];
        if (lastResult.isFinal) {
          handleVoiceCommand(currentTranscript);
        }
      };

      recognition.onerror = (e: any) => {
        console.warn('Speech recognition error:', e);
      };

      recognition.onend = () => {
        if (isListening) {
          try {
            recognition.start();
          } catch (e) {}
        }
      };

      recognitionRef.current = recognition;
    }
  }, [isListening]);

  // Voice command dispatcher
  const handleVoiceCommand = (text: string) => {
    const lower = text.toLowerCase().trim();

    if (lower.includes('research') || lower.includes('search')) {
      const topic = lower.replace(/.*(?:research|search for|search)\s+/i, '');
      onCommand('RESEARCH', topic);
    } else if (lower.includes('github') || lower.includes('repo')) {
      onCommand('GITHUB', text);
    } else if (lower.includes('email') || lower.includes('mail') || lower.includes('gmail')) {
      onCommand('GMAIL', text);
    } else if (lower.includes('workflow') || lower.includes('pipeline')) {
      onCommand('WORKFLOW', text);
    } else if (lower.includes('camera') || lower.includes('vision') || lower.includes('gesture')) {
      onCommand('VISION', text);
    } else if (lower.includes('fit') || lower.includes('2d') || lower.includes('recenter')) {
      onCommand('FIT', text);
    } else {
      // Direct question to Jarvis
      onOpenJarvisWithPrompt(text);
    }
  };

  const toggleListening = () => {
    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      setTranscript('');
    } else {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch (e) {}
      } else {
        // Fallback simulation of voice input
        simulateVoiceInput();
      }
      setIsListening(true);
    }
  };

  const simulateVoiceInput = () => {
    const simulatedPhrases = [
      "Jarvis, research autonomous AI agent swarms",
      "Jarvis, summarize my unread emails",
      "Jarvis, check latest GitHub pull requests",
      "Jarvis, fit graph to 2D view",
      "Jarvis, analyze AI Workshop hub",
    ];
    const phrase = simulatedPhrases[Math.floor(Math.random() * simulatedPhrases.length)];
    setTranscript("Listening...");
    setTimeout(() => {
      setTranscript(phrase);
      setTimeout(() => {
        handleVoiceCommand(phrase);
        setIsListening(false);
        setTranscript('');
      }, 1500);
    }, 1200);
  };

  // Sinusoidal wave animation when listening
  useEffect(() => {
    if (!isListening) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let step = 0;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      step += 0.08;

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

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [isListening]);

  return (
    <>
      {/* Floating Microphone HUD Button */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3.5 py-2 rounded-full glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_8px_32px_rgba(0,0,0,0.7),0_0_20px_rgba(0,240,255,0.15)] select-none">
        <button
          onClick={toggleListening}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-mono font-medium transition-all ${
            isListening
              ? 'bg-cyan-500 text-black shadow-[0_0_15px_#00f0ff] animate-pulse'
              : 'bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-400/50 text-cyan-200'
          }`}
          title={isListening ? "Listening... Click to stop" : "Voice STT: Click or speak to J.A.R.V.I.S."}
        >
          {isListening ? <Mic className="w-4 h-4" /> : <Mic className="w-4 h-4 text-cyan-400" />}
          <span>{isListening ? 'LISTENING...' : 'VOICE CORTEX'}</span>
        </button>

        {isListening && (
          <canvas ref={canvasRef} width={80} height={20} className="block mx-1" />
        )}

        <div className="w-[1px] h-4 bg-cyan-500/20 mx-0.5"></div>

        {/* Vocal TTS Toggle */}
        <button
          onClick={onToggleVoice}
          className={`p-1.5 rounded-full transition-colors ${
            voiceEnabled
              ? 'text-cyan-400 bg-cyan-950/60 border border-cyan-500/40 shadow-[0_0_8px_rgba(0,240,255,0.3)]'
              : 'text-slate-500 hover:text-slate-300'
          }`}
          title={voiceEnabled ? "Mute vocal audio responses" : "Enable spoken voice responses (TTS)"}
        >
          {voiceEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
        </button>
      </div>

      {/* Live Transcript Notification Banner */}
      {isListening && transcript && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-xl bg-black/90 border border-cyan-400/50 shadow-[0_0_20px_rgba(0,240,255,0.3)] text-xs font-mono text-cyan-200 flex items-center gap-2 max-w-lg truncate animate-in slide-in-from-bottom-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
          <span className="text-slate-400">Heard:</span>
          <span className="text-white font-bold truncate">"{transcript}"</span>
        </div>
      )}
    </>
  );
};
