import React from 'react';
import { Sparkles, X, Zap } from 'lucide-react';

interface RobotCompanionProps {
  companion: string;
  message: string;
  suggestions: string[];
  onSuggestion: (suggestion: string) => void;
  onBoost: () => void;
  onDismiss: () => void;
  isBusy: boolean;
}

/**
 * SCREEN 1 — Animated Onboarding Hero.
 * A friendly 3D robot companion avatar inside a floating translucent chat
 * bubble. Fully wired: suggestions & the boost action hit the live backend.
 */
export const RobotCompanion: React.FC<RobotCompanionProps> = ({
  companion,
  message,
  suggestions,
  onSuggestion,
  onBoost,
  onDismiss,
  isBusy,
}) => {
  return (
    <div className="relative w-full max-w-[440px] animate-[nxs-float_7s_ease-in-out_infinite] select-none">
      {/* Ambient glow behind the bubble */}
      <div
        aria-hidden
        className="absolute -inset-8 rounded-[3rem] bg-gradient-to-tr from-cyan-200/50 via-transparent to-violet-200/50 blur-2xl"
      />

      {/* Floating accent orbs */}
      <div
        aria-hidden
        className="absolute -top-5 -right-3 w-4 h-4 rounded-full bg-cyan-300/80 blur-[2px] animate-[nxs-float-accent_5s_ease-in-out_infinite]"
      />
      <div
        aria-hidden
        className="absolute -bottom-6 -left-2 w-3 h-3 rounded-full bg-violet-300/80 blur-[2px] animate-[nxs-float-accent_6s_ease-in-out_0.8s_infinite]"
      />
      <div
        aria-hidden
        className="absolute top-10 -left-5 w-2 h-2 rounded-full bg-amber-300/80 animate-[nxs-float-accent_4.5s_ease-in-out_0.4s_infinite]"
      />

      {/* Translucent chat bubble */}
      <div className="relative rounded-[2rem] bg-white/65 backdrop-blur-2xl border border-white/80 shadow-[0_24px_60px_-18px_rgba(16,24,40,0.28),0_2px_8px_-2px_rgba(16,24,40,0.06)] p-5 pr-6">
        {/* Dismiss */}
        <button
          onClick={onDismiss}
          className="absolute top-3 right-3 w-7 h-7 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition-all cursor-pointer"
          title="Dismiss onboarding companion"
          aria-label="Dismiss onboarding companion"
        >
          <X className="w-3.5 h-3.5" strokeWidth={2} />
        </button>

        <div className="flex items-start gap-4">
          {/* 3D robot avatar */}
          <div className="relative shrink-0">
            <div className="w-28 h-28 sm:w-32 sm:h-32 rounded-3xl overflow-hidden border border-slate-200/80 bg-gradient-to-br from-white to-slate-100 shadow-[inset_0_2px_12px_rgba(15,23,42,0.06),0_10px_24px_-10px_rgba(15,23,42,0.25)]">
              <img
                src="/nixtio-robot.png"
                alt={`${companion} — friendly 3D robot companion`}
                className="w-full h-full object-cover"
                draggable={false}
              />
            </div>
            {/* Online status */}
            <span className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-emerald-500 border-[3px] border-[#F9FAFB] flex items-center justify-center">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            </span>
          </div>

          {/* Bubble copy */}
          <div className="min-w-0 pt-1">
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
              <Sparkles className="w-3 h-3 text-cyan-500" strokeWidth={2.2} />
              Onboarding · {companion}
            </div>
            <p className="mt-2 text-[1.35rem] leading-snug font-bold tracking-tight text-slate-900">
              “{message}”
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">
              Ask anything, or pick a spark below — I’ll run it on the NEXUS cortex.
            </p>

            {/* Suggestion chips — wired to the console */}
            <div className="mt-3.5 flex flex-wrap gap-2">
              {suggestions.slice(0, 2).map((s) => (
                <button
                  key={s}
                  disabled={isBusy}
                  onClick={() => onSuggestion(s)}
                  className="nxs-chip max-w-full truncate px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[12px] font-medium text-slate-600 hover:border-cyan-300 hover:text-cyan-700 hover:shadow-[0_4px_14px_-4px_rgba(6,182,212,0.35)] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  {s}
                </button>
              ))}
            </div>

            <button
              disabled={isBusy}
              onClick={onBoost}
              className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 hover:shadow-[0_10px_24px_-8px_rgba(15,23,42,0.5)] transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <Zap className="w-3.5 h-3.5 text-amber-300" strokeWidth={2.2} />
              {isBusy ? 'Working…' : 'Give me a boost'}
            </button>
          </div>
        </div>

        {/* Bubble tail */}
        <div
          aria-hidden
          className="absolute -bottom-2 left-16 w-5 h-5 rotate-45 bg-white/80 backdrop-blur-2xl border-r border-b border-white/80 rounded-br-md"
        />
      </div>
    </div>
  );
};
