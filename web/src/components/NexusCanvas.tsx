import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { 
  NexusNode, 
  NexusLink, 
  NodeCategory, 
  LayoutAlgorithm 
} from '../types';
import { CATEGORY_STYLES } from '../data/nexusGraphData';
import { 
  Maximize2, 
  Minimize2, 
  RotateCcw, 
  ZoomIn, 
  ZoomOut, 
  Crosshair, 
  Activity, 
  Layers, 
  Share2, 
  Search, 
  Cpu, 
  Sparkles,
  Compass,
  Play,
  Pause,
  ExternalLink,
  PlusCircle,
  FileText,
  Terminal,
  Zap,
  Bookmark
} from 'lucide-react';

interface NexusCanvasProps {
  nodes: NexusNode[];
  links: NexusLink[];
  selectedNode: NexusNode | null;
  onSelectNode: (node: NexusNode | null) => void;
  activeFilter: NodeCategory | null;
  onFilterChange: (category: NodeCategory | null) => void;
  searchQuery: string;
  onNodeNeighborhoodExpand: (node: NexusNode) => void;
  onOpenClaudeStudio: () => void;
  onOpenResearchMode: (topic?: string) => void;
  onOpenWorkflowMode: (workflowId?: string) => void;
}

interface Particle {
  sourceId: string;
  targetId: string;
  progress: number;
  speed: number;
  color: string;
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  node: NexusNode | null;
}

export const NexusCanvas: React.FC<NexusCanvasProps> = ({
  nodes,
  links,
  selectedNode,
  onSelectNode,
  activeFilter,
  onFilterChange,
  searchQuery,
  onNodeNeighborhoodExpand,
  onOpenClaudeStudio,
  onOpenResearchMode,
  onOpenWorkflowMode,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Layout & Simulation State
  const [layout, setLayout] = useState<LayoutAlgorithm>('FORCE');
  const [isSimulating, setIsSimulating] = useState(true);
  const [is3DView, setIs3DView] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [showPulses, setShowPulses] = useState(true);

  // Transform Camera (Pan & Zoom)
  const transformRef = useRef({ x: 0, y: 0, k: 0.85 });
  const [zoomLevel, setZoomLevel] = useState(0.85);

  // Interaction State
  const draggingNodeRef = useRef<NexusNode | null>(null);
  const isPanningRef = useRef(false);
  const panStartRef = useRef({ x: 0, y: 0 });
  const hoveredNodeRef = useRef<NexusNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<NexusNode | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);

  // Context Menu State
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    node: null,
  });

  // Local mutable node list with coordinates
  const simulationNodesRef = useRef<NexusNode[]>([]);
  const particlesRef = useRef<Particle[]>([]);

  // Synchronize incoming nodes into local simulation array with preserved coordinates
  useEffect(() => {
    const existingMap = new Map(simulationNodesRef.current.map((n) => [n.id, n]));
    const width = containerRef.current?.clientWidth || 1000;
    const height = containerRef.current?.clientHeight || 800;
    const cx = width / 2;
    const cy = height / 2;

    simulationNodesRef.current = nodes.map((n, idx) => {
      const existing = existingMap.get(n.id);
      if (existing) {
        return {
          ...n,
          x: existing.x,
          y: existing.y,
          vx: existing.vx,
          vy: existing.vy,
        };
      }
      // Initialize in cluster or ring position
      const angle = (idx / nodes.length) * 2 * Math.PI;
      const radius = 180 + (idx % 4) * 70;
      return {
        ...n,
        x: cx + Math.cos(angle) * radius + (Math.random() - 0.5) * 60,
        y: cy + Math.sin(angle) * radius + (Math.random() - 0.5) * 60,
        vx: 0,
        vy: 0,
      };
    });

    // Initialize edge particles for animated data flow
    particlesRef.current = links.slice(0, 36).map((l, i) => {
      const sId = typeof l.source === 'object' ? l.source.id : l.source;
      const tId = typeof l.target === 'object' ? l.target.id : l.target;
      return {
        sourceId: sId,
        targetId: tId,
        progress: (i * 0.12) % 1,
        speed: 0.004 + (i % 3) * 0.002,
        color: '#00f0ff',
      };
    });
  }, [nodes, links]);

  // Neighbor map for quick connection checking
  const neighborMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    links.forEach((l) => {
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      if (!map.has(s)) map.set(s, new Set());
      if (!map.has(t)) map.set(t, new Set());
      map.get(s)!.add(t);
      map.get(t)!.add(s);
    });
    return map;
  }, [links]);

  // Recenter & Fit Camera
  const handleFit = useCallback(() => {
    const container = containerRef.current;
    if (!container || simulationNodesRef.current.length === 0) return;
    const w = container.clientWidth;
    const h = container.clientHeight;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    simulationNodesRef.current.forEach((n) => {
      if (n.x !== undefined) {
        minX = Math.min(minX, n.x);
        maxX = Math.max(maxX, n.x);
      }
      if (n.y !== undefined) {
        minY = Math.min(minY, n.y);
        maxY = Math.max(maxY, n.y);
      }
    });

    if (minX === Infinity) return;
    const graphWidth = maxX - minX || 600;
    const graphHeight = maxY - minY || 600;
    const k = Math.min(w / (graphWidth + 240), h / (graphHeight + 240), 1.2);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;

    transformRef.current = {
      x: w / 2 - midX * k,
      y: h / 2 - midY * k,
      k: Math.max(0.4, k),
    };
    setZoomLevel(transformRef.current.k);
  }, []);

  // Zoom Helpers
  const handleZoom = useCallback((factor: number) => {
    const container = containerRef.current;
    if (!container) return;
    const cx = container.clientWidth / 2;
    const cy = container.clientHeight / 2;
    const t = transformRef.current;
    const newK = Math.max(0.2, Math.min(3.5, t.k * factor));
    t.x = cx - (cx - t.x) * (newK / t.k);
    t.y = cy - (cy - t.y) * (newK / t.k);
    t.k = newK;
    setZoomLevel(newK);
  }, []);

  // Center on selected node smoothly
  useEffect(() => {
    if (!selectedNode || !containerRef.current) return;
    const found = simulationNodesRef.current.find((n) => n.id === selectedNode.id);
    if (found && found.x !== undefined && found.y !== undefined) {
      const cx = containerRef.current.clientWidth / 2;
      const cy = containerRef.current.clientHeight / 2;
      const targetK = Math.max(transformRef.current.k, 1.1);
      transformRef.current = {
        x: cx - found.x * targetK,
        y: cy - found.y * targetK,
        k: targetK,
      };
      setZoomLevel(targetK);
    }
  }, [selectedNode]);

  // Main Render & Physics Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let pulseAngle = 0;

    // Handle high DPI retina screens
    const resizeCanvas = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = container.clientWidth * dpr;
      canvas.height = container.clientHeight * dpr;
      canvas.style.width = `${container.clientWidth}px`;
      canvas.style.height = `${container.clientHeight}px`;
      ctx.scale(dpr, dpr);
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Physics step
    const stepPhysics = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      const cx = width / 2;
      const cy = height / 2;
      const localNodes = simulationNodesRef.current;
      const nodeCount = localNodes.length;
      if (nodeCount === 0) return;

      const nodeMap = new Map(localNodes.map((n) => [n.id, n]));

      if (layout === 'FORCE') {
        // Multi-body repulsive force
        for (let i = 0; i < nodeCount; i++) {
          const n1 = localNodes[i];
          for (let j = i + 1; j < nodeCount; j++) {
            const n2 = localNodes[j];
            const dx = (n2.x || 0) - (n1.x || 0);
            const dy = (n2.y || 0) - (n1.y || 0);
            const distSq = dx * dx + dy * dy || 1;
            const dist = Math.sqrt(distSq);
            if (dist < 450) {
              const force = (n1.val * n2.val * 55) / distSq;
              const fx = (dx / dist) * force;
              const fy = (dy / dist) * force;
              if (n1 !== draggingNodeRef.current) {
                n1.vx = (n1.vx || 0) - fx;
                n1.vy = (n1.vy || 0) - fy;
              }
              if (n2 !== draggingNodeRef.current) {
                n2.vx = (n2.vx || 0) + fx;
                n2.vy = (n2.vy || 0) + fy;
              }
            }
          }

          // Center gravitational pull
          const dCenterDist = Math.sqrt(((n1.x || 0) - cx) ** 2 + ((n1.y || 0) - cy) ** 2);
          const pull = 0.0006 * n1.val;
          n1.vx = (n1.vx || 0) - ((n1.x || 0) - cx) * pull;
          n1.vy = (n1.vy || 0) - ((n1.y || 0) - cy) * pull;
        }

        // Link spring attraction forces
        links.forEach((l) => {
          const sId = typeof l.source === 'object' ? l.source.id : l.source;
          const tId = typeof l.target === 'object' ? l.target.id : l.target;
          const s = nodeMap.get(sId);
          const t = nodeMap.get(tId);
          if (s && t) {
            const dx = (t.x || 0) - (s.x || 0);
            const dy = (t.y || 0) - (s.y || 0);
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const targetDist = 110;
            const displacement = dist - targetDist;
            const force = displacement * 0.008;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            if (s !== draggingNodeRef.current) {
              s.vx = (s.vx || 0) + fx;
              s.vy = (s.vy || 0) + fy;
            }
            if (t !== draggingNodeRef.current) {
              t.vx = (t.vx || 0) - fx;
              t.vy = (t.vy || 0) - fy;
            }
          }
        });
      } else if (layout === 'RING') {
        // Concentric orbital rings around major hubs
        localNodes.forEach((n, idx) => {
          const ringIndex = n.val > 30 ? 0 : n.val > 20 ? 1 : 2;
          const radius = 100 + ringIndex * 160;
          const angle = (idx / nodeCount) * 2 * Math.PI + pulseAngle * 0.05;
          const targetX = cx + Math.cos(angle) * radius;
          const targetY = cy + Math.sin(angle) * radius;
          n.vx = (n.vx || 0) + (targetX - (n.x || cx)) * 0.04;
          n.vy = (n.vy || 0) + (targetY - (n.y || cy)) * 0.04;
        });
      } else if (layout === 'CLUSTER') {
        // Cluster by Category
        const categories = Object.keys(CATEGORY_STYLES) as NodeCategory[];
        localNodes.forEach((n) => {
          const catIdx = categories.indexOf(n.category);
          const catAngle = (catIdx / categories.length) * 2 * Math.PI;
          const clusterCenterX = cx + Math.cos(catAngle) * 240;
          const clusterCenterY = cy + Math.sin(catAngle) * 240;
          n.vx = (n.vx || 0) + (clusterCenterX - (n.x || cx)) * 0.02;
          n.vy = (n.vy || 0) + (clusterCenterY - (n.y || cy)) * 0.02;
        });
      }

      // Position update with friction damping
      const damping = 0.88;
      localNodes.forEach((n) => {
        if (n !== draggingNodeRef.current) {
          n.vx = (n.vx || 0) * damping;
          n.vy = (n.vy || 0) * damping;
          n.x = (n.x || cx) + (n.vx || 0);
          n.y = (n.y || cy) + (n.vy || 0);
        }
      });
    };

    // Draw frame
    const render = () => {
      pulseAngle += 0.025;
      const width = container.clientWidth;
      const height = container.clientHeight;

      if (isSimulating) {
        stepPhysics();
      }

      ctx.clearRect(0, 0, width, height);

      // Deep graphite technical canvas background
      ctx.fillStyle = '#05070c';
      ctx.fillRect(0, 0, width, height);

      // Camera Transform matrix
      const { x: panX, y: panY, k } = transformRef.current;
      ctx.save();
      ctx.translate(panX, panY);
      ctx.scale(k, k);

      // ── Subtle Technical Dot Grid ──────────────────────────────────────────
      const gridSize = 40;
      const startX = Math.floor((-panX / k) / gridSize) * gridSize - gridSize;
      const endX = startX + (width / k) + gridSize * 2;
      const startY = Math.floor((-panY / k) / gridSize) * gridSize - gridSize;
      const endY = startY + (height / k) + gridSize * 2;

      ctx.fillStyle = 'rgba(0, 240, 255, 0.035)';
      for (let gx = startX; gx < endX; gx += gridSize) {
        for (let gy = startY; gy < endY; gy += gridSize) {
          ctx.fillRect(gx, gy, 1.2, 1.2);
        }
      }

      const localNodes = simulationNodesRef.current;
      const nodeMap = new Map(localNodes.map((n) => [n.id, n]));
      const hovered = hoveredNodeRef.current;

      // ── Render Connections (Edges) ─────────────────────────────────────────
      links.forEach((l) => {
        const sId = typeof l.source === 'object' ? l.source.id : l.source;
        const tId = typeof l.target === 'object' ? l.target.id : l.target;
        const s = nodeMap.get(sId);
        const t = nodeMap.get(tId);
        if (!s || !t || s.x === undefined || t.x === undefined) return;

        const isDirectConnection = 
          selectedNode && (s.id === selectedNode.id || t.id === selectedNode.id);
        const isHoveredConnection = 
          hovered && (s.id === hovered.id || t.id === hovered.id);

        let strokeColor = 'rgba(56, 189, 248, 0.12)';
        let lineWidth = 0.8;

        if (isDirectConnection) {
          strokeColor = 'rgba(0, 240, 255, 0.75)';
          lineWidth = 2.2;
        } else if (isHoveredConnection) {
          strokeColor = 'rgba(168, 85, 247, 0.65)';
          lineWidth = 1.6;
        } else if (selectedNode) {
          strokeColor = 'rgba(100, 116, 139, 0.04)';
        }

        ctx.beginPath();
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = lineWidth;
        ctx.moveTo(s.x, s.y || 0);
        ctx.lineTo(t.x, t.y || 0);
        ctx.stroke();

        // Relation label on highlighted link
        if ((isDirectConnection || isHoveredConnection) && l.relation) {
          const midX = (s.x + t.x) / 2;
          const midY = (s.y + t.y) / 2;
          ctx.font = '8px "JetBrains Mono", monospace';
          ctx.fillStyle = isDirectConnection ? '#00f0ff' : '#c084fc';
          ctx.textAlign = 'center';
          ctx.fillText(l.relation, midX, midY - 4);
        }
      });

      // ── Render Animated Data Stream Particles ──────────────────────────────
      if (showPulses) {
        particlesRef.current.forEach((p) => {
          const s = nodeMap.get(p.sourceId);
          const t = nodeMap.get(p.targetId);
          if (s && t && s.x !== undefined && t.x !== undefined) {
            p.progress += p.speed;
            if (p.progress >= 1) p.progress = 0;

            const px = s.x + (t.x - s.x) * p.progress;
            const py = (s.y || 0) + ((t.y || 0) - (s.y || 0)) * p.progress;

            ctx.beginPath();
            ctx.arc(px, py, 1.8, 0, Math.PI * 2);
            ctx.fillStyle = p.color;
            ctx.shadowColor = p.color;
            ctx.shadowBlur = 8;
            ctx.fill();
            ctx.shadowBlur = 0;
          }
        });
      }

      // ── Render Knowledge Nodes ─────────────────────────────────────────────
      localNodes.forEach((n) => {
        if (n.x === undefined || n.y === undefined) return;
        const style = CATEGORY_STYLES[n.category] || CATEGORY_STYLES.CONCEPT;
        const isSelected = selectedNode?.id === n.id;
        const isHovered = hovered?.id === n.id;
        const isNeighbor = selectedNode && neighborMap.get(selectedNode.id)?.has(n.id);
        const matchesFilter = !activeFilter || n.category === activeFilter;
        const matchesSearch = !searchQuery || n.name.toLowerCase().includes(searchQuery.toLowerCase()) || n.tags.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()));

        // Opacity dimming for non-matching or non-neighbor nodes
        let alpha = 1.0;
        if (activeFilter && !matchesFilter) alpha = 0.12;
        if (searchQuery && !matchesSearch) alpha = 0.12;
        if (selectedNode && !isSelected && !isNeighbor) alpha = Math.min(alpha, 0.2);

        ctx.globalAlpha = alpha;

        const baseRadius = Math.max(7, Math.sqrt(n.val) * 3.4);
        const radius = isSelected ? baseRadius * 1.3 : isHovered ? baseRadius * 1.15 : baseRadius;

        // Animated aura pulsation for active nodes
        if (n.pulsing || isSelected) {
          const pulseR = radius + 4 + Math.sin(pulseAngle * 3) * 3;
          ctx.beginPath();
          ctx.arc(n.x, n.y, pulseR, 0, Math.PI * 2);
          ctx.strokeStyle = style.color;
          ctx.lineWidth = 1;
          ctx.globalAlpha = alpha * 0.45;
          ctx.stroke();
          ctx.globalAlpha = alpha;
        }

        // Outer glow on hover/selected
        if (isSelected || isHovered) {
          ctx.shadowColor = style.color;
          ctx.shadowBlur = 20;
        }

        // Node circle body
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? '#ffffff' : style.color;
        ctx.fill();

        // Thin dark holographic border
        ctx.lineWidth = isSelected ? 2.5 : 1.2;
        ctx.strokeStyle = isSelected ? '#00f0ff' : 'rgba(2, 4, 8, 0.8)';
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Inner Core dot
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = '#05070c';
        ctx.fill();

        // Monospaced Technical Labels
        if (showLabels || isSelected || isHovered || n.val > 25) {
          ctx.font = `${isSelected ? 'bold 11px' : '9px'} "JetBrains Mono", monospace`;
          ctx.fillStyle = isSelected ? '#ffffff' : isNeighbor ? '#e2e8f0' : 'rgba(226, 232, 240, 0.75)';
          ctx.textAlign = 'center';
          ctx.fillText(n.name.length > 24 ? n.name.slice(0, 22) + '…' : n.name, n.x, n.y + radius + 13);

          // Sub-label category tag
          if (isSelected || n.val > 28) {
            ctx.font = '7px "JetBrains Mono", monospace';
            ctx.fillStyle = style.color;
            ctx.fillText(n.category, n.x, n.y + radius + 22);
          }
        }

        ctx.globalAlpha = 1.0;
      });

      ctx.restore();
      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [layout, isSimulating, showLabels, showPulses, links, selectedNode, neighborMap, activeFilter, searchQuery]);

  // Coordinate Conversion (Screen ↔ World Canvas Space)
  const screenToWorld = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const { x: panX, y: panY, k } = transformRef.current;
    return {
      x: (clientX - rect.left - panX) / k,
      y: (clientY - rect.top - panY) / k,
    };
  }, []);

  // Hit Test to find clicked or hovered node
  const getNodeAtPosition = useCallback((worldX: number, worldY: number) => {
    const localNodes = simulationNodesRef.current;
    for (let i = localNodes.length - 1; i >= 0; i--) {
      const n = localNodes[i];
      if (n.x === undefined || n.y === undefined) continue;
      const baseRadius = Math.max(7, Math.sqrt(n.val) * 3.4);
      const hitRadius = baseRadius + 8;
      const dx = worldX - n.x;
      const dy = worldY - n.y;
      if (dx * dx + dy * dy <= hitRadius * hitRadius) {
        return n;
      }
    }
    return null;
  }, []);

  // Mouse Handlers
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (contextMenu.visible) {
      setContextMenu((prev) => ({ ...prev, visible: false }));
    }

    if (e.button === 2) {
      // Right click context menu
      e.preventDefault();
      const world = screenToWorld(e.clientX, e.clientY);
      const target = getNodeAtPosition(world.x, world.y);
      if (target) {
        onSelectNode(target);
        setContextMenu({
          visible: true,
          x: e.clientX,
          y: e.clientY,
          node: target,
        });
      }
      return;
    }

    if (e.button === 0) {
      const world = screenToWorld(e.clientX, e.clientY);
      const target = getNodeAtPosition(world.x, world.y);

      if (target) {
        draggingNodeRef.current = target;
        onSelectNode(target);
      } else {
        isPanningRef.current = true;
        panStartRef.current = {
          x: e.clientX - transformRef.current.x,
          y: e.clientY - transformRef.current.y,
        };
      }
    }
  }, [screenToWorld, getNodeAtPosition, onSelectNode, contextMenu.visible]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (draggingNodeRef.current) {
      const world = screenToWorld(e.clientX, e.clientY);
      draggingNodeRef.current.x = world.x;
      draggingNodeRef.current.y = world.y;
      draggingNodeRef.current.vx = 0;
      draggingNodeRef.current.vy = 0;
      return;
    }

    if (isPanningRef.current) {
      transformRef.current.x = e.clientX - panStartRef.current.x;
      transformRef.current.y = e.clientY - panStartRef.current.y;
      return;
    }

    // Hover tooltip tracking
    const world = screenToWorld(e.clientX, e.clientY);
    const target = getNodeAtPosition(world.x, world.y);
    hoveredNodeRef.current = target;
    setHoveredNode(target);

    if (target) {
      const canvas = canvasRef.current;
      if (canvas) {
        const rect = canvas.getBoundingClientRect();
        setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      }
    } else {
      setTooltipPos(null);
    }
  }, [screenToWorld, getNodeAtPosition]);

  const handleMouseUp = useCallback(() => {
    draggingNodeRef.current = null;
    isPanningRef.current = false;
  }, []);

  // Double click neighborhood expansion
  const handleDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const world = screenToWorld(e.clientX, e.clientY);
    const target = getNodeAtPosition(world.x, world.y);
    if (target) {
      onNodeNeighborhoodExpand(target);
    }
  }, [screenToWorld, getNodeAtPosition, onNodeNeighborhoodExpand]);

  // Wheel Zoom
  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    handleZoom(zoomFactor);
  }, [handleZoom]);

  const categories = Object.keys(CATEGORY_STYLES) as NodeCategory[];

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden bg-[#05070c] select-none">
      {/* Interactive Main Canvas */}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onDoubleClick={handleDoubleClick}
        onWheel={handleWheel}
        onContextMenu={(e) => e.preventDefault()}
        className="w-full h-full cursor-grab active:cursor-grabbing block"
      />

      {/* Floating Tactical Layer Filters (Top-Left under top bar) */}
      <div className="absolute top-18 left-6 z-20 flex items-center gap-1.5 p-1 rounded-xl glass-panel border border-cyan-500/20 bg-slate-950/80 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-x-auto max-w-[85vw]">
        <button
          onClick={() => onFilterChange(null)}
          className={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-medium transition-all ${
            activeFilter === null
              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-[0_0_10px_rgba(0,240,255,0.25)]'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
          }`}
        >
          ALL ({nodes.length})
        </button>

        {categories.map((cat) => {
          const style = CATEGORY_STYLES[cat];
          const count = nodes.filter((n) => n.category === cat).length;
          if (count === 0) return null;
          const isCurrent = activeFilter === cat;

          return (
            <button
              key={cat}
              onClick={() => onFilterChange(isCurrent ? null : cat)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono transition-all ${
                isCurrent
                  ? 'bg-slate-900 text-white border shadow-md'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
              }`}
              style={{
                borderColor: isCurrent ? style.color : 'transparent',
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: style.color }}></span>
              <span>{cat}</span>
              <span className="text-[9px] opacity-60">({count})</span>
            </button>
          );
        })}
      </div>

      {/* Floating Tactical Graph Controls (Bottom-Right) */}
      <div className="absolute bottom-24 right-6 z-20 flex flex-col items-center gap-2 p-1.5 rounded-2xl glass-panel border border-cyan-500/20 bg-slate-950/85 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.7)]">
        {/* Fit to Viewport */}
        <button
          onClick={handleFit}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors"
          title="Fit whole graph to screen"
        >
          <Crosshair className="w-4 h-4 text-cyan-400" />
        </button>

        {/* Zoom In / Out */}
        <button
          onClick={() => handleZoom(1.18)}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors"
          title="Zoom in (+)"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => handleZoom(0.85)}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors"
          title="Zoom out (-)"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <div className="w-4 h-[1px] bg-slate-800 my-0.5"></div>

        {/* Layout Modes */}
        <button
          onClick={() => {
            const modes: LayoutAlgorithm[] = ['FORCE', 'RING', 'CLUSTER'];
            const nextIdx = (modes.indexOf(layout) + 1) % modes.length;
            setLayout(modes[nextIdx]);
          }}
          className="p-2 rounded-xl text-cyan-300 hover:bg-cyan-950/60 transition-colors font-mono text-[9px] font-bold flex flex-col items-center"
          title={`Layout: ${layout} (Click to toggle)`}
        >
          <Compass className="w-4 h-4 text-amber-400 mb-0.5" />
          <span>{layout}</span>
        </button>

        {/* Physics Pause / Play */}
        <button
          onClick={() => setIsSimulating(!isSimulating)}
          className={`p-2 rounded-xl transition-colors ${
            !isSimulating ? 'text-amber-400 bg-amber-950/40' : 'text-slate-400 hover:text-cyan-300'
          }`}
          title={isSimulating ? "Freeze physics" : "Resume physics simulation"}
        >
          {isSimulating ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>

        {/* Labels Toggle */}
        <button
          onClick={() => setShowLabels(!showLabels)}
          className={`p-2 rounded-xl transition-colors ${
            showLabels ? 'text-cyan-400 bg-cyan-950/50' : 'text-slate-500'
          }`}
          title="Toggle node labels"
        >
          <FileText className="w-4 h-4" />
        </button>
      </div>

      {/* Holographic Hover Tooltip */}
      {hoveredNode && tooltipPos && (
        <div
          className="pointer-events-none absolute z-40 p-3 rounded-xl glass-panel border border-cyan-400/30 bg-slate-950/90 backdrop-blur-lg shadow-[0_0_25px_rgba(0,240,255,0.25)] min-w-[220px]"
          style={{
            left: Math.min(tooltipPos.x + 14, (containerRef.current?.clientWidth || 800) - 240),
            top: Math.min(tooltipPos.y + 14, (containerRef.current?.clientHeight || 600) - 180),
          }}
        >
          <div className="flex items-center justify-between gap-2 mb-1.5 pb-1 border-b border-slate-800">
            <span
              className="text-[9px] font-mono px-2 py-0.5 rounded-full font-bold uppercase"
              style={{
                backgroundColor: `${CATEGORY_STYLES[hoveredNode.category]?.color || '#00f0ff'}20`,
                color: CATEGORY_STYLES[hoveredNode.category]?.color || '#00f0ff',
                border: `1px solid ${CATEGORY_STYLES[hoveredNode.category]?.color || '#00f0ff'}40`,
              }}
            >
              {hoveredNode.category}
            </span>
            <span className="text-[10px] font-mono text-emerald-400 font-bold">
              {hoveredNode.confidence}% CONF
            </span>
          </div>

          <h4 className="text-xs font-semibold text-slate-100 font-mono mb-1 leading-tight">
            {hoveredNode.name}
          </h4>
          <p className="text-[10px] text-slate-400 line-clamp-2 mb-2 font-mono leading-relaxed">
            {hoveredNode.description}
          </p>

          <div className="grid grid-cols-2 gap-1.5 text-[9px] font-mono pt-1.5 border-t border-slate-800/80 text-slate-400">
            <div>
              <span className="text-slate-500">IMPORTANCE: </span>
              <span className="text-cyan-300 font-bold">{hoveredNode.importance}/100</span>
            </div>
            <div>
              <span className="text-slate-500">NEIGHBORS: </span>
              <span className="text-slate-200">
                {neighborMap.get(hoveredNode.id)?.size || 0} links
              </span>
            </div>
            {hoveredNode.source && (
              <div className="col-span-2 truncate">
                <span className="text-slate-500">SRC: </span>
                <span className="text-slate-300">{hoveredNode.source}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Intelligent Right-Click Context Menu */}
      {contextMenu.visible && contextMenu.node && (
        <div
          className="fixed z-50 py-1.5 rounded-xl glass-panel border border-cyan-500/30 bg-slate-950/95 backdrop-blur-xl shadow-[0_12px_48px_rgba(0,0,0,0.8),0_0_20px_rgba(0,240,255,0.2)] min-w-[200px] text-xs font-mono text-slate-200"
          style={{
            left: Math.min(contextMenu.x, window.innerWidth - 220),
            top: Math.min(contextMenu.y, window.innerHeight - 340),
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-3 py-1.5 border-b border-slate-800 text-[10px] text-cyan-400 font-bold uppercase truncate">
            {contextMenu.node.name}
          </div>

          <button
            onClick={() => {
              onOpenResearchMode(contextMenu.node?.name);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-cyan-950/60 hover:text-cyan-300 text-left transition-colors cursor-pointer"
          >
            <Search className="w-3.5 h-3.5 text-cyan-400" />
            <span>Deep Research Node</span>
          </button>

          <button
            onClick={() => {
              onNodeNeighborhoodExpand(contextMenu.node!);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-purple-950/60 hover:text-purple-300 text-left transition-colors cursor-pointer"
          >
            <Share2 className="w-3.5 h-3.5 text-purple-400" />
            <span>Expand Neighborhood</span>
          </button>

          <button
            onClick={() => {
              onOpenWorkflowMode(contextMenu.node?.id);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-emerald-950/60 hover:text-emerald-300 text-left transition-colors cursor-pointer"
          >
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
            <span>Add to Autonomous Workflow</span>
          </button>

          <button
            onClick={() => {
              onOpenClaudeStudio();
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-amber-950/60 hover:text-amber-300 text-left transition-colors cursor-pointer"
          >
            <Terminal className="w-3.5 h-3.5 text-amber-400" />
            <span>Execute in Claude Studio</span>
          </button>

          <div className="h-[1px] bg-slate-800 my-1"></div>

          <button
            onClick={() => {
              onFilterChange(contextMenu.node!.category);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-slate-900 text-left text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
          >
            <Layers className="w-3.5 h-3.5 text-slate-400" />
            <span>Filter Category: {contextMenu.node.category}</span>
          </button>
        </div>
      )}
    </div>
  );
};
