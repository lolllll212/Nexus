import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { RefreshCw, Telescope, X, Waypoints, Link2, Shapes } from 'lucide-react';
import { PageHeader, ViewShell, LiveChip, useLiveFetch, graphGroupColor } from './shared';

/* ────────────────────────────────────────────────────────────────────────────
 * Light Knowledge Graph — a force-directed second-brain constellation.
 * Live from GET /api/graph/graph, rendered as a crisp light-mode SVG with
 * drag, zoom, cluster filters, hover tooltips, and an inspector that hands
 * any node straight to the deep-research cockpit.
 * ──────────────────────────────────────────────────────────────────────────── */

interface GraphNode {
  id: string;
  group?: string;
  val?: number;
  hub?: string;
  desc?: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
}

interface GraphPayload {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface LightKnowledgeGraphProps {
  onResearchTopic: (topic: string) => void;
}

const W = 900;
const H = 560;

export const LightKnowledgeGraph: React.FC<LightKnowledgeGraphProps> = ({ onResearchTopic }) => {
  const { data, error, loading, reload } = useLiveFetch<GraphPayload>('/api/graph?limit=150');
  const svgRef = useRef<SVGSVGElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const restyleRef = useRef<(() => void) | null>(null);

  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: GraphNode } | null>(null);
  const [relayoutTick, setRelayoutTick] = useState(0);

  const nodes = useMemo(() => data?.nodes ?? [], [data]);
  const links = useMemo(() => data?.links ?? [], [data]);

  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    nodes.forEach((n) => counts.set(n.group ?? 'Other', (counts.get(n.group ?? 'Other') ?? 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [nodes]);

  const neighborCount = useMemo(() => {
    if (!selected) return 0;
    let count = 0;
    links.forEach((l) => {
      const s = typeof l.source === 'string' ? l.source : l.source.id;
      const t = typeof l.target === 'string' ? l.target : l.target.id;
      if (s === selected.id || t === selected.id) count += 1;
    });
    return count;
  }, [selected, links]);

  /* ── Build the simulation (full d3 rendering for nodes AND links) ─────── */
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;
    const svg = d3.select(svgRef.current);

    const simNodes: GraphNode[] = nodes.map((n) => ({ ...n, x: n.x ?? W / 2 + (Math.random() - 0.5) * 220, y: n.y ?? H / 2 + (Math.random() - 0.5) * 160 }));
    const idSet = new Set(simNodes.map((n) => n.id));
    const simLinks: Array<{ source: string; target: string }> = links
      .map((l) => ({
        source: typeof l.source === 'string' ? l.source : l.source.id,
        target: typeof l.target === 'string' ? l.target : l.target.id,
      }))
      .filter((l) => idSet.has(l.source) && idSet.has(l.target));

    const radius = (d: GraphNode) => 4 + Math.sqrt(Math.max(1, d.val ?? 4)) * 2.1;

    // Links
    const linkSel = svg
      .select<SVGGElement>('.nxs-links')
      .selectAll<SVGLineElement, { source: string; target: string }>('line')
      .data(simLinks);
    linkSel.exit().remove();
    const linkMerge = linkSel.enter().append('line').merge(linkSel);

    // Nodes
    const nodeSel = svg
      .select<SVGGElement>('.nxs-nodes')
      .selectAll<SVGGElement, GraphNode>('g.nxs-node')
      .data(simNodes, (d) => d.id);
    nodeSel.exit().remove();
    const nodeEnter = nodeSel.enter().append('g').attr('class', 'nxs-node').style('cursor', 'pointer');
    nodeEnter.append('circle').attr('class', 'nxs-ring').attr('r', (d) => radius(d) + 4).attr('fill', 'none').attr('stroke-width', 1.5);
    nodeEnter
      .append('circle')
      .attr('class', 'nxs-core')
      .attr('r', (d) => radius(d))
      .attr('stroke', '#FFFFFF')
      .attr('stroke-width', 1.6);
    nodeEnter.append('text').attr('class', 'nxs-label').attr('dy', (d) => radius(d) + 12).attr('text-anchor', 'middle');
    const nodeMerge = nodeEnter.merge(nodeSel);

    // Simulation
    const sim = d3
      .forceSimulation<GraphNode>(simNodes)
      .force(
        'link',
        d3
          .forceLink<GraphNode, { source: string; target: string }>(simLinks)
          .id((d) => d.id)
          .distance(52)
          .strength(0.35)
      )
      .force('charge', d3.forceManyBody<GraphNode>().strength(-190))
      .force('collide', d3.forceCollide<GraphNode>().radius((d) => radius(d) + 5).iterations(2))
      .force('center', d3.forceCenter(W / 2, H / 2).strength(0.06))
      .alphaDecay(0.022);

    // Zoom + pan
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.35, 3.2])
      .on('zoom', (event) => svg.select('.nxs-transform').attr('transform', event.transform));
    svg.call(zoom as any);

    // Drag
    nodeMerge.call(
      d3
        .drag<SVGGElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.25).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
    );

    // Interactions
    nodeMerge
      .on('pointermove', (event, d) => {
        const rect = wrapRef.current?.getBoundingClientRect();
        if (!rect) return;
        setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top, node: d });
      })
      .on('pointerleave', () => setTooltip(null))
      .on('click', (_event, d) => {
        setSelected((prev) => (prev?.id === d.id ? null : { ...d }));
      });

    // Position updates
    sim.on('tick', () => {
      linkMerge
        .attr('x1', (l) => (l.source as unknown as GraphNode).x ?? 0)
        .attr('y1', (l) => (l.source as unknown as GraphNode).y ?? 0)
        .attr('x2', (l) => (l.target as unknown as GraphNode).x ?? 0)
        .attr('y2', (l) => (l.target as unknown as GraphNode).y ?? 0);
      nodeMerge.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    // Declarative styling — rebuilt whenever selection / filter change
    const restyle = () => {
      const selId = selected?.id ?? null;
      const neighborIds = new Set<string>();
      if (selId) {
        simLinks.forEach((l) => {
          if (l.source === selId) neighborIds.add(l.target);
          if (l.target === selId) neighborIds.add(l.source);
        });
      }
      const dim = (d: GraphNode) => activeGroup !== null && (d.group ?? 'Other') !== activeGroup;

      linkMerge
        .attr('stroke', (l) => {
          const s = (l.source as unknown as GraphNode).id;
          const t = (l.target as unknown as GraphNode).id;
          if (selId && (s === selId || t === selId)) return '#22D3EE';
          return dim({ group: nodes.find((n) => n.id === s)?.group } as GraphNode) ? '#EEF2F7' : '#D6DEE8';
        })
        .attr('stroke-width', (l) => {
          const s = (l.source as unknown as GraphNode).id;
          const t = (l.target as unknown as GraphNode).id;
          return selId && (s === selId || t === selId) ? 2.2 : 1;
        })
        .classed('nxs-link-active', (l) => {
          const s = (l.source as unknown as GraphNode).id;
          const t = (l.target as unknown as GraphNode).id;
          return !!selId && (s === selId || t === selId);
        })
        .attr('opacity', (l) => {
          if (!selId) return 1;
          const s = (l.source as unknown as GraphNode).id;
          const t = (l.target as unknown as GraphNode).id;
          return s === selId || t === selId ? 1 : 0.18;
        });

      nodeMerge
        .attr('opacity', (d) => {
          if (dim(d)) return 0.18;
          if (selId && d.id !== selId && !neighborIds.has(d.id)) return 0.3;
          return 1;
        })
        .select('.nxs-core')
        .attr('fill', (d) => graphGroupColor(d.group));

      nodeMerge
        .select('.nxs-ring')
        .attr('stroke', (d) => graphGroupColor(d.group))
        .attr('opacity', (d) => ((d.val ?? 0) >= 12 && !dim(d) ? 0.7 : 0))
        .classed('nxs-node-ring', (d) => (d.val ?? 0) >= 12 && !dim(d));

      nodeMerge
        .select('.nxs-label')
        .attr('fill', (d) => (d.id === selId ? '#0F172A' : '#64748B'))
        .attr('font-size', (d) => ((d.val ?? 0) >= 12 || d.id === selId ? 10.5 : 9))
        .attr('font-weight', (d) => (d.id === selId ? 700 : 500))
        .text((d) => ((d.val ?? 0) >= 12 || d.id === selId ? d.id.slice(0, 22) : ''));
    };
    restyleRef.current = restyle;
    restyle();

    return () => {
      sim.stop();
      restyleRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, links, relayoutTick]);

  // Restyle on selection / filter changes without rebuilding the simulation
  useEffect(() => {
    restyleRef.current?.();
  }, [selected, activeGroup]);

  return (
    <ViewShell>
      <PageHeader
        route="GRAPH"
        right={
          <>
            <LiveChip loading={loading} offline={!!error} />
            <button
              onClick={reload}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white border border-slate-200 text-[12px] font-semibold text-slate-600 hover:border-cyan-300 hover:text-cyan-700 transition-all cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
            <button
              onClick={() => setRelayoutTick((t) => t + 1)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white border border-slate-200 text-[12px] font-semibold text-slate-600 hover:border-cyan-300 hover:text-cyan-700 transition-all cursor-pointer"
            >
              <Waypoints className="w-3.5 h-3.5" /> Relayout
            </button>
          </>
        }
      />

      {/* Cluster filters */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setActiveGroup(null)}
          className={`px-3 py-1.5 rounded-full border text-[12px] font-semibold transition-all cursor-pointer ${
            activeGroup === null
              ? 'bg-slate-900 border-slate-900 text-white'
              : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300'
          }`}
        >
          All · {nodes.length}
        </button>
        {groups.map(([group, count]) => (
          <button
            key={group}
            onClick={() => setActiveGroup((prev) => (prev === group ? null : group))}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[12px] font-semibold transition-all cursor-pointer ${
              activeGroup === group
                ? 'bg-slate-900 border-slate-900 text-white'
                : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300'
            }`}
          >
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: graphGroupColor(group) }} />
            {group} · {count}
          </button>
        ))}
      </div>

      {/* Canvas + inspector */}
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-4">
        <div
          ref={wrapRef}
          className="relative rounded-3xl bg-white border border-slate-200/80 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] overflow-hidden"
        >
          {loading ? (
            <div className="h-[560px] flex items-center justify-center">
              <div className="flex flex-col items-center gap-3 text-slate-400">
                <Shapes className="w-8 h-8 animate-pulse" />
                <p className="text-[13px] font-medium">Weaving the constellation…</p>
              </div>
            </div>
          ) : error ? (
            <div className="h-[560px] flex items-center justify-center px-8">
              <div className="text-center max-w-sm">
                <p className="text-[15px] font-bold text-slate-800">Graph API unreachable</p>
                <p className="mt-2 text-[13px] text-slate-500">{error}</p>
                <button
                  onClick={reload}
                  className="mt-4 px-4 py-2 rounded-full bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 cursor-pointer"
                >
                  Retry
                </button>
              </div>
            </div>
          ) : (
            <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-[560px] block touch-none" role="img" aria-label="Knowledge graph constellation">
              <defs>
                <pattern id="nxs-grid" width="36" height="36" patternUnits="userSpaceOnUse">
                  <circle cx="1" cy="1" r="1" fill="#E8EDF3" />
                </pattern>
              </defs>
              <rect width={W} height={H} fill="url(#nxs-grid)" />
              <g className="nxs-transform">
                <g className="nxs-links" stroke="#D6DEE8" strokeWidth={1} />
                <g className="nxs-nodes" />
              </g>
            </svg>
          )}

          {/* Hover tooltip */}
          {tooltip && !loading && !error && (
            <div
              className="pointer-events-none absolute z-20 max-w-[250px] rounded-2xl bg-slate-900/95 backdrop-blur text-white px-3.5 py-2.5 shadow-xl"
              style={{
                left: Math.min(tooltip.x + 14, (wrapRef.current?.clientWidth ?? 400) - 260),
                top: Math.min(tooltip.y + 14, (wrapRef.current?.clientHeight ?? 400) - 110),
              }}
            >
              <p className="text-[12.5px] font-bold leading-snug">{tooltip.node.id}</p>
              <p className="mt-1 text-[10.5px] nxs-mono text-cyan-300">
                {tooltip.node.group ?? 'Other'} · {tooltip.node.hub ?? '—'}
              </p>
              {tooltip.node.desc && (
                <p className="mt-1.5 text-[11px] leading-relaxed text-slate-300 line-clamp-3">{tooltip.node.desc}</p>
              )}
            </div>
          )}

          <div className="absolute bottom-3 left-3 flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/85 backdrop-blur border border-slate-200 text-[10px] font-semibold text-slate-500">
            <Link2 className="w-3 h-3" />
            {nodes.length} nodes · {links.length} synapses · scroll to zoom · drag to reweave
          </div>
        </div>

        {/* Inspector */}
        <aside className="rounded-3xl bg-white border border-slate-200/80 p-5 shadow-[0_1px_2px_rgba(16,24,40,0.04),0_8px_28px_-16px_rgba(16,24,40,0.12)] h-fit">
          {selected ? (
            <div>
              <div className="flex items-start justify-between gap-2">
                <span
                  className="w-10 h-10 rounded-2xl flex items-center justify-center text-white text-[13px] font-bold shrink-0"
                  style={{ backgroundColor: graphGroupColor(selected.group) }}
                >
                  {selected.id.slice(0, 1).toUpperCase()}
                </span>
                <button
                  onClick={() => setSelected(null)}
                  className="w-7 h-7 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 cursor-pointer"
                  aria-label="Close inspector"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <h3 className="mt-3.5 text-[15px] font-bold text-slate-900 leading-snug">{selected.id}</h3>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="px-2 py-0.5 rounded-md bg-cyan-50 border border-cyan-100 text-[10px] font-bold text-cyan-700 uppercase tracking-wider">
                  {selected.group ?? 'Other'}
                </span>
                {selected.hub && (
                  <span className="px-2 py-0.5 rounded-md bg-slate-50 border border-slate-200 text-[10px] font-bold text-slate-600 uppercase tracking-wider">
                    {selected.hub}
                  </span>
                )}
              </div>
              {selected.desc && <p className="mt-3 text-[12.5px] leading-relaxed text-slate-500">{selected.desc}</p>}
              <dl className="mt-4 space-y-2 text-[12px]">
                <div className="flex justify-between border-t border-slate-100 pt-2">
                  <dt className="text-slate-400">Synaptic weight</dt>
                  <dd className="font-bold text-slate-700 nxs-mono">{selected.val ?? '—'}</dd>
                </div>
                <div className="flex justify-between border-t border-slate-100 pt-2">
                  <dt className="text-slate-400">Direct synapses</dt>
                  <dd className="font-bold text-slate-700 nxs-mono">{neighborCount}</dd>
                </div>
              </dl>
              <button
                onClick={() => onResearchTopic(selected.id)}
                className="mt-4 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-full bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 transition-all cursor-pointer"
              >
                <Telescope className="w-4 h-4 text-cyan-300" />
                Deep research this node
              </button>
            </div>
          ) : (
            <div className="py-6 text-center">
              <Waypoints className="w-8 h-8 text-slate-200 mx-auto" />
              <p className="mt-3 text-[13px] font-semibold text-slate-600">No node selected</p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-slate-400">
                Click any node to inspect its synapses and dispatch deep research. Drag nodes to reweave the constellation.
              </p>
            </div>
          )}
        </aside>
      </div>
    </ViewShell>
  );
};
