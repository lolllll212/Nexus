import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AudioLines,
  BookOpen,
  Brain,
  Check,
  ChevronDown,
  Code2,
  Database,
  Eye,
  Search,
  Sparkles,
  Telescope,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import {
  formatContextWindow,
  formatSpeed,
  getCapabilityLabel,
  getModelById,
} from '../data/modelCatalog';
import type { ModelCatalog, NexusModel } from '../types';

interface ChatModelPickerProps {
  catalog: ModelCatalog;
  value: string;
  onChange: (modelId: string) => void;
  variant?: 'composer' | 'header' | 'settings';
  placement?: 'up' | 'down';
  align?: 'left' | 'right';
  disabled?: boolean;
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

function providerStatusCopy(catalog: ModelCatalog) {
  if (catalog.provider_status === 'live') {
    return {
      label: 'NVIDIA NIM live',
      dot: 'bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.14)]',
      detail: 'Live requests use the backend NVIDIA API key.',
    };
  }
  if (catalog.provider_status === 'offline') {
    return {
      label: 'Catalog offline',
      dot: 'bg-stone-400 shadow-[0_0_0_4px_rgba(168,162,158,0.14)]',
      detail: 'Showing bundled models until the NEXUS API is reachable.',
    };
  }
  return {
    label: 'NIM simulation',
    dot: 'bg-amber-500 shadow-[0_0_0_4px_rgba(245,158,11,0.14)]',
    detail: 'Practical fallback is active. Add an NVIDIA key for live model reasoning.',
  };
}

function isAutoModel(model: NexusModel): boolean {
  return model.id === 'auto' || model.source === 'nexus-default';
}

const ModelOption: React.FC<{
  model: NexusModel;
  selected: boolean;
  highlighted: boolean;
  serverActiveId: string | null;
  labels: Record<string, string>;
  optionRef: (node: HTMLButtonElement | null) => void;
  onSelect: (modelId: string) => void;
  onHighlight: () => void;
}> = ({ model, selected, highlighted, serverActiveId, labels, optionRef, onSelect, onHighlight }) => (
  <button
    ref={optionRef}
    type="button"
    role="option"
    aria-selected={selected}
    data-model-id={model.id}
    onClick={() => onSelect(model.id)}
    onMouseEnter={onHighlight}
    className={`w-full rounded-2xl border px-3.5 py-3 text-left transition-all duration-150 ${
      selected
        ? 'border-[#e6a88f] bg-[#fff6f0] shadow-[inset_0_0_0_1px_rgba(217,119,87,0.12)]'
        : highlighted
          ? 'border-[#e2ddd2] bg-[#fbfaf7]'
          : 'border-transparent bg-transparent hover:border-[#e7e2d6] hover:bg-[#fbfaf7]'
    }`}
  >
    <div className="flex items-start gap-3">
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-[11px] font-bold ${
          selected
            ? 'bg-[linear-gradient(135deg,#d97757,#8b7cf6_58%,#2f9e8f)] text-white shadow-sm'
            : 'bg-[#f0eee6] text-[#77736a]'
        }`}
      >
        {isAutoModel(model) ? '✦' : model.name.slice(0, 1)}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="truncate text-sm font-semibold text-[#262624]">{model.name}</span>
          {model.id === serverActiveId && (
            <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-700">
              Server default
            </span>
          )}
          {model.tags.includes('flagship') && (
            <span className="rounded-full bg-violet-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-violet-700">
              Flagship
            </span>
          )}
          {model.tags.includes('vision') && (
            <span className="rounded-full bg-sky-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-sky-700">
              Vision
            </span>
          )}
        </span>
        <span className="mt-0.5 block truncate text-[11px] font-medium uppercase tracking-[0.11em] text-[#9a968d]">
          {model.provider}
        </span>
        {(model.best_for || model.description) && (
          <span className="mt-1 block line-clamp-2 text-xs leading-5 text-[#77736a]">
            {model.best_for || model.description}
          </span>
        )}

        <span className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="flex items-center gap-1 rounded-full bg-[#f0eee6] px-2 py-0.5 text-[10px] font-semibold text-[#625f58]">
            <Zap className="h-3 w-3 text-[#d97757]" />
            {formatSpeed(model.speed)}
          </span>
          <span className="flex items-center gap-1 rounded-full bg-[#f0eee6] px-2 py-0.5 text-[10px] font-semibold text-[#625f58]">
            <BookOpen className="h-3 w-3 text-[#7c6cf0]" />
            {formatContextWindow(model.context_window)}
          </span>
          {model.capabilities.slice(0, 4).map((capability) => {
            const Icon = CAPABILITY_ICONS[capability] || Sparkles;
            return (
              <span
                key={capability}
                title={getCapabilityLabel(capability, labels)}
                className="flex items-center gap-1 rounded-full border border-[#e7e2d6] bg-white px-2 py-0.5 text-[10px] font-medium text-[#77736a]"
              >
                <Icon className="h-3 w-3" />
                {getCapabilityLabel(capability, labels).replace('Extended ', '').replace(' (images)', '')}
              </span>
            );
          })}
        </span>
      </span>

      <span
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
          selected ? 'border-[#d97757] bg-[#d97757] text-white' : 'border-[#ddd8cc] bg-white text-transparent'
        }`}
      >
        <Check className="h-3.5 w-3.5" />
      </span>
    </div>
  </button>
);

/**
 * Light, Claude-style model changer for the NEXUS chat window.
 *
 * The interaction is Claude-inspired (quiet trigger, rich option rows, check
 * mark), while the gradient/status treatment intentionally blends Gemini and
 * ChatGPT cues. Models are still NEXUS/NVIDIA NIM routes—never Anthropic.
 */
export const ChatModelPicker: React.FC<ChatModelPickerProps> = ({
  catalog,
  value,
  onChange,
  variant = 'composer',
  placement = 'up',
  align = 'right',
  disabled = false,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const optionRefs = useRef(new Map<string, HTMLButtonElement>());

  const selectedModel = useMemo(
    () => getModelById(catalog.models, value) || catalog.models[0] || null,
    [catalog.models, value],
  );

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = catalog.models.filter((model) => {
      if (!needle) return true;
      return [
        model.id,
        model.name,
        model.provider,
        model.description,
        model.best_for,
        formatSpeed(model.speed),
        ...model.tags,
        ...model.capabilities.map((capability) => getCapabilityLabel(capability, catalog.capability_labels)),
      ]
        .join(' ')
        .toLowerCase()
        .includes(needle);
    });

    const auto = filtered.filter(isAutoModel);
    const fast = filtered.filter(
      (model) => !isAutoModel(model) && (['fastest', 'fast'].includes(model.speed) || model.tags.includes('fast')),
    );
    const deep = filtered.filter((model) => !auto.includes(model) && !fast.includes(model));
    return [
      { label: 'Smart default', description: 'Configured NEXUS cortex', models: auto },
      { label: 'Fast for everyday work', description: 'Quick answers and voice', models: fast },
      { label: 'Deep & specialist', description: 'Research, reasoning, vision', models: deep },
    ].filter((group) => group.models.length > 0);
  }, [catalog.capability_labels, catalog.models, query]);

  const flatModels = useMemo(() => groups.flatMap((group) => group.models), [groups]);
  const status = providerStatusCopy(catalog);

  const close = (restoreFocus = false) => {
    setIsOpen(false);
    setQuery('');
    if (restoreFocus) window.setTimeout(() => triggerRef.current?.focus(), 0);
  };

  const open = () => {
    if (disabled || !selectedModel) return;
    const selectedIndex = Math.max(0, catalog.models.findIndex((model) => model.id === selectedModel.id));
    setHighlightedIndex(selectedIndex);
    setIsOpen(true);
  };

  useEffect(() => {
    if (!isOpen) return undefined;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) close();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close(true);
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    const focusTimer = window.setTimeout(() => searchRef.current?.focus(), 30);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const selectedIndex = selectedModel
      ? flatModels.findIndex((model) => model.id === selectedModel.id)
      : -1;
    setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0);
  }, [flatModels, isOpen, query, selectedModel]);

  useEffect(() => {
    if (!isOpen || flatModels.length === 0) return;
    const model = flatModels[Math.min(highlightedIndex, flatModels.length - 1)];
    if (model) optionRefs.current.get(model.id)?.scrollIntoView({ block: 'nearest' });
  }, [flatModels, highlightedIndex, isOpen]);

  const selectModel = (modelId: string) => {
    onChange(modelId);
    close(true);
  };

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlightedIndex((current) => Math.min(current + 1, Math.max(0, flatModels.length - 1)));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightedIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === 'Home') {
      event.preventDefault();
      setHighlightedIndex(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      setHighlightedIndex(Math.max(0, flatModels.length - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const model = flatModels[highlightedIndex];
      if (model) selectModel(model.id);
    }
  };

  const triggerClass =
    variant === 'settings'
      ? 'flex w-full items-center gap-3 rounded-2xl border border-[#ddd8cc] bg-[#fbfaf7] px-4 py-3 text-left shadow-sm transition-all hover:border-[#c9a189] hover:bg-white focus:outline-none focus:ring-2 focus:ring-[#d97757]/20 disabled:cursor-not-allowed disabled:opacity-50'
      : variant === 'header'
        ? 'flex max-w-[260px] items-center gap-2 rounded-full border border-white/70 bg-white/75 px-3.5 py-2 text-left text-sm font-medium text-[#3d392f] shadow-[0_8px_24px_rgba(61,57,47,0.08)] backdrop-blur transition-all hover:bg-white focus:outline-none focus:ring-2 focus:ring-[#d97757]/20 disabled:cursor-not-allowed disabled:opacity-50'
        : 'flex max-w-[205px] items-center gap-1.5 rounded-full px-2.5 py-2 text-left text-sm font-medium text-[#55534d] transition-all hover:bg-[#f3f0e8] hover:text-[#262624] focus:outline-none focus:ring-2 focus:ring-[#d97757]/20 disabled:cursor-not-allowed disabled:opacity-50 sm:max-w-[230px]';

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled || !selectedModel}
        onClick={() => (isOpen ? close(true) : open())}
        onKeyDown={(event) => {
          if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !isOpen) {
            event.preventDefault();
            open();
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        title={selectedModel ? `Change model — currently ${selectedModel.name}` : 'Choose a model'}
        className={triggerClass}
      >
        <span className="nexus-gradient-orb flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white shadow-sm">
          <Sparkles className="h-3.5 w-3.5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate">{selectedModel?.name || 'Choose model'}</span>
          {variant === 'settings' && selectedModel && (
            <span className="mt-0.5 block truncate text-xs font-normal text-[#85817a]">
              {selectedModel.provider} · {selectedModel.best_for}
            </span>
          )}
        </span>
        <span className={`h-2 w-2 shrink-0 rounded-full ${status.dot}`} aria-hidden="true" />
        <ChevronDown className={`h-4 w-4 shrink-0 text-[#85817a] transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && selectedModel && (
        <div
          role="listbox"
          aria-label="Choose a NEXUS model"
          className={`nexus-popover-in absolute z-[70] flex max-h-[min(600px,calc(100dvh-7rem))] w-[396px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-[26px] border border-[#e0dbce] bg-white/[0.985] shadow-[0_28px_80px_rgba(38,38,36,0.22)] backdrop-blur-xl ${
            placement === 'up' ? 'bottom-[calc(100%+10px)]' : 'top-[calc(100%+10px)]'
          } ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          <div className="shrink-0 border-b border-[#efede6] bg-[linear-gradient(135deg,rgba(255,246,238,0.95),rgba(255,255,255,0.98)_48%,rgba(238,244,255,0.92))] px-4 pb-3 pt-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-[#262624]">
                  Choose model
                  <span className="nexus-gradient-text text-[11px] font-bold uppercase tracking-[0.13em]">Nexus routes</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-[#85817a]">
                  Applies to your next message. Tools, backend history, and voice stay connected.
                </p>
              </div>
              <button
                type="button"
                onClick={() => close(true)}
                aria-label="Close model picker"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#85817a] transition-colors hover:bg-white hover:text-[#262624]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="relative mt-3">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#aaa69d]" />
              <input
                ref={searchRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="Search fast, vision, research, Llama…"
                aria-label="Search models"
                className="w-full rounded-full border border-[#ddd8cc] bg-white py-2.5 pl-10 pr-9 text-sm text-[#262624] outline-none transition-all placeholder:text-[#b0aa9d] focus:border-[#c9a189] focus:ring-2 focus:ring-[#d97757]/15"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  aria-label="Clear model search"
                  className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-[#85817a] hover:bg-[#f0eee6]"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>

          <div className="nxs-scroll min-h-0 flex-1 overflow-y-auto p-2.5">
            {groups.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <Search className="mx-auto h-8 w-8 text-[#d8d3c7]" />
                <p className="mt-3 text-sm font-medium text-[#262624]">No models match “{query}”</p>
                <p className="mt-1 text-xs text-[#85817a]">Try “fast”, “vision”, “research”, or a provider name.</p>
              </div>
            ) : (
              groups.map((group) => (
                <div key={group.label} className="mb-2 last:mb-0">
                  <div className="flex items-baseline justify-between gap-3 px-2.5 pb-1.5 pt-2">
                    <span className="text-[11px] font-bold uppercase tracking-[0.13em] text-[#9a968d]">{group.label}</span>
                    <span className="text-[10px] text-[#b0aa9d]">{group.description}</span>
                  </div>
                  <div className="space-y-1">
                    {group.models.map((model) => {
                      const flatIndex = flatModels.findIndex((item) => item.id === model.id);
                      return (
                        <ModelOption
                          key={model.id}
                          model={model}
                          selected={model.id === selectedModel.id}
                          highlighted={flatIndex === highlightedIndex}
                          serverActiveId={catalog.active_model}
                          labels={catalog.capability_labels}
                          optionRef={(node) => {
                            if (node) optionRefs.current.set(model.id, node);
                            else optionRefs.current.delete(model.id);
                          }}
                          onSelect={selectModel}
                          onHighlight={() => setHighlightedIndex(flatIndex)}
                        />
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="shrink-0 border-t border-[#efede6] bg-[#fbfaf7] px-4 py-3">
            <div className="flex items-start gap-2.5">
              <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${status.dot}`} />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-[#262624]">{status.label}</div>
                <div className="mt-0.5 text-[11px] leading-4 text-[#85817a]">{status.detail}</div>
              </div>
              <span className="rounded-full bg-[#f0eee6] px-2 py-1 text-[10px] font-medium text-[#77736a]">
                Not Anthropic
              </span>
            </div>
            <p className="mt-2 text-[10px] leading-4 text-[#b0aa9d]">Tip: use ↑ ↓ and Enter to choose without leaving the keyboard.</p>
          </div>
        </div>
      )}
    </div>
  );
};
