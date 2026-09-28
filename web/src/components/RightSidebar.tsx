import React from 'react';
import { Filter, Activity, Zap, Check } from 'lucide-react';
import { LegendItem, NodeGroup, SystemStates } from '../types';
import { JarvisHUD } from './JarvisHUD';

interface RightSidebarProps {
  legendItems: LegendItem[];
  activeFilter: NodeGroup | null;
  onToggleFilter: (group: NodeGroup) => void;
  systemStates: SystemStates;
  onToggleState: (stateKey: keyof SystemStates) => void;
  hasNimKey: boolean;
  onOpenJarvis: () => void;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  legendItems,
  activeFilter,
  onToggleFilter,
  systemStates,
  onToggleState,
  hasNimKey,
  onOpenJarvis,
}) => {
  const [telemetry, setTelemetry] = React.useState<{ uptime_seconds?: number; tools_count?: number } | null>(null);

  React.useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const res = await fetch('/api/system/telemetry');
        if (res.ok) {
          const data = await res.json();
          setTelemetry(data);
        }
      } catch (_) {}
    };
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 10000);
    return () => clearInterval(interval);
  }, []);

  const stateKeys: (keyof SystemStates)[] = [
    'ONLINE',
    'RING',
    'CUBE',
    'FACE',
    'EYES',
    'WATCH',
    'HOLO',
    'FOCUS',
  ];

  return (
    <aside className="w-72 h-full flex flex-col justify-between z-20 pointer-events-auto border-l border-[rgba(0,240,255,0.14)] glass-panel select-none overflow-y-auto">
      {/* 1. Filter Legend (Top Right) */}
      <div className="p-4 border-b border-[rgba(0,240,255,0.12)]">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-[10px] font-mono tracking-widest text-slate-400 uppercase font-semibold flex items-center gap-1.5">
            <Filter className="w-3 h-3 text-cyan-400" />
            Filter Legend
          </span>
          {activeFilter && (
            <button
              onClick={() => onToggleFilter(activeFilter)}
              className="text-[10px] text-cyan-400 hover:text-cyan-200 font-mono"
            >
              Reset
            </button>
          )}
        </div>

        <div className="space-y-1">
          {legendItems.map((item) => {
            const isSelected = activeFilter === item.id;
            const isDimmed = activeFilter !== null && !isSelected;
            return (
              <button
                key={item.id}
                onClick={() => onToggleFilter(item.id)}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all border ${
                  isSelected
                    ? 'bg-cyan-950/70 border-cyan-400 text-white shadow-[0_0_12px_rgba(0,240,255,0.25)]'
                    : isDimmed
                    ? 'opacity-40 border-transparent hover:opacity-80 text-slate-400'
                    : 'bg-slate-900/40 border-slate-800/80 hover:border-slate-700 text-slate-300 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0 transition-transform hover:scale-125"
                    style={{
                      backgroundColor: item.color,
                      boxShadow: isSelected ? `0 0 10px ${item.color}` : `0 0 4px ${item.color}`,
                    }}
                  />
                  <span className="truncate">{item.label}</span>
                </div>
                <span className={`text-[11px] font-semibold ${isSelected ? 'text-cyan-300' : 'text-slate-400'}`}>
                  {item.count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. J.A.R.V.I.S. HUD (Middle/Bottom Right) */}
      <div className="py-4 flex flex-col items-center justify-center relative">
        <JarvisHUD
          ringActive={systemStates.RING}
          statusText={systemStates.ONLINE ? (hasNimKey ? 'NIM ONLINE' : 'READY') : 'OFFLINE'}
          hasNimKey={hasNimKey}
          onClick={onOpenJarvis}
        />
        <div className="mt-1 text-[10px] font-mono text-cyan-400/70 uppercase tracking-widest flex items-center gap-1">
          <Zap className="w-2.5 h-2.5 text-cyan-400" />
          Click HUD to consult J.A.R.V.I.S.
        </div>
      </div>

      {/* 3. State Toggles (Bottom Right) */}
      <div className="p-4 border-t border-[rgba(0,240,255,0.12)] bg-[#030914]/80">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-mono tracking-widest text-slate-400 uppercase font-semibold flex items-center gap-1.5">
            <Activity className="w-3 h-3 text-cyan-400" />
            System States
          </span>
          <span className="text-[9px] font-mono text-cyan-500/80">
            {telemetry?.uptime_seconds
              ? `${Math.floor(telemetry.uptime_seconds)}s · ${telemetry.tools_count || 20} TOOLS`
              : 'TELEMETRY'}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-1.5">
          {stateKeys.map((key) => {
            const isActive = systemStates[key];
            return (
              <button
                key={key}
                onClick={() => onToggleState(key)}
                className={`flex items-center justify-between px-2.5 py-1.5 rounded-md text-[11px] font-mono transition-all border ${
                  isActive
                    ? 'bg-cyan-950/60 border-cyan-400/60 text-cyan-100 shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                    : 'bg-slate-900/50 border-slate-800/80 text-slate-400 hover:text-slate-300 hover:border-slate-700'
                }`}
              >
                <span className="tracking-wider">{key}</span>
                <div
                  className={`w-2 h-2 rounded-full transition-all ${
                    isActive
                      ? 'bg-cyan-400 shadow-[0_0_8px_#00f0ff]'
                      : 'bg-slate-700'
                  }`}
                />
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
};
