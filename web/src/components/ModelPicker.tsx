import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AudioLines,
  BookOpen,
  Brain,
  Check,
  ChevronDown,
  Code2,
  Cpu,
  Database,
  Eye,
  Sparkles,
  Telescope,
  Wrench,
  Zap,
} from 'lucide-react';
import {
  formatContextWindow,
  formatSpeed,
  getCapabilityLabel,
  getModelById,
} from '../data/modelCatalog';
import type { ModelCatalog, NexusModel } from '../types';

interface ModelPickerProps {
  catalog: ModelCatalog;
  value: string;
  onChange: (modelId: string) => void;
  compact?: boolean;
  disabled?: boolean;
  align?: 'left' | 'right';
  className?: string;
}

const CAPABILITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  reasoning: Brain,
  tool_use: Wrench,
  code: Code2,
  vision: Eye,
  long_context: Database,
  research: Telescope,
  streaming: AudioLines,
};

function ProviderStatus({ catalog }: { catalog: ModelCatalog }) {
  const status = catalog.provider_status || 'simulation';
  const config = {
    live: {
      dot: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]',
      label: 'NVIDIA NIM live',
      detail: 'Requests use your configured NVIDIA API key.',
    },
    simulation: {
      dot: 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]',
      label: 'NIM simulation mode',
      detail: 'Add an NVIDIA API key on the backend for live model replies.',
    },
    offline: {
      dot: 'bg-slate-500',
      label: 'Model catalog offline',
      detail: 'Showing bundled models until the NEXUS API is reachable.',
    },
  }[status] || {
    dot: 'bg-cyan-400',
    label: status,
    detail: 'Model routing is handled by the NEXUS backend.',
  };

  return (
    <div className="flex items-start gap-2 px-3 py-2.5">
      <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${config.dot}`} />
      <div className="min-w-0">
        <div className="text-[9px] font-black uppercase tracking-[0.18em] text-slate-200">
          {config.label}
        </div>
        <div className="mt-0.5 text-[9px] leading-relaxed text-slate-500">{config.detail}</div>
      </div>
    </div>
  );
}

function CapabilityIcons({ model, labels }: { model: NexusModel; labels: Record<string, string> }) {
  if (!model.capabilities.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1" aria-label="Model capabilities">
      {model.capabilities.map((capability) => {
        const Icon = CAPABILITY_ICONS[capability] || Sparkles;
        return (
          <span
            key={capability}
            title={getCapabilityLabel(capability, labels)}
            className="flex h-5 w-5 items-center justify-center rounded-md border border-cyan-400/20 bg-cyan-950/50 text-cyan-300"
          >
            <Icon className="h-3 w-3" />
          </span>
        );
      })}
    </div>
  );
}

const ModelOption: React.FC<{
  model: NexusModel;
  selected: boolean;
  serverActiveId: string | null;
  labels: Record<string, string>;
  onSelect: (modelId: string) => void;
}> = ({ model, selected, serverActiveId, labels, onSelect }) => {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={() => onSelect(model.id)}
      className={`w-full rounded-xl border px-3 py-2.5 text-left transition-all cursor-pointer ${
        selected
          ? 'border-cyan-400/60 bg-cyan-500/10 shadow-[inset_0_0_18px_rgba(0,240,255,0.06)]'
          : 'border-transparent bg-transparent hover:border-slate-700 hover:bg-slate-900/80'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`truncate text-[11px] font-black ${selected ? 'text-cyan-100' : 'text-slate-100'}`}>
              {model.name}
            </span>
            {model.id === serverActiveId && (
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[7.5px] font-black uppercase tracking-wider text-emerald-300">
                Server default
              </span>
            )}
            {model.tags.includes('flagship') && (
              <span className="rounded bg-fuchsia-500/15 px-1.5 py-0.5 text-[7.5px] font-black uppercase tracking-wider text-fuchsia-300">
                Flagship
              </span>
            )}
          </div>
          <div className="mt-0.5 truncate text-[8.5px] font-bold uppercase tracking-[0.16em] text-slate-500">
            {model.provider}
          </div>
        </div>
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
            selected
              ? 'border-cyan-300 bg-cyan-400 text-slate-950'
              : 'border-slate-700 bg-slate-900 text-transparent'
          }`}
        >
          <Check className="h-3 w-3" />
        </span>
      </div>

      {(model.best_for || model.description) && (
        <p className="mt-1.5 line-clamp-2 text-[9.5px] leading-relaxed text-slate-400">
          {model.best_for || model.description}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <CapabilityIcons model={model} labels={labels} />
        <div className="flex items-center gap-1 text-[8px] font-bold uppercase tracking-wider text-slate-500">
          <span className="flex items-center gap-1 rounded bg-slate-900 px-1.5 py-0.5">
            <Zap className="h-2.5 w-2.5 text-amber-300" />
            {formatSpeed(model.speed)}
          </span>
          <span className="flex items-center gap-1 rounded bg-slate-900 px-1.5 py-0.5">
            <BookOpen className="h-2.5 w-2.5 text-cyan-300" />
            {formatContextWindow(model.context_window)}
          </span>
        </div>
      </div>
    </button>
  );
};

export const ModelPicker: React.FC<ModelPickerProps> = ({
  catalog,
  value,
  onChange,
  compact = false,
  disabled = false,
  align = 'left',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const selectedModel = useMemo(
    () => getModelById(catalog.models, value) || catalog.models[0] || null,
    [catalog.models, value],
  );

  const groups = useMemo(() => {
    const auto = catalog.models.filter((model) => model.id === 'auto' || model.source === 'nexus-default');
    const nim = catalog.models.filter((model) => !(model.id === 'auto' || model.source === 'nexus-default'));
    return [
      { label: 'NEXUS Cortex', models: auto },
      { label: 'NVIDIA NIM models', models: nim },
    ].filter((group) => group.models.length > 0);
  }, [catalog.models]);

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

  const handleSelect = (modelId: string) => {
    onChange(modelId);
    setIsOpen(false);
  };

  const statusDot =
    catalog.provider_status === 'live'
      ? 'bg-emerald-400'
      : catalog.provider_status === 'offline'
        ? 'bg-slate-500'
        : 'bg-amber-400';

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled || !selectedModel}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        title={selectedModel ? `Model: ${selectedModel.name}` : 'Choose a model'}
        className={`flex items-center gap-2 rounded-xl border font-mono transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
          compact
            ? 'max-w-[190px] px-2.5 py-1.5 text-[10px]'
            : 'max-w-[250px] px-3 py-2 text-[10.5px]'
        } ${
          isOpen
            ? 'border-cyan-300/70 bg-cyan-500/15 text-cyan-100 shadow-[0_0_16px_rgba(0,240,255,0.18)]'
            : 'border-cyan-400/30 bg-slate-950/70 text-slate-200 hover:border-cyan-400/60 hover:bg-cyan-950/60'
        }`}
      >
        <Cpu className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
        <span className="min-w-0 flex-1 truncate text-left font-black">
          {selectedModel?.name || 'Choose model'}
        </span>
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot}`} />
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && selectedModel && (
        <div
          role="listbox"
          aria-label="Choose a chat model"
          className={`absolute top-[calc(100%+8px)] z-50 flex max-h-[min(560px,calc(100dvh-7rem))] w-[340px] max-w-[88vw] flex-col overflow-hidden rounded-2xl border border-cyan-400/30 bg-[#050914]/98 font-mono shadow-[0_24px_60px_rgba(0,0,0,0.85),0_0_28px_rgba(0,240,255,0.14)] backdrop-blur-2xl ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          <div className="shrink-0 border-b border-slate-800 px-3.5 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-cyan-200">
                  Choose model
                </div>
                <div className="mt-1 text-[9px] leading-relaxed text-slate-500">
                  Applies to the next chat request. NEXUS tools and memory stay active.
                </div>
              </div>
              <Sparkles className="h-4 w-4 shrink-0 text-cyan-400" />
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {groups.map((group) => (
              <div key={group.label} className="mb-2 last:mb-0">
                <div className="px-2 pb-1.5 pt-2 text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                  {group.label}
                </div>
                <div className="space-y-1">
                  {group.models.map((model) => (
                    <ModelOption
                      key={model.id}
                      model={model}
                      selected={model.id === selectedModel.id}
                      serverActiveId={catalog.active_model}
                      labels={catalog.capability_labels}
                      onSelect={handleSelect}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="shrink-0 border-t border-slate-800 bg-slate-950/70">
            <ProviderStatus catalog={catalog} />
          </div>
        </div>
      )}
    </div>
  );
};
