import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import { ChatApp } from './chat/ChatApp';
import './index.css';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ChatErrorBoundary extends Component<Props, State> {
  declare props: Props;

  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error in Nexus Chat:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-[#f7f5ef] p-6 text-[#262624]">
          <div className="max-w-lg rounded-3xl border border-[#e4ddd0] bg-white/80 p-6 text-center shadow-[0_24px_70px_rgba(61,57,47,0.16)]">
            <h1 className="mb-2 text-xl font-bold">Nexus Chat hit a rendering error</h1>
            <p className="mb-5 text-sm leading-6 text-[#6f6a5f]">
              {this.state.error?.message || 'An unexpected error occurred while rendering the chat workspace.'}
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <button
                onClick={() => window.location.reload()}
                className="rounded-full bg-[#262624] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#34322e]"
              >
                Reload chat
              </button>
              <a
                href="/"
                className="rounded-full border border-[#d8d0bf] bg-white px-4 py-2 text-sm font-semibold text-[#262624] transition hover:bg-[#f1ecdf]"
              >
                Open Workplace OS
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ChatErrorBoundary>
      <ChatApp />
    </ChatErrorBoundary>
  </React.StrictMode>,
);
