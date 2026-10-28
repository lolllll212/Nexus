/**
 * NEXUS OS — workspace controller.
 *
 * Binds Screen 1 (dashboard) and Screen 2 (floating cockpit) to the FastAPI
 * cockpit router (`/api/workspace/*`). The console streams SSE frames and maps
 * server state onto the app's `data-state`, which is what drives the dual-layer
 * cyan/violet aura. Everything is progressive: if the API is unreachable the
 * canvas still renders with the local snapshot and the console reports offline.
 */

import { bootRobot } from './robot.js';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const ROUTE_COLORS = {
  deep_research: '#22d3ee',
  image: '#8b5cf6',
  search: '#38bdf8',
  music: '#ff7a18',
};
const ROUTE_ICONS = {
  deep_research: '#i-deep',
  image: '#i-image',
  search: '#i-search',
  music: '#i-music',
};
const PHASE_COPY = {
  thinking: 'Cooking up a plan…',
  streaming: 'Streaming the answer…',
  done: 'Hey there! Need a boost?',
  error: 'That one slipped. Try again?',
  idle: 'Hey there! Need a boost?',
};

const app = $('#app');
const consoleForm = $('#console');
const promptEl = $('#prompt');
const sendBtn = $('#send-btn');
const runPanel = $('#run-panel');
const runSteps = $('#run-steps');
const runAnswer = $('#run-answer');
const runArtifacts = $('#run-artifacts');
const runArtifactsLead = $('#run-artifacts-lead');
const runMeta = $('#run-meta');
const runEngine = $('#run-engine');
const runScroll = $('#run-scroll');
const routeHint = $('#route-hint');
const toastEl = $('#toast');
const runLatestBtn = $('#run-latest');
const spacesSearch = $('#spaces-search');
const spacesPriority = $('#spaces-priority');
const spacesGrid = $('#spaces-grid');
const spacesState = $('#spaces-state');
const spacesSummary = $('#spaces-summary');
const spacesCount = $('#spaces-count');
const WORKSPACE_DRAFT_KEY = 'nexus-legacy-workspace-draft';

const state = {
  route: 'deep_research',
  bootstrap: null,
  run: null,
  controller: null,
  streaming: false,
  answer: '',
  renderQueued: false,
  stickToBottom: true,
  spaces: [],
  spacesController: null,
  robot: null,
  startedAt: 0,
};

/* ── formatting helpers ─────────────────────────────────────────────────── */

const fmt = new Intl.NumberFormat('en-IN');

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]
  ));
}

function safeArtifactUrl(value) {
  const url = String(value || '').trim();
  if (url.startsWith('/') || url.startsWith('./') || url.startsWith('../')) return url;
  if (/^(https?:|data:image\/|data:audio\/)/i.test(url)) return url;
  return '#';
}

function inline(text) {
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])_([^_]+)_/g, '$1<em>$2</em>');
}

/** Deliberately tiny markdown: paragraphs, ordered/unordered lists, bold/italic/code. */
function renderMarkdown(raw) {
  const lines = escapeHtml(raw).split('\n');
  const out = [];
  let list = null;

  const closeList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      return;
    }
    const ordered = trimmed.match(/^(\d+)\.\s+(.*)$/);
    const bullet = trimmed.match(/^[-*]\s+(.*)$/);
    if (ordered || bullet) {
      const kind = ordered ? 'ol' : 'ul';
      if (list !== kind) {
        closeList();
        out.push(`<${kind}>`);
        list = kind;
      }
      out.push(`<li>${inline((ordered ? ordered[2] : bullet[1]).replace(/\s{2}$/, ''))}</li>`);
      return;
    }
    closeList();
    const hardBreak = /\s{2,}$/.test(line);
    out.push(`<p>${inline(trimmed)}${hardBreak ? '<br>' : ''}</p>`);
  });
  closeList();
  return out.join('');
}

function toast(message, tone = 'default') {
  toastEl.textContent = message;
  toastEl.dataset.tone = tone;
  toastEl.classList.add('is-visible');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toastEl.classList.remove('is-visible'), 3200);
}

function setState(next, label) {
  app.dataset.state = next;
  const text = label || ({ thinking: 'THINKING', streaming: 'STREAMING', done: 'READY', error: 'ERROR' }[next] || 'READY');
  $('#console-state-text').textContent = text;
  $('#companion-state').textContent = next === 'thinking' ? 'thinking' : next === 'streaming' ? 'streaming' : 'listening';
  const bubble = $('#bubble-text');
  if (bubble) bubble.textContent = PHASE_COPY[next] || PHASE_COPY.idle;
}

function setRoute(route, { announce = false } = {}) {
  if (!ROUTE_COLORS[route]) return;
  state.route = route;
  app.dataset.route = route;
  app.style.setProperty('--route', ROUTE_COLORS[route]);
  $$('.nx-chip').forEach((chip) => chip.setAttribute('aria-pressed', String(chip.dataset.route === route)));
  const meta = state.bootstrap?.routes?.find((item) => item.id === route);
  routeHint.textContent = meta?.hint || '';
  $('#console-thread').textContent = `New thread · ${meta?.label || 'NEXUS'}`;
  const badge = $('#run-route-badge use');
  if (badge) badge.setAttribute('href', ROUTE_ICONS[route]);
  if (announce) toast(`${meta?.label || 'Route'} armed — describe what you need.`);
}

function updateUsage(usage) {
  if (!usage) return;
  const left = usage.credits_left ?? 0;
  $('#console-credit').textContent = `${fmt.format(left)} credits`;
  $('#stat-credits').textContent = fmt.format(left);
  $('#stat-runs').textContent = String(6 + (usage.runs_today || 0));
}

/* ── audio artifact ─────────────────────────────────────────────────────── */

function wireAudio(card) {
  const audio = $('audio', card);
  const button = $('.nx-audio__play', card);
  const wave = $('.nx-audio__wave', card);
  const time = $('.nx-audio__time', card);
  const bars = $$('i', wave);
  if (!audio || !button) return;

  const clock = (value) => {
    if (!Number.isFinite(value)) return '0:00';
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  };
  const paint = () => {
    const duration = audio.duration || 8;
    const ratio = duration ? audio.currentTime / duration : 0;
    bars.forEach((bar, index) => bar.classList.toggle('is-played', index / bars.length <= ratio));
    time.textContent = `${clock(audio.currentTime)} / ${clock(duration)}`;
  };
  const toggle = () => {
    if (audio.paused) {
      audio.play().catch(() => toast('Playback blocked by the browser — press play again.'));
    } else {
      audio.pause();
    }
  };
  button.addEventListener('click', toggle);
  wave.addEventListener('click', (event) => {
    const rect = wave.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    if (Number.isFinite(audio.duration)) audio.currentTime = ratio * audio.duration;
    paint();
  });
  audio.addEventListener('play', () => { button.innerHTML = '<svg class="nx-icon"><use href="#i-pause"/></svg>'; });
  audio.addEventListener('pause', () => { button.innerHTML = '<svg class="nx-icon"><use href="#i-play"/></svg>'; });
  audio.addEventListener('timeupdate', paint);
  audio.addEventListener('loadedmetadata', paint);
  audio.addEventListener('ended', () => { audio.currentTime = 0; paint(); });
  paint();
}

/* ── artifacts ──────────────────────────────────────────────────────────── */

function renderArtifact(artifact) {
  const card = document.createElement('div');
  const safeUrl = escapeHtml(safeArtifactUrl(artifact.url));
  card.className = 'nx-art';

  if (artifact.kind === 'image') {
    card.classList.add('nx-art--image');
    card.innerHTML = `
      <a class="nx-art__zoom" href="${safeUrl}" target="_blank" rel="noopener"
         aria-label="Open the full-size poster">
        <img src="${safeUrl}" alt="${escapeHtml(artifact.title)}" loading="lazy">
      </a>
      <div class="nx-art__bar">
        <span class="nx-art__cap">${escapeHtml(artifact.title)}<span>${escapeHtml(artifact.subtitle || '')}</span></span>
        <a class="nx-art__dl nx-art__dl--light" href="${safeUrl}" download="${escapeHtml(artifact.download || 'nexus-poster.svg')}" aria-label="Download poster">
          <svg class="nx-icon"><use href="#i-download"/></svg>
        </a>
      </div>`;
  } else if (artifact.kind === 'asset') {
    card.classList.add('nx-art--source');
    card.innerHTML = `
      <i class="nx-kind"><svg class="nx-icon"><use href="#i-image"/></svg></i>
      <div class="nx-art__src">
        <strong>${escapeHtml(artifact.title)}</strong>
        <p>${escapeHtml(artifact.subtitle || '')}</p>
      </div>
      <a class="nx-art__dl" style="background:#f1f5f9;border-color:rgba(11,15,25,.08);color:#0b0f19"
         href="${safeUrl}" download="${escapeHtml(artifact.download || 'nexus-asset.jpg')}" aria-label="Open reference">
        <svg class="nx-icon"><use href="#i-download"/></svg>
      </a>`;
  } else if (artifact.kind === 'audio') {
    card.classList.add('nx-art--audio');
    const seed = [...(artifact.url || '')].reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) % 9973, 7);
    const bars = Array.from({ length: 42 }, (_, index) => {
      const height = 24 + ((Math.sin(index * 0.55 + seed * 0.017) + 1) / 2) * 62;
      return `<i style="--h:${height.toFixed(0)}%"></i>`;
    }).join('');
    card.innerHTML = `
      <button class="nx-audio__play" type="button" aria-label="Play rendered stem">
        <svg class="nx-icon"><use href="#i-play"/></svg>
      </button>
      <div class="nx-audio__body">
        <div class="nx-audio__top"><strong>${escapeHtml(artifact.title)}</strong><span class="nx-audio__time">0:00 / 0:08</span></div>
        <div class="nx-audio__wave" role="slider" tabindex="0" aria-label="Seek" aria-valuemin="0" aria-valuemax="8">${bars}</div>
      </div>
      <a class="nx-art__dl" style="background:#f1f5f9;border-color:rgba(11,15,25,.08);color:#0b0f19"
         href="${safeUrl}" download="${escapeHtml(artifact.download || 'nexus-stem.wav')}" aria-label="Download stem">
        <svg class="nx-icon"><use href="#i-download"/></svg>
      </a>
      <audio src="${safeUrl}" preload="metadata" hidden></audio>`;
  } else if (artifact.kind === 'source') {
    card.classList.add('nx-art--source');
    card.innerHTML = `
      <i class="nx-kind"><svg class="nx-icon"><use href="#i-layers"/></svg></i>
      <div class="nx-art__src">
        <strong>${escapeHtml(artifact.title)}</strong>
        <p>${escapeHtml(artifact.snippet || '')}</p>
        <code>${escapeHtml(artifact.subtitle || '')}</code>
      </div>
      <span class="nx-art__score">${artifact.match ? `${escapeHtml(String(artifact.match))}%` : ''}</span>`;
  } else {
    card.classList.add('nx-art--note');
    card.innerHTML = `
      <svg class="nx-icon"><use href="#i-sparkle"/></svg>
      <div><strong>${escapeHtml(artifact.title)}</strong> — ${escapeHtml(artifact.subtitle || '')}</div>`;
  }

  const lead = artifact.kind === 'image' || artifact.kind === 'audio';
  (lead ? runArtifactsLead : runArtifacts).appendChild(card);
  if (artifact.kind === 'audio') wireAudio(card);
  if (artifact.kind === 'image') {
    const img = $('img', card);
    img?.addEventListener('error', () => {
      card.innerHTML = `<div class="nx-art--note" style="border:0">Poster preview unavailable — download the SVG instead.</div>`;
    });
  }
}

/* ── run surface ────────────────────────────────────────────────────────── */

function openRunPanel(run, plan) {
  runPanel.hidden = false;
  app.dataset.panel = 'open';
  $('#run-prompt').textContent = run.prompt;
  $('#run-route-label').textContent = run.route_label || 'NEXUS';
  $('#run-route-badge use').setAttribute('href', ROUTE_ICONS[run.route] || '#i-deep');
  runEngine.textContent = 'queued';
  runEngine.dataset.engine = '';
  runMeta.textContent = 'opening stream…';
  runAnswer.innerHTML = '<div class="nx-skeleton"><i></i><i></i><i></i></div>';
  runArtifacts.innerHTML = '';
  runArtifactsLead.innerHTML = '';
  runSteps.innerHTML = (plan || []).map((step) => (
    `<li data-step="${escapeHtml(step.id)}">${escapeHtml(step.title)}</li>`
  )).join('');
  state.answer = '';
  state.stickToBottom = true;
  if (runLatestBtn) runLatestBtn.hidden = true;
  runScroll.scrollTop = 0;
}

function renderAnswer(ready = false) {
  state.renderQueued = false;
  runAnswer.innerHTML = state.answer ? renderMarkdown(state.answer) : '';
  runAnswer.classList.toggle('is-typing', state.streaming && !ready);
  if (state.stickToBottom) runScroll.scrollTop = runScroll.scrollHeight;
}

function scheduleAnswer() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  requestAnimationFrame(() => renderAnswer());
}

function markStep(id, status, note) {
  const el = runSteps.querySelector(`[data-step="${id}"]`);
  if (!el) return;
  el.classList.toggle('is-running', status === 'running');
  el.classList.toggle('is-done', status === 'done');
  if (note) {
    let badge = $('.nx-step__note', el);
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'nx-step__note';
      el.appendChild(badge);
    }
    badge.textContent = note;
  }
}

function finishRun(run, failed = false) {
  state.streaming = false;
  state.controller = null;
  sendBtn.setAttribute('aria-label', 'Send to NEXUS');
  runAnswer.classList.remove('is-typing');
  renderAnswer(true);
  if (failed) {
    setState('error');
    runMeta.textContent = 'stream interrupted';
    return;
  }
  setState('done');
  $('#run-rerun').disabled = false;
  state.stickToBottom = false;
  if (runLatestBtn) runLatestBtn.hidden = runScroll.scrollHeight <= runScroll.clientHeight + 48;
  runScroll.scrollTo({ top: 0, behavior: 'smooth' });
  if (run) {
    const seconds = ((run.duration_ms || 0) / 1000).toFixed(1);
    runMeta.textContent = `complete · ${seconds}s · ${run.credits || 0} credits`;
  }
}

/* ── SSE ────────────────────────────────────────────────────────────────── */

async function streamRun(runId, registry, signal) {
  const response = await fetch(`/api/workspace/runs/${runId}/stream`, {
    headers: { Accept: 'text/event-stream' },
    signal,
    cache: 'no-store',
  });
  if (!response.ok || !response.body) {
    throw new Error(`stream failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatch = (frame) => {
    let event = 'message';
    let data = '';
    frame.split('\n').forEach((line) => {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    });
    if (!data) return;
    const handler = registry[event];
    if (typeof handler !== 'function') return;
    try {
      handler(JSON.parse(data));
    } catch (error) {
      console.warn('[nexus] bad SSE frame', frame, error);
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf('\n\n');
    while (split >= 0) {
      const frame = buffer.slice(0, split).trim();
      buffer = buffer.slice(split + 2);
      if (frame) dispatch(frame);
      split = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim()) dispatch(buffer.trim());
}

const handlers = {
  state(frame) {
    const status = frame.status || 'thinking';
    if (status === 'cancelled') {
      state.streaming = false;
      setState('idle', 'CANCELLED');
      runMeta.textContent = 'stopped by operator';
      runAnswer.classList.remove('is-typing');
    } else {
      setState(status, frame.label);
      runEngine.textContent = status;
      runMeta.textContent = status === 'streaming' ? 'streaming tokens…' : 'planning the run…';
    }
  },
  plan(frame) {
    runSteps.innerHTML = (frame.steps || []).map((step) => (
      `<li data-step="${escapeHtml(step.id)}">${escapeHtml(step.title)}</li>`
    )).join('');
  },
  step(frame) { markStep(frame.id, frame.status, frame.note); },
  delta(frame) {
    state.answer += frame.text || '';
    scheduleAnswer();
    runMeta.textContent = `${fmt.format(state.answer.length)} chars streamed`;
  },
  artifact(frame) { if (frame.artifact) renderArtifact(frame.artifact); },
  usage(frame) { updateUsage(frame); },
  meta(frame) {
    runEngine.textContent = frame.engine || 'local';
    runEngine.dataset.engine = frame.engine || '';
    if (frame.note) runMeta.textContent = frame.note;
  },
  error(frame) {
    toast(frame.message || 'The stream hit an error.', 'error');
    setState('error');
  },
  done(frame) {
    if (frame.run) state.run = { ...state.run, ...frame.run };
    finishRun(state.run);
  },
};

/* ── submit / cancel ────────────────────────────────────────────────────── */

async function submit(promptOverride) {
  if (state.streaming) {
    cancelRun();
    return;
  }
  const prompt = (promptOverride ?? promptEl.value).trim();
  if (!prompt) {
    promptEl.focus();
    toast('Give the cockpit something to work with.');
    return;
  }
  if (promptOverride) promptEl.value = promptOverride;
  try { sessionStorage.setItem(WORKSPACE_DRAFT_KEY, promptEl.value); } catch { /* storage unavailable */ }
  autosize();

  state.streaming = true;
  state.startedAt = performance.now();
  state.controller = new AbortController();
  sendBtn.setAttribute('aria-label', 'Stop the run');
  setState('thinking');
  $('#run-rerun').disabled = true;
  state.robot?.react('talk', 2600);

  try {
    const response = await fetch('/api/workspace/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, route: state.route }),
      signal: state.controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      state.streaming = false;
      state.controller = null;
      setState('idle');
      if (response.status === 402) {
        toast('Credit ceiling reached — this run was capped by the plan limit.', 'error');
      } else {
        toast(payload?.error || `Could not open a run (${response.status}).`, 'error');
      }
      return;
    }
    state.run = payload.run;
    openRunPanel(payload.run, payload.plan);
    await streamRun(payload.run.id, handlers, state.controller.signal);
    if (state.streaming) finishRun(state.run, true);
  } catch (error) {
    if (error?.name === 'AbortError') {
      state.streaming = false;
      state.controller = null;
      setState('idle', 'STOPPED');
      runMeta.textContent = 'stopped by operator';
      toast('Run stopped.');
      return;
    }
    state.streaming = false;
    state.controller = null;
    setState('error');
    runMeta.textContent = 'cockpit API unreachable';
    toast('Cockpit API unreachable — is the FastAPI server running?', 'error');
  }
}

async function cancelRun() {
  if (!state.streaming) return;
  const runId = state.run?.id;
  state.controller?.abort();
  setState('idle', 'STOPPED');
  if (runId) {
    fetch(`/api/workspace/runs/${runId}/cancel`, { method: 'POST' }).catch(() => {});
  }
}

function autosize() {
  promptEl.style.height = 'auto';
  promptEl.style.height = `${Math.min(promptEl.scrollHeight, 132)}px`;
}

/* ── Platform Spaces ────────────────────────────────────────────────────── */

function makeTextElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = String(text ?? '');
  return element;
}

function renderSpaces(payload) {
  if (!spacesGrid || !spacesState || !spacesSummary || !spacesCount) return;
  const spaces = Array.isArray(payload?.spaces) ? payload.spaces : [];
  const summary = payload?.summary || {};
  state.spaces = spaces;

  if (spacesPriority && Array.isArray(payload?.priorities)) {
    const current = spacesPriority.value;
    const options = [makeTextElement('option', '', 'All priorities')];
    options[0].value = '';
    payload.priorities.forEach((priority) => {
      const option = makeTextElement('option', '', priority);
      option.value = String(priority);
      options.push(option);
    });
    spacesPriority.replaceChildren(...options);
    spacesPriority.value = payload.priorities.includes(current) ? current : '';
  }

  const generated = payload?.generated_at ? new Date(payload.generated_at) : null;
  const generatedLabel = generated && Number.isFinite(generated.getTime())
    ? generated.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short',
      })
    : 'time unavailable';
  spacesCount.textContent = `${spaces.length} shown · ${summary.landed ?? 0}/${summary.total ?? spaces.length} landed`;
  spacesSummary.replaceChildren(
    makeTextElement('span', '', `${summary.landed ?? 0} landed`),
    makeTextElement('span', '', `${summary.pending ?? 0} pending`),
    makeTextElement('span', '', `Updated ${generatedLabel} IST`),
    makeTextElement('span', '', 'Shared catalog'),
  );

  if (!spaces.length) {
    spacesGrid.replaceChildren();
    spacesGrid.hidden = true;
    spacesState.hidden = false;
    spacesState.textContent = 'No platform spaces match this search. Try a name, priority, runtime note, or evidence path.';
    return;
  }

  const cards = spaces.map((space) => {
    const card = document.createElement('article');
    card.className = 'nx-space-card';
    const head = document.createElement('div');
    head.className = 'nx-space-card__head';
    head.appendChild(makeTextElement('span', 'nx-space-card__id', String(space.id ?? '?').padStart(2, '0')));
    head.appendChild(makeTextElement('h4', '', space.name || 'Untitled space'));
    const badges = document.createElement('div');
    badges.className = 'nx-space-card__badges';
    badges.appendChild(makeTextElement('span', 'nx-space-badge nx-space-badge--priority', space.priority || '—'));
    badges.appendChild(makeTextElement('span', 'nx-space-badge', space.status || 'unknown'));
    head.appendChild(badges);
    card.appendChild(head);
    card.appendChild(makeTextElement('p', '', space.summary || ''));
    if (space.runtime_note) {
      card.appendChild(makeTextElement('p', 'nx-space-card__note', space.runtime_note));
    }
    const evidence = document.createElement('div');
    evidence.className = 'nx-space-card__evidence';
    (Array.isArray(space.evidence) ? space.evidence : []).forEach((path) => {
      const code = makeTextElement('code', '', path);
      code.title = String(path);
      evidence.appendChild(code);
    });
    if (evidence.childNodes.length) card.appendChild(evidence);
    return card;
  });

  spacesGrid.replaceChildren(...cards);
  spacesGrid.hidden = false;
  spacesState.hidden = true;
}

async function loadSpaces() {
  if (!spacesGrid || !spacesState) return;
  state.spacesController?.abort();
  const controller = new AbortController();
  state.spacesController = controller;
  const refresh = $('#spaces-refresh');
  if (refresh) refresh.disabled = true;
  spacesState.hidden = false;
  spacesState.textContent = 'Loading the shared platform catalog…';

  const params = new URLSearchParams();
  const query = spacesSearch?.value.trim() || '';
  const priority = spacesPriority?.value || '';
  if (query) params.set('q', query);
  if (priority) params.set('priority', priority);
  const suffix = params.toString() ? `?${params.toString()}` : '';

  try {
    const response = await fetch(`/api/workspace/spaces${suffix}`, {
      cache: 'no-store',
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.error || `spaces failed (${response.status})`);
    renderSpaces(payload);
  } catch (error) {
    if (error?.name === 'AbortError') return;
    spacesGrid.hidden = true;
    spacesState.hidden = false;
    spacesState.textContent = 'Platform Spaces could not load. Check that the workspace API is running, then refresh.';
    spacesCount.textContent = 'Unavailable';
    spacesSummary?.replaceChildren(makeTextElement('span', '', 'Catalog unavailable'));
  } finally {
    if (state.spacesController === controller) {
      state.spacesController = null;
      if (refresh) refresh.disabled = false;
    }
  }
}

function wireSpaces() {
  let timer = null;
  spacesSearch?.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(loadSpaces, 160);
  });
  spacesPriority?.addEventListener('change', loadSpaces);
  $('#spaces-refresh')?.addEventListener('click', loadSpaces);
}

/* ── bootstrap ──────────────────────────────────────────────────────────── */

function renderWeek() {
  const now = new Date();
  const monday = new Date(now);
  const weekday = (now.getDay() + 6) % 7;
  monday.setDate(now.getDate() - weekday);
  const cells = $$('.nx-week__day');
  cells.forEach((cell, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    $('i', cell).textContent = ['M', 'T', 'W', 'T', 'F', 'S', 'S'][index];
    $('b', cell).textContent = String(date.getDate());
    cell.classList.toggle('is-today', date.toDateString() === now.toDateString());
    cell.classList.toggle('is-dim', index > 4);
  });
  const label = now.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
  $('#runway-date').textContent = label;
  $('#hero-session').textContent = `${now.toLocaleDateString('en-IN', { weekday: 'long' })} · Session ${String(now.getDate()).padStart(2, '0')}`;
}

function applyBootstrap(data) {
  state.bootstrap = data;
  if (data.user) {
    $('#avatar-initials').textContent = data.user.initials || 'NX';
    if (data.user.plan_label) $('#plan-pill').textContent = data.user.plan_label;
    if (data.user.workspace) $('#workspace-name').textContent = data.user.workspace;
  }
  if (data.greeting) {
    $('#bubble-text').textContent = data.greeting.bubble || 'Hey there! Need a boost?';
    if (data.greeting.subtitle) $('#hero-subtitle').textContent = data.greeting.subtitle;
    const ideas = $('.nx-ideas');
    if (ideas && data.suggestions?.length) {
      ideas.innerHTML = data.suggestions.slice(0, 3).map((item) => `
        <button class="nx-idea" type="button" data-route="${escapeHtml(item.route)}" data-prompt="${escapeHtml(item.prompt)}">
          ${escapeHtml(shortLabel(item.route))}
        </button>`).join('');
      wireIdeas();
    }
  }
  if (data.engine) {
    $('#hero-engine').textContent = data.engine.label || 'Grounding engine · local';
    $('#footnote-engine').textContent = data.engine.label || 'Grounding engine · local';
  }
  if (data.knowledge) $('#stat-knowledge').textContent = fmt.format(data.knowledge.passages || 0);
  updateUsage(data.usage);
  setRoute(state.route);

  if (data.features) {
    const [fast, team, plan] = data.features;
    if (fast) {
      $('#fast-metric').textContent = fast.metric;
      $('#fast-trend').textContent = fast.trend;
      const arc = $('#fast-arc');
      const progress = fast.progress ?? 0.6;
      arc.setAttribute('stroke-dashoffset', String(Math.round(295 * (1 - progress))));
      $('#fast-pct').textContent = `${Math.round(progress * 100)}%`;
      $('#fast-items').innerHTML = (fast.items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    }
    if (team) {
      $('#team-metric').textContent = team.metric;
      $('#team-trend').textContent = team.trend;
    }
    if (plan) {
      $('#plan-metric').textContent = plan.metric;
      $('#plan-trend').textContent = plan.trend;
    }
  }

  if (data.activity?.length) {
    const icons = {
      research: ['#i-deep', 'nx-kind--research'], image: ['#i-image', 'nx-kind--image'],
      music: ['#i-music', 'nx-kind--music'], search: ['#i-search', 'nx-kind--search'],
    };
    $('#activity-list').innerHTML = data.activity.map((item) => {
      const [icon, klass] = icons[item.kind] || icons.search;
      return `<li>
        <i class="nx-kind ${klass}"><svg class="nx-icon"><use href="${icon}"/></svg></i>
        <div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p></div>
        <time>${escapeHtml(item.ago)}</time>
      </li>`;
    }).join('');
  }
}

function shortLabel(route) {
  if (route === 'deep_research') return 'Quantum, simply';
  if (route === 'image') return 'Poster for launch';
  if (route === 'music') return 'Focus loop';
  return 'Sandbox defaults';
}

async function bootstrap() {
  try {
    const response = await fetch('/api/workspace/bootstrap', { cache: 'no-store' });
    if (!response.ok) throw new Error(String(response.status));
    applyBootstrap(await response.json());
  } catch (error) {
    console.warn('[nexus] bootstrap failed', error);
    $('#hero-engine').textContent = 'Cockpit API offline';
    $('#console-state-text').textContent = 'OFFLINE';
    toast('Cockpit API offline — dashboard is showing its local snapshot.', 'error');
  }
}

/* ── wiring ─────────────────────────────────────────────────────────────── */

function wireIdeas() {
  $$('.nx-idea').forEach((button) => {
    button.addEventListener('click', () => {
      setRoute(button.dataset.route);
      submit(button.dataset.prompt || '');
    });
  });
}

function wireCockpit() {
  $$('.nx-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      setRoute(chip.dataset.route, { announce: true });
      promptEl.focus();
      autosize();
    });
  });

  consoleForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submit();
  });

  promptEl.addEventListener('input', () => {
    autosize();
    try { sessionStorage.setItem(WORKSPACE_DRAFT_KEY, promptEl.value); } catch { /* storage unavailable */ }
  });
  promptEl.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
      event.preventDefault();
      submit();
    }
  });

  document.addEventListener('keydown', (event) => {
    const typing = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName);
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      promptEl.focus();
      promptEl.select();
      return;
    }
    if (event.key === '/' && !typing) {
      event.preventDefault();
      promptEl.focus();
      return;
    }
    if (event.key === 'Escape') {
      if (state.streaming) cancelRun();
      else if (!runPanel.hidden) {
        runPanel.hidden = true;
        delete app.dataset.panel;
        setState('idle');
      }
    }
  });

  runScroll.addEventListener('scroll', () => {
    const distance = runScroll.scrollHeight - runScroll.scrollTop - runScroll.clientHeight;
    state.stickToBottom = distance < 48;
    if (runLatestBtn) runLatestBtn.hidden = state.stickToBottom;
  });

  runLatestBtn?.addEventListener('click', () => {
    state.stickToBottom = true;
    runLatestBtn.hidden = true;
    runScroll.scrollTo({ top: runScroll.scrollHeight, behavior: 'smooth' });
  });

  $('#run-close').addEventListener('click', () => {
    if (state.streaming) cancelRun();
    runPanel.hidden = true;
    delete app.dataset.panel;
    setState('idle');
  });

  $('#run-copy').addEventListener('click', async () => {
    const text = runAnswer.innerText.trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast('Answer copied to clipboard.');
    } catch {
      toast('Clipboard blocked by the browser.', 'error');
    }
  });

  $('#run-rerun').addEventListener('click', () => {
    const prompt = state.run?.prompt || promptEl.value;
    if (prompt) submit(prompt);
  });

  const submitFromAnywhere = (event) => {
    const target = event.currentTarget;
    const route = target.dataset.route;
    if (route) setRoute(route);
    submit(target.dataset.prompt || '');
  };
  $$('[data-route][data-prompt]').forEach((node) => {
    node.addEventListener('click', submitFromAnywhere);
  });

  $$('.nx-rail__item[data-focus-chips]').forEach((node) => {
    node.addEventListener('click', () => {
      setRoute(node.dataset.focusChips, { announce: true });
      promptEl.focus();
    });
  });
  $$('[data-scroll]').forEach((node) => {
    node.addEventListener('click', () => {
      document.getElementById(node.dataset.scroll)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
  $$('[data-focus-console]').forEach((node) => {
    node.addEventListener('click', () => {
      promptEl.focus({ preventScroll: false });
      promptEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  $('#attach-btn').addEventListener('click', () => {
    toast('File context isn’t wired to the cockpit yet — prompts are text-only in this build.');
  });
  $('#bell-btn').addEventListener('click', () => toast('No new alerts. Three agents reported in clean.'));
  $('#settings-btn').addEventListener('click', () => toast('Settings live in the next cockpit build.'));
  $('#account-btn').addEventListener('click', () => toast('Signed in as Nixtio · Atlas Lab.'));
  $('#history-btn').addEventListener('click', () => toast('Full history lands with the thread archive.'));
  $('#quickfind').addEventListener('click', () => { setRoute('search'); promptEl.focus(); });
}

/* ── boot ───────────────────────────────────────────────────────────────── */

function init() {
  renderWeek();
  wireCockpit();
  wireSpaces();
  wireIdeas();
  try {
    const draft = sessionStorage.getItem(WORKSPACE_DRAFT_KEY);
    if (draft) promptEl.value = draft;
  } catch { /* storage unavailable */ }
  setRoute('deep_research');
  autosize();
  bootstrap();
  loadSpaces();
  state.robot = bootRobot();
  setTimeout(() => state.robot?.react('talk', 1800), 1400);
  window.addEventListener('beforeunload', () => state.robot?.dispose?.());
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
