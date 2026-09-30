import React, { useEffect, useRef } from 'react';

interface HoloCubeOverlayProps {
  active: boolean;
}

export const HoloCubeOverlay: React.FC<HoloCubeOverlayProps> = ({ active }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let angleX = 0;
    let angleY = 0;
    let angleZ = 0;

    // Cube vertices (-1 to 1)
    const vertices = [
      [-1, -1, -1],
      [1, -1, -1],
      [1, 1, -1],
      [-1, 1, -1],
      [-1, -1, 1],
      [1, -1, 1],
      [1, 1, 1],
      [-1, 1, 1],
    ];

    // Edges connecting vertices
    const edges = [
      [0, 1], [1, 2], [2, 3], [3, 0], // back face
      [4, 5], [5, 6], [6, 7], [7, 4], // front face
      [0, 4], [1, 5], [2, 6], [3, 7], // connecting edges
    ];

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const size = 55;

      angleX += 0.012;
      angleY += 0.016;
      angleZ += 0.008;

      // Rotate vertices
      const radX = angleX;
      const radY = angleY;
      const radZ = angleZ;

      const projected = vertices.map(([x, y, z]) => {
        // Rotate X
        let y1 = y * Math.cos(radX) - z * Math.sin(radX);
        let z1 = y * Math.sin(radX) + z * Math.cos(radX);

        // Rotate Y
        let x2 = x * Math.cos(radY) + z1 * Math.sin(radY);
        let z2 = -x * Math.sin(radY) + z1 * Math.cos(radY);

        // Rotate Z
        let x3 = x2 * Math.cos(radZ) - y1 * Math.sin(radZ);
        let y3 = x2 * Math.sin(radZ) + y1 * Math.cos(radZ);

        // Perspective projection
        const fov = 3.5;
        const scale = fov / (fov + z2);
        return {
          x: cx + x3 * size * scale,
          y: cy + y3 * size * scale,
          z: z2,
        };
      });

      // Draw wireframe edges
      ctx.lineWidth = 1.5;
      edges.forEach(([i, j]) => {
        const p1 = projected[i];
        const p2 = projected[j];
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(0, 240, 255, 0.65)';
        ctx.shadowColor = '#00f0ff';
        ctx.shadowBlur = 8;
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      });

      // Draw glowing vertices
      projected.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.shadowColor = '#00f0ff';
        ctx.shadowBlur = 10;
        ctx.fill();
      });

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [active]);

  if (!active) return null;

  return (
    <div className="fixed bottom-24 right-80 z-30 pointer-events-none p-3 rounded-2xl glass-panel border border-cyan-400/30 flex flex-col items-center">
      <div className="text-[9px] font-mono tracking-widest text-cyan-300 uppercase mb-1">
        HOLO CUBE // 3D MATRIX
      </div>
      <canvas ref={canvasRef} width={160} height={160} className="block" />
    </div>
  );
};
