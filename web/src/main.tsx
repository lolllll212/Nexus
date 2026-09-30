import React, { Component, ErrorInfo, ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './index.css';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error in AI Workshop OS:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-[#020408] text-cyan-300 font-mono p-6">
          <div className="p-6 rounded-xl border border-cyan-500/30 bg-slate-950/80 max-w-lg text-center shadow-[0_0_30px_rgba(0,240,255,0.2)]">
            <h1 className="text-xl font-bold text-cyan-400 mb-2">⚡ SYSTEM DIAGNOSTIC ALERT</h1>
            <p className="text-sm text-slate-300 mb-4">
              {this.state.error?.message || "An unexpected error occurred while rendering HUD components."}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-black font-semibold rounded text-sm transition-all"
            >
              Reinitialize System
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
