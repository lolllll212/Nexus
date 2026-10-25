import React from 'react';
import {
  Home,
  Share2,
  Telescope,
  GitBranch,
  Boxes,
  BarChart3,
  Bot,
  Radio,
  Settings2,
} from 'lucide-react';
import { WorkspaceRoute } from './shared';

interface WorkspaceNavRailProps {
  activeRoute: WorkspaceRoute;
  onRouteChange: (route: WorkspaceRoute) => void;
  onOpenIntegrations: () => void;
}

interface RailItem {
  id: WorkspaceRoute;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}

const RAIL_ITEMS: RailItem[] = [
  { id: 'HOME', label: 'Workspace Home', icon: Home },
  { id: 'GRAPH', label: 'Knowledge Graph', icon: Share2 },
  { id: 'RESEARCH', label: 'Deep Research Lab', icon: Telescope },
  { id: 'WORKFLOW', label: 'Workflow Canvas', icon: GitBranch },
  { id: 'ARCHITECTURE', label: 'Hexagonal Architecture', icon: Boxes },
  { id: 'ANALYTICS', label: 'Analytics Dashboard', icon: BarChart3 },
  { id: 'AGENTS', label: 'Agent Orchestration', icon: Bot },
];

/**
 * The NEXUS OS rail — thin, fixed, line-art icons. Every destination is an
 * internal light-workspace route (the legacy dark surfaces are not opened
 * from here). Integrations & settings stay one click away at the bottom.
 */
export const WorkspaceNavRail: React.FC<WorkspaceNavRailProps> = ({
  activeRoute,
  onRouteChange,
  onOpenIntegrations,
}) => {
  return (
    <nav className="fixed left-0 top-0 bottom-0 z-40 w-[72px] flex flex-col items-center bg-white/75 backdrop-blur-xl border-r border-slate-200/70 py-5 select-none">
      {/* Brand mark */}
      <button
        onClick={() => onRouteChange('HOME')}
        className="group relative w-11 h-11 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700 text-white flex items-center justify-center shadow-[0_8px_20px_-6px_rgba(15,23,42,0.5)] hover:shadow-[0_10px_26px_-6px_rgba(15,23,42,0.6)] transition-all cursor-pointer"
        title="NEXUS OS"
      >
        <span className="text-[15px] font-extrabold tracking-tight">N</span>
        <span className="absolute -right-0.5 -top-0.5 w-2.5 h-2.5 rounded-full bg-gradient-to-br from-cyan-400 to-violet-500 border-2 border-white" />
      </button>

      <div className="w-8 h-px bg-slate-200 my-4" />

      {/* Primary destinations — all internal to the light workspace */}
      <div className="flex flex-col items-center gap-1.5 flex-1 overflow-y-auto nxs-scroll">
        {RAIL_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeRoute === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onRouteChange(item.id)}
              className={`group relative w-11 h-11 rounded-2xl flex items-center justify-center transition-all duration-200 cursor-pointer ${
                isActive
                  ? 'bg-slate-900 text-white shadow-[0_8px_20px_-8px_rgba(15,23,42,0.55)]'
                  : 'text-slate-400 hover:text-slate-900 hover:bg-slate-100'
              }`}
              title={item.label}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon className="w-[19px] h-[19px]" strokeWidth={1.6} />
              {/* Active indicator bar */}
              <span
                className={`absolute -left-[14px] w-[3px] rounded-full bg-slate-900 transition-all duration-200 ${
                  isActive ? 'h-6 opacity-100' : 'h-2 opacity-0'
                }`}
              />
              {/* Hover tooltip */}
              <span className="pointer-events-none absolute left-[54px] whitespace-nowrap rounded-lg bg-slate-900 text-white text-[11px] font-medium px-2.5 py-1.5 opacity-0 translate-x-[-4px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 shadow-lg z-50">
                {item.label}
              </span>
            </button>
          );
        })}
      </div>

      <div className="w-8 h-px bg-slate-200 mb-4" />

      {/* Orchestration shortcuts */}
      <div className="flex flex-col items-center gap-1.5">
        <button
          onClick={onOpenIntegrations}
          className="group relative w-11 h-11 rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition-all duration-200 cursor-pointer"
          title="External Integrations"
          aria-label="External Integrations"
        >
          <Radio className="w-[19px] h-[19px]" strokeWidth={1.6} />
          <span className="pointer-events-none absolute left-[54px] whitespace-nowrap rounded-lg bg-slate-900 text-white text-[11px] font-medium px-2.5 py-1.5 opacity-0 translate-x-[-4px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 shadow-lg z-50">
            Integrations
          </span>
        </button>
        <button
          onClick={onOpenIntegrations}
          className="group relative w-11 h-11 rounded-2xl flex items-center justify-center text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition-all duration-200 cursor-pointer"
          title="System Settings"
          aria-label="System Settings"
        >
          <Settings2 className="w-[19px] h-[19px]" strokeWidth={1.6} />
          <span className="pointer-events-none absolute left-[54px] whitespace-nowrap rounded-lg bg-slate-900 text-white text-[11px] font-medium px-2.5 py-1.5 opacity-0 translate-x-[-4px] group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-150 shadow-lg z-50">
            Settings
          </span>
        </button>
      </div>
    </nav>
  );
};
