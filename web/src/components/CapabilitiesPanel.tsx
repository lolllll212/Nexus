import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AudioLines,
  Brain,
  Check,
  Code2,
  Database,
  Eye,
  Settings2,
  Sparkles,
  Telescope,
  Volume2,
  Wrench,
  X,
} from 'lucide-react';
import {
  CAPABILITY_KEYS,
  CAPABILITY_META,
  CHAT_EFFORT_OPTIONS,
  getCapabilityLabel,
  getChatEffortOption,
  modelSupports,
} from '../data/modelCatalog';
import type {
  ChatCapabilities,
  ChatCapabilityToggleKey,
  ModelCapabilityKey,
  NexusModel,
} from '../types';

interface CapabilitiesPanelProps {
  capabilities: ChatCapabilities;
  onChange: (capabilities: ChatCapabilities) => void;
  selectedModel?: NexusModel | null;
  capabilityLabels?: Record<string, string>;
  disabled?: boolean;
  align?: 'left' | 'right';
  placement?: 'top' | 'bottom';
  className?: string;
}

type CapabilityToggleKey = ChatCapabilityToggleKey;

interface CapabilityToggleDefinition {
  key: CapabilityToggleKey;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  modelCapability?: ModelCapabilityKey;
  note?: string;
}

const CAPABILITY_TOGGLES: CapabilityToggleDefinition[] = [
  {
    key: 'extendedThinking',
    label: 'Extended thinking',
    description: 'Ask for deeper step-by-step reasoning and reveal a collapsible Thinking section.',
    icon: Brain,
    modelCapability: 'reasoning',
    note: 'Best with reasoning models',
  },
  {
    key: 'artifacts',
    label: 'Artifacts',
    description: 'Present code and reusable deliverables as copyable artifact cards.',
    icon: Code2,
    modelCapability: 'code',
  },
  {
    key: 'deepResearch',
    label: 'Deep research',
    description: 'Use tools, cross-check evidence, and structure a source-aware answer.',
    icon: Telescope,
    modelCapability: 'research',
    note: 'May take longer',
  },
  {
    key: 'voiceReplies',
    label: 'Voice replies',
    description: 'Read new assistant answers aloud using your selected accent and voice.',
    icon: Volume2,
  },
  {
    key: 'memory',
    label: 'Conversation memory',
    description: 'Reuse this chat session so follow-up messages keep their context.',
    icon: Database,
    modelCapability: 'long_context',
  },
];

const MODEL_CAPABILITY_ICONS: Record<ModelCapabilityKey, React.ComponentType<{ className?: string }>> = {
  reasoning: Brain,
  tool_use: Wrench,
  code: Code2,
  vision: Eye,
  long_context: Database,
  research: Telescope,
  streaming: AudioLines,
};

function ToggleSwitch({
  enabled,
  disabled,
  label,
  onToggle,
}: {
  enabled: boolean;
  disabled?: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-5 w-9 shrink-0 rounded-full border transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 ${
        enabled
          ? 'border-cyan-300/70 bg-cyan-400 shadow-[0_0_12px_rgba(0,240,255,0.35)]'
          : 'border-slate-700 bg-slate-800 hover:border-slate-500'
      }`}
    >
      <span
        className={`absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full transition-all ${
          enabled ? 'left-[18px] bg-slate-950' : 'left-[3px] bg-slate-400'
        }`}
      />
    </button>
  );
}

export const CapabilitiesPanel: React.FC<CapabilitiesPanelProps> = ({
  capabilities,
  onChange,
  selectedModel,
  capabilityLabels,
  disabled = false,
  align = 'left',
  placement = 'top',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const activeCount = useMemo(
    () =>
      Object.values(capabilities).filter((value) => typeof value === 'boolean' && value).length +
      (capabilities.effort !== 'auto' ? 1 : 0),
    [capabilities],
  );
  const selectedEffort = getChatEffortOption(capabilities.effort);

  useEffect(() => {
    if (!isOpen) return undefined;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const toggleCapability = (key: CapabilityToggleKey) => {
    onChange({
      ...capabilities,
      [key]: !capabilities[key],
    });
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title="Chat capabilities"
        className={`relative flex h-8 w-8 items-center justify-center rounded-xl border font-mono transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
          isOpen
            ? 'border-cyan-300/70 bg-cyan-500/15 text-cyan-100 shadow-[0_0_14px_rgba(0,240,255,0.18)]'
            : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-cyan-400/50 hover:text-cyan-200'
        }`}
      >
        <Settings2 className="h-3.5 w-3.5" />
        {activeCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-cyan-400 px-0.5 text-[7px] font-black text-slate-950">
            {activeCount}
          </span>
        )}
        <span className="sr-only">Chat capabilities</span>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label="Chat capabilities"
          className={`absolute z-50 flex max-h-[min(620px,calc(100dvh-7rem))] w-[340px] max-w-[88vw] flex-col overflow-hidden rounded-2xl border border-cyan-400/30 bg-[#050914]/98 font-mono shadow-[0_24px_60px_rgba(0,0,0,0.85),0_0_28px_rgba(0,240,255,0.14)] backdrop-blur-2xl ${
            placement === 'top' ? 'bottom-[calc(100%+8px)]' : 'top-[calc(100%+8px)]'
          } ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          <div className="shrink-0 border-b border-slate-800 px-3.5 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-cyan-200">
                  <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                  Capabilities
                </div>
                <p className="mt-1 text-[9px] leading-relaxed text-slate-500">
                  Claude-style controls for how NEXUS thinks, answers, and speaks.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                title="Close capabilities"
                className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-white cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            {selectedModel && (
              <div className="mt-2 truncate rounded-lg border border-slate-800 bg-slate-950/70 px-2 py-1.5 text-[8.5px] text-slate-400">
                <span className="font-black uppercase tracking-wider text-slate-500">Model </span>
                <span className="font-bold text-cyan-100">{selectedModel.name}</span>
                <span className="text-slate-600"> · {selectedModel.provider}</span>
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="border-b border-slate-800 px-3.5 py-3">
              <div className="flex items-center gap-1.5 text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                <Sparkles className="h-3 w-3 text-cyan-300" />
                Execution effort
              </div>
              <div className="mt-2 grid grid-cols-5 gap-1" role="group" aria-label="Execution effort">
                {CHAT_EFFORT_OPTIONS.map((option) => {
                  const selected = capabilities.effort === option.id;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      disabled={disabled}
                      aria-pressed={selected}
                      title={`${option.label}: ${option.description}`}
                      onClick={() => onChange({ ...capabilities, effort: option.id })}
                      className={`rounded-lg border px-1 py-1.5 text-[8px] font-black transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                        selected
                          ? 'border-cyan-300/80 bg-cyan-400 text-slate-950 shadow-[0_0_12px_rgba(0,240,255,0.25)]'
                          : 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-cyan-400/40 hover:text-cyan-100'
                      }`}
                    >
                      {option.shortLabel}
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 text-[9px] leading-relaxed text-slate-500">
                <span className="font-bold text-cyan-100">{selectedEffort.label}:</span>{' '}
                {selectedEffort.description}
              </p>
            </div>

            <div className="space-y-1 p-2">
              {CAPABILITY_TOGGLES.map((toggle) => {
                const Icon = toggle.icon;
                const enabled = capabilities[toggle.key];
                const modelSupported =
                  !toggle.modelCapability || modelSupports(selectedModel, toggle.modelCapability);

                return (
                  <div
                    key={toggle.key}
                    className={`flex items-start gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                      enabled
                        ? 'border-cyan-400/35 bg-cyan-500/8'
                        : 'border-transparent hover:border-slate-800 hover:bg-slate-900/70'
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${
                        enabled
                          ? 'border-cyan-400/40 bg-cyan-950 text-cyan-300'
                          : 'border-slate-800 bg-slate-950 text-slate-500'
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] font-black text-slate-100">{toggle.label}</span>
                        {toggle.note && (
                          <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[7px] font-black uppercase tracking-wider text-slate-500">
                            {toggle.note}
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-[9px] leading-relaxed text-slate-500">
                        {toggle.description}
                      </p>
                      {toggle.modelCapability && selectedModel && !modelSupported && (
                        <p className="mt-1 text-[7.5px] font-bold uppercase tracking-wider text-amber-300/80">
                          Not a listed strength of this model
                        </p>
                      )}
                    </div>

                    <ToggleSwitch
                      enabled={enabled}
                      disabled={disabled}
                      label={toggle.label}
                      onToggle={() => toggleCapability(toggle.key)}
                    />
                  </div>
                );
              })}
            </div>

            <div className="border-t border-slate-800 px-3.5 py-3">
              <div className="text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                Selected model capabilities
              </div>
              {selectedModel ? (
                <div className="mt-2 grid grid-cols-2 gap-1.5">
                  {CAPABILITY_KEYS.map((capability) => {
                    const Icon = MODEL_CAPABILITY_ICONS[capability];
                    const supported = modelSupports(selectedModel, capability);
                    const label = getCapabilityLabel(capability, capabilityLabels);
                    return (
                      <div
                        key={capability}
                        title={`${label}: ${CAPABILITY_META[capability].description}`}
                        className={`flex items-center gap-1.5 rounded-lg border px-2 py-1.5 text-[8px] font-bold ${
                          supported
                            ? 'border-cyan-400/25 bg-cyan-950/50 text-cyan-100'
                            : 'border-slate-800 bg-slate-950/50 text-slate-600'
                        }`}
                      >
                        <Icon className={`h-3 w-3 shrink-0 ${supported ? 'text-cyan-300' : 'text-slate-600'}`} />
                        <span className="min-w-0 flex-1 truncate">{label}</span>
                        {supported ? (
                          <Check className="h-3 w-3 shrink-0 text-emerald-300" />
                        ) : (
                          <X className="h-3 w-3 shrink-0 text-slate-700" />
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-2 text-[9px] leading-relaxed text-slate-500">
                  Choose a model to see its supported capabilities.
                </p>
              )}
            </div>
          </div>

          <div className="shrink-0 border-t border-slate-800 bg-slate-950/70 px-3.5 py-2 text-[8px] leading-relaxed text-slate-500">
            Changes apply to the next message. Extended thinking never changes the spoken text—voice replies read the final answer only.
          </div>
        </div>
      )}
    </div>
  );
};
