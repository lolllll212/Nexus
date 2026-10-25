import React, { useMemo, useState } from 'react';
import { Boxes, ArrowRight, X, Route, ShieldCheck, Layers3 } from 'lucide-react';
import { nexusJson } from '../../api';
import { PageHeader, ViewShell, LiveChip } from './shared';

/* ────────────────────────────────────────────────────────────────────────────
 * Light Hexagonal Architecture viewer — ports & adapters, live.
 * The diagram itself is the running system: infrastructure adapters and their
 * route counts are read straight from GET /openapi.json, grouped under the
 * six application use-case modules around the domain hexagon.
 * ──────────────────────────────────────────────────────────────────────────── */

interface OpenApiSpec {
  paths: Record<string, Record<string, { tags?: string[] }>>;
}

interface AdapterInfo {
  tag: string;
  routes: string[];
}

interface Sector {
  name: string;
  sub: string;
  hex: string;
  adapters: string[];
}

const SECTORS: Sector[] = [
  { name: 'Cortex', sub: 'interactive reasoning', hex: '#F59E0B', adapters: ['chat', 'coding', 'coding_assistant', 'nvidia-nim', 'audio'] },
  { name: 'Subcortex', sub: 'background synthesis', hex: '#06B6D4', adapters: ['memory', 'system', 'telemetry', 'analyze'] },
  { name: 'Swarm', sub: 'multi-agent mesh', hex: '#8B5CF6', adapters: ['swarm', 'goals', 'workflows'] },
  { name: 'Autonomy', sub: 'self-evolution', hex: '#10B981', adapters: ['research', 'tools', 'mcp', 'autonomy'] },
  { name: 'Perception', sub: 'multimodal bridge', hex: '#3B82F6', adapters: ['multimodal', 'graph', 'workspace'] },
  { name: 'Integrations', sub: 'external universe', hex: '#F43F5E', adapters: ['integrations'] },
];

const METHOD_COLORS: Record<string, string> = {
  get: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  post: 'bg-violet-50 text-violet-700 border-violet-200',
  put: 'bg-amber-50 text-amber-700 border-amber-200',
  delete: 'bg-rose-50 text-rose-700 border-rose-200',
  websocket: 'bg-cyan-50 text-cyan-700 border-cyan-200',
};

const CX = 460;
const CY = 310;
const APP_RING = 195;
const ADAPTER_RING = 305;

function hexPoints(cx: number, cy: number, r: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const a = ((-90 + i * 60) * Math.PI) / 180;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  }).join(' ');
}

function polar(cx: number, cy: number, r: number, deg: number): { x: number; y: number } {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}

export const ArchitectureLight: React.FC = () => {
  const [spec, setSpec] = useState<OpenApiSpec | null>(null);
  const [offline, setOffline] = useState(false);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await nexusJson<OpenApiSpec>('/openapi.json');
        if (!cancelled) {
          setSpec(data);
          setOffline(false);
        }
      } catch {
        if (!cancelled) setOffline(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Tag → routes index from the live OpenAPI spec
  const tagIndexMemo = useMemo(() => {
    const index: Record<string, string[]> = {};
    if (spec) {
      Object.entries(spec.paths).forEach(([path, methods]) => {
        Object.entries(methods).forEach(([method, op]) => {
          (op?.tags ?? ['untagged']).forEach((tag) => {
            const key = tag === 'meta' ? 'meta' : tag;
            (index[key] ??= []).push(`${method.toUpperCase()} ${path}`);
          });
        });
      });
    }
    return index;
    // NOTE: assigned to an explicitly typed const below — the local
    // react/tsgo combo erases useMemo generics to `any`.
  }, [spec]);
  const tagIndex: Record<string, string[]> = tagIndexMemo ?? {};

  const totalRoutes = useMemo(() => Object.values(tagIndex).reduce((acc, r) => acc + r.length, 0), [tagIndex]);

  // Assign every live tag to its sector (known mapping first, then round-robin)
  const sectorAdapters = useMemo(() => {
    const result = SECTORS.map((s) => ({ ...s, items: [] as AdapterInfo[] }));
    const known = new Map<string, number>();
    SECTORS.forEach((s, i) => s.adapters.forEach((t) => known.set(t, i)));
    let rr = 0;
    Object.keys(tagIndex)
      .sort()
      .forEach((tag) => {
        const info: AdapterInfo = { tag, routes: tagIndex[tag] ?? [] };
        const sectorIdx = known.get(tag) ?? rr++ % SECTORS.length;
        result[sectorIdx].items.push(info);
      });
    return result;
  }, [tagIndex]);

  const selected = useMemo(() => {
    if (!selectedTag) return null;
    for (const s of sectorAdapters) {
      const found = s.items.find((a) => a.tag === selectedTag);
      if (found) return { ...found, sector: s };
    }
    return null;
  }, [selectedTag, sectorAdapters]);

  const allTags = sectorAdapters.reduce((n, s) => n + s.items.length, 0);

  return (
    <ViewShell>
      <PageHeader
        route="ARCHITECTURE"
        right={
          <>
            <LiveChip offline={offline} label={offline ? 'OpenAPI offline' : `${totalRoutes} live routes`} />
            <span className="inline-flex items-center gap-2 px-3.5 py-2 rounded-full bg-white border border-slate-200 text-[12px] font-semibold text-slate-600">
              <Route className="w-3.5 h-3.5 text-amber-500" /> {allTags} adapters
            </span>
          </>
        }
      />

      {/* Legend */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900 text-white text-[11px] font-bold">
          <Boxes className="w-3 h-3" /> Domain — pure core
        </span>
        <ArrowRight className="w-3.5 h-3.5 text-slate-300" />
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[11px] font-bold text-slate-600">
          <Layers3 className="w-3 h-3 text-amber-500" /> Application use cases
        </span>
        <ArrowRight className="w-3.5 h-3.5 text-slate-300" />
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-slate-200 text-[11px] font-bold text-slate-600">
          <Route className="w-3 h-3 text-slate-400" /> Infrastructure adapters (live)
        </span>
      </div>

      {/* The hexagon */}
      <div className="mt-4 rounded-3xl bg-white border border-slate-200/80 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] overflow-hidden">
        <svg viewBox="0 0 920 620" className="w-full block" role="img" aria-label="Hexagonal architecture diagram">
          <defs>
            <pattern id="arch-grid" width="34" height="34" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r="1" fill="#EEF2F6" />
            </pattern>
          </defs>
          <rect width="920" height="620" fill="url(#arch-grid)" />

          {/* Spokes: domain → application */}
          {sectorAdapters.map((s, k) => {
            const a = -90 + k * 60;
            const p1 = polar(CX, CY, 96, a);
            const p2 = polar(CX, CY, APP_RING - 52, a);
            return <line key={`spoke-${s.name}`} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#CBD5E1" strokeWidth={1.6} strokeDasharray="3 4" />;
          })}

          {/* Application ring */}
          {sectorAdapters.map((s, k) => {
            const a = -90 + k * 60;
            const p = polar(CX, CY, APP_RING, a);
            return (
              <g key={s.name}>
                <polygon
                  points={hexPoints(p.x, p.y, 50)}
                  fill="#FFFFFF"
                  stroke={s.hex}
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                />
                <text x={p.x} y={p.y - 4} textAnchor="middle" fontSize={12.5} fontWeight={800} fill="#0F172A">
                  {s.name}
                </text>
                <text x={p.x} y={p.y + 11} textAnchor="middle" fontSize={8.5} fill="#94A3B8">
                  {s.sub}
                </text>
                <text x={p.x} y={p.y + 26} textAnchor="middle" fontSize={9} fontWeight={700} fill={s.hex} className="nxs-mono">
                  {s.items.length} adapters
                </text>
              </g>
            );
          })}

          {/* Adapters ring */}
          {sectorAdapters.map((s, k) => {
            const sectorAngle = -90 + k * 60;
            const n = s.items.length;
            return s.items.map((adapter, j) => {
              const spread = Math.min(20, 56 / Math.max(1, n));
              const angle = sectorAngle + (j - (n - 1) / 2) * spread;
              const appPoint = polar(CX, CY, APP_RING + 52, sectorAngle);
              const p = polar(CX, CY, ADAPTER_RING, angle);
              const w = 22 + adapter.tag.length * 6.4;
              const isSelected = selectedTag === adapter.tag;
              return (
                <g key={`${s.name}-${adapter.tag}`} style={{ cursor: 'pointer' }} onClick={() => setSelectedTag(isSelected ? null : adapter.tag)}>
                  <line
                    x1={appPoint.x}
                    y1={appPoint.y}
                    x2={p.x}
                    y2={p.y}
                    stroke={s.hex}
                    strokeWidth={isSelected ? 2 : 1}
                    opacity={isSelected ? 0.9 : 0.35}
                  />
                  <rect
                    x={p.x - w / 2}
                    y={p.y - 13}
                    width={w}
                    height={26}
                    rx={13}
                    fill={isSelected ? s.hex : '#FFFFFF'}
                    stroke={s.hex}
                    strokeWidth={isSelected ? 0 : 1.5}
                  />
                  <text
                    x={p.x}
                    y={p.y + 4}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={700}
                    fill={isSelected ? '#FFFFFF' : '#334155'}
                  >
                    {adapter.tag}
                    <tspan fontSize={8.5} fill={isSelected ? '#FFFFFF' : '#94A3B8'} opacity={0.85}>
                      {'  '}{adapter.routes.length}
                    </tspan>
                  </text>
                </g>
              );
            });
          })}

          {/* Domain core */}
          <polygon
            points={hexPoints(CX, CY, 92)}
            fill="#0F172A"
            stroke="#F59E0B"
            strokeWidth={3}
            strokeLinejoin="round"
          />
          <polygon points={hexPoints(CX, CY, 78)} fill="none" stroke="rgba(255,255,255,0.14)" strokeWidth={1.2} strokeLinejoin="round" />
          <text x={CX} y={CY - 16} textAnchor="middle" fontSize={10} fontWeight={800} letterSpacing={2.5} fill="#F59E0B">
            DOMAIN
          </text>
          <text x={CX} y={CY + 4} textAnchor="middle" fontSize={15} fontWeight={800} fill="#FFFFFF">
            NEXUS Core
          </text>
          <text x={CX} y={CY + 22} textAnchor="middle" fontSize={9} fill="#94A3B8">
            entities · value objects · ports
          </text>
          <text x={CX} y={CY + 38} textAnchor="middle" fontSize={8.5} fill="#64748B">
            zero framework imports
          </text>
        </svg>
      </div>

      {/* Selected adapter detail */}
      {selected && (
        <div className="mt-4 rounded-3xl bg-white border border-slate-200/80 p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] animate-[nxs-rise_0.3s_cubic-bezier(0.22,1,0.36,1)]">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <span
                className="w-10 h-10 rounded-2xl flex items-center justify-center text-white text-[12px] font-extrabold"
                style={{ backgroundColor: selected.sector.hex }}
              >
                {selected.tag.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <h3 className="text-[15px] font-bold text-slate-900">
                  <span className="nxs-mono">{selected.tag}</span> adapter
                </h3>
                <p className="text-[12px] text-slate-400 mt-0.5">
                  Infrastructure adapter · drives the <span className="font-semibold" style={{ color: selected.sector.hex }}>{selected.sector.name}</span> use-case module · {selected.routes.length} routes
                </p>
              </div>
            </div>
            <button
              onClick={() => setSelectedTag(null)}
              className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 cursor-pointer"
              aria-label="Close adapter detail"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {selected.routes.slice(0, 12).map((route) => {
              const [method, ...rest] = route.split(' ');
              const styleKey = method.toLowerCase();
              return (
                <span
                  key={route}
                  className={`inline-flex items-center gap-2 px-2.5 py-1.5 rounded-xl border text-[11px] nxs-mono ${
                    METHOD_COLORS[styleKey] ?? 'bg-slate-50 text-slate-600 border-slate-200'
                  }`}
                >
                  <span className="font-extrabold">{method}</span>
                  <span className="text-slate-500">{rest.join(' ')}</span>
                </span>
              );
            })}
            {selected.routes.length > 12 && (
              <span className="px-2.5 py-1.5 text-[11px] nxs-mono text-slate-400">+{selected.routes.length - 12} more…</span>
            )}
          </div>
          <p className="mt-4 flex items-center gap-1.5 text-[11px] text-slate-400">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
            All adapter routes sit behind the bearer-token identity dependency; admin routes additionally require Role.ADMIN.
          </p>
        </div>
      )}

      {offline && (
        <div className="mt-4 rounded-3xl border border-amber-200 bg-amber-50 p-5 text-[13px] text-amber-800">
          OpenAPI catalog unreachable — the diagram is showing structure without live route counts. Start the NEXUS API
          server to light up the adapters.
        </div>
      )}
    </ViewShell>
  );
};
