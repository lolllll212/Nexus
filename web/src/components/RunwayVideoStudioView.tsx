import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Play, 
  Pause, 
  RotateCcw, 
  Volume2, 
  VolumeX, 
  Maximize2, 
  Sparkles, 
  Film, 
  Camera, 
  Sliders, 
  Layers, 
  Eye, 
  Download, 
  Share2, 
  Zap, 
  Check, 
  Clock, 
  Plus, 
  ChevronRight, 
  Wand2, 
  Crosshair, 
  Grid, 
  Compass, 
  Scissors, 
  SkipBack, 
  SkipForward, 
  FastForward, 
  Cpu, 
  Video, 
  Flame 
} from 'lucide-react';
import { 
  VideoAspectRatio, 
  VideoResolution, 
  CameraMotionParams, 
  TimelineTrack, 
  TimelineClip, 
  VideoRenderTask 
} from '../types';
import { playHudClick, playChime, playSuccessChime } from '../utils/soundEffects';

interface RunwayVideoStudioViewProps {
  onInjectVideoIntoGraph: (title: string, prompt: string, metadata: any) => void;
  onOpenClaudeStudio?: () => void;
}

export const RunwayVideoStudioView: React.FC<RunwayVideoStudioViewProps> = ({
  onInjectVideoIntoGraph,
  onOpenClaudeStudio,
}) => {
  // ── Generation Settings ───────────────────────────────────────────────────
  const [model, setModel] = useState<'Gen-3 Alpha Turbo' | 'Gen-3 Alpha' | 'Gen-2 HD' | 'NEXUS Neural Video V2'>('Gen-3 Alpha Turbo');
  const [prompt, setPrompt] = useState(
    'Hyper-detailed cinematic tracking shot of futuristic quantum neural network matrix with bioluminescent nodes, volumetric laser fog, and anamorphic lens flares'
  );
  const [negativePrompt, setNegativePrompt] = useState('blurry, low resolution, artifacts, stutter, distorted text, overexposed');
  const [aspectRatio, setAspectRatio] = useState<VideoAspectRatio>('16:9');
  const [resolution, setResolution] = useState<VideoResolution>('1080p');
  const [durationSec, setDurationSec] = useState<number>(10);
  const [seed, setSeed] = useState<number>(4289104);
  const [isExpandingPrompt, setIsExpandingPrompt] = useState(false);
  const [stylePreset, setStylePreset] = useState<string>('Cinematic Photoreal');

  // ── 6-Axis Camera Motion Director ─────────────────────────────────────────
  const [camera, setCamera] = useState<CameraMotionParams>({
    pan: 4.5,
    tilt: -2.0,
    zoom: 3.0,
    roll: 1.0,
    speed: 1.2,
    motionBrush: 6.0,
    motionVectors: true,
  });

  // ── Player & Timecode State ───────────────────────────────────────────────
  const [isPlaying, setIsPlaying] = useState(true);
  const [currentTime, setCurrentTime] = useState<number>(2.45);
  const [totalDuration, setTotalDuration] = useState<number>(10.0);
  const [fps, setFps] = useState<24 | 60>(60);
  const [isLooping, setIsLooping] = useState(true);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(0.85);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [activeClipId, setActiveClipId] = useState<string>('clip-1');

  // ── Canvas Preview Refs ───────────────────────────────────────────────────
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // ── Render Queue & Asset Gallery ──────────────────────────────────────────
  const [renderTasks, setRenderTasks] = useState<VideoRenderTask[]>([
    {
      id: 'task-101',
      prompt: 'Quantum holographic cube floating in zero gravity with neon cyan emitter sparks',
      model: 'Gen-3 Alpha Turbo',
      ratio: '16:9',
      resolution: '4K',
      status: 'completed',
      progress: 100,
      durationSec: 10,
      timestamp: '2 mins ago',
      thumbnailUrl: 'linear-gradient(135deg, #09203f 0%, #537895 100%)',
    },
    {
      id: 'task-102',
      prompt: 'Hyper-detailed cinematic tracking shot of futuristic quantum neural network matrix',
      model: 'Gen-3 Alpha Turbo',
      ratio: '16:9',
      resolution: '1080p',
      status: 'rendering',
      progress: 68,
      durationSec: 10,
      timestamp: 'Just now',
      thumbnailUrl: 'linear-gradient(135deg, #05192d 0%, #00f0ff 100%)',
    },
  ]);

  const [assetGallery, setAssetGallery] = useState([
    {
      id: 'asset-1',
      title: 'Neural Core Genesis',
      prompt: 'Quantum synapse crystal firing electrical pulses inside deep subterranean server cathedral',
      ratio: '16:9' as VideoAspectRatio,
      resolution: '4K' as VideoResolution,
      duration: '10s',
      fps: 60,
      color: '#00f0ff',
      gradient: 'linear-gradient(135deg, #041426 0%, #00f0ff 100%)',
    },
    {
      id: 'asset-2',
      title: 'Subcortex Nebula',
      prompt: 'Volumetric purple dreaming particles consolidating into hexagonal grid geometry',
      ratio: '21:9' as VideoAspectRatio,
      resolution: '1080p' as VideoResolution,
      duration: '8s',
      fps: 60,
      color: '#a855f7',
      gradient: 'linear-gradient(135deg, #1e0836 0%, #a855f7 100%)',
    },
    {
      id: 'asset-3',
      title: 'Cybernetic Matrix Drone',
      prompt: 'FPV flight through illuminated optical fiber server racks with anamorphic flare',
      ratio: '9:16' as VideoAspectRatio,
      resolution: '1080p' as VideoResolution,
      duration: '5s',
      fps: 24,
      color: '#10b981',
      gradient: 'linear-gradient(135deg, #02231c 0%, #10b981 100%)',
    },
  ]);

  // ── Multi-Track Timeline Data ─────────────────────────────────────────────
  const [timelineTracks, setTimelineTracks] = useState<TimelineTrack[]>([
    {
      id: 'track-video',
      name: 'V1 Video (Gen-3)',
      type: 'video',
      clips: [
        { id: 'clip-1', title: 'Neural Matrix A', start: 0, duration: 5.0, color: '#00f0ff' },
        { id: 'clip-2', title: 'Quantum Synapse B', start: 5.0, duration: 5.0, color: '#0284c7' },
      ],
    },
    {
      id: 'track-keyframes',
      name: 'Cam Motion & Vectors',
      type: 'keyframes',
      clips: [
        { id: 'kf-1', title: 'Pan: +4.5 · Tilt: -2.0', start: 0, duration: 3.5, color: '#f59e0b' },
        { id: 'kf-2', title: 'Dolly Zoom In +3.0', start: 3.5, duration: 6.5, color: '#ec4899' },
      ],
    },
    {
      id: 'track-audio',
      name: 'A1 Voice Cortex Audio',
      type: 'audio',
      clips: [
        { id: 'aud-1', title: 'NEXUS Spoken Synthesis (British Vocal)', start: 0.5, duration: 8.5, color: '#10b981' },
      ],
    },
    {
      id: 'track-fx',
      name: 'FX Motion Brush',
      type: 'effects',
      clips: [
        { id: 'fx-1', title: 'Volumetric Laser Fog Mask', start: 1.0, duration: 7.0, color: '#8b5cf6' },
      ],
    },
  ]);

  // ── Camera Motion Presets ─────────────────────────────────────────────────
  const motionPresets = [
    { name: 'Orbital Pan', pan: 6.5, tilt: 0.5, zoom: 0.5, roll: 0, speed: 1.2 },
    { name: 'Dolly Zoom / Vertigo', pan: 0, tilt: 0, zoom: 7.5, roll: 0, speed: 1.5 },
    { name: 'FPV Drone Dive', pan: 3.0, tilt: -7.5, zoom: 5.0, roll: 3.5, speed: 2.0 },
    { name: 'Cinematic Crane Down', pan: 0, tilt: 6.0, zoom: 2.0, roll: 0, speed: 0.8 },
    { name: 'Dutch Angle Roll', pan: 2.5, tilt: 1.0, zoom: 1.0, roll: 8.5, speed: 1.4 },
    { name: 'Static Tripod', pan: 0, tilt: 0, zoom: 0, roll: 0, speed: 1.0 },
  ];

  // ── AI Magic Prompt Expansion ─────────────────────────────────────────────
  const handleMagicPromptExpand = () => {
    setIsExpandingPrompt(true);
    playChime();
    setTimeout(() => {
      const cinematicEnhancements = [
        "shot on 35mm anamorphic prime lens, T1.5 aperture, cinematic 8k UHD render, volumetric dust particles caught in cyan laser shafts, shallow depth of field, photorealistic raymarched caustics, octane render, color graded in DaVinci Resolve",
        "ultra-realistic cinematic IMAX 70mm, volumetric god rays, fluid atmospheric turbulence, sub-surface light scattering, intricate quantum circuit micro-details, unreal engine 5.4 Lumen global illumination",
        "cinematic masterpiece, directional motion blur, subtle film grain, dynamic bokeh, specular highlights reflecting across wet obsidian panels, master lighting cinematography",
      ];
      const addition = cinematicEnhancements[Math.floor(Math.random() * cinematicEnhancements.length)];
      setPrompt((prev) => `${prev.trim()}, ${addition}`);
      setIsExpandingPrompt(false);
      playSuccessChime();
    }, 600);
  };

  // ── Dispatch New Video Render ─────────────────────────────────────────────
  const handleGenerateVideo = () => {
    playSuccessChime();
    const newTaskId = `task-${Date.now()}`;
    const newTask: VideoRenderTask = {
      id: newTaskId,
      prompt,
      model,
      ratio: aspectRatio,
      resolution,
      status: 'rendering',
      progress: 5,
      durationSec,
      timestamp: 'Just now',
      thumbnailUrl: 'linear-gradient(135deg, #021a2d 0%, #00f0ff 100%)',
    };

    setRenderTasks((prev) => [newTask, ...prev]);

    // Simulate progressive render increments
    let currentProgress = 5;
    const interval = setInterval(() => {
      currentProgress += Math.floor(Math.random() * 18 + 12);
      if (currentProgress >= 100) {
        currentProgress = 100;
        clearInterval(interval);
        setRenderTasks((prev) =>
          prev.map((t) =>
            t.id === newTaskId
              ? { ...t, progress: 100, status: 'completed' as const }
              : t
          )
        );
        // Add to gallery
        const newAsset = {
          id: `asset-${Date.now()}`,
          title: prompt.slice(0, 24) + '...',
          prompt,
          ratio: aspectRatio,
          resolution,
          duration: `${durationSec}s`,
          fps: 60,
          color: '#00f0ff',
          gradient: 'linear-gradient(135deg, #062338 0%, #00f0ff 100%)',
        };
        setAssetGallery((prev) => [newAsset, ...prev]);
        playSuccessChime();
      } else {
        setRenderTasks((prev) =>
          prev.map((t) =>
            t.id === newTaskId ? { ...t, progress: currentProgress } : t
          )
        );
      }
    }, 800);
  };

  // ── Extend Video +4s ──────────────────────────────────────────────────────
  const handleExtendDuration = () => {
    playHudClick();
    setTotalDuration((prev) => prev + 4.0);
    setTimelineTracks((prev) =>
      prev.map((track) => {
        if (track.type === 'video') {
          const lastClip = track.clips[track.clips.length - 1];
          const extClip: TimelineClip = {
            id: `ext-${Date.now()}`,
            title: `Continuous Ext (+4s)`,
            start: lastClip.start + lastClip.duration,
            duration: 4.0,
            color: '#38bdf8',
          };
          return { ...track, clips: [...track.clips, extClip] };
        }
        return track;
      })
    );
    playSuccessChime();
  };

  // ── Upscale 4K Enhancement ────────────────────────────────────────────────
  const handleUpscale4K = () => {
    playHudClick();
    setResolution('4K');
    playSuccessChime();
  };

  // ── Inject Video into Second Brain Graph ──────────────────────────────────
  const handleInjectActiveIntoGraph = () => {
    playSuccessChime();
    onInjectVideoIntoGraph('Neural Matrix Cinematic Studio', prompt, {
      model,
      ratio: aspectRatio,
      resolution,
      camera,
      duration: totalDuration,
      fps,
    });
  };

  // ── Format SMPTE Timecode (HH:MM:SS:FF) ───────────────────────────────────
  const formatTimecode = (sec: number, targetFps: number = 60) => {
    const totalFrames = Math.floor(sec * targetFps);
    const frames = totalFrames % targetFps;
    const totalSeconds = Math.floor(sec);
    const s = totalSeconds % 60;
    const m = Math.floor(totalSeconds / 60) % 60;
    const h = Math.floor(totalSeconds / 3600);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(frames).padStart(2, '0')}`;
  };

  // ── Interactive Canvas Animation Loop ─────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let localTime = currentTime;
    let lastStamp = performance.now();

    const renderFrame = (now: number) => {
      const delta = (now - lastStamp) / 1000;
      lastStamp = now;

      if (isPlaying) {
        localTime += delta;
        if (localTime >= totalDuration) {
          if (isLooping) {
            localTime = 0;
          } else {
            localTime = totalDuration;
            setIsPlaying(false);
          }
        }
        setCurrentTime(localTime);
      }

      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      // Deep cinematic background gradient
      const bgGrad = ctx.createRadialGradient(
        w / 2 + camera.pan * 8,
        h / 2 + camera.tilt * 8,
        20,
        w / 2,
        h / 2,
        Math.max(w, h)
      );
      bgGrad.addColorStop(0, '#0a1d37');
      bgGrad.addColorStop(0.4, '#040d1a');
      bgGrad.addColorStop(1, '#01040a');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, w, h);

      // Dynamic 3D Camera Projection Space
      ctx.save();
      ctx.translate(w / 2, h / 2);

      // Apply 6-axis Camera Director Transforms
      const radRoll = (camera.roll * Math.PI) / 180;
      ctx.rotate(radRoll);
      const zoomFactor = Math.max(0.6, 1 + camera.zoom * 0.08);
      ctx.scale(zoomFactor, zoomFactor);
      ctx.translate(camera.pan * 12, camera.tilt * 12);

      // Render Perspective Grid
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.12)';
      ctx.lineWidth = 1;
      const gridSize = 40;
      const phase = (localTime * camera.speed * 20) % gridSize;

      for (let x = -w; x < w; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x + phase, -h);
        ctx.lineTo(x + phase, h);
        ctx.stroke();
      }
      for (let y = -h; y < h; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(-w, y + phase);
        ctx.lineTo(w, y + phase);
        ctx.stroke();
      }

      // Render Central Quantum Node Matrix
      const nodeCount = 36;
      for (let i = 0; i < nodeCount; i++) {
        const angle = (i / nodeCount) * Math.PI * 2 + localTime * 0.4 * camera.speed;
        const radius = 90 + Math.sin(localTime * 1.5 + i) * 35;
        const px = Math.cos(angle) * radius;
        const py = Math.sin(angle) * radius * 0.55;

        // Draw Synapse Lines to center
        ctx.strokeStyle = i % 2 === 0 ? 'rgba(0, 240, 255, 0.25)' : 'rgba(168, 85, 247, 0.25)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(px, py);
        ctx.stroke();

        // Glowing Bioluminescent Nodes
        ctx.beginPath();
        ctx.arc(px, py, 4 + (i % 3), 0, Math.PI * 2);
        ctx.fillStyle = i % 3 === 0 ? '#00f0ff' : i % 3 === 1 ? '#a855f7' : '#38bdf8';
        ctx.shadowColor = '#00f0ff';
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // Central Reactor Core
      const coreGrad = ctx.createRadialGradient(0, 0, 5, 0, 0, 45);
      coreGrad.addColorStop(0, '#ffffff');
      coreGrad.addColorStop(0.3, '#00f0ff');
      coreGrad.addColorStop(0.8, 'rgba(0, 240, 255, 0.3)');
      coreGrad.addColorStop(1, 'transparent');
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(0, 0, 45, 0, Math.PI * 2);
      ctx.fill();

      // Motion Vectors Overlay (When Enabled)
      if (camera.motionVectors) {
        ctx.strokeStyle = '#f59e0b';
        ctx.fillStyle = '#f59e0b';
        ctx.lineWidth = 1.5;

        const vecStep = 60;
        for (let vx = -w / 2 + 30; vx < w / 2; vx += vecStep) {
          for (let vy = -h / 2 + 30; vy < h / 2; vy += vecStep) {
            const dx = camera.pan * 2.5 + Math.cos(localTime + vx * 0.01) * 6;
            const dy = camera.tilt * 2.5 + Math.sin(localTime + vy * 0.01) * 6;

            ctx.beginPath();
            ctx.moveTo(vx, vy);
            ctx.lineTo(vx + dx, vy + dy);
            ctx.stroke();

            // Arrow tip
            ctx.beginPath();
            ctx.arc(vx + dx, vy + dy, 2, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      ctx.restore();

      // Film Grain & Anamorphic Letterbox Overlay
      ctx.fillStyle = 'rgba(0, 240, 255, 0.02)';
      ctx.fillRect(0, 0, w, h);

      animFrameRef.current = requestAnimationFrame(renderFrame);
    };

    animFrameRef.current = requestAnimationFrame(renderFrame);

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isPlaying, isLooping, totalDuration, camera, fps]);

  // Aspect Ratio Dimensions map
  const aspectClass = {
    '16:9': 'aspect-video w-full max-w-4xl',
    '9:16': 'aspect-[9/16] w-64 max-h-[500px]',
    '1:1': 'aspect-square w-96 max-w-full',
    '21:9': 'aspect-[21/9] w-full max-w-5xl',
  }[aspectRatio];

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-[#03060c] text-slate-100 font-sans select-none pt-16">
      {/* ── Studio Top Toolbar ─────────────────────────────────────────────── */}
      <div className="px-6 py-2.5 bg-slate-950/90 border-b border-cyan-500/20 backdrop-blur-xl flex items-center justify-between text-xs font-mono shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1 rounded-xl bg-cyan-950/80 border border-cyan-400/50 text-cyan-300 font-bold shadow-[0_0_12px_rgba(0,240,255,0.25)]">
            <Film className="w-4 h-4 text-cyan-400 animate-pulse" />
            <span>RUNWAY GEN-3 ALPHA CREATIVE STUDIO</span>
          </div>

          {/* Model Selector */}
          <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-900 border border-slate-800">
            {(['Gen-3 Alpha Turbo', 'Gen-3 Alpha', 'Gen-2 HD', 'NEXUS Neural Video V2'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setModel(m)}
                className={`px-2.5 py-1 rounded-md text-[11px] transition-all cursor-pointer ${
                  model === m
                    ? 'bg-cyan-500/20 border border-cyan-400/60 text-cyan-300 shadow-[0_0_8px_rgba(0,240,255,0.3)] font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Global Studio Stats */}
        <div className="flex items-center gap-4 text-slate-400">
          <div className="flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span>NVIDIA TensorRT-LLM Video Pipeline</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Flame className="w-3.5 h-3.5 text-amber-400" />
            <span>Credits: 2,400 / 3,000</span>
          </div>
        </div>
      </div>

      {/* ── Studio Main Workspace (Left Controls + Center Canvas + Right Queue) */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Left Column: Prompt Studio & 6-Axis Camera Motion Director ─────── */}
        <div className="w-84 xl:w-96 border-r border-cyan-500/20 bg-slate-950/70 backdrop-blur-md flex flex-col p-4 space-y-4 overflow-y-auto custom-scrollbar shrink-0">
          {/* Prompt Studio Card */}
          <div className="p-3.5 rounded-2xl bg-[#061120] border border-cyan-500/30 space-y-2.5 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                <Wand2 className="w-3.5 h-3.5 text-cyan-400" />
                Text-To-Video Prompt
              </span>
              <button
                onClick={handleMagicPromptExpand}
                disabled={isExpandingPrompt}
                className="px-2 py-0.5 rounded-lg bg-gradient-to-r from-purple-900/60 to-pink-900/60 hover:from-purple-800 hover:to-pink-800 border border-purple-500/40 text-[10px] font-mono text-purple-200 flex items-center gap-1 cursor-pointer transition-all shadow-sm"
                title="AI Magic Prompt: Automatically expand with cinematic lighting, lenses, and textures"
              >
                <Sparkles className="w-3 h-3 text-purple-300 animate-spin-slow" />
                <span>{isExpandingPrompt ? 'Expanding...' : 'Magic Prompt'}</span>
              </button>
            </div>

            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              placeholder="Describe your cinematic video shot..."
              className="w-full p-2.5 rounded-xl bg-slate-900/90 border border-cyan-500/30 text-xs font-mono text-cyan-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 resize-none leading-relaxed"
            />

            {/* Negative Prompt */}
            <div className="space-y-1">
              <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Negative Prompt</span>
              <input
                type="text"
                value={negativePrompt}
                onChange={(e) => setNegativePrompt(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-[11px] font-mono text-slate-300 focus:outline-none focus:border-cyan-500/40"
              />
            </div>
          </div>

          {/* 6-Axis Camera Motion Director */}
          <div className="p-3.5 rounded-2xl bg-[#061120] border border-cyan-500/30 space-y-3 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                <Compass className="w-3.5 h-3.5 text-cyan-400" />
                6-Axis Camera Motion Director
              </span>
              <button
                onClick={() => setCamera({ pan: 0, tilt: 0, zoom: 0, roll: 0, speed: 1.0, motionBrush: 5, motionVectors: camera.motionVectors })}
                className="text-[10px] font-mono text-cyan-400 hover:text-cyan-200 cursor-pointer flex items-center gap-1"
                title="Reset Camera Sliders"
              >
                <RotateCcw className="w-2.5 h-2.5" />
                <span>Reset</span>
              </button>
            </div>

            {/* Presets Quick Grid */}
            <div className="grid grid-cols-2 gap-1.5">
              {motionPresets.map((p) => (
                <button
                  key={p.name}
                  onClick={() => {
                    setCamera((prev) => ({
                      ...prev,
                      pan: p.pan,
                      tilt: p.tilt,
                      zoom: p.zoom,
                      roll: p.roll,
                      speed: p.speed,
                    }));
                    playHudClick();
                  }}
                  className="px-2 py-1 rounded-lg bg-slate-900/90 hover:bg-cyan-950/60 border border-slate-800 hover:border-cyan-500/40 text-[10px] font-mono text-slate-300 hover:text-cyan-200 transition-all text-left truncate cursor-pointer"
                >
                  {p.name}
                </button>
              ))}
            </div>

            {/* 6 Sliders: Pan, Tilt, Zoom, Roll, Speed, Motion Brush */}
            <div className="space-y-2 pt-1 font-mono text-[10.5px]">
              {/* Pan */}
              <div className="space-y-0.5">
                <div className="flex justify-between text-slate-400">
                  <span>Pan (Horizontal)</span>
                  <span className="text-cyan-400">{camera.pan > 0 ? `+${camera.pan}` : camera.pan}</span>
                </div>
                <input
                  type="range"
                  min="-10"
                  max="10"
                  step="0.5"
                  value={camera.pan}
                  onChange={(e) => setCamera({ ...camera, pan: parseFloat(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* Tilt */}
              <div className="space-y-0.5">
                <div className="flex justify-between text-slate-400">
                  <span>Tilt (Vertical)</span>
                  <span className="text-cyan-400">{camera.tilt > 0 ? `+${camera.tilt}` : camera.tilt}</span>
                </div>
                <input
                  type="range"
                  min="-10"
                  max="10"
                  step="0.5"
                  value={camera.tilt}
                  onChange={(e) => setCamera({ ...camera, tilt: parseFloat(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* Zoom */}
              <div className="space-y-0.5">
                <div className="flex justify-between text-slate-400">
                  <span>Zoom (In / Out)</span>
                  <span className="text-cyan-400">{camera.zoom > 0 ? `+${camera.zoom}` : camera.zoom}</span>
                </div>
                <input
                  type="range"
                  min="-10"
                  max="10"
                  step="0.5"
                  value={camera.zoom}
                  onChange={(e) => setCamera({ ...camera, zoom: parseFloat(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* Roll */}
              <div className="space-y-0.5">
                <div className="flex justify-between text-slate-400">
                  <span>Roll (Dutch Angle)</span>
                  <span className="text-cyan-400">{camera.roll > 0 ? `+${camera.roll}°` : `${camera.roll}°`}</span>
                </div>
                <input
                  type="range"
                  min="-10"
                  max="10"
                  step="0.5"
                  value={camera.roll}
                  onChange={(e) => setCamera({ ...camera, roll: parseFloat(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* Speed */}
              <div className="space-y-0.5">
                <div className="flex justify-between text-slate-400">
                  <span>Motion Speed</span>
                  <span className="text-cyan-400">{camera.speed}x</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.5"
                  step="0.1"
                  value={camera.speed}
                  onChange={(e) => setCamera({ ...camera, speed: parseFloat(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* Motion Vectors Overlay Toggle */}
              <div className="flex items-center justify-between pt-1 border-t border-slate-800">
                <span className="text-slate-300">Show Motion Vectors</span>
                <button
                  onClick={() => setCamera({ ...camera, motionVectors: !camera.motionVectors })}
                  className={`px-2 py-0.5 rounded text-[10px] font-bold border transition-all cursor-pointer ${
                    camera.motionVectors
                      ? 'bg-amber-950 border-amber-400 text-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.3)]'
                      : 'bg-slate-900 border-slate-800 text-slate-500'
                  }`}
                >
                  {camera.motionVectors ? 'ACTIVE' : 'OFF'}
                </button>
              </div>
            </div>
          </div>

          {/* Aspect Ratio & Format Controls */}
          <div className="p-3.5 rounded-2xl bg-[#061120] border border-cyan-500/30 space-y-3 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
            <span className="text-[11px] font-mono font-bold text-cyan-300 uppercase tracking-wider block">
              Aspect Ratio & Dimensions
            </span>
            <div className="grid grid-cols-4 gap-1.5 font-mono text-[11px]">
              {(['16:9', '9:16', '1:1', '21:9'] as VideoAspectRatio[]).map((ratio) => (
                <button
                  key={ratio}
                  onClick={() => setAspectRatio(ratio)}
                  className={`py-1.5 rounded-lg border text-center transition-all cursor-pointer ${
                    aspectRatio === ratio
                      ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200 shadow-[0_0_10px_rgba(0,240,255,0.3)] font-bold'
                      : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {ratio}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
              <div>
                <span className="text-[10px] text-slate-400 block mb-1">Resolution</span>
                <select
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value as VideoResolution)}
                  className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-cyan-200 focus:outline-none focus:border-cyan-400"
                >
                  <option value="720p">720p HD</option>
                  <option value="1080p">1080p Full HD</option>
                  <option value="4K">4K UHD (Master)</option>
                </select>
              </div>

              <div>
                <span className="text-[10px] text-slate-400 block mb-1">Duration</span>
                <select
                  value={durationSec}
                  onChange={(e) => setDurationSec(parseInt(e.target.value))}
                  className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-cyan-200 focus:outline-none focus:border-cyan-400"
                >
                  <option value={5}>5 Seconds</option>
                  <option value={10}>10 Seconds</option>
                </select>
              </div>
            </div>
          </div>

          {/* Primary Generate Button */}
          <button
            onClick={handleGenerateVideo}
            className="w-full py-3 px-4 rounded-2xl bg-gradient-to-r from-cyan-500 via-teal-400 to-cyan-500 hover:from-cyan-400 hover:to-teal-300 text-black font-mono font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-[0_0_25px_rgba(0,240,255,0.4)] transition-all cursor-pointer active:scale-98"
          >
            <Sparkles className="w-4 h-4 text-black animate-spin-slow" />
            <span>Generate Clip (Gen-3 Alpha)</span>
          </button>
        </div>

        {/* ── Center Column: Cinematic Canvas Viewport & Player ──────────────── */}
        <div className="flex-1 flex flex-col bg-[#02050a] relative overflow-hidden">
          {/* Viewport Top HUD Bar */}
          <div className="px-6 py-2 border-b border-cyan-500/15 flex items-center justify-between text-xs font-mono text-slate-400 bg-slate-950/40">
            <div className="flex items-center gap-3">
              <span className="text-cyan-400 font-bold flex items-center gap-1.5">
                <Camera className="w-3.5 h-3.5" />
                <span>PREVIEW MONITOR</span>
              </span>
              <span>·</span>
              <span className="px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 text-[10px]">
                {resolution} · {fps} FPS · {aspectRatio}
              </span>
            </div>

            {/* Quick Action Badges */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleExtendDuration}
                className="px-2.5 py-1 rounded-lg bg-blue-950/60 hover:bg-blue-900/80 border border-blue-500/40 text-blue-200 text-[11px] font-mono flex items-center gap-1 transition-all cursor-pointer shadow-sm"
                title="Extend video length by +4 continuous seconds"
              >
                <FastForward className="w-3 h-3 text-blue-400" />
                <span>Extend +4s</span>
              </button>

              <button
                onClick={handleUpscale4K}
                className="px-2.5 py-1 rounded-lg bg-amber-950/60 hover:bg-amber-900/80 border border-amber-500/40 text-amber-200 text-[11px] font-mono flex items-center gap-1 transition-all cursor-pointer shadow-sm"
                title="Upscale resolution to 4K UHD"
              >
                <Sparkles className="w-3 h-3 text-amber-400" />
                <span>Upscale 4K</span>
              </button>

              <button
                onClick={handleInjectActiveIntoGraph}
                className="px-2.5 py-1 rounded-lg bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 text-[11px] font-mono flex items-center gap-1 transition-all cursor-pointer shadow-sm"
                title="Inject this generated video into the Second Brain Knowledge Universe"
              >
                <Share2 className="w-3 h-3 text-emerald-400" />
                <span>Inject into Graph</span>
              </button>
            </div>
          </div>

          {/* Interactive Cinematic Preview Canvas */}
          <div className="flex-1 flex items-center justify-center p-6 relative overflow-hidden bg-radial from-slate-900/20 to-black">
            <div className={`relative rounded-2xl border border-cyan-500/30 shadow-[0_0_50px_rgba(0,240,255,0.15)] overflow-hidden flex items-center justify-center bg-black ${aspectClass}`}>
              <canvas
                ref={canvasRef}
                width={1280}
                height={720}
                className="w-full h-full object-cover"
              />

              {/* Canvas Overlay Badges */}
              <div className="absolute top-3 left-3 flex items-center gap-2 pointer-events-none">
                <span className="px-2 py-0.5 rounded bg-black/80 border border-cyan-500/40 text-[10px] font-mono text-cyan-300 backdrop-blur-md">
                  SMPTE: {formatTimecode(currentTime, fps)}
                </span>
                {camera.motionVectors && (
                  <span className="px-2 py-0.5 rounded bg-amber-950/80 border border-amber-400/40 text-[10px] font-mono text-amber-300 backdrop-blur-md flex items-center gap-1">
                    <Grid className="w-2.5 h-2.5" />
                    VECTORS ACTIVE
                  </span>
                )}
              </div>

              <div className="absolute bottom-3 right-3 pointer-events-none">
                <span className="px-2 py-0.5 rounded bg-black/80 border border-slate-700 text-[10px] font-mono text-slate-400">
                  {totalDuration.toFixed(1)}s TOTAL
                </span>
              </div>
            </div>
          </div>

          {/* Player Controls & Scrubber Transport Bar */}
          <div className="px-6 py-3 bg-slate-950/90 border-t border-cyan-500/20 backdrop-blur-xl flex flex-col space-y-2">
            {/* Scrubber Bar */}
            <div className="flex items-center gap-3">
              <span className="text-[11px] font-mono text-cyan-300 w-24">
                {formatTimecode(currentTime, fps)}
              </span>
              <input
                type="range"
                min="0"
                max={totalDuration}
                step="0.05"
                value={currentTime}
                onChange={(e) => setCurrentTime(parseFloat(e.target.value))}
                className="flex-1 accent-cyan-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
              />
              <span className="text-[11px] font-mono text-slate-400 w-24 text-right">
                {formatTimecode(totalDuration, fps)}
              </span>
            </div>

            {/* Transport Buttons */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentTime(0)}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
                  title="Skip to Start"
                >
                  <SkipBack className="w-4 h-4" />
                </button>

                <button
                  onClick={() => setCurrentTime((prev) => Math.max(0, prev - 1 / fps))}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
                  title="Step 1 Frame Back"
                >
                  <SkipBack className="w-3 h-3" />
                </button>

                <button
                  onClick={() => setIsPlaying(!isPlaying)}
                  className="px-4 py-1.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-bold font-mono text-xs flex items-center gap-1.5 shadow-[0_0_12px_rgba(0,240,255,0.4)] transition-all cursor-pointer"
                >
                  {isPlaying ? <Pause className="w-3.5 h-3.5 fill-black" /> : <Play className="w-3.5 h-3.5 fill-black" />}
                  <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
                </button>

                <button
                  onClick={() => setCurrentTime((prev) => Math.min(totalDuration, prev + 1 / fps))}
                  className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
                  title="Step 1 Frame Forward"
                >
                  <SkipForward className="w-3 h-3" />
                </button>

                <button
                  onClick={() => setIsLooping(!isLooping)}
                  className={`p-1.5 rounded-lg border transition-all cursor-pointer ${
                    isLooping
                      ? 'bg-cyan-950 border-cyan-400 text-cyan-300 shadow-[0_0_8px_rgba(0,240,255,0.25)]'
                      : 'bg-slate-900 border-slate-800 text-slate-500'
                  }`}
                  title={isLooping ? 'Looping enabled' : 'Looping disabled'}
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Volume & Fullscreen */}
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setIsMuted(!isMuted)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                >
                  {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={isMuted ? 0 : volume}
                  onChange={(e) => {
                    setVolume(parseFloat(e.target.value));
                    setIsMuted(false);
                  }}
                  className="w-20 accent-cyan-400 cursor-pointer h-1 bg-slate-800 rounded"
                />
              </div>
            </div>
          </div>
        </div>

        {/* ── Right Column: Render Queue & Asset Gallery ─────────────────────── */}
        <div className="w-80 xl:w-92 border-l border-cyan-500/20 bg-slate-950/70 backdrop-blur-md flex flex-col p-4 space-y-4 overflow-y-auto custom-scrollbar shrink-0">
          {/* Active Render Queue Card */}
          <div className="p-3.5 rounded-2xl bg-[#061120] border border-cyan-500/30 space-y-3 shadow-[0_4px_20px_rgba(0,0,0,0.5)]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                Render Tasks ({renderTasks.length})
              </span>
              <span className="text-[9.5px] font-mono text-slate-400">GPU Cluster Active</span>
            </div>

            <div className="space-y-2.5">
              {renderTasks.map((task) => (
                <div
                  key={task.id}
                  className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1.5 font-mono text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-cyan-300 font-bold truncate max-w-[160px]">
                      {task.model}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase ${
                        task.status === 'completed'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                          : 'bg-cyan-950 text-cyan-300 border border-cyan-500/30 animate-pulse'
                      }`}
                    >
                      {task.status}
                    </span>
                  </div>

                  <p className="text-[10.5px] text-slate-300 truncate line-clamp-1">
                    {task.prompt}
                  </p>

                  {/* Progress Bar */}
                  <div className="space-y-0.5">
                    <div className="flex justify-between text-[9px] text-slate-400">
                      <span>Progress</span>
                      <span>{task.progress}%</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-500 to-teal-400 rounded-full transition-all duration-300"
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Generated Asset Gallery */}
          <div className="p-3.5 rounded-2xl bg-[#061120] border border-cyan-500/30 space-y-3 shadow-[0_4px_20px_rgba(0,0,0,0.5)] flex-1">
            <span className="text-[11px] font-mono font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              Asset Gallery ({assetGallery.length})
            </span>

            <div className="space-y-3">
              {assetGallery.map((asset) => (
                <div
                  key={asset.id}
                  className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-cyan-500/40 transition-all space-y-2 group"
                >
                  <div
                    className="w-full h-24 rounded-lg flex items-center justify-center relative overflow-hidden shadow-inner cursor-pointer"
                    style={{ background: asset.gradient }}
                    onClick={() => {
                      setPrompt(asset.prompt);
                      setAspectRatio(asset.ratio);
                      setResolution(asset.resolution);
                      playHudClick();
                    }}
                  >
                    <div className="absolute inset-0 bg-black/30 group-hover:bg-black/10 transition-colors" />
                    <Play className="w-8 h-8 text-white/80 group-hover:scale-125 transition-transform" />
                    <div className="absolute bottom-1.5 left-2 text-[9px] font-mono px-1.5 py-0.5 rounded bg-black/70 text-cyan-300">
                      {asset.duration} · {asset.resolution}
                    </div>
                  </div>

                  <div className="space-y-1">
                    <div className="text-xs font-mono font-bold text-white group-hover:text-cyan-300 transition-colors">
                      {asset.title}
                    </div>
                    <p className="text-[10px] text-slate-400 line-clamp-2 leading-relaxed font-sans">
                      {asset.prompt}
                    </p>
                  </div>

                  <div className="flex items-center gap-1.5 pt-1">
                    <button
                      onClick={() => {
                        onInjectVideoIntoGraph(asset.title, asset.prompt, {
                          ratio: asset.ratio,
                          resolution: asset.resolution,
                        });
                        playSuccessChime();
                      }}
                      className="flex-1 py-1 px-2 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-400/40 text-[10px] font-mono text-cyan-200 flex items-center justify-center gap-1 transition-all cursor-pointer"
                    >
                      <Share2 className="w-3 h-3 text-cyan-400" />
                      <span>To Graph</span>
                    </button>
                    <button
                      onClick={handleUpscale4K}
                      className="py-1 px-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10px] font-mono text-slate-300 transition-colors cursor-pointer"
                      title="Upscale 4K"
                    >
                      4K
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Bottom Section: Multi-Track Timeline Sequencer ───────────────────── */}
      <div className="h-44 border-t border-cyan-500/20 bg-[#040812] flex flex-col shrink-0">
        {/* Timeline Header Controls */}
        <div className="px-6 py-2 border-b border-cyan-500/10 flex items-center justify-between text-xs font-mono text-slate-400 bg-slate-950/50">
          <div className="flex items-center gap-3">
            <span className="text-cyan-400 font-bold flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" />
              <span>TIMELINE SEQUENCER</span>
            </span>
            <span className="text-[10px] text-slate-500">4 Synchronized Audio/Visual Tracks</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-[11px]">
              <span className="text-slate-400">Zoom:</span>
              <button
                onClick={() => setZoomLevel((z) => Math.max(0.5, z - 0.25))}
                className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 hover:text-white"
              >
                -
              </button>
              <span className="text-cyan-300 w-10 text-center">{zoomLevel}x</span>
              <button
                onClick={() => setZoomLevel((z) => Math.min(2.5, z + 0.25))}
                className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 hover:text-white"
              >
                +
              </button>
            </div>
          </div>
        </div>

        {/* Tracks Sequencer View */}
        <div className="flex-1 overflow-x-auto overflow-y-hidden custom-scrollbar relative p-2 space-y-1.5 bg-[#02050b]">
          {/* Draggable Playhead Needle across all tracks */}
          <div
            className="absolute top-0 bottom-0 w-[2px] bg-red-500 z-30 pointer-events-none transition-all duration-75 shadow-[0_0_8px_#ef4444]"
            style={{
              left: `${192 + (currentTime / totalDuration) * 720 * zoomLevel}px`,
            }}
          >
            <div className="w-2.5 h-2.5 bg-red-500 rotate-45 -translate-x-[4px] -translate-y-1 shadow-[0_0_6px_#ef4444]" />
          </div>

          {timelineTracks.map((track) => (
            <div key={track.id} className="flex items-center h-6.5 text-[11px] font-mono">
              {/* Track Label Header */}
              <div className="w-48 px-3 py-1 rounded-l-lg bg-slate-900 border border-slate-800 text-slate-300 font-semibold truncate flex items-center justify-between shrink-0">
                <span className="truncate">{track.name}</span>
                <span className="text-[9px] text-cyan-400/80">{track.clips.length} clip</span>
              </div>

              {/* Track Content Timeline Bar */}
              <div
                className="flex-1 h-full bg-slate-950/80 border-y border-r border-slate-900 rounded-r-lg relative overflow-hidden cursor-pointer"
                style={{ minWidth: `${720 * zoomLevel}px` }}
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  const clickX = e.clientX - rect.left;
                  const ratio = Math.max(0, Math.min(1, clickX / rect.width));
                  setCurrentTime(ratio * totalDuration);
                  playHudClick();
                }}
              >
                {track.clips.map((clip) => {
                  const leftPct = (clip.start / totalDuration) * 100;
                  const widthPct = (clip.duration / totalDuration) * 100;

                  return (
                    <div
                      key={clip.id}
                      className="absolute top-0.5 bottom-0.5 rounded px-2 flex items-center text-[10px] text-black font-bold shadow-md truncate hover:brightness-110 transition-all border border-black/20"
                      style={{
                        left: `${leftPct}%`,
                        width: `${widthPct}%`,
                        backgroundColor: clip.color,
                      }}
                    >
                      <span className="truncate">{clip.title}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
