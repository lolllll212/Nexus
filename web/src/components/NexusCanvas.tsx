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
  Bookmark,
  Pin,
  BookOpen,
  Box,
  Target,
  Radio,
  HelpCircle,
  CheckCircle2,
  Database,
  AlignLeft,
  Check
} from 'lucide-react';
import { playHudClick, playChime, playSuccessChime } from '../utils/soundEffects';

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
  onAskNexus?: (query: string) => void;
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
  onAskNexus,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Layout & Simulation State
  const [layout, setLayout] = useState<LayoutAlgorithm>('FORCE');
  const [isSimulating, setIsSimulating] = useState(true);
  const [is3DView, setIs3DView] = useState(false);
  const [isTracing, setIsTracing] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [showPulses, setShowPulses] = useState(true);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

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

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

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
          pinned: existing.pinned,
          fx: existing.fx,
          fy: existing.fy,
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
    particlesRef.current = links.slice(0, 48).map((l, i) => {
      const sId = typeof l.source === 'object' ? l.source.id : l.source;
      const tId = typeof l.target === 'object' ? l.target.id : l.target;
      return {
        sourceId: sId,
        targetId: tId,
        progress: (i * 0.08) % 1,
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

  // Recenter & Fit Camera (FIT)
  const handleFit = useCallback(() => {
    playHudClick();
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

    const graphW = Math.max(maxX - minX + 160, 400);
    const graphH = Math.max(maxY - minY + 160, 400);
    const scale = Math.min(w / graphW, h / graphH, 1.2) * 0.88;

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    transformRef.current = {
      x: w / 2 - centerX * scale,
      y: h / 2 - centerY * scale,
      k: scale,
    };
    setZoomLevel(scale);
    showToast("Graph fitted to viewport");
  }, []);

  // Focus on Selected Node or Core Hub (FOCUS)
  const handleFocus = useCallback(() => {
    playHudClick();
    const container = containerRef.current;
    if (!container) return;
    const target = selectedNode || simulationNodesRef.current.find(n => n.id === 'res-core') || simulationNodesRef.current[0];
    if (target && target.x !== undefined && target.y !== undefined) {
      const w = container.clientWidth;
      const h = container.clientHeight;
      const targetScale = 1.35;
      transformRef.current = {
        x: w / 2 - target.x * targetScale,
        y: h / 2 - target.y * targetScale,
        k: targetScale,
      };
      setZoomLevel(targetScale);
      showToast(`Focused on: ${target.name}`);
    }
  }, [selectedNode]);

  // Reset Camera View (RESET)
  const handleReset = useCallback(() => {
    playHudClick();
    const container = containerRef.current;
    if (!container) return;
    transformRef.current = { x: 0, y: 0, k: 0.85 };
    setZoomLevel(0.85);
    showToast("Camera reset (Scale: 0.85)");
  }, []);

  // Zoom Handler
  const handleZoom = useCallback((factor: number) => {
    playHudClick();
    const container = containerRef.current;
    if (!container) return;
    const cx = container.clientWidth / 2;
    const cy = container.clientHeight / 2;
    const { x, y, k } = transformRef.current;
    const newK = Math.min(Math.max(k * factor, 0.25), 3.5);

    transformRef.current = {
      x: cx - (cx - x) * (newK / k),
      y: cy - (cy - y) * (newK / k),
      k: newK,
    };
    setZoomLevel(newK);
  }, []);

  // Expand Neighborhood on Selected Node (EXPAND)
  const handleExpand = useCallback(() => {
    playSuccessChime();
    const target = selectedNode || simulationNodesRef.current.find(n => n.id === 'res-core') || simulationNodesRef.current[0];
    if (target) {
      onNodeNeighborhoodExpand(target);
      showToast(`Expanded neighborhood for: ${target.name}`);
    }
  }, [selectedNode, onNodeNeighborhoodExpand]);

  // Main Canvas Render & Animation Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let pulseAngle = 0;

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
              if (n1 !== draggingNodeRef.current && !n1.pinned) {
                n1.vx = (n1.vx || 0) - fx;
                n1.vy = (n1.vy || 0) - fy;
              }
              if (n2 !== draggingNodeRef.current && !n2.pinned) {
                n2.vx = (n2.vx || 0) + fx;
                n2.vy = (n2.vy || 0) + fy;
              }
            }
          }

          // Center gravitational pull
          const pull = 0.0006 * n1.val;
          if (!n1.pinned && n1 !== draggingNodeRef.current) {
            n1.vx = (n1.vx || 0) - ((n1.x || 0) - cx) * pull;
            n1.vy = (n1.vy || 0) - ((n1.y || 0) - cy) * pull;
          }
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
            const targetDist = 115;
            const displacement = dist - targetDist;
            const force = displacement * 0.008;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            if (s !== draggingNodeRef.current && !s.pinned) {
              s.vx = (s.vx || 0) + fx;
              s.vy = (s.vy || 0) + fy;
            }
            if (t !== draggingNodeRef.current && !t.pinned) {
              t.vx = (t.vx || 0) - fx;
              t.vy = (t.vy || 0) - fy;
            }
          }
        });
      } else if (layout === 'RING') {
        // Concentric orbital rings around major hubs
        localNodes.forEach((n, idx) => {
          if (n.pinned || n === draggingNodeRef.current) return;
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
          if (n.pinned || n === draggingNodeRef.current) return;
          const catIdx = categories.indexOf(n.category);
          const catAngle = (catIdx / categories.length) * 2 * Math.PI;
          const clusterCenterX = cx + Math.cos(catAngle) * 250;
          const clusterCenterY = cy + Math.sin(catAngle) * 250;
          n.vx = (n.vx || 0) + (clusterCenterX - (n.x || cx)) * 0.025;
          n.vy = (n.vy || 0) + (clusterCenterY - (n.y || cy)) * 0.025;
        });
      } else if (layout === 'RADIAL') {
        // Concentric radial tree from root node
        const rootId = selectedNode?.id || 'res-core' || (localNodes[0] ? localNodes[0].id : '');
        const depths = new Map<string, number>();
        depths.set(rootId, 0);

        const queue = [rootId];
        while (queue.length > 0) {
          const curr = queue.shift()!;
          const d = depths.get(curr) || 0;
          const neighbors = neighborMap.get(curr);
          if (neighbors) {
            neighbors.forEach((nbr) => {
              if (!depths.has(nbr)) {
                depths.set(nbr, d + 1);
                queue.push(nbr);
              }
            });
          }
        }

        const depthGroups = new Map<number, NexusNode[]>();
        localNodes.forEach((n) => {
          const d = Math.min(depths.get(n.id) ?? 3, 3);
          if (!depthGroups.has(d)) depthGroups.set(d, []);
          depthGroups.get(d)!.push(n);
        });

        depthGroups.forEach((groupNodes, d) => {
          if (d === 0) {
            groupNodes.forEach((n) => {
              if (n.pinned || n === draggingNodeRef.current) return;
              n.vx = (n.vx || 0) + (cx - (n.x || cx)) * 0.05;
              n.vy = (n.vy || 0) + (cy - (n.y || cy)) * 0.05;
            });
          } else {
            const radius = d * 145;
            const count = groupNodes.length;
            groupNodes.forEach((n, idx) => {
              if (n.pinned || n === draggingNodeRef.current) return;
              const angle = (idx / count) * 2 * Math.PI + pulseAngle * 0.02;
              const targetX = cx + Math.cos(angle) * radius;
              const targetY = cy + Math.sin(angle) * radius;
              n.vx = (n.vx || 0) + (targetX - (n.x || cx)) * 0.035;
              n.vy = (n.vy || 0) + (targetY - (n.y || cy)) * 0.035;
            });
          }
        });
      }

      // Position update with friction damping
      const damping = 0.88;
      localNodes.forEach((n) => {
        if (n !== draggingNodeRef.current && !n.pinned) {
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
      const cx = width / 2;
      const cy = height / 2;

      if (isSimulating) {
        stepPhysics();
      }

      // Projection helper for 3D Isometric View vs 2D View
      const project = (wx: number, wy: number, node?: NexusNode) => {
        if (!is3DView) {
          return { px: wx, py: wy, scale: 1, elevation: 0, groundPy: wy };
        }
        const importance = node?.importance || 50;
        const elevation = (importance / 100) * 85;
        const yaw = 0.38;
        const pitch = 0.52;
        const rx = (wx - cx) * Math.cos(yaw) - (wy - cy) * Math.sin(yaw);
        const ry = (wx - cx) * Math.sin(yaw) + (wy - cy) * Math.cos(yaw);
        const groundPy = cy + ry * Math.sin(pitch);
        const px = cx + rx;
        const py = groundPy - elevation;
        const scale = 0.85 + (elevation / 85) * 0.4;
        return { px, py, scale, elevation, groundPy };
      };

      // Clear Canvas with rich dark background
      ctx.fillStyle = '#030508';
      ctx.fillRect(0, 0, width, height);

      // Camera Transform matrix
      const { x: panX, y: panY, k } = transformRef.current;
      ctx.save();
      ctx.translate(panX, panY);
      ctx.scale(k, k);

      // ── Grid Rendering (2D Dot Grid vs 3D Isometric Plane) ──────────────────
      if (is3DView) {
        ctx.strokeStyle = 'rgba(0, 240, 255, 0.04)';
        ctx.lineWidth = 1;
        const yaw = 0.38;
        const pitch = 0.52;
        for (let gx = -600; gx <= 1600; gx += 120) {
          const rx1 = (gx - cx) * Math.cos(yaw) - (-600 - cy) * Math.sin(yaw);
          const ry1 = (gx - cx) * Math.sin(yaw) + (-600 - cy) * Math.cos(yaw);
          const rx2 = (gx - cx) * Math.cos(yaw) - (1600 - cy) * Math.sin(yaw);
          const ry2 = (gx - cx) * Math.sin(yaw) + (1600 - cy) * Math.cos(yaw);
          ctx.beginPath();
          ctx.moveTo(cx + rx1, cy + ry1 * Math.sin(pitch));
          ctx.lineTo(cx + rx2, cy + ry2 * Math.sin(pitch));
          ctx.stroke();
        }
        for (let gy = -600; gy <= 1600; gy += 120) {
          const rx1 = (-600 - cx) * Math.cos(yaw) - (gy - cy) * Math.sin(yaw);
          const ry1 = (-600 - cx) * Math.sin(yaw) + (gy - cy) * Math.cos(yaw);
          const rx2 = (1600 - cx) * Math.cos(yaw) - (gy - cy) * Math.sin(yaw);
          const ry2 = (1600 - cx) * Math.sin(yaw) + (gy - cy) * Math.cos(yaw);
          ctx.beginPath();
          ctx.moveTo(cx + rx1, cy + ry1 * Math.sin(pitch));
          ctx.lineTo(cx + rx2, cy + ry2 * Math.sin(pitch));
          ctx.stroke();
        }
      } else {
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

        const sProj = project(s.x, s.y || cy, s);
        const tProj = project(t.x, t.y || cy, t);

        const isDirectConnection = 
          selectedNode && (s.id === selectedNode.id || t.id === selectedNode.id);
        const isHoveredConnection = 
          hovered && (s.id === hovered.id || t.id === hovered.id);
        const isTracedLink = isTracing && (isDirectConnection || s.id === 'res-core' || t.id === 'res-core');

        let strokeColor = 'rgba(56, 189, 248, 0.12)';
        let lineWidth = 0.8;

        if (isTracedLink) {
          strokeColor = 'rgba(0, 240, 255, 0.85)';
          lineWidth = 2.4;
        } else if (isDirectConnection) {
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
        ctx.moveTo(sProj.px, sProj.py);
        ctx.lineTo(tProj.px, tProj.py);
        ctx.stroke();

        // Relation label on highlighted link
        if ((isDirectConnection || isHoveredConnection || isTracedLink) && l.relation) {
          const midX = (sProj.px + tProj.px) / 2;
          const midY = (sProj.py + tProj.py) / 2;
          ctx.font = '8px "JetBrains Mono", monospace';
          ctx.fillStyle = isDirectConnection || isTracedLink ? '#00f0ff' : '#c084fc';
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
            const speedMultiplier = isTracing ? 2.2 : 1.0;
            p.progress += p.speed * speedMultiplier;
            if (p.progress >= 1) p.progress = 0;

            const sProj = project(s.x, s.y || cy, s);
            const tProj = project(t.x, t.y || cy, t);

            const px = sProj.px + (tProj.px - sProj.px) * p.progress;
            const py = sProj.py + (tProj.py - sProj.py) * p.progress;

            ctx.beginPath();
            ctx.arc(px, py, isTracing ? 2.4 : 1.8, 0, Math.PI * 2);
            ctx.fillStyle = isTracing ? '#00f0ff' : p.color;
            ctx.shadowColor = '#00f0ff';
            ctx.shadowBlur = isTracing ? 12 : 6;
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

        const proj = project(n.x, n.y, n);
        const baseRadius = Math.max(7, Math.sqrt(n.val) * 3.4) * proj.scale;
        const radius = isSelected ? baseRadius * 1.3 : isHovered ? baseRadius * 1.15 : baseRadius;

        // 3D Isometric Elevation Pillar & Ground Shadow
        if (is3DView) {
          ctx.beginPath();
          ctx.ellipse(proj.px, proj.groundPy, radius * 0.75, radius * 0.35, 0, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
          ctx.fill();

          ctx.beginPath();
          ctx.setLineDash([2, 3]);
          ctx.strokeStyle = `${style.color}40`;
          ctx.lineWidth = 1;
          ctx.moveTo(proj.px, proj.groundPy);
          ctx.lineTo(proj.px, proj.py);
          ctx.stroke();
          ctx.setLineDash([]);
        }

        // Animated aura pulsation for active nodes
        if (n.pulsing || isSelected) {
          const pulseR = radius + 4 + Math.sin(pulseAngle * 3) * 3;
          ctx.beginPath();
          ctx.arc(proj.px, proj.py, pulseR, 0, Math.PI * 2);
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
        ctx.arc(proj.px, proj.py, radius, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? '#ffffff' : style.color;
        ctx.fill();

        // Thin dark holographic border
        ctx.lineWidth = isSelected ? 2.5 : 1.2;
        ctx.strokeStyle = isSelected ? '#00f0ff' : 'rgba(2, 4, 8, 0.8)';
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Inner Core dot (or pin indicator)
        ctx.beginPath();
        ctx.arc(proj.px, proj.py, radius * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = n.pinned ? '#ef4444' : '#05070c';
        ctx.fill();

        // Monospaced Technical Labels
        if (showLabels || isSelected || isHovered || n.val > 25) {
          ctx.font = `${isSelected ? 'bold 11px' : '9px'} "JetBrains Mono", monospace`;
          ctx.fillStyle = isSelected ? '#ffffff' : isNeighbor ? '#e2e8f0' : 'rgba(226, 232, 240, 0.75)';
          ctx.textAlign = 'center';
          ctx.fillText(n.name.length > 24 ? n.name.slice(0, 22) + '…' : n.name, proj.px, proj.py + radius + 13);

          // Sub-label category tag
          if (isSelected || n.val > 28) {
            ctx.font = '7px "JetBrains Mono", monospace';
            ctx.fillStyle = style.color;
            ctx.fillText(n.category, proj.px, proj.py + radius + 22);
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
  }, [layout, isSimulating, is3DView, isTracing, showLabels, showPulses, links, selectedNode, neighborMap, activeFilter, searchQuery]);

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
    const cx = (containerRef.current?.clientWidth || 1000) / 2;
    const cy = (containerRef.current?.clientHeight || 800) / 2;

    for (let i = localNodes.length - 1; i >= 0; i--) {
      const n = localNodes[i];
      if (n.x === undefined || n.y === undefined) continue;

      let targetX = n.x;
      let targetY = n.y;

      if (is3DView) {
        const importance = n.importance || 50;
        const elevation = (importance / 100) * 85;
        const yaw = 0.38;
        const pitch = 0.52;
        const rx = (n.x - cx) * Math.cos(yaw) - (n.y - cy) * Math.sin(yaw);
        const ry = (n.x - cx) * Math.sin(yaw) + (n.y - cy) * Math.cos(yaw);
        targetX = cx + rx;
        targetY = cy + ry * Math.sin(pitch) - elevation;
      }

      const baseRadius = Math.max(7, Math.sqrt(n.val) * 3.4);
      const hitRadius = baseRadius + 10;
      const dx = worldX - targetX;
      const dy = worldY - targetY;
      if (dx * dx + dy * dy <= hitRadius * hitRadius) {
        return n;
      }
    }
    return null;
  }, [is3DView]);

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
        playChime();
      }
      return;
    }

    if (e.button === 0) {
      const world = screenToWorld(e.clientX, e.clientY);
      const target = getNodeAtPosition(world.x, world.y);

      if (target) {
        draggingNodeRef.current = target;
        onSelectNode(target);
        playHudClick();
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
      if (draggingNodeRef.current.pinned) {
        draggingNodeRef.current.fx = world.x;
        draggingNodeRef.current.fy = world.y;
      }
      return;
    }

    if (isPanningRef.current) {
      transformRef.current.x = e.clientX - panStartRef.current.x;
      transformRef.current.y = e.clientY - panStartRef.current.y;
      return;
    }

    // Hover detection
    const world = screenToWorld(e.clientX, e.clientY);
    const target = getNodeAtPosition(world.x, world.y);
    hoveredNodeRef.current = target;
    setHoveredNode(target);

    if (target) {
      const canvas = canvasRef.current;
      const rect = canvas?.getBoundingClientRect();
      if (rect) {
        setTooltipPos({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
        });
      }
    } else {
      setTooltipPos(null);
    }
  }, [screenToWorld, getNodeAtPosition]);

  const handleMouseUp = useCallback(() => {
    draggingNodeRef.current = null;
    isPanningRef.current = false;
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.08 : 0.92;
    handleZoom(factor);
  }, [handleZoom]);

  const handleDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const world = screenToWorld(e.clientX, e.clientY);
    const target = getNodeAtPosition(world.x, world.y);
    if (target) {
      onNodeNeighborhoodExpand(target);
    }
  }, [screenToWorld, getNodeAtPosition, onNodeNeighborhoodExpand]);

  const categories = Object.keys(CATEGORY_STYLES) as NodeCategory[];

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden bg-[#030508] select-none font-mono"
      onContextMenu={(e) => e.preventDefault()}
    >
      {/* ── Main Canvas Viewport ───────────────────────────────────────────── */}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        onDoubleClick={handleDoubleClick}
        className="w-full h-full cursor-grab active:cursor-grabbing"
      />

      {/* ── Status Toast ───────────────────────────────────────────────────── */}
      {toastMessage && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-40 px-3.5 py-1.5 rounded-xl glass-panel border border-cyan-400/40 bg-slate-950/90 text-cyan-300 text-xs shadow-[0_0_20px_rgba(0,240,255,0.3)] animate-fadeIn flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* ── Top-Left Graph Telemetry Badges ─────────────────────────────────── */}
      <div className="absolute top-16 left-6 z-20 flex items-center gap-2 text-[10px] text-slate-400">
        <div className="px-2.5 py-1 rounded-xl glass-panel border border-cyan-500/20 bg-slate-950/80 backdrop-blur-md flex items-center gap-1.5 shadow-lg">
          <Activity className="w-3 h-3 text-cyan-400 animate-pulse" />
          <span className="font-bold text-white">{nodes.length}</span>
          <span>NODES</span>
          <span className="text-slate-600">&bull;</span>
          <span className="font-bold text-cyan-300">{links.length}</span>
          <span>SYNAPSES</span>
        </div>

        <div className="px-2.5 py-1 rounded-xl glass-panel border border-cyan-500/20 bg-slate-950/80 backdrop-blur-md flex items-center gap-1.5">
          <span className="text-slate-500">MODE:</span>
          <span className="text-cyan-300 font-bold">{is3DView ? '3D ISOMETRIC' : '2D TOP-DOWN'}</span>
        </div>

        {isTracing && (
          <div className="px-2.5 py-1 rounded-xl glass-panel border border-cyan-400/50 bg-cyan-950/60 text-cyan-300 font-bold flex items-center gap-1.5 animate-pulse">
            <Radio className="w-3 h-3 text-cyan-400" />
            <span>TRACE ACTIVE</span>
          </div>
        )}
      </div>

      {/* ── Top-Center Quick Filter Bar ─────────────────────────────────────── */}
      <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 p-1 rounded-xl glass-panel border border-cyan-500/20 bg-slate-950/80 backdrop-blur-md max-w-[55vw] overflow-x-auto shadow-lg">
        <button
          onClick={() => {
            onFilterChange(null);
            playHudClick();
          }}
          className={`px-2.5 py-1 rounded-lg text-[10px] font-mono transition-all cursor-pointer ${
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
              onClick={() => {
                onFilterChange(isCurrent ? null : cat);
                playHudClick();
              }}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono transition-all cursor-pointer ${
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

      {/* ── Tactical Graph Controls Toolbar (Bottom-Right) ──────────────────── */}
      {/* Tactical controls: FIT, FOCUS, RESET, ZOOM, LAYOUT (Force, Ring, Cluster, Radial), TRACE, EXPAND, 2D/3D */}
      <div className="absolute bottom-24 right-6 z-20 flex flex-col items-center gap-1.5 p-2 rounded-2xl glass-panel border border-cyan-500/25 bg-slate-950/90 backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.8),0_0_20px_rgba(0,240,255,0.1)]">
        {/* FIT */}
        <button
          onClick={handleFit}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors cursor-pointer"
          title="FIT: Auto-fit whole graph bounds into viewport"
        >
          <Crosshair className="w-4 h-4 text-cyan-400" />
        </button>

        {/* FOCUS */}
        <button
          onClick={handleFocus}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors cursor-pointer"
          title="FOCUS: Center on selected node or core hub"
        >
          <Target className="w-4 h-4 text-purple-400" />
        </button>

        {/* RESET */}
        <button
          onClick={handleReset}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors cursor-pointer"
          title="RESET: Reset zoom & pan to default"
        >
          <RotateCcw className="w-4 h-4 text-slate-400" />
        </button>

        <div className="w-5 h-[1px] bg-slate-800 my-0.5"></div>

        {/* ZOOM IN / OUT */}
        <button
          onClick={() => handleZoom(1.18)}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors cursor-pointer"
          title="ZOOM IN (+)"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => handleZoom(0.85)}
          className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition-colors cursor-pointer"
          title="ZOOM OUT (-)"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <div className="w-5 h-[1px] bg-slate-800 my-0.5"></div>

        {/* LAYOUT: Force, Ring, Cluster, Radial */}
        <button
          onClick={() => {
            playHudClick();
            const modes: LayoutAlgorithm[] = ['FORCE', 'RING', 'CLUSTER', 'RADIAL'];
            const nextIdx = (modes.indexOf(layout) + 1) % modes.length;
            setLayout(modes[nextIdx]);
            showToast(`Layout changed to: ${modes[nextIdx]}`);
          }}
          className="p-2 rounded-xl text-cyan-300 hover:bg-cyan-950/60 transition-colors font-mono text-[9px] font-bold flex flex-col items-center cursor-pointer"
          title={`LAYOUT: ${layout} (Click to cycle Force, Ring, Cluster, Radial)`}
        >
          <Compass className="w-4 h-4 text-amber-400 mb-0.5" />
          <span>{layout}</span>
        </button>

        {/* TRACE */}
        <button
          onClick={() => {
            playHudClick();
            setIsTracing(!isTracing);
            showToast(isTracing ? "Trace Mode: OFF" : "Trace Mode: ACTIVE");
          }}
          className={`p-2 rounded-xl transition-colors cursor-pointer ${
            isTracing ? 'text-cyan-300 bg-cyan-950/80 border border-cyan-400/40' : 'text-slate-400 hover:text-cyan-300'
          }`}
          title={isTracing ? "Disable Network Tracing" : "TRACE: Stream animated pulses along connected edges"}
        >
          <Radio className="w-4 h-4" />
        </button>

        {/* EXPAND */}
        <button
          onClick={handleExpand}
          className="p-2 rounded-xl text-slate-400 hover:text-purple-300 hover:bg-purple-950/60 transition-colors cursor-pointer"
          title="EXPAND: Double-click or expand selected node neighborhood"
        >
          <Share2 className="w-4 h-4 text-purple-400" />
        </button>

        {/* 2D / 3D MODE TOGGLE */}
        <button
          onClick={() => {
            playHudClick();
            setIs3DView(!is3DView);
            showToast(is3DView ? "Switched to 2D Top-Down" : "Switched to 3D Isometric View");
          }}
          className={`p-2 rounded-xl transition-colors cursor-pointer font-bold text-[9px] flex flex-col items-center ${
            is3DView ? 'text-cyan-300 bg-cyan-950/80 border border-cyan-400/40 shadow-[0_0_12px_rgba(0,240,255,0.3)]' : 'text-slate-400 hover:text-cyan-300'
          }`}
          title={is3DView ? "Switch to 2D Top-Down" : "Switch to 3D Isometric Perspective Projection"}
        >
          <Box className="w-4 h-4 text-cyan-400 mb-0.5" />
          <span>{is3DView ? '3D' : '2D'}</span>
        </button>

        <div className="w-5 h-[1px] bg-slate-800 my-0.5"></div>

        {/* Physics Pause / Play */}
        <button
          onClick={() => {
            playHudClick();
            setIsSimulating(!isSimulating);
          }}
          className={`p-2 rounded-xl transition-colors cursor-pointer ${
            !isSimulating ? 'text-amber-400 bg-amber-950/40' : 'text-slate-400 hover:text-cyan-300'
          }`}
          title={isSimulating ? "Freeze physics simulation" : "Resume physics simulation"}
        >
          {isSimulating ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>

        {/* Labels Toggle */}
        <button
          onClick={() => {
            playHudClick();
            setShowLabels(!showLabels);
          }}
          className={`p-2 rounded-xl transition-colors cursor-pointer ${
            showLabels ? 'text-cyan-400 bg-cyan-950/50' : 'text-slate-500'
          }`}
          title="Toggle node labels"
        >
          <FileText className="w-4 h-4" />
        </button>
      </div>

      {/* ── Compact Holographic Hover Tooltip ────────────────────────────────── */}
      {hoveredNode && tooltipPos && (
        <div
          className="pointer-events-none absolute z-40 p-3 rounded-2xl glass-panel border border-cyan-400/40 bg-slate-950/95 backdrop-blur-xl shadow-[0_0_30px_rgba(0,240,255,0.25)] min-w-[240px] text-xs font-mono"
          style={{
            left: Math.min(tooltipPos.x + 16, (containerRef.current?.clientWidth || 800) - 260),
            top: Math.min(tooltipPos.y + 16, (containerRef.current?.clientHeight || 600) - 200),
          }}
        >
          <div className="flex items-center justify-between gap-2 mb-1.5 pb-1 border-b border-slate-800">
            <span
              className="text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider"
              style={{
                backgroundColor: `${CATEGORY_STYLES[hoveredNode.category]?.color || '#00f0ff'}20`,
                color: CATEGORY_STYLES[hoveredNode.category]?.color || '#00f0ff',
                border: `1px solid ${CATEGORY_STYLES[hoveredNode.category]?.color || '#00f0ff'}40`,
              }}
            >
              {hoveredNode.category}
            </span>
            <span className="text-[10px] text-emerald-400 font-bold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              {hoveredNode.confidence}% CONF
            </span>
          </div>

          <h4 className="text-xs font-bold text-white mb-1 leading-tight">
            {hoveredNode.name}
          </h4>

          <p className="text-[10px] text-slate-400 line-clamp-2 mb-2 leading-relaxed">
            {hoveredNode.description}
          </p>

          <div className="grid grid-cols-2 gap-1 text-[9px] pt-1.5 border-t border-slate-800/80 text-slate-400">
            <div>
              <span className="text-slate-500">IMPORTANCE: </span>
              <span className="text-cyan-300 font-bold">{hoveredNode.importance}/100</span>
            </div>
            <div>
              <span className="text-slate-500">SYNAPSES: </span>
              <span className="text-slate-200">
                {neighborMap.get(hoveredNode.id)?.size || 0} links
              </span>
            </div>
            {hoveredNode.hub && (
              <div className="col-span-2 truncate">
                <span className="text-slate-500">HUB: </span>
                <span className="text-purple-300">{hoveredNode.hub}</span>
              </div>
            )}
            {hoveredNode.source && (
              <div className="col-span-2 truncate text-slate-500">
                <span>SRC: </span>
                <span className="text-slate-300">{hoveredNode.source}</span>
              </div>
            )}
          </div>

          <div className="mt-2 pt-1 border-t border-slate-800 text-[8px] text-slate-500 flex items-center justify-between">
            <span>Right-click for tactical actions</span>
            <span>2x click expand</span>
          </div>
        </div>
      )}

      {/* ── Intelligent Right-Click Context Menu (All 11 Actions) ─────────────── */}
      {/* Actions: RESEARCH, TRACE CONNECTIONS, OPEN SOURCE, ADD TO WORKFLOW, CREATE TASK, ASK NEXUS, SUMMARIZE, MEMORIZE, EXECUTE, PIN, FILTER */}
      {contextMenu.visible && contextMenu.node && (
        <div
          className="fixed z-50 py-1.5 rounded-2xl glass-panel border border-cyan-500/40 bg-slate-950/95 backdrop-blur-2xl shadow-[0_12px_48px_rgba(0,0,0,0.9),0_0_25px_rgba(0,240,255,0.2)] min-w-[220px] text-xs font-mono text-slate-200 animate-fadeIn"
          style={{
            left: Math.min(contextMenu.x, window.innerWidth - 240),
            top: Math.min(contextMenu.y, window.innerHeight - 440),
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="px-3 py-1.5 border-b border-slate-800 text-[10px] text-cyan-400 font-bold uppercase truncate flex items-center justify-between">
            <span className="truncate">{contextMenu.node.name}</span>
            <span className="text-[8px] text-slate-500 shrink-0 ml-1">[{contextMenu.node.category}]</span>
          </div>

          {/* 1. RESEARCH */}
          <button
            onClick={() => {
              playHudClick();
              onOpenResearchMode(contextMenu.node?.name);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-cyan-950/60 hover:text-cyan-300 text-left transition-colors cursor-pointer"
          >
            <Search className="w-3.5 h-3.5 text-cyan-400" />
            <span>RESEARCH Node</span>
          </button>

          {/* 2. TRACE CONNECTIONS */}
          <button
            onClick={() => {
              playHudClick();
              setIsTracing(true);
              onSelectNode(contextMenu.node);
              showToast(`Tracing connections for: ${contextMenu.node?.name}`);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-cyan-950/60 hover:text-cyan-300 text-left transition-colors cursor-pointer"
          >
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
            <span>TRACE CONNECTIONS</span>
          </button>

          {/* 3. OPEN SOURCE */}
          <button
            onClick={() => {
              playHudClick();
              showToast(`Opened source: ${contextMenu.node?.source || 'Internal Graph Node'}`);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-slate-900 text-left text-slate-300 hover:text-white transition-colors cursor-pointer"
          >
            <BookOpen className="w-3.5 h-3.5 text-slate-400" />
            <span>OPEN SOURCE</span>
          </button>

          {/* 4. ADD TO WORKFLOW */}
          <button
            onClick={() => {
              playHudClick();
              onOpenWorkflowMode(contextMenu.node?.id);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-emerald-950/60 hover:text-emerald-300 text-left transition-colors cursor-pointer"
          >
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
            <span>ADD TO WORKFLOW</span>
          </button>

          {/* 5. CREATE TASK */}
          <button
            onClick={() => {
              playSuccessChime();
              onNodeNeighborhoodExpand(contextMenu.node!);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-purple-950/60 hover:text-purple-300 text-left transition-colors cursor-pointer"
          >
            <PlusCircle className="w-3.5 h-3.5 text-purple-400" />
            <span>CREATE TASK</span>
          </button>

          {/* 6. ASK NEXUS */}
          <button
            onClick={() => {
              playHudClick();
              if (onAskNexus) {
                onAskNexus(`Tell me about ${contextMenu.node?.name}`);
              }
              const input = document.querySelector('input[placeholder*="Ask NEXUS"]') as HTMLInputElement;
              if (input) {
                input.value = `Tell me about ${contextMenu.node?.name}`;
                input.focus();
              }
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-blue-950/60 hover:text-blue-300 text-left transition-colors cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-400" />
            <span>ASK NEXUS</span>
          </button>

          {/* 7. SUMMARIZE */}
          <button
            onClick={() => {
              playChime();
              onSelectNode(contextMenu.node);
              showToast(`Executive summary generated for: ${contextMenu.node?.name}`);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-slate-900 text-left text-slate-300 hover:text-white transition-colors cursor-pointer"
          >
            <AlignLeft className="w-3.5 h-3.5 text-indigo-400" />
            <span>SUMMARIZE</span>
          </button>

          {/* 8. MEMORIZE */}
          <button
            onClick={() => {
              playSuccessChime();
              if (contextMenu.node) {
                contextMenu.node.status = 'synced';
                showToast(`Memorized to Subcortex (Qdrant Vector Store)`);
              }
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-pink-950/60 hover:text-pink-300 text-left transition-colors cursor-pointer"
          >
            <Database className="w-3.5 h-3.5 text-pink-400" />
            <span>MEMORIZE (Subcortex)</span>
          </button>

          {/* 9. EXECUTE */}
          <button
            onClick={() => {
              playHudClick();
              onOpenClaudeStudio();
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-amber-950/60 hover:text-amber-300 text-left transition-colors cursor-pointer"
          >
            <Terminal className="w-3.5 h-3.5 text-amber-400" />
            <span>EXECUTE in Studio</span>
          </button>

          <div className="h-[1px] bg-slate-800 my-1"></div>

          {/* 10. PIN / UNPIN */}
          <button
            onClick={() => {
              playHudClick();
              if (contextMenu.node) {
                contextMenu.node.pinned = !contextMenu.node.pinned;
                if (contextMenu.node.pinned) {
                  contextMenu.node.fx = contextMenu.node.x;
                  contextMenu.node.fy = contextMenu.node.y;
                  showToast(`Pinned node position`);
                } else {
                  contextMenu.node.fx = null;
                  contextMenu.node.fy = null;
                  showToast(`Unpinned node position`);
                }
              }
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-slate-900 text-left text-slate-300 hover:text-white transition-colors cursor-pointer"
          >
            <Pin className={`w-3.5 h-3.5 ${contextMenu.node.pinned ? 'text-red-400' : 'text-slate-400'}`} />
            <span>{contextMenu.node.pinned ? 'UNPIN Position' : 'PIN Position'}</span>
          </button>

          {/* 11. FILTER */}
          <button
            onClick={() => {
              playHudClick();
              onFilterChange(contextMenu.node!.category);
              setContextMenu((prev) => ({ ...prev, visible: false }));
            }}
            className="w-full flex items-center gap-2.5 px-3 py-1.5 hover:bg-slate-900 text-left text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
          >
            <Layers className="w-3.5 h-3.5 text-slate-400" />
            <span>FILTER: {contextMenu.node.category}</span>
          </button>
        </div>
      )}
    </div>
  );
};
