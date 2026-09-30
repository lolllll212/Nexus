import React from 'react';

interface FaceTrackerOverlayProps {
  faceActive: boolean;
  eyesActive: boolean;
}

export const FaceTrackerOverlay: React.FC<FaceTrackerOverlayProps> = ({
  faceActive,
  eyesActive,
}) => {
  if (!faceActive && !eyesActive) return null;

  return (
    <div className="fixed inset-0 pointer-events-none z-20 overflow-hidden select-none">
      {/* EYES: Scanning laser beam sweep */}
      {eyesActive && (
        <div className="absolute inset-0">
          <div className="w-full h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_15px_#00f0ff] animate-[bounce_4s_ease-in-out_infinite] opacity-60"></div>
          <div className="absolute top-6 left-1/2 -translate-x-1/2 px-3 py-1 rounded bg-black/60 border border-cyan-400/40 text-[9px] font-mono text-cyan-300 tracking-widest uppercase">
            EYES ACTIVE: OPTICAL SYNAPSE SCANNING
          </div>
        </div>
      )}

      {/* FACE: Tactical HUD Reticle */}
      {faceActive && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 border border-cyan-500/20 rounded-full flex items-center justify-center">
          {/* Corner brackets */}
          <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-cyan-400"></div>
          <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-cyan-400"></div>
          <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-cyan-400"></div>
          <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-cyan-400"></div>

          {/* Centered crosshair */}
          <div className="w-16 h-16 border border-cyan-400/40 rounded-full flex items-center justify-center animate-pulse">
            <div className="w-1 h-1 bg-cyan-400 rounded-full shadow-[0_0_8px_#00f0ff]"></div>
          </div>

          {/* Bio-telemetry readout */}
          <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] font-mono text-cyan-400 tracking-widest bg-black/70 px-2 py-0.5 rounded border border-cyan-400/30">
            BIO-LOCK: OPERATOR // 99.8% NEURAL SYNC
          </div>
        </div>
      )}
    </div>
  );
};
