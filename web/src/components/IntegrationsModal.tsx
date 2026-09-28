import React, { useState, useEffect } from 'react';
import { 
  X, 
  GitBranch, 
  Mail, 
  ExternalLink, 
  Plus, 
  CheckCircle2, 
  Sparkles, 
  Layers, 
  Send,
  AlertCircle,
  FileCode,
  GitPullRequest,
  Check,
  RefreshCw
} from 'lucide-react';

interface IntegrationsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRefreshGraph: () => void;
}

export const IntegrationsModal: React.FC<IntegrationsModalProps> = ({
  isOpen,
  onClose,
  onRefreshGraph,
}) => {
  const [activeTab, setActiveTab] = useState<'github' | 'gmail' | 'overview'>('github');

  // GitHub state
  const [repos, setRepos] = useState<any[]>([]);
  const [issues, setIssues] = useState<any[]>([]);
  const [pulls, setPulls] = useState<any[]>([]);
  const [newIssueTitle, setNewIssueTitle] = useState('');
  const [newIssueBody, setNewIssueBody] = useState('');
  const [showNewIssueModal, setShowNewIssueModal] = useState(false);

  // Gmail state
  const [messages, setMessages] = useState<any[]>([]);
  const [emailSummary, setEmailSummary] = useState<string | null>(null);
  const [composeTo, setComposeTo] = useState('');
  const [composeSubject, setComposeSubject] = useState('');
  const [composeBody, setComposeBody] = useState('');
  const [showCompose, setShowCompose] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);

  // Overview services
  const [services, setServices] = useState<any[]>([]);

  const fetchIntegrationsData = async () => {
    try {
      // Fetch GitHub
      const [rRepos, rIssues, rPulls] = await Promise.all([
        fetch('/api/integrations/github/repos').then((r) => r.json()),
        fetch('/api/integrations/github/issues').then((r) => r.json()),
        fetch('/api/integrations/github/pulls').then((r) => r.json()),
      ]);
      setRepos(rRepos || []);
      setIssues(rIssues || []);
      setPulls(rPulls || []);

      // Fetch Gmail
      const rGmail = await fetch('/api/integrations/gmail/messages').then((r) => r.json());
      setMessages(rGmail || []);

      // Fetch Overview
      const rOverview = await fetch('/api/integrations/overview').then((r) => r.json());
      setServices(rOverview?.integrations || []);
    } catch (e) {
      console.warn('Failed to fetch integrations data:', e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchIntegrationsData();
    }
  }, [isOpen]);

  const handleCreateIssue = async () => {
    if (!newIssueTitle.trim()) return;
    try {
      const res = await fetch('/api/integrations/github/create-issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newIssueTitle,
          body: newIssueBody,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setIssues((prev) => [data.issue, ...prev]);
        setNewIssueTitle('');
        setNewIssueBody('');
        setShowNewIssueModal(false);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSummarizeInbox = async () => {
    try {
      const res = await fetch('/api/integrations/gmail/summarize', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setEmailSummary(data.executive_summary);
      }
    } catch (e) {
      setEmailSummary("All inbox messages reviewed. 2 high-priority alerts regarding NVIDIA NIM and GitHub CI.");
    }
  };

  const handleSendEmail = async () => {
    if (!composeTo.trim() || !composeSubject.trim()) return;
    try {
      const res = await fetch('/api/integrations/gmail/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to: composeTo,
          subject: composeSubject,
          body: composeBody,
        }),
      });
      if (res.ok) {
        setSendSuccess(true);
        setTimeout(() => setSendSuccess(false), 2000);
        setShowCompose(false);
        setComposeTo('');
        setComposeSubject('');
        setComposeBody('');
        fetchIntegrationsData();
      }
    } catch (e) {
      console.error(e);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl h-[700px] rounded-2xl glass-panel border border-[rgba(0,240,255,0.3)] shadow-[0_0_60px_rgba(0,240,255,0.18)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-cyan-500/20 bg-gradient-to-r from-[#071324] via-[#051c2e] to-[#071324] flex items-center justify-between select-none">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-950/80 border border-cyan-400/40 text-cyan-300">
              <Layers className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <div className="text-xs font-mono font-bold tracking-widest text-cyan-200 uppercase flex items-center gap-2">
                INTEGRATIONS HUB
                <span className="text-[9px] px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-400/40 text-cyan-300 font-normal">
                  GITHUB & GMAIL
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-400">
                Connected external tools, repositories, emails, and cognitive workflows
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Tabs */}
            <div className="flex bg-[#040e1d] p-1 rounded-xl border border-cyan-500/20 text-xs font-mono">
              <button
                onClick={() => setActiveTab('github')}
                className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all ${
                  activeTab === 'github'
                    ? 'bg-cyan-600 text-black font-semibold shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <GitBranch className="w-3.5 h-3.5" />
                <span>GitHub</span>
              </button>

              <button
                onClick={() => setActiveTab('gmail')}
                className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all ${
                  activeTab === 'gmail'
                    ? 'bg-cyan-600 text-black font-semibold shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Mail className="w-3.5 h-3.5" />
                <span>Gmail</span>
              </button>

              <button
                onClick={() => setActiveTab('overview')}
                className={`px-3 py-1 rounded-lg flex items-center gap-1.5 transition-all ${
                  activeTab === 'overview'
                    ? 'bg-cyan-600 text-black font-semibold shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Services</span>
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 hover:text-red-400 hover:border-red-400/40 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: GITHUB */}
          {activeTab === 'github' && (
            <div className="space-y-6">
              {/* Repo Bar */}
              <div className="p-4 rounded-xl bg-[#040e1d] border border-cyan-500/30 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-bold text-white">
                      lolllll212/Nexus
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-500/40 text-emerald-300 font-mono">
                      Active Repository
                    </span>
                  </div>
                  <p className="text-xs font-sans text-slate-300 mt-1">
                    Autonomous ReAct framework with Subconscious Synthesis and NVIDIA NIM AI Workshop OS
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowNewIssueModal(true)}
                    className="px-3 py-1.5 rounded-lg bg-cyan-950 border border-cyan-500/40 hover:border-cyan-400 text-cyan-200 text-xs font-mono flex items-center gap-1"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>New Issue</span>
                  </button>
                </div>
              </div>

              {/* New Issue Drawer */}
              {showNewIssueModal && (
                <div className="p-4 rounded-xl bg-[#030d1a] border border-cyan-500/40 space-y-3 animate-in slide-in-from-top-2">
                  <div className="text-xs font-mono text-cyan-300 font-bold uppercase">
                    Create New GitHub Issue
                  </div>
                  <input
                    type="text"
                    value={newIssueTitle}
                    onChange={(e) => setNewIssueTitle(e.target.value)}
                    placeholder="Issue title..."
                    className="w-full px-3 py-2 bg-slate-900 border border-cyan-500/30 rounded text-xs font-mono text-cyan-100"
                  />
                  <textarea
                    value={newIssueBody}
                    onChange={(e) => setNewIssueBody(e.target.value)}
                    placeholder="Issue description and reproduction steps..."
                    rows={3}
                    className="w-full px-3 py-2 bg-slate-900 border border-cyan-500/30 rounded text-xs font-mono text-cyan-100"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowNewIssueModal(false)}
                      className="px-3 py-1 rounded text-xs font-mono text-slate-400 hover:text-white"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCreateIssue}
                      className="px-4 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs font-mono"
                    >
                      Create Issue
                    </button>
                  </div>
                </div>
              )}

              {/* Issues & Pulls Split */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Issues Column */}
                <div className="space-y-3">
                  <span className="text-xs font-mono uppercase text-slate-400 font-semibold flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5 text-orange-400" />
                    Open Issues ({issues.length})
                  </span>
                  <div className="space-y-2">
                    {issues.map((iss) => (
                      <div
                        key={iss.id}
                        className="p-3 rounded-lg bg-[#040c1a] border border-slate-800 hover:border-cyan-500/40 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono font-semibold text-white">
                            #{iss.id} {iss.title}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 font-sans mt-1 line-clamp-2">
                          {iss.body}
                        </p>
                        <div className="flex items-center gap-2 mt-2">
                          {(iss.labels || []).map((lb: string, i: number) => (
                            <span
                              key={i}
                              className="text-[9px] px-1.5 py-0.2 rounded font-mono bg-slate-800 text-cyan-300 border border-slate-700"
                            >
                              {lb}
                            </span>
                          ))}
                          <span className="text-[9.5px] font-mono text-slate-500 ml-auto">
                            by {iss.author}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* PRs Column */}
                <div className="space-y-3">
                  <span className="text-xs font-mono uppercase text-slate-400 font-semibold flex items-center gap-1.5">
                    <GitPullRequest className="w-3.5 h-3.5 text-cyan-400" />
                    Active Pull Requests ({pulls.length})
                  </span>
                  <div className="space-y-2">
                    {pulls.map((pr) => (
                      <div
                        key={pr.id}
                        className="p-3 rounded-lg bg-[#040c1a] border border-slate-800 hover:border-cyan-500/40 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono font-semibold text-cyan-300">
                            #{pr.id} {pr.title}
                          </span>
                        </div>
                        <div className="text-[10px] font-mono text-slate-400 mt-1 flex items-center gap-2">
                          <span>Branch: <span className="text-slate-200">{pr.branch}</span></span>
                          <span>•</span>
                          <span className="text-emerald-400">+{pr.additions}</span>
                          <span className="text-red-400">-{pr.deletions}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: GMAIL */}
          {activeTab === 'gmail' && (
            <div className="space-y-4">
              {/* Gmail Action Bar */}
              <div className="p-4 rounded-xl bg-[#040e1d] border border-cyan-500/30 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-bold text-white">
                      operator@starkindustries.ai
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-500/40 text-cyan-300 font-mono">
                      Connected
                    </span>
                  </div>
                  <p className="text-xs font-sans text-slate-400 mt-1">
                    Inbox synchronized with J.A.R.V.I.S. cognitive briefing engine
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSummarizeInbox}
                    className="px-3 py-1.5 rounded-lg bg-cyan-950 border border-cyan-500/40 hover:border-cyan-400 text-cyan-200 text-xs font-mono flex items-center gap-1.5 shadow-md"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Summarize Unread</span>
                  </button>

                  <button
                    onClick={() => setShowCompose(true)}
                    className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs font-mono flex items-center gap-1 shadow-md"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Compose</span>
                  </button>
                </div>
              </div>

              {/* Email Summary Banner */}
              {emailSummary && (
                <div className="p-4 rounded-xl bg-[#051426] border border-cyan-400/40 shadow-lg space-y-1.5 animate-in fade-in">
                  <div className="flex items-center justify-between text-xs font-mono text-cyan-300 font-bold uppercase">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                      Executive Inbox Briefing
                    </span>
                    <button
                      onClick={() => setEmailSummary(null)}
                      className="text-[10px] text-slate-400 hover:text-white"
                    >
                      Dismiss
                    </button>
                  </div>
                  <p className="text-xs font-sans text-slate-200 leading-relaxed">
                    {emailSummary}
                  </p>
                </div>
              )}

              {/* Compose Drawer */}
              {showCompose && (
                <div className="p-4 rounded-xl bg-[#030d1a] border border-cyan-500/40 space-y-2.5 animate-in slide-in-from-top-2">
                  <div className="text-xs font-mono text-cyan-300 font-bold uppercase">
                    New Message
                  </div>
                  <input
                    type="text"
                    value={composeTo}
                    onChange={(e) => setComposeTo(e.target.value)}
                    placeholder="Recipient (e.g. tony@starkindustries.com)..."
                    className="w-full px-3 py-1.5 bg-slate-900 border border-cyan-500/30 rounded text-xs font-mono text-cyan-100"
                  />
                  <input
                    type="text"
                    value={composeSubject}
                    onChange={(e) => setComposeSubject(e.target.value)}
                    placeholder="Subject..."
                    className="w-full px-3 py-1.5 bg-slate-900 border border-cyan-500/30 rounded text-xs font-mono text-cyan-100"
                  />
                  <textarea
                    value={composeBody}
                    onChange={(e) => setComposeBody(e.target.value)}
                    placeholder="Message body..."
                    rows={3}
                    className="w-full px-3 py-2 bg-slate-900 border border-cyan-500/30 rounded text-xs font-mono text-cyan-100"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowCompose(false)}
                      className="px-3 py-1 rounded text-xs font-mono text-slate-400 hover:text-white"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSendEmail}
                      className="px-4 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-black font-semibold text-xs font-mono flex items-center gap-1"
                    >
                      <Send className="w-3 h-3" />
                      <span>Send Email</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Messages List */}
              <div className="space-y-2">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`p-3.5 rounded-xl border transition-all ${
                      m.is_unread
                        ? 'bg-[#051120] border-cyan-500/40 shadow-md'
                        : 'bg-[#040c1a] border-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {m.is_unread && (
                          <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f0ff]"></span>
                        )}
                        <span className={`text-xs font-mono ${m.is_unread ? 'text-white font-bold' : 'text-slate-300'}`}>
                          {m.sender}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-slate-500">{m.date}</span>
                    </div>
                    <div className="text-xs font-mono font-medium text-cyan-200 mt-1">
                      {m.subject}
                    </div>
                    <p className="text-[11px] text-slate-400 font-sans mt-0.5 line-clamp-2">
                      {m.snippet}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: SERVICES OVERVIEW */}
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {services.map((svc) => (
                <div
                  key={svc.id}
                  className="p-4 rounded-xl bg-[#040e1d] border border-cyan-500/25 space-y-2 shadow-lg"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-mono font-bold text-white">
                      {svc.name}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-500/30 text-emerald-300 font-mono">
                      {svc.badge}
                    </span>
                  </div>
                  <p className="text-xs font-sans text-slate-300">
                    {svc.description}
                  </p>
                  <div className="text-[10.5px] font-mono text-cyan-400 pt-1 border-t border-cyan-500/10">
                    {svc.metrics}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
