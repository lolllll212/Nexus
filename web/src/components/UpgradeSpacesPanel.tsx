import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  Clock3,
  FileCheck2,
  Filter,
  Gauge,
  Layers3,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { fetchUpgradeSpaces } from '../api';
import type { UpgradeSpacesResponse } from '../types';

function formatGeneratedAt(value: string | undefined): string {
  if (!value) return 'Not loaded yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kolkata',
  }).format(date);
}

function priorityClass(priority: string): string {
  const normalized = priority.toLowerCase();
  if (normalized.includes('critical') || normalized.includes('high') || normalized.includes('p0')) {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  if (normalized.includes('medium') || normalized.includes('p1')) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  return 'border-cyan-200 bg-cyan-50 text-cyan-700';
}

export const UpgradeSpacesPanel: React.FC = () => {
  const [data, setData] = useState<UpgradeSpacesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [priority, setPriority] = useState('all');
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchUpgradeSpaces(controller.signal);
      if (!controller.signal.aborted) setData(response);
    } catch (loadError) {
      if (controller.signal.aborted || (loadError instanceof Error && loadError.name === 'AbortError')) return;
      setError(loadError instanceof Error ? loadError.message : 'Could not load Upgrade Spaces.');
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => controllerRef.current?.abort();
  }, [load]);

  const priorities = useMemo(
    () => ['all', ...Array.from(new Set((data?.spaces ?? []).map((space) => space.priority))).sort()],
    [data],
  );

  const filteredSpaces = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.spaces ?? []).filter((space) => {
      if (priority !== 'all' && space.priority !== priority) return false;
      if (!needle) return true;
      return [
        String(space.id),
        space.name,
        space.priority,
        space.owner,
        space.summary,
        space.status,
        space.runtime_note,
        ...space.evidence,
      ]
        .join(' ')
        .toLowerCase()
        .includes(needle);
    });
  }, [data, priority, query]);

  const telemetryCounters = Object.entries(data?.telemetry.counters ?? {}).slice(0, 6);

  return (
    <main className="mx-auto w-full max-w-[1180px] px-6 pb-48 pt-12 sm:px-10">
      <header className="flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0 max-w-3xl">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.24em] text-slate-400">
            <Layers3 className="h-4 w-4 text-cyan-600" />
            Nexus OS · Upgrade Spaces
          </div>
          <h1 className="mt-4 text-4xl font-extrabold tracking-[-0.025em] text-slate-900 sm:text-5xl">
            Ten spaces. <span className="text-slate-400">One shared source of truth.</span>
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-slate-500">
            Search every platform upgrade, inspect its implementation evidence, and distinguish code that has landed
            from optional runtime features that still need credentials, Docker, or an explicit environment switch.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition-all hover:border-cyan-300 hover:text-cyan-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </header>

      <section className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Upgrade Spaces summary">
        <div className="rounded-3xl border border-emerald-100 bg-emerald-50/70 p-5">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-600">
            <CheckCircle2 className="h-4 w-4" /> Landed
          </div>
          <div className="mt-2 text-3xl font-extrabold text-slate-900">
            {data ? `${data.summary.landed}/${data.summary.total}` : '—'}
          </div>
          <p className="mt-1 text-xs text-slate-500">Implementation present in the repository.</p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
            <Clock3 className="h-4 w-4" /> Generated
          </div>
          <div className="mt-2 text-base font-bold leading-snug text-slate-900">{formatGeneratedAt(data?.generated_at)}</div>
          <p className="mt-1 text-xs text-slate-500">Asia/Kolkata · live API response.</p>
        </div>
        <div className="rounded-3xl border border-violet-100 bg-violet-50/70 p-5">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-violet-600">
            <Wrench className="h-4 w-4" /> Tool registry
          </div>
          <div className="mt-2 text-3xl font-extrabold text-slate-900">{data?.tools_count ?? '—'}</div>
          <p className="mt-1 text-xs text-slate-500">Tools currently registered with Nexus.</p>
        </div>
        <div className="rounded-3xl border border-cyan-100 bg-cyan-50/70 p-5">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-700">
            <Gauge className="h-4 w-4" /> Telemetry
          </div>
          <div className="mt-2 text-lg font-extrabold text-slate-900">
            {data ? (data.telemetry.enabled ? 'Enabled' : 'Inert by default') : '—'}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            {data
              ? `${data.telemetry.metrics_backend ?? 'metrics n/a'} · ${data.telemetry.tracer_backend ?? 'tracer n/a'}`
              : 'Waiting for the telemetry snapshot.'}
          </p>
        </div>
      </section>

      {telemetryCounters.length > 0 && (
        <section className="mt-4 flex flex-wrap items-center gap-2 rounded-3xl border border-slate-200 bg-white px-5 py-4" aria-label="Agent telemetry counters">
          <span className="mr-1 inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
            <Activity className="h-4 w-4 text-cyan-600" /> Agent telemetry
          </span>
          {telemetryCounters.map(([name, value]) => (
            <span key={name} className="rounded-full bg-slate-50 px-3 py-1.5 font-mono text-[11px] text-slate-600">
              {name}: <strong className="text-slate-900">{value}</strong>
            </span>
          ))}
          {data?.telemetry.heal_success_rate !== undefined && data.telemetry.heal_success_rate !== null && (
            <span className="rounded-full bg-emerald-50 px-3 py-1.5 font-mono text-[11px] text-emerald-700">
              heal_success_rate: <strong>{Math.round(data.telemetry.heal_success_rate * 100)}%</strong>
            </span>
          )}
        </section>
      )}

      <section className="sticky top-4 z-20 mt-6 rounded-3xl border border-slate-200/90 bg-white/90 p-3 shadow-[0_16px_40px_-24px_rgba(15,23,42,0.35)] backdrop-blur-xl">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search Upgrade Spaces</span>
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search spaces, evidence files, owners, runtime notes…"
              className="w-full rounded-full border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-cyan-400 focus:bg-white"
            />
          </label>
          <label className="relative sm:w-52">
            <span className="sr-only">Filter by priority</span>
            <Filter className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              className="w-full appearance-none rounded-full border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-sm font-medium capitalize text-slate-700 outline-none focus:border-cyan-400 focus:bg-white"
            >
              {priorities.map((item) => (
                <option key={item} value={item}>{item === 'all' ? 'All priorities' : item}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="px-2 pt-2 text-xs text-slate-400" aria-live="polite">
          Showing {filteredSpaces.length} of {data?.spaces.length ?? 0} spaces.
        </div>
      </section>

      {error && (
        <div className="mt-6 rounded-3xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-relaxed text-amber-900">
          <strong>Upgrade Spaces could not be loaded.</strong> {error}
          <button type="button" onClick={() => void load()} className="ml-3 font-bold underline underline-offset-2">
            Retry
          </button>
        </div>
      )}

      {isLoading && !data ? (
        <div className="mt-10 flex items-center justify-center gap-3 rounded-3xl border border-slate-200 bg-white px-6 py-16 text-sm font-medium text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-600" />
          Loading the shared Upgrade Spaces catalog…
        </div>
      ) : filteredSpaces.length === 0 && !error ? (
        <div className="mt-10 rounded-3xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <Search className="mx-auto h-8 w-8 text-slate-300" />
          <h2 className="mt-3 text-lg font-bold text-slate-900">No spaces match that search</h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate-500">
            Try a capability (“telemetry”), an evidence filename, or clear the priority filter.
          </p>
          <button
            type="button"
            onClick={() => { setQuery(''); setPriority('all'); }}
            className="mt-5 rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <section className="mt-6 grid gap-5 md:grid-cols-2" aria-label="Upgrade Spaces catalog">
          {filteredSpaces.map((space) => (
            <article key={space.id} className="group rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_12px_34px_-24px_rgba(16,24,40,0.3)] transition-all hover:-translate-y-0.5 hover:border-cyan-200 hover:shadow-[0_24px_50px_-28px_rgba(8,145,178,0.45)]">
              <div className="flex items-start justify-between gap-3">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-900 font-mono text-sm font-bold text-white">
                  {String(space.id).padStart(2, '0')}
                </span>
                <div className="flex flex-wrap justify-end gap-1.5">
                  <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${priorityClass(space.priority)}`}>
                    {space.priority}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                    <ShieldCheck className="h-3 w-3" /> {space.status}
                  </span>
                </div>
              </div>

              <h2 className="mt-5 text-xl font-extrabold tracking-tight text-slate-900">{space.name}</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{space.summary}</p>

              <div className="mt-4 rounded-2xl bg-amber-50/80 px-4 py-3 text-xs leading-relaxed text-amber-900">
                <span className="font-bold uppercase tracking-wider">Runtime note · </span>
                {space.runtime_note}
              </div>

              <div className="mt-4">
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                  <FileCheck2 className="h-3.5 w-3.5 text-cyan-600" /> Evidence
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {space.evidence.map((path) => (
                    <code key={path} className="max-w-full truncate rounded-full bg-slate-50 px-2.5 py-1 font-mono text-[10px] text-slate-500" title={path}>
                      {path}
                    </code>
                  ))}
                </div>
              </div>

              <div className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-400">
                Owner <span className="font-semibold text-slate-600">{space.owner}</span>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
};
