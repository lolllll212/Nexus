import React, { useRef, useEffect, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { GraphNode, GraphLink, GraphData, NodeGroup, HubCategory, ForceSettings, SystemStates } from '../types';
import { GROUP_COLORS, HUB_CONFIG } from '../data/mockData';

interface CenterCanvasProps {
  data: GraphData;
  selectedNode: GraphNode | null;
  onSelectNode: (node: GraphNode | null) => void;
  activeFilter: NodeGroup | null;
  activeHub: HubCategory | null;
  searchTerm: string;
  forces: ForceSettings;
  isSimulating: boolean;
  showLabels: boolean;
  showPulses: boolean;
  is3DMode: boolean;
  systemStates: SystemStates;
  fitTrigger: number;
}

interface PulseParticle {
  linkIndex: number;
  progress: number;
  speed: number;
}

export const CenterCanvas: React.FC<CenterCanvasProps> = ({
  data,
  selectedNode,
  onSelectNode,
  activeFilter,
  activeHub,
  searchTerm,
  forces,
  isSimulating,
  showLabels,
  showPulses,
  is3DMode,
  systemStates,
  fitTrigger,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphLink> | null>(null);
  const transformRef = useRef<d3.ZoomTransform>(d3.zoomIdentity);
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<HTMLCanvasElement, unknown> | null>(null);

  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);

  // Cached node positions and links for simulation
  const nodesRef = useRef<GraphNode[]>([]);
  const linksRef = useRef<GraphLink[]>([]);
  const pulsesRef = useRef<PulseParticle[]>([]);

  // Track connected node ids for fast neighbor lookup
  const neighborIds = React.useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const set = new Set<string>();
    set.add(selectedNode.id);
    data.links.forEach((link) => {
      const sId = typeof link.source === 'object' ? (link.source as GraphNode).id : link.source;
      const tId = typeof link.target === 'object' ? (link.target as GraphNode).id : link.target;
      if (sId === selectedNode.id) set.add(tId);
      if (tId === selectedNode.id) set.add(sId);
    });
    return set;
  }, [selectedNode, data.links]);

  // Initialize simulation
  useEffect(() => {
    // Clone nodes and links
    const nodes: GraphNode[] = data.nodes.map((n) => ({ ...n }));
    const links: GraphLink[] = data.links.map((l) => ({ ...l }));

    nodesRef.current = nodes;
    linksRef.current = links;

    // Create random pulses along some links
    pulsesRef.current = Array.from({ length: 30 }, () => ({
      linkIndex: Math.floor(Math.random() * links.length),
      progress: Math.random(),
      speed: 0.004 + Math.random() * 0.006,
    }));

    const width = containerRef.current?.clientWidth || window.innerWidth;
    const height = containerRef.current?.clientHeight || window.innerHeight;

    // Hub cluster centers for organic grouping
    const hubCenters: Record<string, { x: number; y: number }> = {
      'AI Workshop':      { x: width * 0.42, y: height * 0.42 },
      'Skill Suites':     { x: width * 0.65, y: height * 0.35 },
      'Local Businesses': { x: width * 0.35, y: height * 0.65 },
      'Claude Code':      { x: width * 0.62, y: height * 0.68 },
    };

    const sim = d3
      .forceSimulation<GraphNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.id)
          .distance(forces.linkLength)
      )
      .force('charge', d3.forceManyBody().strength(forces.repel))
      .force('center', d3.forceCenter(width / 2, height / 2).strength(0.05))
      .force('collide', d3.forceCollide<GraphNode>().radius((d) => Math.max(8, d.val * 1.5 + 4)))
      .force('cluster', (alpha) => {
        // Subtle cluster force towards each node's assigned hub
        nodes.forEach((n) => {
          if (n.hub && hubCenters[n.hub]) {
            const center = hubCenters[n.hub];
            n.vx = (n.vx || 0) + (center.x - (n.x || width / 2)) * 0.04 * alpha;
            n.vy = (n.vy || 0) + (center.y - (n.y || height / 2)) * 0.04 * alpha;
          }
        });
      });

    simulationRef.current = sim;

    return () => {
      sim.stop();
    };
  }, [data]);

  // Update simulation parameters when forces change
  useEffect(() => {
    if (!simulationRef.current) return;
    const sim = simulationRef.current;
    const linkForce = sim.force('link') as d3.ForceLink<GraphNode, GraphLink> | undefined;
    if (linkForce) {
      linkForce.distance(forces.linkLength);
    }
    const chargeForce = sim.force('charge') as d3.ForceManyBody<GraphNode> | undefined;
    if (chargeForce) {
      chargeForce.strength(forces.repel);
    }
    sim.alpha(0.3).restart();
  }, [forces]);

  // Simulation pause/play control
  useEffect(() => {
    if (!simulationRef.current) return;
    if (isSimulating) {
      simulationRef.current.restart();
    } else {
      simulationRef.current.stop();
    }
  }, [isSimulating]);

  // Zoom & Pan setup
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const zoom = d3
      .zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.15, 6])
      .on('zoom', (event) => {
        transformRef.current = event.transform;
      });

    zoomBehaviorRef.current = zoom;
    d3.select(canvas).call(zoom);

    // Initial center transform
    const width = containerRef.current?.clientWidth || window.innerWidth;
    const height = containerRef.current?.clientHeight || window.innerHeight;
    const initialTransform = d3.zoomIdentity.translate(0, 0).scale(1);
    d3.select(canvas).call(zoom.transform, initialTransform);
  }, []);

  // Fit function smoothly centering nodes
  const fitGraph = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    const zoom = zoomBehaviorRef.current;
    const nodes = nodesRef.current;
    if (!canvas || !container || !zoom || nodes.length === 0) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    nodes.forEach((n) => {
      if (n.x === undefined || n.y === undefined) return;
      if (n.x < minX) minX = n.x;
      if (n.x > maxX) maxX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.y > maxY) maxY = n.y;
    });

    if (minX === Infinity) return;

    const width = container.clientWidth;
    const height = container.clientHeight;
    const padding = 120;
    const dx = maxX - minX || 100;
    const dy = maxY - minY || 100;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    const scale = Math.min(2.5, Math.max(0.25, 0.82 / Math.max(dx / width, dy / height)));
    const targetTransform = d3.zoomIdentity
      .translate(width / 2 - scale * cx, height / 2 - scale * cy)
      .scale(scale);

    d3.select(canvas)
      .transition()
      .duration(750)
      .call(zoom.transform, targetTransform);
  }, []);

  // Trigger fit when fitTrigger increments
  useEffect(() => {
    if (fitTrigger > 0) {
      fitGraph();
    }
  }, [fitTrigger, fitGraph]);

  // Main Canvas Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    let animId: number;
    let pulseTick = 0;

    const render = () => {
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const width = container.clientWidth;
      const height = container.clientHeight;
      const dpr = window.devicePixelRatio || 1;

      // Handle resize
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
      }

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      const transform = transformRef.current;
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);

      const nodes = nodesRef.current;
      const links = linksRef.current;
      const isFocusActive = systemStates.FOCUS || !!selectedNode;

      // Draw faint cybernetic background grid
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.025)';
      ctx.lineWidth = 1 / transform.k;
      const gridSize = 60;
      const startX = Math.floor((-transform.x / transform.k) / gridSize) * gridSize - gridSize;
      const endX = startX + (width / transform.k) + gridSize * 2;
      const startY = Math.floor((-transform.y / transform.k) / gridSize) * gridSize - gridSize;
      const endY = startY + (height / transform.k) + gridSize * 2;

      ctx.beginPath();
      for (let x = startX; x <= endX; x += gridSize) {
        ctx.moveTo(x, startY);
        ctx.lineTo(x, endY);
      }
      for (let y = startY; y <= endY; y += gridSize) {
        ctx.moveTo(startX, y);
        ctx.lineTo(endX, y);
      }
      ctx.stroke();

      // 1. Draw Links
      links.forEach((link, idx) => {
        const source = link.source as GraphNode;
        const target = link.target as GraphNode;
        if (source.x === undefined || source.y === undefined || target.x === undefined || target.y === undefined) return;

        const isConnectedToSelected =
          selectedNode && (source.id === selectedNode.id || target.id === selectedNode.id);

        let linkAlpha = 0.16;
        let strokeColor = 'rgba(0, 240, 255, ';
        let strokeWidth = 1;

        if (isFocusActive) {
          if (isConnectedToSelected) {
            linkAlpha = 0.85;
            strokeWidth = 2;
            strokeColor = 'rgba(0, 240, 255, ';
          } else {
            linkAlpha = 0.03;
          }
        } else if (isConnectedToSelected) {
          linkAlpha = 0.75;
          strokeWidth = 2;
        }

        ctx.beginPath();
        ctx.strokeStyle = `${strokeColor}${linkAlpha})`;
        ctx.lineWidth = strokeWidth / transform.k;
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);
        ctx.stroke();

        // Animated Synaptic Pulse along links
        if (showPulses && (!isFocusActive || isConnectedToSelected)) {
          const pulse = pulsesRef.current[idx % pulsesRef.current.length];
          if (pulse) {
            pulse.progress = (pulse.progress + pulse.speed) % 1;
            const px = source.x + (target.x - source.x) * pulse.progress;
            const py = source.y + (target.y - source.y) * pulse.progress;

            ctx.beginPath();
            ctx.arc(px, py, (2 / transform.k), 0, Math.PI * 2);
            ctx.fillStyle = '#00f0ff';
            ctx.shadowColor = '#00f0ff';
            ctx.shadowBlur = 8;
            ctx.fill();
            ctx.shadowBlur = 0;
          }
        }
      });

      // 2. Draw Nodes
      pulseTick += 0.03;
      nodes.forEach((node) => {
        if (node.x === undefined || node.y === undefined) return;

        // Filtering logic
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hoveredNode?.id === node.id;
        const isNeighbor = neighborIds.has(node.id);
        const matchesFilter = !activeFilter || node.group === activeFilter;
        const matchesHub = !activeHub || node.hub === activeHub;
        const matchesSearch =
          !searchTerm || node.id.toLowerCase().includes(searchTerm.toLowerCase());

        let nodeAlpha = 1.0;
        if (!matchesFilter || !matchesHub || !matchesSearch) {
          nodeAlpha = 0.1;
        } else if (isFocusActive && !isNeighbor) {
          nodeAlpha = 0.12;
        }

        ctx.globalAlpha = nodeAlpha;

        const colors = GROUP_COLORS[node.group] || GROUP_COLORS.Concepts;
        // Node radius based on value / importance
        const radius = Math.max(4, Math.min(15, (node.val || 6) * 0.9));

        // Outer glow on hover or selected or hub nodes
        const isMajorHub = node.val >= 14 || node.group === 'Router';

        if (isSelected || isHovered) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius + 7 / transform.k, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(0, 240, 255, 0.18)';
          ctx.fill();

          ctx.beginPath();
          ctx.arc(node.x, node.y, radius + 4 / transform.k, 0, Math.PI * 2);
          ctx.strokeStyle = '#00f0ff';
          ctx.lineWidth = 1.5 / transform.k;
          ctx.stroke();
        } else if (isMajorHub) {
          // Pulsing halo for major hubs
          const pulseR = radius + (2 + Math.sin(pulseTick + (node.val || 0)) * 2) / transform.k;
          ctx.beginPath();
          ctx.arc(node.x, node.y, pulseR, 0, Math.PI * 2);
          ctx.strokeStyle = colors.glow;
          ctx.lineWidth = 1 / transform.k;
          ctx.stroke();
        }

        // Draw node body with radial gradient
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);

        const grad = ctx.createRadialGradient(
          node.x - radius * 0.3,
          node.y - radius * 0.3,
          radius * 0.1,
          node.x,
          node.y,
          radius
        );
        grad.addColorStop(0, '#ffffff');
        grad.addColorStop(0.3, colors.base);
        grad.addColorStop(1, colors.base);

        ctx.fillStyle = grad;
        ctx.shadowColor = colors.base;
        ctx.shadowBlur = isSelected || isHovered ? 16 : isMajorHub ? 10 : 5;
        ctx.fill();
        ctx.shadowBlur = 0;

        // Node border
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 0.8 / transform.k;
        ctx.stroke();

        // 3. Draw Labels
        const shouldShowLabel =
          showLabels ||
          isSelected ||
          isHovered ||
          isMajorHub ||
          (isFocusActive && isNeighbor && transform.k > 0.8);

        if (shouldShowLabel && nodeAlpha > 0.3) {
          const fontSize = Math.max(9, Math.min(13, 11 / Math.sqrt(transform.k)));
          ctx.font = `${isMajorHub || isSelected ? 'bold' : 'normal'} ${fontSize}px "SF Mono", monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';

          const textY = node.y + radius + 4 / transform.k;
          const text = node.id;
          const metrics = ctx.measureText(text);
          const bgPad = 3 / transform.k;

          // Label pill background
          ctx.fillStyle = 'rgba(2, 6, 17, 0.85)';
          ctx.fillRect(
            node.x - metrics.width / 2 - bgPad,
            textY - 1 / transform.k,
            metrics.width + bgPad * 2,
            fontSize + bgPad * 1.5
          );

          // Label text
          ctx.fillStyle = isSelected ? '#00f0ff' : isHovered ? '#ffffff' : colors.text;
          ctx.fillText(text, node.x, textY);
        }

        ctx.globalAlpha = 1.0;
      });

      ctx.restore();
      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [
    selectedNode,
    hoveredNode,
    neighborIds,
    activeFilter,
    activeHub,
    searchTerm,
    showLabels,
    showPulses,
    systemStates.FOCUS,
  ]);

  // Handle Mouse Hover & Click Detection
  const getNodeAtCoords = useCallback(
    (clientX: number, clientY: number): GraphNode | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;

      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;

      const transform = transformRef.current;
      // Invert transform to get graph space coordinates
      const graphX = (x - transform.x) / transform.k;
      const graphY = (y - transform.y) / transform.k;

      // Find closest node within radius
      const nodes = nodesRef.current;
      for (let i = nodes.length - 1; i >= 0; i--) {
        const node = nodes[i];
        if (node.x === undefined || node.y === undefined) continue;
        const dx = node.x - graphX;
        const dy = node.y - graphY;
        const radius = Math.max(8, (node.val || 6) * 1.1);
        if (dx * dx + dy * dy <= radius * radius) {
          return node;
        }
      }
      return null;
    },
    []
  );

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const node = getNodeAtCoords(e.clientX, e.clientY);
    setHoveredNode(node);
    if (node) {
      setTooltipPos({ x: e.clientX, y: e.clientY });
    } else {
      setTooltipPos(null);
    }
  };

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const node = getNodeAtCoords(e.clientX, e.clientY);
    onSelectNode(node);
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full overflow-hidden bg-[#020408] ${
        is3DMode ? 'perspective-1000' : ''
      }`}
    >
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onClick={handleClick}
        className={`w-full h-full block cursor-crosshair transition-transform duration-700 ${
          is3DMode ? 'rotate-x-12 scale-95 shadow-2xl' : ''
        }`}
      />

      {/* Floating Hover Tooltip */}
      {hoveredNode && tooltipPos && (
        <div
          className="fixed z-40 pointer-events-none transform -translate-x-1/2 -translate-y-full mb-3 px-3 py-2 rounded-xl glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_8px_24px_rgba(0,0,0,0.8)] text-left select-none animate-in fade-in zoom-in-95 duration-100"
          style={{
            left: `${tooltipPos.x}px`,
            top: `${tooltipPos.y - 10}px`,
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: GROUP_COLORS[hoveredNode.group]?.base || '#00f0ff' }}
            />
            <span className="text-xs font-mono font-bold text-white tracking-wide">
              {hoveredNode.id}
            </span>
          </div>
          <div className="text-[10px] font-mono text-cyan-300 mt-0.5">
            Group: {hoveredNode.group} {hoveredNode.hub ? `· Hub: ${hoveredNode.hub}` : ''}
          </div>
          {hoveredNode.desc && (
            <p className="text-[10px] text-slate-300 font-sans mt-1 max-w-[200px] line-clamp-2 leading-tight">
              {hoveredNode.desc}
            </p>
          )}
        </div>
      )}
    </div>
  );
};
