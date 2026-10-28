import { useCallback, useEffect, useRef, useState } from 'react';
import { nexusChatStream } from '../api';
import {
  FALLBACK_CATALOG,
  fetchModelCatalog,
  getStoredCapabilities,
  getStoredModelId,
  resolveSelectedModelId,
  saveCapabilities,
  saveStoredModelId,
} from '../data/modelCatalog';
import type {
  AgentStatus,
  ChatCapabilities,
  ChatExecutionMetadata,
  ChatQualityMetadata,
  ChatSessionRecord,
  ChatSessionSummary,
  ConversationalMessage,
  ModelCatalog,
  TaskDifficulty,
} from '../types';
import {
  appendChatMessages,
  clearChatSessions,
  conversationalToStored,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  newSessionId,
  renameChatSession,
  storedToConversational,
  summaryFromRecord,
  type HistorySource,
} from '../utils/chatHistory';
import {
  getVoicePreferences,
  saveVoicePreferences,
  speakWithStatus,
  stopAnySpeaking,
  type VoicePreferences,
} from '../utils/voiceManager';

export type StandaloneChatAction = 'GRAPH' | 'CODE' | 'RESEARCH';

interface QueuedChatCommand {
  id: string;
  query: string;
  actionType: StandaloneChatAction;
  userMessage: ConversationalMessage;
  model: string;
  capabilities: ChatCapabilities;
  sessionId: string;
}

function createChatWelcomeMessage(): ConversationalMessage {
  return {
    id: `chat-init-${Date.now()}`,
    role: 'assistant',
    content:
      'Hi, I’m Nexus Chat — the standalone Claude-style surface for practical answers, coding help, file work, repository building, research, tools, voice, and backend-saved history. What should we solve first?',
    timestamp: new Date().toLocaleTimeString(),
    toolsUsed: ['chat_ready'],
    difficulty: 'low',
    status: 'complete',
  };
}

function sanitizeThinking(text: string): string {
  if (!text) return '';
  let cleaned = text.replace(/\r\n/g, '\n');
  const finalAnswerMatch = cleaned.match(/final\s+answer\s*:/i);
  if (finalAnswerMatch?.index !== undefined) {
    cleaned = cleaned.slice(0, finalAnswerMatch.index);
  }
  return cleaned
    .split('\n')
    .filter((line) => !/TOOL_CALL\s*:/i.test(line))
    .join('\n')
    .replace(/^\s*(thought|thinking|reasoning)\s*:\s*/i, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function difficultyForQuery(query: string): TaskDifficulty {
  const q = query.toLowerCase();
  if (q.includes('security') || q.includes('critical') || q.includes('threat') || q.includes('hardening')) {
    return 'critical';
  }
  if (
    q.includes('code') ||
    q.includes('debug') ||
    q.includes('python') ||
    q.includes('typescript') ||
    q.includes('repository') ||
    q.includes('repo')
  ) {
    return 'high';
  }
  if (q.includes('research') || q.includes('compare') || q.includes('image') || q.includes('video')) {
    return 'medium';
  }
  return 'low';
}

export function useStandaloneChatController() {
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog>(FALLBACK_CATALOG);
  const [selectedModelId, setSelectedModelId] = useState<string>(() => getStoredModelId());
  const [capabilities, setCapabilities] = useState<ChatCapabilities>(() => getStoredCapabilities());
  const [voicePreferences, setVoicePreferences] = useState<VoicePreferences>(() => getVoicePreferences());
  const [agentStatus, setAgentStatus] = useState<AgentStatus>('idle');
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationalMessage[]>(() => [createChatWelcomeMessage()]);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [historySource, setHistorySource] = useState<HistorySource>('local');
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => newSessionId());
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [queuedCount, setQueuedCount] = useState(0);

  const commandQueueRef = useRef<QueuedChatCommand[]>([]);
  const isProcessingRef = useRef(false);
  const activeControllerRef = useRef<AbortController | null>(null);
  const speechGatesQueueRef = useRef(false);
  const selectedModelIdRef = useRef(selectedModelId);
  const capabilitiesRef = useRef(capabilities);
  const voicePreferencesRef = useRef(voicePreferences);
  const currentSessionIdRef = useRef(currentSessionId);
  const agentStatusRef = useRef(agentStatus);
  const stopSpeakingRef = useRef<() => void>(() => {});

  useEffect(() => {
    selectedModelIdRef.current = selectedModelId;
  }, [selectedModelId]);

  useEffect(() => {
    capabilitiesRef.current = capabilities;
  }, [capabilities]);

  useEffect(() => {
    voicePreferencesRef.current = voicePreferences;
  }, [voicePreferences]);

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    agentStatusRef.current = agentStatus;
    if (agentStatus !== 'speaking') setSpeakingMessageId(null);
  }, [agentStatus]);

  useEffect(
    () => () => {
      activeControllerRef.current?.abort();
      stopAnySpeaking();
    },
    [],
  );

  const handleModelChange = useCallback((modelId: string) => {
    const saved = saveStoredModelId(modelId);
    selectedModelIdRef.current = saved;
    setSelectedModelId(saved);
  }, []);

  const handleCapabilitiesChange = useCallback((next: ChatCapabilities) => {
    const saved = saveCapabilities(next);
    capabilitiesRef.current = saved;
    setCapabilities(saved);
    if (!saved.voiceReplies && agentStatusRef.current === 'speaking') {
      stopSpeakingRef.current();
    }
  }, []);

  const handleVoicePreferencesChange = useCallback((preferences: VoicePreferences) => {
    const saved = saveVoicePreferences(preferences);
    voicePreferencesRef.current = saved;
    setVoicePreferences(saved);
  }, []);

  const refreshHistory = useCallback(async (): Promise<void> => {
    setIsHistoryLoading(true);
    try {
      const result = await listChatSessions('', 100);
      setSessions(result.sessions);
      setHistorySource(result.source);
    } finally {
      setIsHistoryLoading(false);
    }
  }, []);

  const upsertSessionSummary = useCallback((record: ChatSessionRecord) => {
    const summary = summaryFromRecord(record);
    setSessions((prev) =>
      [summary, ...prev.filter((session) => session.id !== summary.id)].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      ),
    );
  }, []);

  const startFreshSession = useCallback((): string => {
    const sessionId = newSessionId();
    currentSessionIdRef.current = sessionId;
    setCurrentSessionId(sessionId);
    setMessages([createChatWelcomeMessage()]);
    setSpeakingMessageId(null);
    return sessionId;
  }, []);

  const prepareForSessionSwitch = useCallback((): boolean => {
    if (commandQueueRef.current.length > 0) return false;
    if (agentStatusRef.current === 'thinking' || agentStatusRef.current === 'listening') return false;
    if (isProcessingRef.current && !speechGatesQueueRef.current) return false;
    if (agentStatusRef.current === 'speaking') stopSpeakingRef.current();
    return !isProcessingRef.current;
  }, []);

  const handleNewChat = useCallback(async (): Promise<boolean> => {
    if (!prepareForSessionSwitch()) return false;
    startFreshSession();
    return true;
  }, [prepareForSessionSwitch, startFreshSession]);

  const handleOpenSession = useCallback(
    async (sessionId: string): Promise<boolean> => {
      if (sessionId === currentSessionIdRef.current && sessions.some((session) => session.id === sessionId)) {
        return true;
      }
      if (!prepareForSessionSwitch()) return false;

      setIsHistoryLoading(true);
      try {
        const result = await getChatSession(sessionId);
        if (!result.session) return false;
        setHistorySource(result.source);
        currentSessionIdRef.current = result.session.id;
        setCurrentSessionId(result.session.id);
        const restored = result.session.messages.map(storedToConversational);
        setMessages(restored.length > 0 ? restored : [createChatWelcomeMessage()]);
        setSpeakingMessageId(null);
        return true;
      } finally {
        setIsHistoryLoading(false);
      }
    },
    [prepareForSessionSwitch, sessions],
  );

  const handleRenameSession = useCallback(
    async (sessionId: string, title: string): Promise<boolean> => {
      const result = await renameChatSession(sessionId, title);
      if (!result.session) return false;
      setHistorySource(result.source);
      upsertSessionSummary(result.session);
      return true;
    },
    [upsertSessionSummary],
  );

  const handleDeleteSession = useCallback(
    async (sessionId: string): Promise<boolean> => {
      const deletingCurrent = sessionId === currentSessionIdRef.current;
      if (deletingCurrent && !prepareForSessionSwitch()) return false;

      const result = await deleteChatSession(sessionId);
      if (!result.deleted) return false;
      setHistorySource(result.source);
      setSessions((prev) => prev.filter((session) => session.id !== sessionId));
      if (deletingCurrent) startFreshSession();
      return true;
    },
    [prepareForSessionSwitch, startFreshSession],
  );

  const handleClearHistory = useCallback(async (): Promise<boolean> => {
    if (!prepareForSessionSwitch()) return false;
    const result = await clearChatSessions();
    setHistorySource(result.source);
    setSessions([]);
    startFreshSession();
    return true;
  }, [prepareForSessionSwitch, startFreshSession]);

  useEffect(() => {
    let cancelled = false;
    void fetchModelCatalog().then((catalog) => {
      if (cancelled) return;
      setModelCatalog(catalog);
      const resolved = resolveSelectedModelId(catalog, selectedModelIdRef.current);
      selectedModelIdRef.current = resolved;
      setSelectedModelId(resolved);
      saveStoredModelId(resolved);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const processNextCommand = useCallback(() => {
    if (commandQueueRef.current.length === 0) {
      isProcessingRef.current = false;
      activeControllerRef.current = null;
      setQueuedCount(0);
      setAgentStatus('idle');
      return;
    }

    const next = commandQueueRef.current.shift()!;
    setQueuedCount(commandQueueRef.current.length);
    const generationController = new AbortController();
    activeControllerRef.current = generationController;
    isProcessingRef.current = true;
    setAgentStatus('thinking');

    const diff = difficultyForQuery(next.query);
    const userMsg = next.userMessage;
    const assistantId = `ai-${next.id}`;
    const initialModelSource = next.model === 'auto' ? 'nexus-default' : 'nvidia-nim';

    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: 'assistant',
        content: 'Connecting to Nexus…',
        timestamp: new Date().toLocaleTimeString(),
        toolsUsed: [],
        difficulty: diff,
        model: next.model,
        modelSource: initialModelSource,
        thinking: '',
        status: 'streaming',
      },
    ]);

    void (async () => {
      let finalAnswer = '';
      let finalModel = next.model;
      let finalModelSource = initialModelSource;
      let thinkingTrace = '';
      let streamSucceeded = false;
      let generationStopped = false;
      let finalExecution: ChatExecutionMetadata | undefined;
      let finalQuality: ChatQualityMetadata | undefined;
      const toolsUsed = new Set<string>();

      try {
        let answerReceived = false;
        await nexusChatStream(
          next.query,
          next.actionType === 'CODE' ? 'coding' : 'general',
          (event) => {
            if (event.model) finalModel = event.model;
            if (event.model_source) finalModelSource = event.model_source;
            if (event.execution) finalExecution = event.execution;
            if (event.quality) finalQuality = event.quality;
            if (event.type === 'tool_call' && event.tool_id) toolsUsed.add(event.tool_id);

            if (event.type === 'metadata') {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? { ...item, execution: finalExecution, quality: finalQuality }
                    : item,
                ),
              );
            }

            if (event.type === 'thought' && next.capabilities.extendedThinking && event.content) {
              const piece = sanitizeThinking(event.content);
              if (piece) {
                if (!thinkingTrace || piece.startsWith(thinkingTrace)) {
                  thinkingTrace = piece;
                } else if (!thinkingTrace.includes(piece)) {
                  thinkingTrace = `${thinkingTrace}\n\n${piece}`;
                }
              }
            }

            if (
              event.type === 'start' ||
              event.type === 'thought' ||
              event.type === 'tool_call' ||
              event.type === 'quality_repair'
            ) {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? {
                        ...item,
                        content:
                          event.type === 'thought'
                            ? 'Nexus is reasoning…'
                            : event.type === 'quality_repair'
                              ? 'Nexus is verifying and improving the answer…'
                              : 'Nexus is working…',
                        toolsUsed: [...toolsUsed],
                        model: finalModel,
                        modelSource: finalModelSource,
                        thinking: thinkingTrace,
                        status: 'streaming',
                      }
                    : item,
                ),
              );
            }

            if (event.type === 'answer') {
              answerReceived = true;
              finalAnswer = event.content || '';
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === assistantId
                    ? {
                        ...item,
                        content: finalAnswer,
                        toolsUsed: [...toolsUsed],
                        model: finalModel,
                        modelSource: finalModelSource,
                        thinking: thinkingTrace,
                        status: 'streaming',
                      }
                    : item,
                ),
              );
            }
          },
          {
            model: next.model,
            effort: next.capabilities.effort,
            sessionId: next.capabilities.memory ? next.sessionId : undefined,
            extendedThinking: next.capabilities.extendedThinking,
            deepResearch: next.capabilities.deepResearch,
            artifacts: next.capabilities.artifacts,
            signal: generationController.signal,
          },
        );
        if (!answerReceived) throw new Error('Nexus stream ended without an answer.');
        streamSucceeded = true;
      } catch (error) {
        const aborted =
          generationController.signal.aborted ||
          (error instanceof DOMException && error.name === 'AbortError') ||
          (error instanceof Error && error.name === 'AbortError');
        generationStopped = aborted;

        if (aborted) {
          finalAnswer = finalAnswer.trim()
            ? `${finalAnswer.trim()}\n\n_Generation stopped._`
            : 'Generation stopped before an answer arrived.';
          setMessages((prev) =>
            prev.map((item) =>
              item.id === assistantId
                ? { ...item, content: finalAnswer, status: 'stopped', thinking: thinkingTrace }
                : item,
            ),
          );
        } else {
          const message = error instanceof Error ? error.message : 'Unknown stream error.';
          finalAnswer = '';
          setMessages((prev) =>
            prev.map((item) =>
              item.id === assistantId
                ? { ...item, content: `Nexus stream failed: ${message}`, status: 'error' }
                : item,
            ),
          );
        }
      } finally {
        if (activeControllerRef.current === generationController) {
          activeControllerRef.current = null;
        }
      }

      if (streamSucceeded) {
        setMessages((prev) =>
          prev.map((item) =>
            item.id === assistantId
              ? { ...item, status: 'complete', execution: finalExecution, quality: finalQuality }
              : item,
          ),
        );
      }

      if (streamSucceeded || generationStopped) {
        const finalAssistantMessage: ConversationalMessage = {
          id: assistantId,
          role: 'assistant',
          content: finalAnswer,
          timestamp: new Date().toLocaleTimeString(),
          toolsUsed: [...toolsUsed],
          difficulty: diff,
          model: finalModel,
          modelSource: finalModelSource,
          thinking: thinkingTrace,
          execution: finalExecution,
          quality: finalQuality,
          status: generationStopped ? 'stopped' : 'complete',
        };
        try {
          const historyResult = await appendChatMessages(
            next.sessionId,
            [conversationalToStored(userMsg), conversationalToStored(finalAssistantMessage)],
            { model: finalModel },
          );
          setHistorySource(historyResult.source);
          if (historyResult.session) upsertSessionSummary(historyResult.session);
        } catch {
          // History has a local fallback; never let persistence hide the answer.
        }
      }

      if (streamSucceeded && next.capabilities.voiceReplies && finalAnswer.trim()) {
        speechGatesQueueRef.current = true;
        setSpeakingMessageId(assistantId);
        let speechSettled = false;
        const finishSpeech = () => {
          if (speechSettled) return;
          speechSettled = true;
          speechGatesQueueRef.current = false;
          setSpeakingMessageId(null);
          processNextCommand();
        };
        const started = speakWithStatus(
          finalAnswer,
          setAgentStatus,
          finishSpeech,
          voicePreferencesRef.current,
        );
        if (!started) finishSpeech();
      } else {
        window.setTimeout(processNextCommand, 350);
      }
    })();
  }, [upsertSessionSummary]);

  const sendMessage = useCallback(
    (message: string, actionType: StandaloneChatAction = 'GRAPH') => {
      const cleanQuery = message.trim();
      if (!cleanQuery) return;

      const capabilitySnapshot: ChatCapabilities = {
        ...capabilitiesRef.current,
        deepResearch: capabilitiesRef.current.deepResearch || actionType === 'RESEARCH',
      };
      const commandId = `cmd-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      const userMessage: ConversationalMessage = {
        id: `usr-${commandId}`,
        role: 'user',
        content: cleanQuery,
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      commandQueueRef.current.push({
        id: commandId,
        query: cleanQuery,
        actionType,
        userMessage,
        model: selectedModelIdRef.current,
        capabilities: capabilitySnapshot,
        sessionId: currentSessionIdRef.current,
      });
      setQueuedCount(commandQueueRef.current.length);

      if (!isProcessingRef.current) processNextCommand();
    },
    [processNextCommand],
  );

  const stopGeneration = useCallback(() => {
    activeControllerRef.current?.abort();
  }, []);

  const stopSpeaking = useCallback(() => {
    const shouldResumeQueue = speechGatesQueueRef.current;
    speechGatesQueueRef.current = false;
    stopAnySpeaking();
    setSpeakingMessageId(null);
    setAgentStatus('idle');
    if (shouldResumeQueue) processNextCommand();
  }, [processNextCommand]);

  useEffect(() => {
    stopSpeakingRef.current = stopSpeaking;
  }, [stopSpeaking]);

  const speakMessage = useCallback(
    (message: ConversationalMessage) => {
      if (!message.content.trim()) return;
      const shouldResumeQueue = speechGatesQueueRef.current;
      setSpeakingMessageId(message.id);
      let speechSettled = false;
      const finishSpeech = () => {
        if (speechSettled) return;
        speechSettled = true;
        setSpeakingMessageId(null);
        if (shouldResumeQueue) {
          speechGatesQueueRef.current = false;
          processNextCommand();
        }
      };
      const started = speakWithStatus(
        message.content,
        setAgentStatus,
        finishSpeech,
        voicePreferencesRef.current,
      );
      if (!started) finishSpeech();
    },
    [processNextCommand],
  );

  return {
    messages,
    isStreaming: agentStatus === 'thinking',
    onSendMessage: sendMessage,
    onStopGeneration: stopGeneration,
    queuedCount,
    modelCatalog,
    selectedModelId,
    onModelChange: handleModelChange,
    capabilities,
    onCapabilitiesChange: handleCapabilitiesChange,
    voicePreferences,
    onVoicePreferencesChange: handleVoicePreferencesChange,
    agentStatus,
    onAgentStatusChange: setAgentStatus,
    speakingMessageId,
    onSpeakMessage: speakMessage,
    onStopSpeaking: stopSpeaking,
    sessions,
    historySource,
    currentSessionId,
    isHistoryLoading,
    onRefreshHistory: refreshHistory,
    onNewChat: handleNewChat,
    onOpenSession: handleOpenSession,
    onRenameSession: handleRenameSession,
    onDeleteSession: handleDeleteSession,
    onClearHistory: handleClearHistory,
  };
}
