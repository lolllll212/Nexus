import React, { useEffect, useRef } from 'react';

interface NexusAuroraBackgroundProps {
  /** Slightly increases motion/brightness while NEXUS is thinking or streaming. */
  active?: boolean;
  className?: string;
}

interface AuroraNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  hue: number;
}

/**
 * A quiet "living" background for the hybrid chat surface:
 * warm Claude-like paper, Gemini-like aurora colour, and a faint NEXUS
 * constellation. It is decorative only and respects reduced-motion settings.
 */
export const NexusAuroraBackground: React.FC<NexusAuroraBackgroundProps> = ({
  active = false,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const activeRef = useRef(active);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const context = canvas.getContext('2d');
    if (!context) return undefined;

    const parent = canvas.parentElement;
    if (!parent) return undefined;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let width = 0;
    let height = 0;
    let nodes: AuroraNode[] = [];
    let animationFrame = 0;
    let pointerX = -10_000;
    let pointerY = -10_000;

    const palette = [18, 262, 168, 210, 36];

    const seedNodes = () => {
      const count = Math.max(24, Math.min(72, Math.round((width * height) / 24_000)));
      nodes = Array.from({ length: count }, (_, index) => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        radius: 0.8 + Math.random() * 1.7,
        hue: palette[index % palette.length],
      }));
    };

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      const ratio = Math.min(window.devicePixelRatio || 1, 1.6);
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      seedNodes();
      if (reducedMotion.matches) drawFrame(0, true);
    };

    function drawFrame(time: number, staticFrame = false) {
      context.clearRect(0, 0, width, height);
      const isActive = activeRef.current;
      const speed = isActive ? 1.45 : 0.8;
      const linkDistance = Math.min(154, Math.max(96, width / 9));

      nodes.forEach((node) => {
        if (!staticFrame) {
          node.x += node.vx * speed;
          node.y += node.vy * speed;
          if (node.x < -12) node.x = width + 12;
          if (node.x > width + 12) node.x = -12;
          if (node.y < -12) node.y = height + 12;
          if (node.y > height + 12) node.y = -12;
        }

        const pointerDistance = Math.hypot(node.x - pointerX, node.y - pointerY);
        if (pointerDistance < 170) {
          const strength = (170 - pointerDistance) / 170;
          context.beginPath();
          context.moveTo(node.x, node.y);
          context.lineTo(pointerX, pointerY);
          context.strokeStyle = `hsla(${node.hue}, 72%, 52%, ${0.05 + strength * 0.12})`;
          context.lineWidth = 1;
          context.stroke();
        }
      });

      for (let i = 0; i < nodes.length; i += 1) {
        for (let j = i + 1; j < nodes.length; j += 1) {
          const a = nodes[i];
          const b = nodes[j];
          const distance = Math.hypot(a.x - b.x, a.y - b.y);
          if (distance > linkDistance) continue;
          const alpha = (1 - distance / linkDistance) * (isActive ? 0.14 : 0.09);
          context.beginPath();
          context.moveTo(a.x, a.y);
          context.lineTo(b.x, b.y);
          context.strokeStyle = `hsla(${(a.hue + b.hue) / 2}, 55%, 48%, ${alpha})`;
          context.lineWidth = 1;
          context.stroke();
        }
      }

      nodes.forEach((node, index) => {
        const pulse = staticFrame ? 0 : Math.sin(time / 900 + index) * 0.35;
        context.beginPath();
        context.arc(node.x, node.y, Math.max(0.6, node.radius + pulse * 0.25), 0, Math.PI * 2);
        context.fillStyle = `hsla(${node.hue}, 76%, 48%, ${isActive ? 0.34 : 0.24})`;
        context.fill();
      });
    }

    const tick = (time: number) => {
      if (!document.hidden) drawFrame(time);
      animationFrame = window.requestAnimationFrame(tick);
    };

    const handlePointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointerX = event.clientX - rect.left;
      pointerY = event.clientY - rect.top;
      if (reducedMotion.matches) drawFrame(0, true);
    };

    const handlePointerLeave = () => {
      pointerX = -10_000;
      pointerY = -10_000;
    };

    const handleMotionChange = () => {
      window.cancelAnimationFrame(animationFrame);
      if (reducedMotion.matches) drawFrame(0, true);
      else animationFrame = window.requestAnimationFrame(tick);
    };

    resize();
    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    resizeObserver?.observe(parent);
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('pointerleave', handlePointerLeave);
    reducedMotion.addEventListener?.('change', handleMotionChange);

    if (!reducedMotion.matches) animationFrame = window.requestAnimationFrame(tick);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerleave', handlePointerLeave);
      reducedMotion.removeEventListener?.('change', handleMotionChange);
    };
  }, []);

  return (
    <div aria-hidden="true" className={`nexus-aurora ${active ? 'nexus-aurora-active' : ''} ${className}`}>
      <div className="nexus-aurora-blob nexus-aurora-blob-warm" />
      <div className="nexus-aurora-blob nexus-aurora-blob-violet" />
      <div className="nexus-aurora-blob nexus-aurora-blob-teal" />
      <div className="nexus-aurora-grid" />
      <canvas ref={canvasRef} className="nexus-aurora-canvas" />
      <div className="nexus-aurora-vignette" />
    </div>
  );
};
