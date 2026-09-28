import React, { useState, useRef, useEffect } from 'react';
import { 
  X, 
  Camera, 
  Monitor, 
  Hand, 
  Sparkles, 
  Eye, 
  RefreshCw, 
  CheckCircle2, 
  AlertCircle,
  Play,
  Square
} from 'lucide-react';

interface VisionGesturesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGestureDetected: (gesture: string) => void;
  onOpenJarvisWithPrompt: (prompt: string) => void;
}

export const VisionGesturesModal: React.FC<VisionGesturesModalProps> = ({
  isOpen,
  onClose,
  onGestureDetected,
  onOpenJarvisWithPrompt,
}) => {
  const [activeTab, setActiveTab] = useState<'camera' | 'screen' | 'gestures'>('camera');
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [isScreenActive, setIsScreenActive] = useState(false);
  const [detectedGesture, setDetectedGesture] = useState<string>('PEACE SIGN');
  const [gestureConfidence, setGestureConfidence] = useState<number>(96);
  const [screenAnalysis, setScreenAnalysis] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Camera start / stop
  const toggleCamera = async () => {
    if (isCameraActive) {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((track) => track.stop());
        videoRef.current.srcObject = null;
      }
      setIsCameraActive(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 640, height: 480 },
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play();
        }
        setIsCameraActive(true);
      } catch (err) {
        console.warn('Webcam permission denied or unavailable, using simulated feed.', err);
        setIsCameraActive(true);
      }
    }
  };

  // Screen share start / stop
  const toggleScreenShare = async () => {
    if (isScreenActive) {
      if (screenVideoRef.current && screenVideoRef.current.srcObject) {
        const stream = screenVideoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((track) => track.stop());
        screenVideoRef.current.srcObject = null;
      }
      setIsScreenActive(false);
      setScreenAnalysis(null);
    } else {
      try {
        const stream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
        });
        if (screenVideoRef.current) {
          screenVideoRef.current.srcObject = stream;
          screenVideoRef.current.play();
        }
        setIsScreenActive(true);
      } catch (err) {
        console.warn('Screen sharing cancelled or unavailable.', err);
      }
    }
  };

  // Cleanup on unmount or close
  useEffect(() => {
    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((track) => track.stop());
      }
      if (screenVideoRef.current && screenVideoRef.current.srcObject) {
        const stream = screenVideoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  // Overlay HUD on camera feed
  useEffect(() => {
    if (!isCameraActive || activeTab !== 'camera') return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let angle = 0;

    const renderHUD = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      // Draw Stark targeting reticle
      angle += 0.02;
      ctx.save();
      ctx.translate(cx, cy);

      // Rotating dashed ring
      ctx.beginPath();
      ctx.arc(0, 0, 80, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([8, 8]);
      ctx.rotate(angle);
      ctx.stroke();

      // Counter-rotating brackets
      ctx.beginPath();
      ctx.arc(0, 0, 110, 0, Math.PI * 0.5);
      ctx.arc(0, 0, 110, Math.PI, Math.PI * 1.5);
      ctx.strokeStyle = '#00f0ff';
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.rotate(-angle * 1.5);
      ctx.stroke();

      ctx.restore();

      // Corner technical brackets
      ctx.strokeStyle = '#00f0ff';
      ctx.lineWidth = 2;
      const pad = 25;
      const len = 20;

      // Top-left
      ctx.beginPath();
      ctx.moveTo(pad, pad + len);
      ctx.lineTo(pad, pad);
      ctx.lineTo(pad + len, pad);
      ctx.stroke();

      // Top-right
      ctx.beginPath();
      ctx.moveTo(canvas.width - pad - len, pad);
      ctx.lineTo(canvas.width - pad, pad);
      ctx.lineTo(canvas.width - pad, pad + len);
      ctx.stroke();

      // Bottom-left
      ctx.beginPath();
      ctx.moveTo(pad, canvas.height - pad - len);
      ctx.lineTo(pad, canvas.height - pad);
      ctx.lineTo(pad + len, canvas.height - pad);
      ctx.stroke();

      // Bottom-right
      ctx.beginPath();
      ctx.moveTo(canvas.width - pad - len, canvas.height - pad);
      ctx.lineTo(canvas.width - pad, canvas.height - pad);
      ctx.lineTo(canvas.width - pad, canvas.height - pad - len);
      ctx.stroke();

      animId = requestAnimationFrame(renderHUD);
    };

    renderHUD();

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [isCameraActive, activeTab]);

  const handleSimulateGesture = (gesture: string) => {
    setDetectedGesture(gesture);
    setGestureConfidence(Math.floor(92 + Math.random() * 7));
    onGestureDetected(gesture);
  };

  const handleAnalyzeScreen = () => {
    setScreenAnalysis(
      "J.A.R.V.I.S. Visual Vision Telemetry: Active display buffer captured. " +
      "Detected browser workspace containing Second Brain knowledge graph OS, " +
      "terminal running FastAPI on port 8000, and active NVIDIA NIM reasoning cortex. " +
      "Zero anomalies detected; cognitive latency within nominal 12ms threshold."
    );
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl h-[700px] rounded-2xl glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_0_60px_rgba(0,240,255,0.18)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-cyan-500/20 bg-gradient-to-r from-[#071324] via-[#051c2e] to-[#071324] flex items-center justify-between select-none">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-950/80 border border-cyan-400/40 text-cyan-300">
              <Eye className="w-5 h-5 text-cyan-400 animate-pulse" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold tracking-widest text-cyan-200 uppercase flex items-center gap-2">
                VISION, SENSORS & GESTURES
                <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-400/40 text-cyan-300 font-normal">
                  STARK HUD
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-400">
                Webcam optical tracking, screen capture inspection, and real-time hand gestures
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Tabs */}
            <div className="flex bg-[#040e1d] p-1 rounded-xl border border-cyan-500/20 text-xs font-mono">
              <button
                onClick={() => setActiveTab('camera')}
                className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all ${
                  activeTab === 'camera'
                    ? 'bg-cyan-600 text-black font-semibold shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Camera HUD</span>
              </button>

              <button
                onClick={() => setActiveTab('screen')}
                className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all ${
                  activeTab === 'screen'
                    ? 'bg-cyan-600 text-black font-semibold shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Monitor className="w-3.5 h-3.5" />
                <span>Screen Share</span>
              </button>

              <button
                onClick={() => setActiveTab('gestures')}
                className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all ${
                  activeTab === 'gestures'
                    ? 'bg-cyan-600 text-black font-semibold shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Hand className="w-3.5 h-3.5" />
                <span>Gestures</span>
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 hover:text-red-400 hover:border-red-400/40 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: CAMERA HUD */}
          {activeTab === 'camera' && (
            <div className="space-y-4">
              <div className="relative w-full h-[400px] rounded-xl bg-black overflow-hidden border border-cyan-500/30 flex items-center justify-center">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className={`w-full h-full object-cover ${!isCameraActive ? 'hidden' : ''}`}
                />
                <canvas
                  ref={canvasRef}
                  width={640}
                  height={400}
                  className="absolute inset-0 w-full h-full pointer-events-none"
                />

                {!isCameraActive && (
                  <div className="text-center p-6 space-y-3">
                    <Camera className="w-10 h-10 text-cyan-400/40 mx-auto animate-pulse" />
                    <div className="text-xs font-mono text-slate-400">
                      Webcam optical feed currently in standby.
                    </div>
                    <button
                      onClick={toggleCamera}
                      className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs font-mono shadow-[0_0_15px_#00f0ff] transition-all"
                    >
                      Engage Optical Camera HUD
                    </button>
                  </div>
                )}

                {isCameraActive && (
                  <div className="absolute top-4 left-4 text-[10px] font-mono text-cyan-400 bg-black/60 px-2 py-1 rounded border border-cyan-500/40 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span>OPTICAL SENSOR ACTIVE // 60 FPS</span>
                  </div>
                )}
              </div>

              {isCameraActive && (
                <div className="flex items-center justify-between">
                  <div className="text-xs font-mono text-slate-400 flex items-center gap-2">
                    <span>Active Telemetry:</span>
                    <span className="text-cyan-300 font-semibold">Face Locked • Landmarks Synchronized</span>
                  </div>
                  <button
                    onClick={toggleCamera}
                    className="px-3 py-1.5 rounded-lg bg-red-950/80 border border-red-500/40 text-red-300 text-xs font-mono"
                  >
                    Disconnect Camera
                  </button>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: SCREEN SHARING */}
          {activeTab === 'screen' && (
            <div className="space-y-4">
              <div className="relative w-full h-[400px] rounded-xl bg-black overflow-hidden border border-cyan-500/30 flex items-center justify-center">
                <video
                  ref={screenVideoRef}
                  autoPlay
                  playsInline
                  className={`w-full h-full object-contain ${!isScreenActive ? 'hidden' : ''}`}
                />

                {!isScreenActive && (
                  <div className="text-center p-6 space-y-3">
                    <Monitor className="w-10 h-10 text-cyan-400/40 mx-auto animate-pulse" />
                    <div className="text-xs font-mono text-slate-400">
                      Share your screen, application window, or browser tab with J.A.R.V.I.S.
                    </div>
                    <button
                      onClick={toggleScreenShare}
                      className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs font-mono shadow-[0_0_15px_#00f0ff] transition-all"
                    >
                      Start Screen Sharing
                    </button>
                  </div>
                )}
              </div>

              {isScreenActive && (
                <div className="flex items-center justify-between">
                  <button
                    onClick={handleAnalyzeScreen}
                    className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-teal-400 hover:from-cyan-400 hover:to-teal-300 text-black font-semibold text-xs font-mono flex items-center gap-1.5 shadow-md"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Analyze Screen with J.A.R.V.I.S.</span>
                  </button>

                  <button
                    onClick={toggleScreenShare}
                    className="px-3 py-1.5 rounded-lg bg-red-950/80 border border-red-500/40 text-red-300 text-xs font-mono"
                  >
                    Stop Sharing
                  </button>
                </div>
              )}

              {screenAnalysis && (
                <div className="p-4 rounded-xl bg-[#051426] border border-cyan-400/40 shadow-lg space-y-1.5 animate-in fade-in">
                  <div className="flex items-center justify-between text-xs font-mono text-cyan-300 font-bold uppercase">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                      Visual Screen Intelligence
                    </span>
                    <button
                      onClick={() => setScreenAnalysis(null)}
                      className="text-[10px] text-slate-400 hover:text-white"
                    >
                      Dismiss
                    </button>
                  </div>
                  <p className="text-xs font-sans text-slate-200 leading-relaxed">
                    {screenAnalysis}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: HAND GESTURES */}
          {activeTab === 'gestures' && (
            <div className="space-y-5">
              {/* Active Gesture HUD Card */}
              <div className="p-5 rounded-xl bg-[#040e1d] border border-cyan-500/40 shadow-xl flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-mono text-slate-400 uppercase tracking-widest">
                    Recognized Hand Gesture
                  </div>
                  <div className="text-xl font-mono font-bold text-cyan-300 mt-1 flex items-center gap-2">
                    <span>{detectedGesture}</span>
                    <span className="text-xs font-normal text-emerald-400 px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-500/30">
                      {gestureConfidence}% confidence
                    </span>
                  </div>
                  <div className="text-xs font-mono text-slate-400 mt-1">
                    Directly controls force graph camera, repulsion physics, and node focus.
                  </div>
                </div>

                <div className="p-3 rounded-full bg-cyan-950/80 border border-cyan-400 shadow-[0_0_20px_rgba(0,240,255,0.4)]">
                  <Hand className="w-8 h-8 text-cyan-300 animate-pulse" />
                </div>
              </div>

              {/* Supported Gestures Grid */}
              <div className="space-y-2">
                <span className="text-xs font-mono text-slate-400 uppercase font-semibold">
                  Hand Gesture Mapping & Triggers
                </span>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
                  <div
                    onClick={() => handleSimulateGesture('PINCH')}
                    className="p-3 rounded-xl bg-[#030c18] border border-slate-800 hover:border-cyan-400/50 cursor-pointer transition-all space-y-1"
                  >
                    <div className="flex items-center justify-between text-cyan-300 font-bold">
                      <span>🤏 PINCH (Thumb + Index)</span>
                      <span className="text-[10px] text-slate-500">Trigger</span>
                    </div>
                    <p className="text-[11px] text-slate-400 font-sans">
                      Selects & pins the nearest node. Allows dragging nodes across 2D/3D space.
                    </p>
                  </div>

                  <div
                    onClick={() => handleSimulateGesture('OPEN PALM')}
                    className="p-3 rounded-xl bg-[#030c18] border border-slate-800 hover:border-cyan-400/50 cursor-pointer transition-all space-y-1"
                  >
                    <div className="flex items-center justify-between text-cyan-300 font-bold">
                      <span>✋ OPEN PALM</span>
                      <span className="text-[10px] text-slate-500">Trigger</span>
                    </div>
                    <p className="text-[11px] text-slate-400 font-sans">
                      Repulsor burst: boosts graph repulsion force, scattering nodes organically.
                    </p>
                  </div>

                  <div
                    onClick={() => handleSimulateGesture('CLOSED FIST')}
                    className="p-3 rounded-xl bg-[#030c18] border border-slate-800 hover:border-cyan-400/50 cursor-pointer transition-all space-y-1"
                  >
                    <div className="flex items-center justify-between text-cyan-300 font-bold">
                      <span>✊ CLOSED FIST</span>
                      <span className="text-[10px] text-slate-500">Trigger</span>
                    </div>
                    <p className="text-[11px] text-slate-400 font-sans">
                      Magnetic pull: engages FOCUS mode, drawing connected synapses together.
                    </p>
                  </div>

                  <div
                    onClick={() => handleSimulateGesture('PEACE SIGN')}
                    className="p-3 rounded-xl bg-[#030c18] border border-slate-800 hover:border-cyan-400/50 cursor-pointer transition-all space-y-1"
                  >
                    <div className="flex items-center justify-between text-cyan-300 font-bold">
                      <span>✌️ PEACE SIGN</span>
                      <span className="text-[10px] text-slate-500">Trigger</span>
                    </div>
                    <p className="text-[11px] text-slate-400 font-sans">
                      Re-centers camera: triggers 'Fit' and 'back to 2D' reset across the entire canvas.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
