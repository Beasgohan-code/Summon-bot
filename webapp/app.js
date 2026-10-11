const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  data: null,
  screen: location.hash.slice(1) || 'home',
  busy: false,
  toast: null,
  guest: false,
  transactionFilter: 'all',
  transactionSearch: '',
  transactionSort: 'newest',
  transactionRange: 'all',
  tickerTimer: null,
  cooldownTimer: null,
  selectedTransaction: null,
  anime: null,
  three: null,
  practice: {
    active: false,
    score: 0,
    combo: 0,
    timeLeft: 20,
    timer: null,
    verifying: false,
    best: Number(localStorage.getItem('summon-practice-best') || 0) || 0,
  },
  memory: {
    active: false,
    verifying: false,
    phase: 'idle',
    round: 0,
    maxRounds: 3,
    sequence: [],
    input: [],
    score: 0,
    best: Number(localStorage.getItem('summon-memory-best') || 0) || 0,
    timer: null,
    timers: [],
  },
  meteor: {
    active: false,
    verifying: false,
    lane: 1,
    score: 0,
    timeLeft: 15,
    timer: null,
    spawnTimer: null,
    frame: null,
    lastFrame: 0,
    startedAt: 0,
    meteors: [],
    nextId: 0,
    best: Number(localStorage.getItem('summon-meteor-best') || 0) || 0,
  },
  orbit: {
    active: false,
    verifying: false,
    round: 0,
    maxRounds: 3,
    score: 0,
    best: Number(localStorage.getItem('summon-orbit-best') || 0) || 0,
    cursor: 0,
    targetStart: 0,
    targetWidth: 0,
    locked: false,
    frame: null,
    roundTimer: null,
    nextRoundTimer: null,
    roundStartedAt: 0,
  },
  prism: {
    active: false,
    verifying: false,
    timeLeft: 15,
    score: 0,
    combo: 0,
    target: 0,
    locked: false,
    best: Number(localStorage.getItem('summon-prism-best') || 0) || 0,
    timer: null,
    targetTimer: null,
  },
  signal: {
    active: false,
    verifying: false,
    timeLeft: 18,
    score: 0,
    combo: 0,
    target: 'up',
    locked: false,
    best: Number(localStorage.getItem('summon-signal-best') || 0) || 0,
    timer: null,
    targetTimer: null,
  },
  arena: {
    room: null,
    pollTimer: null,
    running: false,
    submitted: false,
    sequence: [],
    step: 0,
    score: 0,
    combo: 0,
    timeLeft: 18,
    timer: null,
  },
};
const initData = tg?.initData || '';
const fmt = new Intl.NumberFormat();
const shortFmt = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value == null ? '—' : String(value);
}
function coins(value) { return fmt.format(Math.max(0, Number(value) || 0)); }
function initials(value) { return String(value || 'S').trim().slice(0, 1).toUpperCase() || 'S'; }
function haptic(type = 'light') { try { tg?.HapticFeedback?.impactOccurred(type); } catch (_) {} }
function showToast(message, error = false) {
  const node = $('#toast');
  if (!node) return;
  node.textContent = message;
  node.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(state.toast);
  state.toast = setTimeout(() => { node.className = 'toast'; }, 3600);
}
function setConnection(mode, label) {
  const node = $('#connection');
  if (!node) return;
  node.className = `connection ${mode}`;
  setText('#connection-label', label);
}
function setProgress(selector, percent) {
  const node = $(selector);
  if (node) node.style.transform = `scaleX(${Math.max(0, Math.min(100, Number(percent) || 0)) / 100})`;
}
function eventId() { return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
function parseTimestamp(value) {
  if (!value) return null;
  const parsed = new Date(String(value).replace(' ', 'T') + (String(value).includes('Z') ? '' : 'Z'));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
function dateKey(value) {
  const parsed = value instanceof Date ? value : parseTimestamp(value);
  return parsed ? parsed.toLocaleDateString() : '';
}
function relative(value) {
  const parsed = parseTimestamp(value);
  if (!parsed) return 'Recently';
  const seconds = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
function duration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return hours ? `${hours}h ${minutes}m left` : `${Math.max(1, minutes)}m left`;
}
function gameLabel(game) {
  if (game === 'spin') return 'Cosmic spin';
  if (game === 'constellation') return 'Constellation hunt';
  if (game === 'rune_memory') return 'Rune recall';
  if (game === 'meteor_dodge') return 'Meteor dodge';
  if (game === 'orbit_lock') return 'Orbit lock';
  if (game === 'prism_sort') return 'Prism sort';
  if (game === 'signal_trace') return 'Signal trace';
  if (game === 'duo_relay') return 'Duo relay';
  return 'Daily vault';
}
function formatDate(value) {
  const parsed = parseTimestamp(value);
  return parsed ? parsed.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Recently';
}
function transactionMatches(item) {
  const query = state.transactionSearch.trim().toLowerCase();
  const modeMatch = state.transactionFilter === 'all' || item.game === state.transactionFilter;
  const text = `${gameLabel(item.game)} ${item.game || ''} ${item.amount || ''} ${item.created_at || ''} ${item.id || ''}`.toLowerCase();
  if (!modeMatch || (query && !text.includes(query))) return false;
  const created = parseTimestamp(item.created_at);
  if (state.transactionRange === 'today' && (!created || dateKey(created) !== dateKey(new Date()))) return false;
  if (state.transactionRange === '7d' && (!created || Date.now() - created.getTime() > 7 * 86400000)) return false;
  return true;
}
function visibleTransactions(items = []) {
  const filtered = items.filter(transactionMatches);
  return filtered.sort((a, b) => {
    if (state.transactionSort === 'largest') return (Number(b.amount) || 0) - (Number(a.amount) || 0);
    if (state.transactionSort === 'mode') return gameLabel(a.game).localeCompare(gameLabel(b.game)) || (Number(b.amount) || 0) - (Number(a.amount) || 0);
    return (parseTimestamp(b.created_at)?.getTime() || 0) - (parseTimestamp(a.created_at)?.getTime() || 0);
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { 'X-Telegram-Init-Data': initData, ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({ ok: false, error: 'Invalid server response' }));
  if (!response.ok || data.ok === false) {
    const error = new Error(data.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function applyTelegramTheme() {
  if (!tg?.themeParams) return;
  const root = document.documentElement;
  const colors = tg.themeParams;
  if (colors.bg_color) root.style.setProperty('--bg', colors.bg_color);
  if (colors.secondary_bg_color) root.style.setProperty('--panel-2', colors.secondary_bg_color);
  if (colors.text_color) root.style.setProperty('--text', colors.text_color);
  if (colors.hint_color) root.style.setProperty('--muted', colors.hint_color);
  if (colors.button_color) root.style.setProperty('--violet', colors.button_color);
}
function setupTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  applyTelegramTheme();
  try {
    const background = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
    tg.setHeaderColor(background);
    tg.setBackgroundColor(background);
    tg.onEvent?.('themeChanged', applyTelegramTheme);
  } catch (_) {}
}
function prefersReducedMotion() { return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches; }
function motion(target, props) {
  const anime = state.anime?.default || state.anime;
  if (typeof anime === 'function' && !prefersReducedMotion()) return anime({ targets: target, ...props });
  return null;
}
async function loadMotionLibraries() {
  if (prefersReducedMotion()) return;
  const [animeResult, threeResult] = await Promise.allSettled([
    import('https://cdn.jsdelivr.net/npm/animejs@3.2.2/lib/anime.es.js'),
    import('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js'),
  ]);
  if (animeResult.status === 'fulfilled') state.anime = animeResult.value.default || animeResult.value;
  if (threeResult.status === 'fulfilled') {
    state.three = threeResult.value;
    setupThreeHero(threeResult.value);
  }
}
function setupThreeHero(THREE) {
  const canvas = $('#three-hero-scene');
  const host = canvas?.parentElement;
  if (!canvas || !host || !THREE?.WebGLRenderer) return;
  try {
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, .1, 30);
    camera.position.z = 4.6;
    const group = new THREE.Group();
    const geometry = new THREE.BufferGeometry();
    const count = 190;
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const radius = 1.2 + Math.random() * 2.2;
      const angle = Math.random() * Math.PI * 2;
      positions[index * 3] = Math.cos(angle) * radius;
      positions[index * 3 + 1] = (Math.random() - .5) * 2.4;
      positions[index * 3 + 2] = Math.sin(angle) * radius * .48;
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({ color: 0x7dd3fc, size: .025, transparent: true, opacity: .7, depthWrite: false, blending: THREE.AdditiveBlending });
    const particles = new THREE.Points(geometry, material);
    group.add(particles);
    const ringGeometry = new THREE.TorusGeometry(1.65, .008, 8, 96);
    const ringMaterial = new THREE.MeshBasicMaterial({ color: 0xa78bfa, transparent: true, opacity: .28, blending: THREE.AdditiveBlending });
    const ring = new THREE.Mesh(ringGeometry, ringMaterial);
    ring.rotation.x = Math.PI * .48;
    group.add(ring);
    scene.add(group);
    const resize = () => {
      const rect = host.getBoundingClientRect();
      renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false);
      camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height);
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener('resize', resize, { passive: true });
    const tick = (time) => {
      if (!document.hidden) {
        group.rotation.y = time * .00008;
        particles.rotation.z = time * .000035;
        ring.rotation.z = -time * .00012;
        renderer.render(scene, camera);
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    host.classList.add('three-ready');
  } catch (_) {
    host.classList.add('three-fallback');
  }
}

function setGuestMode(guest) {
  state.guest = Boolean(guest);
  document.body.classList.toggle('guest-mode', state.guest);
  $$('[data-private]').forEach((node) => { node.hidden = state.guest; });
  const banner = $('#guest-banner'); if (banner) banner.hidden = !state.guest;
  const overview = $('#guest-overview'); if (overview) overview.hidden = !state.guest;
  const privateTitle = $('#private-progress-title'); if (privateTitle) privateTitle.hidden = state.guest;
  const guestTitle = $('#guest-progress-title'); if (guestTitle) guestTitle.hidden = !state.guest;
}

function animateNumber(selector, target, formatter = coins, durationMs = 700) {
  const node = $(selector);
  if (!node) return;
  const value = Number(target) || 0;
  const from = Number(node.dataset.value || 0);
  node.dataset.value = String(value);
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    node.textContent = formatter(value);
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const progress = Math.min(1, (now - start) / durationMs);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = formatter(from + ((value - from) * eased));
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function renderPracticeAvailability(cooldowns = state.data?.cooldowns || {}) {
  const button = $('#practice-start');
  const info = cooldowns.constellation || { available: true, remaining_seconds: 0 };
  if (!button || state.practice.active || state.practice.verifying) return;
  button.disabled = state.guest || !info.available;
  if (!info.available) {
    button.innerHTML = `Reward window in ${duration(info.remaining_seconds)} <span>◷</span>`;
    setText('#practice-status', `Come back in ${duration(info.remaining_seconds)} for a verified coin reward`);
  } else if (state.practice.active === false) {
    button.innerHTML = state.practice.score ? 'Run again <span>↗</span>' : 'Start practice <span>↗</span>';
  }
}
function renderMemoryAvailability(cooldowns = state.data?.cooldowns || {}) {
  const button = $('#memory-start');
  const info = cooldowns.rune_memory || { available: true, remaining_seconds: 0 };
  if (!button || state.memory.active || state.memory.verifying) return;
  button.disabled = state.guest || !info.available;
  if (!info.available) {
    button.innerHTML = `Reward window in ${duration(info.remaining_seconds)} <span>◷</span>`;
    setText('#memory-status', `Next verified reward in ${duration(info.remaining_seconds)}`);
  } else if (state.memory.phase !== 'showing' && state.memory.phase !== 'input') {
    button.innerHTML = state.memory.score ? 'Play again <span>↗</span>' : 'Start rune recall <span>↗</span>';
  }
}
function renderMeteorAvailability(cooldowns = state.data?.cooldowns || {}) {
  const button = $('#meteor-start');
  const info = cooldowns.meteor_dodge || { available: true, remaining_seconds: 0 };
  if (!button || state.meteor.active || state.meteor.verifying) return;
  button.disabled = state.guest || !info.available;
  if (!info.available) {
    button.innerHTML = `Reward window in ${duration(info.remaining_seconds)} <span>◷</span>`;
    setText('#meteor-status', `Next verified reward in ${duration(info.remaining_seconds)}`);
  } else {
    button.innerHTML = state.meteor.score ? 'Play again <span>↗</span>' : 'Start meteor dodge <span>↗</span>';
  }
}
function renderOrbitAvailability(cooldowns = state.data?.cooldowns || {}) {
  const button = $('#orbit-start');
  const info = cooldowns.orbit_lock || { available: true, remaining_seconds: 0 };
  if (!button || state.orbit.active || state.orbit.verifying) return;
  button.disabled = state.guest || !info.available;
  if (!info.available) {
    button.innerHTML = `Reward window in ${duration(info.remaining_seconds)} <span>◷</span>`;
    setText('#orbit-status', `Next verified reward in ${duration(info.remaining_seconds)}`);
  } else {
    button.innerHTML = state.orbit.score ? 'Run again <span>↗</span>' : 'Start orbit lock <span>↗</span>';
  }
}
function renderPrismAvailability(cooldowns = state.data?.cooldowns || {}) {
  const button = $('#prism-start');
  const info = cooldowns.prism_sort || { available: true, remaining_seconds: 0 };
  if (!button || state.prism.active || state.prism.verifying) return;
  button.disabled = state.guest || !info.available;
  if (!info.available) {
    button.innerHTML = `Reward window in ${duration(info.remaining_seconds)} <span>◷</span>`;
    setText('#prism-status', `Next verified reward in ${duration(info.remaining_seconds)}`);
  } else {
    button.innerHTML = state.prism.score ? 'Run again <span>↗</span>' : 'Start prism sort <span>↗</span>';
  }
}
function renderSignalAvailability(cooldowns = state.data?.cooldowns || {}) {
  const button = $('#signal-start');
  const info = cooldowns.signal_trace || { available: true, remaining_seconds: 0 };
  if (!button || state.signal.active || state.signal.verifying) return;
  button.disabled = state.guest || !info.available;
  if (!info.available) {
    button.innerHTML = `Reward window in ${duration(info.remaining_seconds)} <span>◷</span>`;
    setText('#signal-status', `Next verified reward in ${duration(info.remaining_seconds)}`);
  } else {
    button.innerHTML = state.signal.score ? 'Run again <span>↗</span>' : 'Start signal trace <span>↗</span>';
  }
}
function renderGames(cooldowns = {}) {
  ['daily', 'spin'].forEach((game) => {
    const info = cooldowns[game] || { available: true, remaining_seconds: 0 };
    const ready = Boolean(info.available);
    $$(`[data-status="${game}"]`).forEach((status) => {
      status.textContent = ready ? 'Ready to play' : duration(info.remaining_seconds);
      status.className = `game-status ${ready ? 'ready' : 'locked'}`;
    });
    $$(`[data-game="${game}"]`).forEach((button) => {
      button.disabled = !ready || state.busy;
      button.classList.toggle('is-busy', state.busy);
    });
  });
  renderPracticeAvailability(cooldowns);
  renderMemoryAvailability(cooldowns);
  renderMeteorAvailability(cooldowns);
  renderOrbitAvailability(cooldowns);
  renderPrismAvailability(cooldowns);
  renderSignalAvailability(cooldowns);
}
function startCooldownTicker() {
  clearInterval(state.cooldownTimer);
  state.cooldownTimer = setInterval(() => {
    if (state.guest || !state.data?.cooldowns) return;
    let changed = false;
    Object.values(state.data.cooldowns).forEach((info) => {
      if (info?.available) return;
      info.remaining_seconds = Math.max(0, (Number(info.remaining_seconds) || 0) - 1);
      if (info.remaining_seconds === 0) info.available = true;
      changed = true;
    });
    if (changed) {
      renderGames(state.data.cooldowns);
      renderInsights(state.data.history || [], state.data.cooldowns);
      renderPulse(state.data.history || [], state.data.streak || {});
      renderIntel(state.data.history || [], state);
    }
  }, 1000);
}
function practiceState(status) {
  const target = $('#practice-target');
  const arena = $('#practice-arena');
  if (arena) arena.dataset.state = status;
  if (target) target.hidden = status !== 'active';
  setText('#practice-score', state.practice.score);
  setText('#practice-combo', `${state.practice.combo}×`);
  setText('#practice-best', state.practice.best);
  setText('#practice-status', status === 'active' ? `${state.practice.timeLeft}s remaining · catch the signal` : status === 'complete' ? `Run complete · ${state.practice.score} points` : 'Ready when you are');
  const start = $('#practice-start');
  if (start) {
    start.disabled = state.practice.verifying;
    start.innerHTML = state.practice.verifying ? 'Verifying run…' : status === 'active' ? 'Abort run <span>×</span>' : status === 'complete' ? 'Run again <span>↗</span>' : 'Start practice <span>↗</span>';
  }
  if (!state.practice.verifying && status !== 'active') renderPracticeAvailability();
}
function movePracticeTarget() {
  const arena = $('#practice-arena');
  const target = $('#practice-target');
  if (!arena || !target) return;
  const inset = 18;
  const x = inset + Math.random() * Math.max(1, arena.clientWidth - target.offsetWidth - inset * 2);
  const y = inset + Math.random() * Math.max(1, arena.clientHeight - target.offsetHeight - inset * 2);
  target.style.left = `${x}px`;
  target.style.top = `${y}px`;
  motion(target, { scale: [.65, 1], rotate: [-24, 0], duration: 420, easing: 'easeOutElastic(1, .6)' });
}
async function finishPracticeGame(aborted = false) {
  clearInterval(state.practice.timer);
  state.practice.timer = null;
  state.practice.active = false;
  if (state.practice.score > state.practice.best) {
    state.practice.best = state.practice.score;
    localStorage.setItem('summon-practice-best', String(state.practice.best));
  }
  practiceState(aborted ? 'idle' : 'complete');
  if (aborted || state.guest) return;
  const finalScore = state.practice.score;
  state.practice.verifying = true;
  practiceState('complete');
  haptic('medium');
  setText('#practice-status', 'Verifying your constellation run…');
  try {
    const result = await api('/api/miniapp/game', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game: 'constellation', score: finalScore, event_id: eventId() }),
    });
    showReward('constellation', result.winnings);
    await load({ quiet: true });
  } catch (error) {
    showToast(error.message || 'Run completed, but the reward could not be recorded.', true);
    setText('#practice-status', 'Run complete · reward verification unavailable');
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  } finally {
    state.practice.verifying = false;
    practiceState('complete');
    renderPracticeAvailability();
  }
}
function startPracticeGame() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter the arcade lab.', true); return; }
  if (state.practice.verifying) return;
  if (!state.practice.active && state.data?.cooldowns?.constellation && !state.data.cooldowns.constellation.available) {
    showToast(`The next coin reward is available in ${duration(state.data.cooldowns.constellation.remaining_seconds)}.`, true);
    return;
  }
  if (state.practice.active) { finishPracticeGame(true); return; }
  state.practice.active = true;
  state.practice.score = 0;
  state.practice.combo = 0;
  state.practice.timeLeft = 20;
  practiceState('active');
  movePracticeTarget();
  haptic('light');
  state.practice.timer = setInterval(() => {
    state.practice.timeLeft -= 1;
    if (state.practice.timeLeft <= 0) finishPracticeGame();
    else practiceState('active');
  }, 1000);
}
function hitPracticeTarget() {
  if (!state.practice.active) return;
  state.practice.combo += 1;
  state.practice.score += 10 + Math.min(30, (state.practice.combo - 1) * 2);
  haptic(state.practice.combo % 5 === 0 ? 'medium' : 'light');
  practiceState('active');
  movePracticeTarget();
}

const memoryRunes = ['✦', '◈', '✧', '◇', '⊹', '✹', '⌁', '◉', '△'];
function memoryClearTimers() {
  clearTimeout(state.memory.timer);
  state.memory.timer = null;
  state.memory.timers.forEach((timer) => clearTimeout(timer));
  state.memory.timers = [];
}
function memoryState(status = state.memory.phase) {
  const board = $('#memory-board');
  if (board) board.dataset.state = status;
  setText('#memory-round', `${Math.min(state.memory.round, state.memory.maxRounds)}/${state.memory.maxRounds}`);
  setText('#memory-progress', state.memory.round ? `Round ${Math.min(state.memory.round, state.memory.maxRounds)} / ${state.memory.maxRounds}` : '3 rounds');
  setText('#memory-score', state.memory.score);
  setText('#memory-best', state.memory.best);
  const copy = {
    showing: 'Memorize the rune sequence…',
    input: 'Repeat the sequence',
    wrong: 'Sequence broken · run ended',
    failed: 'Run failed · try again',
    complete: `Run complete · ${state.memory.score} points`,
    idle: 'Ready when you are',
  };
  setText('#memory-status', copy[status] || copy.idle);
  const start = $('#memory-start');
  if (start) {
    start.disabled = state.memory.verifying;
    start.innerHTML = state.memory.verifying ? 'Verifying run…' : state.memory.active ? 'Abort run <span>×</span>' : status === 'complete' ? 'Play again <span>↗</span>' : 'Start rune recall <span>↗</span>';
  }
  $$('[data-memory-tile]').forEach((tile) => { tile.disabled = status !== 'input'; });
  if (!state.memory.active && !state.memory.verifying) renderMemoryAvailability();
}
function memoryBeginRound() {
  if (!state.memory.active) return;
  memoryClearTimers();
  state.memory.round += 1;
  state.memory.input = [];
  state.memory.sequence = [];
  const length = Math.min(3 + state.memory.round, 6);
  while (state.memory.sequence.length < length) {
    const index = Math.floor(Math.random() * memoryRunes.length);
    if (!state.memory.sequence.includes(index)) state.memory.sequence.push(index);
  }
  $$('[data-memory-tile]').forEach((tile) => tile.classList.remove('showing', 'correct', 'wrong'));
  state.memory.phase = 'showing';
  memoryState('showing');
  const gap = 620;
  state.memory.sequence.forEach((index, position) => {
    const revealTimer = setTimeout(() => {
      const tile = $(`[data-memory-tile="${index}"]`);
      if (!tile) return;
      tile.classList.add('showing');
      motion(tile, { scale: [.72, 1], rotate: [-8, 0], duration: 360, easing: 'easeOutBack' });
      haptic('light');
      const hideTimer = setTimeout(() => tile.classList.remove('showing'), 420);
      state.memory.timers.push(hideTimer);
    }, position * gap + 260);
    state.memory.timers.push(revealTimer);
  });
  const inputTimer = setTimeout(memoryBeginInput, state.memory.sequence.length * gap + 520);
  state.memory.timers.push(inputTimer);
}
function memoryBeginInput() {
  if (!state.memory.active) return;
  state.memory.phase = 'input';
  memoryState('input');
  state.memory.timer = setTimeout(() => finishMemoryGame(false, false, true), 9000);
}
function finishMemoryGame(success = false, aborted = false, timeout = false) {
  memoryClearTimers();
  state.memory.active = false;
  if (state.memory.score > state.memory.best) {
    state.memory.best = state.memory.score;
    localStorage.setItem('summon-memory-best', String(state.memory.best));
  }
  if (aborted) {
    state.memory.phase = 'idle';
    memoryState('idle');
    return;
  }
  if (!success) {
    state.memory.phase = timeout ? 'failed' : 'wrong';
    memoryState(state.memory.phase);
    haptic('medium');
    showToast(timeout ? 'Rune Recall timed out.' : 'Wrong rune. Better luck next run.', true);
    return;
  }
  const finalScore = state.memory.score;
  state.memory.verifying = true;
  state.memory.phase = 'complete';
  memoryState('complete');
  haptic('heavy');
  setText('#memory-status', 'Verifying your rune sequence…');
  api('/api/miniapp/game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game: 'rune_memory', score: finalScore, event_id: eventId() }),
  }).then(async (result) => {
    showReward('rune_memory', result.winnings);
    await load({ quiet: true });
  }).catch(async (error) => {
    showToast(error.message || 'Run completed, but the reward could not be recorded.', true);
    setText('#memory-status', 'Run complete · reward verification unavailable');
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  }).finally(() => {
    state.memory.verifying = false;
    state.memory.phase = 'complete';
    memoryState('complete');
    renderMemoryAvailability();
  });
}
function startMemoryGame() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Rune Recall.', true); return; }
  if (state.memory.verifying) return;
  if (!state.memory.active && state.data?.cooldowns?.rune_memory && !state.data.cooldowns.rune_memory.available) {
    showToast(`The next rune reward is available in ${duration(state.data.cooldowns.rune_memory.remaining_seconds)}.`, true);
    return;
  }
  if (state.memory.active) { finishMemoryGame(false, true); return; }
  state.memory.active = true;
  state.memory.phase = 'showing';
  state.memory.round = 0;
  state.memory.score = 0;
  state.memory.input = [];
  state.memory.sequence = [];
  haptic('light');
  memoryBeginRound();
}
function hitMemoryTile(event) {
  if (!state.memory.active || state.memory.phase !== 'input') return;
  const tile = event.currentTarget;
  const index = Number(tile.dataset.memoryTile);
  const expected = state.memory.sequence[state.memory.input.length];
  if (index !== expected) {
    tile.classList.add('wrong');
    motion(tile, { translateX: [-5, 5, -4, 4, 0], duration: 260 });
    finishMemoryGame(false);
    return;
  }
  state.memory.input.push(index);
  tile.classList.add('correct');
  haptic('light');
  const clearTimer = setTimeout(() => tile.classList.remove('correct'), 260);
  state.memory.timers.push(clearTimer);
  if (state.memory.input.length < state.memory.sequence.length) return;
  clearTimeout(state.memory.timer);
  state.memory.timer = null;
  state.memory.score += 100 + state.memory.round * 50;
  haptic('medium');
  if (state.memory.round < state.memory.maxRounds) {
    state.memory.phase = 'showing';
    memoryState('showing');
    const nextRound = setTimeout(memoryBeginRound, 520);
    state.memory.timers.push(nextRound);
  } else {
    finishMemoryGame(true);
  }
}

const METEOR_DURATION = 15;
function meteorState(status = state.meteor.active ? 'active' : 'idle') {
  const arena = $('#meteor-arena');
  const player = $('#meteor-player');
  if (arena) arena.dataset.state = status;
  if (player) {
    player.style.left = `${((state.meteor.lane + 0.5) / 3) * 100}%`;
    player.classList.toggle('is-hit', status === 'crashed');
  }
  setText('#meteor-time', `${Math.max(0, state.meteor.timeLeft)}s`);
  setText('#meteor-score', state.meteor.score);
  setText('#meteor-best', state.meteor.best);
  setText('#meteor-progress', status === 'active' ? `${state.meteor.timeLeft}s remaining` : status === 'complete' ? 'storm cleared' : '15 seconds');
  const copy = {
    active: 'Stay in the safe lane · use arrows or touch',
    crashed: `Impact detected · ${state.meteor.score} points`,
    complete: `Storm cleared · ${state.meteor.score} points`,
    idle: 'Ready when you are',
  };
  setText('#meteor-status', copy[status] || copy.idle);
  const start = $('#meteor-start');
  if (start) {
    start.disabled = state.meteor.verifying;
    start.innerHTML = state.meteor.verifying ? 'Verifying run…' : status === 'active' ? 'Abort run <span>×</span>' : status === 'complete' ? 'Play again <span>↗</span>' : status === 'crashed' ? 'Try again <span>↗</span>' : 'Start meteor dodge <span>↗</span>';
  }
  if (!state.meteor.active && !state.meteor.verifying) renderMeteorAvailability();
}
function meteorClear() {
  clearInterval(state.meteor.timer);
  clearInterval(state.meteor.spawnTimer);
  state.meteor.timer = null;
  state.meteor.spawnTimer = null;
  if (state.meteor.frame) cancelAnimationFrame(state.meteor.frame);
  state.meteor.frame = null;
  state.meteor.lastFrame = 0;
  state.meteor.meteors.forEach((meteor) => meteor.el?.remove());
  state.meteor.meteors = [];
}
function meteorSpawn() {
  if (!state.meteor.active) return;
  const lanes = $$('[data-meteor-lane]');
  if (!lanes.length) return;
  const lane = Math.floor(Math.random() * lanes.length);
  const rock = document.createElement('span');
  rock.className = 'meteor-rock';
  rock.textContent = ['◆', '✧', '•'][Math.floor(Math.random() * 3)];
  rock.setAttribute('aria-hidden', 'true');
  lanes[lane].append(rock);
  state.meteor.meteors.push({ lane, y: -34, speed: 112 + Math.random() * 42, el: rock, id: state.meteor.nextId += 1 });
}
function meteorMove(direction) {
  if (!state.meteor.active) return;
  const next = Math.max(0, Math.min(2, state.meteor.lane + direction));
  if (next === state.meteor.lane) {
    haptic('light');
    return;
  }
  state.meteor.lane = next;
  const player = $('#meteor-player');
  motion(player, { scale: [.78, 1], rotate: direction < 0 ? [8, 0] : [-8, 0], duration: 240, easing: 'easeOutBack' });
  meteorState('active');
  haptic('light');
}
function meteorFrame(now) {
  if (!state.meteor.active) return;
  if (!state.meteor.lastFrame) state.meteor.lastFrame = now;
  const delta = Math.min(.055, Math.max(0, (now - state.meteor.lastFrame) / 1000));
  state.meteor.lastFrame = now;
  const arena = $('#meteor-arena');
  const player = $('#meteor-player');
  const laneTop = 43;
  const playerHeight = player?.offsetHeight || 40;
  const collisionTop = Math.max(0, (arena?.clientHeight || 286) - 56 - playerHeight - laneTop);
  for (let index = state.meteor.meteors.length - 1; index >= 0; index -= 1) {
    const meteor = state.meteor.meteors[index];
    meteor.y += meteor.speed * delta;
    meteor.el.style.transform = `translate(-50%, ${meteor.y}px) rotate(${18 + meteor.y * .7}deg)`;
    if (meteor.lane === state.meteor.lane && meteor.y + 25 >= collisionTop && meteor.y <= collisionTop + playerHeight - 3) {
      meteor.el.classList.add('is-hit');
      finishMeteorGame(false, false, true);
      return;
    }
    if (meteor.y > (arena?.clientHeight || 286) - laneTop + 38) {
      meteor.el.remove();
      state.meteor.meteors.splice(index, 1);
      state.meteor.score += 25;
    }
  }
  state.meteor.score = Math.max(state.meteor.score, Math.floor((now - state.meteor.startedAt) / 100));
  setText('#meteor-score', state.meteor.score);
  state.meteor.frame = requestAnimationFrame(meteorFrame);
}
function finishMeteorGame(success = false, aborted = false, crashed = false) {
  if (!state.meteor.active && !state.meteor.verifying) return;
  meteorClear();
  state.meteor.active = false;
  if (state.meteor.score > state.meteor.best) {
    state.meteor.best = state.meteor.score;
    localStorage.setItem('summon-meteor-best', String(state.meteor.best));
  }
  if (aborted) {
    state.meteor.timeLeft = METEOR_DURATION;
    meteorState('idle');
    return;
  }
  if (!success) {
    state.meteor.timeLeft = Math.max(0, state.meteor.timeLeft);
    meteorState(crashed ? 'crashed' : 'idle');
    haptic('heavy');
    showToast(crashed ? 'A meteor found your lane. Try again.' : 'Meteor Dodge ended.', true);
    return;
  }
  const finalScore = state.meteor.score;
  state.meteor.verifying = true;
  state.meteor.timeLeft = 0;
  meteorState('complete');
  haptic('heavy');
  setText('#meteor-status', 'Verifying your survival run…');
  api('/api/miniapp/game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game: 'meteor_dodge', score: finalScore, event_id: eventId() }),
  }).then(async (result) => {
    showReward('meteor_dodge', result.winnings);
    await load({ quiet: true });
  }).catch(async (error) => {
    showToast(error.message || 'Survival complete, but the reward could not be recorded.', true);
    setText('#meteor-status', 'Survival complete · reward verification unavailable');
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  }).finally(() => {
    state.meteor.verifying = false;
    meteorState('complete');
    renderMeteorAvailability();
  });
}
function startMeteorGame() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Meteor Dodge.', true); return; }
  if (state.meteor.verifying) return;
  if (!state.meteor.active && state.data?.cooldowns?.meteor_dodge && !state.data.cooldowns.meteor_dodge.available) {
    showToast(`The next meteor reward is available in ${duration(state.data.cooldowns.meteor_dodge.remaining_seconds)}.`, true);
    return;
  }
  if (state.meteor.active) { finishMeteorGame(false, true); return; }
  meteorClear();
  state.meteor.active = true;
  state.meteor.lane = 1;
  state.meteor.score = 0;
  state.meteor.timeLeft = METEOR_DURATION;
  state.meteor.startedAt = performance.now();
  meteorState('active');
  meteorSpawn();
  state.meteor.spawnTimer = setInterval(meteorSpawn, 680);
  state.meteor.timer = setInterval(() => {
    state.meteor.timeLeft -= 1;
    if (state.meteor.timeLeft <= 0) {
      state.meteor.timeLeft = 0;
      finishMeteorGame(true);
    } else meteorState('active');
  }, 1000);
  state.meteor.frame = requestAnimationFrame(meteorFrame);
  $('#meteor-arena')?.focus({ preventScroll: true });
  haptic('light');
}

function orbitState(status = state.orbit.active ? 'active' : 'idle') {
  const board = $('#orbit-board');
  const target = $('#orbit-target');
  const cursor = $('#orbit-cursor');
  if (board) board.dataset.state = status;
  if (target) {
    target.style.left = `${state.orbit.targetStart}%`;
    target.style.width = `${state.orbit.targetWidth}%`;
    target.classList.toggle('is-hit', status === 'locked');
  }
  if (cursor) cursor.style.left = `${state.orbit.cursor}%`;
  setText('#orbit-round', `${Math.min(state.orbit.round, state.orbit.maxRounds)}/${state.orbit.maxRounds}`);
  setText('#orbit-score', state.orbit.score);
  setText('#orbit-best', state.orbit.best);
  setText('#orbit-progress', status === 'active' ? `Round ${state.orbit.round} of ${state.orbit.maxRounds}` : status === 'complete' ? 'signal secured' : '3 rounds');
  const copy = {
    active: 'Track the signal · lock inside the violet zone',
    locked: 'Perfect lock · recalibrating orbit…',
    missed: `Signal missed · ${state.orbit.score} points`,
    complete: `Orbit secured · ${state.orbit.score} points`,
    idle: 'Ready when you are',
  };
  setText('#orbit-status', copy[status] || copy.idle);
  const start = $('#orbit-start');
  if (start) {
    start.disabled = state.orbit.verifying;
    start.innerHTML = state.orbit.verifying ? 'Verifying run…' : status === 'active' || status === 'locked' ? 'Abort run <span>×</span>' : status === 'complete' ? 'Run again <span>↗</span>' : status === 'missed' ? 'Try again <span>↗</span>' : 'Start orbit lock <span>↗</span>';
  }
  const lock = $('#orbit-lock');
  if (lock) lock.disabled = status !== 'active' || state.orbit.verifying;
  if (!state.orbit.active && !state.orbit.verifying) renderOrbitAvailability();
}
function orbitClear() {
  if (state.orbit.frame) cancelAnimationFrame(state.orbit.frame);
  clearTimeout(state.orbit.roundTimer);
  clearTimeout(state.orbit.nextRoundTimer);
  state.orbit.frame = null;
  state.orbit.roundTimer = null;
  state.orbit.nextRoundTimer = null;
  state.orbit.locked = false;
}
function orbitBeginRound() {
  if (!state.orbit.active) return;
  clearTimeout(state.orbit.roundTimer);
  state.orbit.locked = false;
  const width = Math.max(16, 30 - state.orbit.round * 4);
  state.orbit.targetWidth = width;
  state.orbit.targetStart = 8 + Math.random() * (84 - width);
  state.orbit.cursor = 0;
  state.orbit.roundStartedAt = performance.now();
  orbitState('active');
  state.orbit.roundTimer = setTimeout(() => finishOrbitGame(false, false, true), 4800);
  state.orbit.frame = requestAnimationFrame(orbitFrame);
}
function orbitFrame(now) {
  if (!state.orbit.active || state.orbit.locked) return;
  const elapsed = (now - state.orbit.roundStartedAt) % 2600;
  state.orbit.cursor = elapsed < 1300 ? (elapsed / 13) : ((2600 - elapsed) / 13);
  const cursor = $('#orbit-cursor');
  if (cursor) cursor.style.left = `${state.orbit.cursor}%`;
  state.orbit.frame = requestAnimationFrame(orbitFrame);
}
function lockOrbit() {
  if (!state.orbit.active || state.orbit.locked) return;
  state.orbit.locked = true;
  clearTimeout(state.orbit.roundTimer);
  if (state.orbit.cursor >= state.orbit.targetStart && state.orbit.cursor <= state.orbit.targetStart + state.orbit.targetWidth) {
    state.orbit.score += 100 + state.orbit.round * 45;
    haptic('medium');
    orbitState('locked');
    if (state.orbit.round < state.orbit.maxRounds) {
      state.orbit.nextRoundTimer = setTimeout(() => {
        state.orbit.round += 1;
        orbitBeginRound();
      }, 620);
    } else {
      state.orbit.nextRoundTimer = setTimeout(() => finishOrbitGame(true), 620);
    }
    return;
  }
  haptic('heavy');
  finishOrbitGame(false, false, false);
}
function finishOrbitGame(success = false, aborted = false, timeout = false) {
  if (!state.orbit.active && !state.orbit.verifying) return;
  orbitClear();
  state.orbit.active = false;
  if (state.orbit.score > state.orbit.best) {
    state.orbit.best = state.orbit.score;
    localStorage.setItem('summon-orbit-best', String(state.orbit.best));
  }
  if (aborted) {
    state.orbit.round = 0;
    state.orbit.score = 0;
    orbitState('idle');
    return;
  }
  if (!success) {
    orbitState('missed');
    showToast(timeout ? 'Orbit Lock timed out.' : 'The signal slipped away. Try again.', true);
    return;
  }
  const finalScore = state.orbit.score;
  state.orbit.verifying = true;
  orbitState('complete');
  haptic('heavy');
  setText('#orbit-status', 'Verifying your orbit run…');
  api('/api/miniapp/game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game: 'orbit_lock', score: finalScore, event_id: eventId() }),
  }).then(async (result) => {
    showReward('orbit_lock', result.winnings);
    await load({ quiet: true });
  }).catch(async (error) => {
    showToast(error.message || 'Run complete, but the reward could not be recorded.', true);
    setText('#orbit-status', 'Run complete · reward verification unavailable');
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  }).finally(() => {
    state.orbit.verifying = false;
    orbitState('complete');
    renderOrbitAvailability();
  });
}
function startOrbitGame() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Orbit Lock.', true); return; }
  if (state.orbit.verifying) return;
  if (!state.orbit.active && state.data?.cooldowns?.orbit_lock && !state.data.cooldowns.orbit_lock.available) {
    showToast(`The next orbit reward is available in ${duration(state.data.cooldowns.orbit_lock.remaining_seconds)}.`, true);
    return;
  }
  if (state.orbit.active) { finishOrbitGame(false, true); return; }
  orbitClear();
  state.orbit.active = true;
  state.orbit.round = 1;
  state.orbit.score = 0;
  orbitBeginRound();
  $('#orbit-board')?.focus({ preventScroll: true });
  haptic('light');
}

const prismColors = [
  { name: 'Aqua', glyph: '◆', className: 'aqua' },
  { name: 'Violet', glyph: '✦', className: 'violet' },
  { name: 'Gold', glyph: '✧', className: 'gold' },
];
function prismState(status = state.prism.active ? 'active' : 'idle') {
  const board = $('#prism-board');
  const target = prismColors[state.prism.target] || prismColors[0];
  if (board) board.dataset.state = status;
  setText('#prism-time', `${Math.max(0, state.prism.timeLeft)}s`);
  setText('#prism-score', state.prism.score);
  setText('#prism-combo', `${state.prism.combo}×`);
  setText('#prism-best', state.prism.best);
  setText('#prism-target-label', status === 'active' || status === 'locked' ? `Sort ${target.name}` : status === 'complete' ? 'run cleared' : 'Ready when you are');
  const targetGlyph = $('#prism-target-glyph');
  if (targetGlyph) {
    targetGlyph.textContent = target.glyph;
    targetGlyph.className = `prism-target-glyph ${target.className}`;
  }
  setText('#prism-progress', status === 'active' || status === 'locked' ? `${state.prism.timeLeft}s remaining` : status === 'complete' ? 'colors aligned' : '15 seconds');
  const copy = {
    active: 'Match the glowing prism · keys 1, 2, 3 also work',
    locked: 'Good sort · next prism incoming…',
    complete: `Run complete · ${state.prism.score} points`,
    idle: 'Ready when you are',
  };
  setText('#prism-status', copy[status] || copy.idle);
  const start = $('#prism-start');
  if (start) {
    start.disabled = state.prism.verifying;
    start.innerHTML = state.prism.verifying ? 'Verifying run…' : status === 'active' || status === 'locked' ? 'Abort run <span>×</span>' : status === 'complete' ? 'Run again <span>↗</span>' : 'Start prism sort <span>↗</span>';
  }
  $$('[data-prism-color]').forEach((button, index) => {
    button.disabled = status !== 'active' || state.prism.verifying;
    button.classList.toggle('selected', index === state.prism.target && status === 'active');
  });
  if (!state.prism.active && !state.prism.verifying) renderPrismAvailability();
}
function prismClearTimers() {
  clearInterval(state.prism.timer);
  clearTimeout(state.prism.targetTimer);
  state.prism.timer = null;
  state.prism.targetTimer = null;
  state.prism.locked = false;
  $$('[data-prism-color]').forEach((button) => button.classList.remove('correct', 'wrong', 'selected'));
}
function prismNextTarget() {
  state.prism.target = Math.floor(Math.random() * prismColors.length);
  prismState('active');
}
function choosePrism(event) {
  if (!state.prism.active || state.prism.locked) return;
  const choice = Number(event.currentTarget.dataset.prismColor);
  state.prism.locked = true;
  const correct = choice === state.prism.target;
  const button = event.currentTarget;
  button.classList.add(correct ? 'correct' : 'wrong');
  if (correct) {
    state.prism.combo += 1;
    state.prism.score += 15 + Math.min(45, (state.prism.combo - 1) * 5);
    haptic(state.prism.combo % 4 === 0 ? 'medium' : 'light');
    prismState('locked');
  } else {
    state.prism.combo = 0;
    haptic('heavy');
    setText('#prism-status', `Wrong prism · target was ${prismColors[state.prism.target].name}`);
  }
  state.prism.targetTimer = setTimeout(() => {
    button.classList.remove('correct', 'wrong');
    state.prism.locked = false;
    prismNextTarget();
  }, correct ? 260 : 420);
}
function finishPrismGame(success = false, aborted = false) {
  if (!state.prism.active && !state.prism.verifying) return;
  prismClearTimers();
  state.prism.active = false;
  if (state.prism.score > state.prism.best) {
    state.prism.best = state.prism.score;
    localStorage.setItem('summon-prism-best', String(state.prism.best));
  }
  if (aborted) {
    state.prism.timeLeft = 15;
    state.prism.score = 0;
    state.prism.combo = 0;
    prismState('idle');
    return;
  }
  if (!success) return;
  const finalScore = state.prism.score;
  state.prism.verifying = true;
  state.prism.timeLeft = 0;
  prismState('complete');
  haptic('heavy');
  setText('#prism-status', 'Verifying your prism run…');
  api('/api/miniapp/game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game: 'prism_sort', score: finalScore, event_id: eventId() }),
  }).then(async (result) => {
    showReward('prism_sort', result.winnings);
    await load({ quiet: true });
  }).catch(async (error) => {
    showToast(error.message || 'Run complete, but the reward could not be recorded.', true);
    setText('#prism-status', 'Run complete · reward verification unavailable');
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  }).finally(() => {
    state.prism.verifying = false;
    prismState('complete');
    renderPrismAvailability();
  });
}
function startPrismGame() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Prism Sort.', true); return; }
  if (state.prism.verifying) return;
  if (!state.prism.active && state.data?.cooldowns?.prism_sort && !state.data.cooldowns.prism_sort.available) {
    showToast(`The next prism reward is available in ${duration(state.data.cooldowns.prism_sort.remaining_seconds)}.`, true);
    return;
  }
  if (state.prism.active) { finishPrismGame(false, true); return; }
  prismClearTimers();
  state.prism.active = true;
  state.prism.timeLeft = 15;
  state.prism.score = 0;
  state.prism.combo = 0;
  state.prism.target = Math.floor(Math.random() * prismColors.length);
  prismState('active');
  state.prism.timer = setInterval(() => {
    state.prism.timeLeft -= 1;
    if (state.prism.timeLeft <= 0) {
      state.prism.timeLeft = 0;
      finishPrismGame(true);
    } else prismState('active');
  }, 1000);
  $('#prism-board')?.focus({ preventScroll: true });
  haptic('light');
}


const signalDirections = [
  { key: 'up', name: 'North', glyph: '↑', className: 'up' },
  { key: 'right', name: 'East', glyph: '→', className: 'right' },
  { key: 'down', name: 'South', glyph: '↓', className: 'down' },
  { key: 'left', name: 'West', glyph: '←', className: 'left' },
];
function signalDirection(key) {
  return signalDirections.find((direction) => direction.key === key) || signalDirections[0];
}
function signalState(status = state.signal.active ? 'active' : 'idle') {
  const board = $('#signal-board');
  const target = signalDirection(state.signal.target);
  if (board) board.dataset.state = status;
  setText('#signal-time', `${Math.max(0, state.signal.timeLeft)}s`);
  setText('#signal-score', state.signal.score);
  setText('#signal-combo', `${state.signal.combo}×`);
  setText('#signal-target-label', status === 'active' || status === 'locked' ? `Trace ${target.name}` : status === 'complete' ? 'circuit cleared' : 'Ready when you are');
  const glyph = $('#signal-target-glyph');
  if (glyph) {
    glyph.textContent = target.glyph;
    glyph.className = `signal-target-glyph ${target.className}`;
  }
  setText('#signal-progress', status === 'active' || status === 'locked' ? `${state.signal.timeLeft}s remaining` : status === 'complete' ? 'current aligned' : '18 seconds');
  const copy = {
    active: 'Follow the pulse · arrows or W, A, S, D',
    locked: 'Signal caught · next pulse incoming…',
    complete: `Circuit complete · ${state.signal.score} points`,
    idle: 'Ready when you are',
  };
  setText('#signal-status', copy[status] || copy.idle);
  const start = $('#signal-start');
  if (start) {
    start.disabled = state.signal.verifying;
    start.innerHTML = state.signal.verifying ? 'Verifying run…' : status === 'active' || status === 'locked' ? 'Abort run <span>×</span>' : status === 'complete' ? 'Run again <span>↗</span>' : 'Start signal trace <span>↗</span>';
  }
  $$('[data-signal-direction]').forEach((button) => {
    button.disabled = status !== 'active' || state.signal.verifying;
    button.classList.toggle('selected', button.dataset.signalDirection === state.signal.target && status === 'active');
  });
  if (!state.signal.active && !state.signal.verifying) renderSignalAvailability();
}
function signalClearTimers() {
  clearInterval(state.signal.timer);
  clearTimeout(state.signal.targetTimer);
  state.signal.timer = null;
  state.signal.targetTimer = null;
  state.signal.locked = false;
  $$('[data-signal-direction]').forEach((button) => button.classList.remove('correct', 'wrong', 'selected'));
}
function signalNextTarget() {
  const current = signalDirections.findIndex((direction) => direction.key === state.signal.target);
  let next = Math.floor(Math.random() * signalDirections.length);
  if (signalDirections.length > 1 && next === current) next = (next + 1) % signalDirections.length;
  state.signal.target = signalDirections[next].key;
  signalState('active');
}
function chooseSignal(event) {
  if (!state.signal.active || state.signal.locked) return;
  const choice = event.currentTarget.dataset.signalDirection;
  const button = event.currentTarget;
  const correct = choice === state.signal.target;
  state.signal.locked = true;
  button.classList.add(correct ? 'correct' : 'wrong');
  if (correct) {
    state.signal.combo += 1;
    state.signal.score += 18 + Math.min(54, (state.signal.combo - 1) * 6);
    haptic(state.signal.combo % 4 === 0 ? 'medium' : 'light');
    signalState('locked');
  } else {
    state.signal.combo = 0;
    haptic('heavy');
    setText('#signal-status', `Wrong direction · follow ${signalDirection(state.signal.target).name}`);
  }
  state.signal.targetTimer = setTimeout(() => {
    button.classList.remove('correct', 'wrong');
    state.signal.locked = false;
    signalNextTarget();
  }, correct ? 250 : 420);
}
function finishSignalGame(success = false, aborted = false) {
  if (!state.signal.active && !state.signal.verifying) return;
  signalClearTimers();
  state.signal.active = false;
  if (state.signal.score > state.signal.best) {
    state.signal.best = state.signal.score;
    localStorage.setItem('summon-signal-best', String(state.signal.best));
  }
  if (aborted) {
    state.signal.timeLeft = 18;
    state.signal.score = 0;
    state.signal.combo = 0;
    signalState('idle');
    return;
  }
  if (!success) return;
  const finalScore = state.signal.score;
  state.signal.verifying = true;
  state.signal.timeLeft = 0;
  signalState('complete');
  haptic('heavy');
  setText('#signal-status', 'Verifying your signal run…');
  api('/api/miniapp/game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game: 'signal_trace', score: finalScore, event_id: eventId() }),
  }).then(async (result) => {
    showReward('signal_trace', result.winnings);
    await load({ quiet: true });
  }).catch(async (error) => {
    showToast(error.message || 'Run complete, but the reward could not be recorded.', true);
    setText('#signal-status', 'Run complete · reward verification unavailable');
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  }).finally(() => {
    state.signal.verifying = false;
    signalState('complete');
    renderSignalAvailability();
  });
}
function startSignalGame() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Signal Trace.', true); return; }
  if (state.signal.verifying) return;
  if (!state.signal.active && state.data?.cooldowns?.signal_trace && !state.data.cooldowns.signal_trace.available) {
    showToast(`The next signal reward is available in ${duration(state.data.cooldowns.signal_trace.remaining_seconds)}.`, true);
    return;
  }
  if (state.signal.active) { finishSignalGame(false, true); return; }
  signalClearTimers();
  state.signal.active = true;
  state.signal.timeLeft = 18;
  state.signal.score = 0;
  state.signal.combo = 0;
  state.signal.target = signalDirections[Math.floor(Math.random() * signalDirections.length)].key;
  signalState('active');
  state.signal.timer = setInterval(() => {
    state.signal.timeLeft -= 1;
    if (state.signal.timeLeft <= 0) {
      state.signal.timeLeft = 0;
      finishSignalGame(true);
    } else signalState('active');
  }, 1000);
  $('#signal-board')?.focus({ preventScroll: true });
  haptic('light');
}


function arenaFormatTime(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}
async function arenaApi(action, payload = {}) {
  const result = await api('/api/miniapp/arena', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...payload }),
  });
  return result.room;
}
function arenaMe(room = state.arena.room) {
  return room?.players?.find((player) => player.is_you) || null;
}
function arenaOpponent(room = state.arena.room) {
  return room?.players?.find((player) => !player.is_you) || null;
}
function arenaClearTimer() {
  clearInterval(state.arena.timer);
  state.arena.timer = null;
}
function arenaStopPolling() {
  clearInterval(state.arena.pollTimer);
  state.arena.pollTimer = null;
}
function arenaResetLocal() {
  arenaClearTimer();
  arenaStopPolling();
  state.arena.room = null;
  state.arena.running = false;
  state.arena.submitted = false;
  state.arena.sequence = [];
  state.arena.step = 0;
  state.arena.score = 0;
  state.arena.combo = 0;
  state.arena.timeLeft = 18;
  const lobby = $('#arena-lobby');
  const room = $('#arena-room');
  if (lobby) lobby.hidden = state.guest;
  if (room) room.hidden = true;
  arenaState('idle');
}
function arenaRenderPlayers(room) {
  const node = $('#arena-players');
  if (!node) return;
  node.replaceChildren();
  const players = room?.players || [];
  [players[0], players[1]].forEach((player, index) => {
    const card = document.createElement('article');
    card.className = `arena-player ${player?.is_you ? 'you' : ''} ${player ? '' : 'empty'}`;
    const badge = document.createElement('span');
    badge.className = 'arena-player-badge';
    badge.textContent = player ? (player.is_you ? 'YOU' : 'RIVAL') : `SLOT 0${index + 1}`;
    const avatar = document.createElement('span');
    avatar.className = 'arena-player-avatar';
    avatar.textContent = player ? initials(player.name) : '+';
    const copy = document.createElement('span');
    copy.className = 'arena-player-copy';
    const name = document.createElement('b');
    name.textContent = player ? player.name : 'Open slot';
    const status = document.createElement('small');
    status.textContent = player ? (room.status === 'complete' ? `${player.score ?? 0} points` : player.ready ? 'Ready signal locked' : 'Choosing a loadout') : 'Share the code to invite';
    copy.append(name, status);
    const stateMark = document.createElement('span');
    stateMark.className = `arena-player-state ${player?.ready ? 'ready' : ''}`;
    stateMark.textContent = player?.ready ? '✓' : player ? '…' : '·';
    card.append(badge, avatar, copy, stateMark);
    node.append(card);
  });
}
function arenaRenderResult(room) {
  const result = $('#arena-result');
  if (!result) return;
  const complete = room?.status === 'complete';
  result.hidden = !complete;
  if (!complete) return;
  const medal = $('#arena-result-medal');
  const title = $('#arena-result-title');
  const copy = $('#arena-result-copy');
  const reward = $('#arena-result-reward');
  const outcome = room.winner;
  if (medal) medal.textContent = outcome === 'you' ? '✦' : outcome === 'tie' ? '◇' : '⚔';
  setText('#arena-result-title', outcome === 'you' ? 'You won the relay' : outcome === 'tie' ? 'A perfectly matched draw' : 'Relay complete');
  setText('#arena-result-copy', outcome === 'you' ? `${room.winner_name || 'Your run'} took the lead. Server-selected coins are now in your ledger.` : outcome === 'tie' ? 'Both signals landed together. Your tie reward was selected by the server.' : `${room.winner_name || 'Your rival'} took the lead. Your participation reward is still secured.`);
  setText('#arena-result-reward', `+${coins(room.reward)} COINS`);
  if (reward) reward.className = `arena-result-reward ${outcome === 'you' ? 'winner' : ''}`;
}
function arenaRender(room) {
  if (!room) return;
  state.arena.room = room;
  const lobby = $('#arena-lobby');
  const roomPanel = $('#arena-room');
  if (lobby) lobby.hidden = true;
  if (roomPanel) roomPanel.hidden = false;
  setText('#arena-room-code', room.code);
  setText('#arena-room-expiry', arenaFormatTime(room.expires_in));
  arenaRenderPlayers(room);
  const me = arenaMe(room);
  const opponent = arenaOpponent(room);
  const bothReady = Boolean(me?.ready && opponent?.ready);
  const waiting = $('#arena-waiting');
  const readyActions = $('#arena-ready-actions');
  const readyButton = $('#arena-ready');
  const startCard = $('#arena-start-card');
  const startButton = $('#arena-start-run');
  const duel = $('#arena-duel');
  if (room.status === 'complete') {
    setText('#arena-room-status', 'Match settled · ledger updated');
  } else if (!opponent) {
    setText('#arena-room-status', 'Waiting for a second player…');
  } else if (!bothReady) {
    setText('#arena-room-status', 'Both players must lock their ready signal.');
  } else if (room.status === 'running') {
    setText('#arena-room-status', 'Relay in progress · scores are sealed on submit');
  } else {
    setText('#arena-room-status', 'Both signals locked · start your relay');
  }
  if (waiting) {
    waiting.hidden = room.status === 'complete' || state.arena.running;
    setText('#arena-waiting-title', !opponent ? 'Waiting for your teammate' : !me?.ready ? 'Lock your ready signal' : !opponent?.ready ? 'Waiting for your rival to ready up' : me?.submitted ? 'Score sealed · waiting for rival' : 'Room is live');
    setText('#arena-waiting-copy', !opponent ? 'Share the room code to bring another player into the relay.' : !bothReady ? 'Both players need to be ready before the circuit unlocks.' : me?.submitted ? 'Your score is safely stored. The result will settle when the other player finishes.' : 'Start when you are ready. Your rival can run at the same time.');
  }
  if (readyActions) readyActions.hidden = room.status === 'complete' || state.arena.running || Boolean(me?.submitted);
  if (readyButton) {
    readyButton.disabled = !opponent || room.status === 'complete' || bothReady || state.arena.running || Boolean(me?.submitted);
    readyButton.innerHTML = me?.ready ? 'Ready signal locked <span>✓</span>' : 'Mark ready <span>✓</span>';
  }
  if (startCard) {
    const canStart = !me?.submitted && !state.arena.running && (bothReady || room.status === 'running');
    startCard.hidden = !canStart || room.status === 'complete';
    if (startButton) startButton.innerHTML = room.status === 'running' ? 'Join relay <span>↗</span>' : 'Start relay <span>↗</span>';
  }
  if (duel) duel.hidden = !state.arena.running || room.status === 'complete';
  arenaRenderResult(room);
  if (room.status === 'complete') arenaStopPolling();
}
async function arenaRefresh(quiet = true) {
  if (!state.arena.room?.code || state.guest) return;
  try {
    const room = await arenaApi('get', { code: state.arena.room.code });
    arenaRender(room);
  } catch (error) {
    if (!quiet) showToast(error.message || 'Could not refresh the room.', true);
    if (error.status === 404 || error.status === 400) arenaResetLocal();
  }
}
function arenaStartPolling() {
  arenaStopPolling();
  state.arena.pollTimer = setInterval(() => arenaRefresh(true), 1500);
}
function arenaSeededSequence(seed, length = 12) {
  let value = (Number(seed) || 1) >>> 0;
  const directions = ['up', 'right', 'down', 'left'];
  return Array.from({ length }, () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return directions[value % directions.length];
  });
}
function arenaState(status = state.arena.running ? 'active' : 'idle') {
  const board = $('#arena-duel');
  const target = state.arena.sequence[state.arena.step] || 'up';
  if (board) board.dataset.state = status;
  setText('#arena-duel-glyph', signalDirection(target).glyph);
  setText('#arena-duel-step', `${String(Math.min(state.arena.step + 1, state.arena.sequence.length || 12)).padStart(2, '0')} / ${state.arena.sequence.length || 12}`);
  setText('#arena-duel-score', state.arena.score);
  setText('#arena-duel-time', `${Math.max(0, state.arena.timeLeft)}s`);
  setText('#arena-duel-progress', status === 'active' ? `${state.arena.timeLeft}s remaining` : status === 'complete' ? 'score submitted' : '12 pulses');
  setText('#arena-duel-status', status === 'active' ? `Trace pulse ${state.arena.step + 1}` : status === 'complete' ? 'Score sealed · waiting for rival' : 'Ready when you are');
  $$('[data-arena-direction]').forEach((button) => {
    button.disabled = status !== 'active';
    button.classList.toggle('selected', button.dataset.arenaDirection === target && status === 'active');
  });
}
function arenaFinishRun() {
  if (!state.arena.running || state.arena.submitted) return;
  arenaClearTimer();
  state.arena.running = false;
  state.arena.submitted = true;
  arenaState('complete');
  const room = state.arena.room;
  if (!room?.code) return;
  arenaApi('submit', { code: room.code, score: state.arena.score }).then((nextRoom) => {
    arenaRender(nextRoom);
    showToast('Your score is sealed in the private relay.');
  }).catch((error) => {
    state.arena.submitted = false;
    showToast(error.message || 'The relay score could not be submitted.', true);
    arenaState('idle');
  });
}
function arenaChoose(event) {
  if (!state.arena.running) return;
  const choice = event.currentTarget.dataset.arenaDirection;
  const target = state.arena.sequence[state.arena.step];
  if (choice === target) {
    state.arena.combo += 1;
    state.arena.score += 30 + Math.min(70, state.arena.combo * 8);
    state.arena.step += 1;
    haptic(state.arena.combo % 4 === 0 ? 'medium' : 'light');
    if (state.arena.step >= state.arena.sequence.length) {
      arenaFinishRun();
      return;
    }
  } else {
    state.arena.combo = 0;
    state.arena.score = Math.max(0, state.arena.score - 10);
    haptic('heavy');
    setText('#arena-duel-status', `Signal mismatch · pulse ${state.arena.step + 1} remains`);
  }
  arenaState('active');
}
function arenaStartRun() {
  const room = state.arena.room;
  const me = arenaMe(room);
  const opponent = arenaOpponent(room);
  if (!room || !me?.ready || !opponent?.ready || me.submitted || state.arena.running) return;
  state.arena.sequence = arenaSeededSequence(room.seed, 12);
  state.arena.step = 0;
  state.arena.score = 0;
  state.arena.combo = 0;
  state.arena.timeLeft = 18;
  state.arena.submitted = false;
  state.arena.running = true;
  arenaState('active');
  const startCard = $('#arena-start-card');
  if (startCard) startCard.hidden = true;
  state.arena.timer = setInterval(() => {
    state.arena.timeLeft -= 1;
    if (state.arena.timeLeft <= 0) {
      state.arena.timeLeft = 0;
      arenaFinishRun();
    } else arenaState('active');
  }, 1000);
  $('#arena-duel')?.focus({ preventScroll: true });
  haptic('light');
}
async function createArenaRoom() {
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Duo Arena.', true); return; }
  const button = $('#arena-create');
  if (button) { button.disabled = true; button.innerHTML = 'Creating room…'; }
  try {
    const room = await arenaApi('create');
    arenaRender(room);
    arenaStartPolling();
    showToast(`Room ${room.code} created · invite a player.`);
  } catch (error) {
    showToast(error.message || 'Could not create a room.', true);
  } finally { if (button) { button.disabled = false; button.innerHTML = 'Create room <span>↗</span>'; } }
}
async function joinArenaRoom(event) {
  event.preventDefault();
  if (state.guest) { showToast('Open the Mini App in Telegram to enter Duo Arena.', true); return; }
  const input = $('#arena-code');
  const code = String(input?.value || '').trim().toUpperCase();
  if (!code) return;
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  if (submit) { submit.disabled = true; submit.innerHTML = 'Joining…'; }
  try {
    const room = await arenaApi('join', { code });
    arenaRender(room);
    arenaStartPolling();
    showToast(`Joined room ${room.code}. Lock your ready signal.`);
    if (input) input.value = '';
  } catch (error) {
    showToast(error.message || 'Could not join that room.', true);
  } finally { if (submit) { submit.disabled = false; submit.innerHTML = 'Join <span>→</span>'; } }
}
async function toggleArenaReady() {
  const room = state.arena.room;
  const me = arenaMe(room);
  if (!room || !me || !arenaOpponent(room)) return;
  try {
    const nextRoom = await arenaApi('ready', { code: room.code, ready: !me.ready });
    arenaRender(nextRoom);
  } catch (error) {
    showToast(error.message || 'Could not update readiness.', true);
  }
}
async function leaveArenaRoom() {
  const room = state.arena.room;
  if (room?.code) {
    try { await arenaApi('leave', { code: room.code }); } catch (_) {}
  }
  arenaResetLocal();
  showToast('You left the Duo Arena room.');
}
async function copyArenaCode() {
  const code = state.arena.room?.code;
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code);
    showToast('Room code copied');
  } catch (_) {
    showToast(`Share code ${code} with your teammate.`);
  }
}

function transactionItem(item) {
  const row = document.createElement('article');
  row.className = 'transaction-item transaction-clickable';
  row.tabIndex = 0;
  row.setAttribute('role', 'button');
  row.setAttribute('aria-label', `Open ${gameLabel(item.game)} receipt for ${coins(item.amount)} coins`);
  row.dataset.eventId = item.id || '';
  row.style.setProperty('--item-delay', `${Math.min(5, Math.random() * 5) * 45}ms`);
  const icon = document.createElement('span');
  const iconMode = item.game === 'spin' ? 'spin' : item.game === 'constellation' ? 'constellation' : item.game === 'rune_memory' ? 'memory' : item.game === 'meteor_dodge' ? 'meteor' : item.game === 'orbit_lock' ? 'orbit' : item.game === 'prism_sort' ? 'prism' : item.game === 'signal_trace' ? 'signal' : item.game === 'duo_relay' ? 'duo' : 'daily';
  icon.className = `transaction-icon ${iconMode}`;
  icon.textContent = item.game === 'spin' ? '✹' : item.game === 'constellation' ? '✦' : item.game === 'rune_memory' ? '◈' : item.game === 'meteor_dodge' ? '☄' : item.game === 'orbit_lock' ? '◎' : item.game === 'prism_sort' ? '⬢' : item.game === 'signal_trace' ? '↯' : item.game === 'duo_relay' ? '⚔' : '☀';
  const copy = document.createElement('span');
  copy.className = 'transaction-copy';
  const title = document.createElement('b');
  title.textContent = gameLabel(item.game);
  const details = document.createElement('small');
  details.textContent = `${relative(item.created_at)} · server confirmed`;
  copy.append(title, details);
  const amount = document.createElement('strong');
  amount.className = 'transaction-amount';
  amount.textContent = `+${coins(item.amount)}`;
  const coin = document.createElement('small');
  coin.className = 'transaction-unit';
  coin.textContent = 'COINS';
  const amountWrap = document.createElement('span');
  amountWrap.className = 'transaction-value';
  amountWrap.append(amount, coin);
  row.append(icon, copy, amountWrap);
  const open = () => openTransactionDetail(item);
  row.addEventListener('click', open);
  row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } });
  return row;
}
function renderTransactions(selector, items = [], limit = Infinity) {
  const node = $(selector);
  if (!node) return;
  const visible = visibleTransactions(items);
  if (selector === '#history') {
    setText('#ledger-result-count', visible.length ? `${visible.length} matching event${visible.length === 1 ? '' : 's'}` : 'No matching events');
    setText('#ledger-total', `${coins(visible.reduce((sum, item) => sum + (Number(item.amount) || 0), 0))} coins in view`);
  }
  node.replaceChildren();
  if (!visible.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.innerHTML = '<span>◌</span><b>No matching transactions</b><small>Try another search, range, or filter.</small>';
    node.append(empty);
    return;
  }
  visible.slice(0, limit).forEach((item) => node.append(transactionItem(item)));
}
function renderSparkline(items = []) {
  const svg = $('#balance-sparkline');
  if (!svg) return;
  svg.replaceChildren();
  const values = items.slice(0, 8).reverse().map((item) => Math.max(0, Number(item.amount) || 0));
  const points = values.length > 1 ? values : [0, 0, 0, 0, 0, 0, 0];
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const coords = points.map((value, index) => {
    const x = (index / Math.max(1, points.length - 1)) * 220;
    const y = 61 - (((value - min) / Math.max(1, max - min)) * 43);
    return [x, y];
  });
  const path = coords.map(([x, y], index) => `${index ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const area = `${path} L 220 72 L 0 72 Z`;
  svg.innerHTML = `<defs><linearGradient id="spark-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#8c7bff" stop-opacity=".4"/><stop offset="1" stop-color="#8c7bff" stop-opacity="0"/></linearGradient></defs><path class="spark-area" d="${area}"/><path class="spark-line" d="${path}"/>`;
}
function renderRarities(items = []) {
  const node = $('#guest-rarities');
  if (!node) return;
  node.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('span');
    empty.className = 'muted';
    empty.textContent = 'No catalogue metadata yet.';
    node.append(empty);
    return;
  }
  items.forEach((item) => {
    const pill = document.createElement('span');
    pill.className = 'rarity-pill';
    pill.textContent = `${item.name}: ${fmt.format(item.count || 0)}`;
    node.append(pill);
  });
}
function renderLeaders(entries = []) {
  const node = $('#leaders');
  if (!node) return;
  node.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.innerHTML = '<span>◌</span><b>No leaderboard data yet</b><small>The world is waiting for its first legends.</small>';
    node.append(empty);
    return;
  }
  entries.forEach((entry, index) => {
    const row = document.createElement('article');
    row.className = `leader-row rank-${Math.min(index + 1, 3)}`;
    const rank = document.createElement('span'); rank.className = 'leader-rank'; rank.textContent = `0${entry.rank}`.slice(-2);
    const avatar = document.createElement('span'); avatar.className = 'leader-avatar'; avatar.textContent = initials(entry.name);
    const name = document.createElement('span'); name.className = 'leader-name';
    const primary = document.createElement('b'); primary.textContent = entry.name;
    const secondary = document.createElement('small'); secondary.textContent = entry.is_you ? 'That’s you' : (entry.username ? `@${entry.username}` : 'Summoner');
    name.append(primary, secondary);
    const balance = document.createElement('span'); balance.className = 'leader-coins';
    const balanceValue = document.createElement('b'); balanceValue.textContent = shortFmt.format(entry.balance || 0);
    const balanceUnit = document.createElement('small'); balanceUnit.textContent = ' 🪙';
    balance.append(balanceValue, balanceUnit);
    row.append(rank, avatar, name, balance);
    node.append(row);
  });
}
function renderStreak(streak = {}) {
  const current = Number(streak.current) || 0;
  const best = Number(streak.best) || 0;
  setText('#streak-message', current ? `${current} day${current === 1 ? '' : 's'} on fire` : 'Start your streak');
  setText('#streak-detail', current ? `Best run: ${best} days. Keep the chain alive.` : 'Claim your daily reward to build momentum.');
  setText('#best', best);
  animateNumber('#streak-ring-value', current, (value) => Math.round(value));
  const next = current < 3 ? 3 : current < 7 ? 7 : current + 7;
  setText('#next-milestone', `${next} day streak`);
  const percent = Math.min(100, (current / Math.max(1, next)) * 100);
  const bar = $('#milestone-bar'); if (bar) bar.style.width = `${percent}%`;
}
function renderInsights(history = [], cooldowns = {}) {
  const total = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const today = dateKey(new Date());
  const todayTotal = history.filter((item) => dateKey(item.created_at) === today)
    .reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const average = history.length ? Math.round(total / history.length) : 0;
  const daily = history.filter((item) => item.game === 'daily').length;
  const spin = history.filter((item) => item.game === 'spin').length;
  const constellation = history.filter((item) => item.game === 'constellation').length;
  const memory = history.filter((item) => item.game === 'rune_memory').length;
  const meteor = history.filter((item) => item.game === 'meteor_dodge').length;
  const orbit = history.filter((item) => item.game === 'orbit_lock').length;
  const prism = history.filter((item) => item.game === 'prism_sort').length;
  const signal = history.filter((item) => item.game === 'signal_trace').length;
  const duo = history.filter((item) => item.game === 'duo_relay').length;
  const modes = [['Daily vault', daily], ['Cosmic spin', spin], ['Constellation hunt', constellation], ['Rune recall', memory], ['Meteor dodge', meteor], ['Orbit lock', orbit], ['Prism sort', prism], ['Signal trace', signal], ['Duo relay', duo]].sort((a, b) => b[1] - a[1]);
  const favourite = history.length && modes[0][1] > 0 ? modes[0][0] : '—';
  setText('#earned-total', coins(todayTotal));
  setText('#average-reward', coins(average));
  setText('#favorite-mode', favourite);
  setText('#favorite-detail', history.length ? `${Math.max(daily, spin, constellation, memory, meteor, orbit, prism, signal, duo)} verified claims` : 'waiting for activity');
  const available = Object.entries(cooldowns).filter(([, value]) => value?.available);
  const next = available.length ? null : Object.entries(cooldowns).sort((a, b) => (a[1]?.remaining_seconds || 0) - (b[1]?.remaining_seconds || 0))[0];
  if (!next) {
    setText('#next-window', 'Ready');
    setText('#next-window-detail', 'Your next reward is available.');
  } else {
    setText('#next-window', duration(next[1]?.remaining_seconds));
    setText('#next-window-detail', `${gameLabel(next[0])} unlocks next.`);
  }
}
function renderPulse(history = [], streak = {}) {
  const node = $('#activity-bars');
  if (!node) return;
  const now = new Date();
  const days = Array.from({ length: 7 }, (_, offset) => {
    const date = new Date(now);
    date.setHours(12, 0, 0, 0);
    date.setDate(now.getDate() - (6 - offset));
    const key = dateKey(date);
    const events = history.filter((item) => dateKey(item.created_at) === key);
    return { date, key, count: events.length, amount: events.reduce((sum, item) => sum + (Number(item.amount) || 0), 0) };
  });
  const max = Math.max(...days.map((day) => day.amount), 1);
  node.replaceChildren();
  days.forEach((day, index) => {
    const column = document.createElement('div');
    column.className = `activity-bar ${day.count ? 'has-activity' : ''}`;
    column.style.setProperty('--bar-delay', `${index * 45}ms`);
    column.title = `${day.count} verified event${day.count === 1 ? '' : 's'} · ${coins(day.amount)} coins`;
    column.setAttribute('aria-label', column.title);
    const fill = document.createElement('i');
    fill.style.height = `${day.amount ? Math.max(16, (day.amount / max) * 100) : 7}%`;
    const count = document.createElement('b');
    count.textContent = day.count || '';
    const label = document.createElement('small');
    label.textContent = day.date.toLocaleDateString([], { weekday: 'short' }).slice(0, 2);
    column.append(fill, count, label);
    node.append(column);
  });
  const total = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const activeDays = days.filter((day) => day.count).length;
  const score = Math.min(100, activeDays * 10 + Math.min(30, history.length * 3) + Math.min(35, (Number(streak.current) || 0) * 5) + (history.length ? 10 : 0));
  const scoreRing = $('#pulse-score-ring');
  if (scoreRing) scoreRing.style.setProperty('--pulse-progress', score);
  animateNumber('#pulse-score', score, (value) => Math.round(value), 550);
  setText('#pulse-total', coins(total));
  setText('#pulse-active-days', `${activeDays}/7`);
  setText('#pulse-message', score >= 75 ? 'Excellent momentum' : score >= 40 ? 'Your rhythm is building' : 'Start your next run');
  setText('#pulse-detail', history.length ? `${history.length} recent verified event${history.length === 1 ? '' : 's'} shaping this pulse.` : 'Your first verified claim will start the pulse.');
}
function updateLiveTicker(history = []) {
  const node = $('#live-ticker');
  if (!node) return;
  clearInterval(state.tickerTimer);
  const messages = history.length
    ? history.slice(0, 4).map((item) => `${gameLabel(item.game)} · +${coins(item.amount)} coins · ${relative(item.created_at)}`)
    : ['Waiting for your next verified event…', 'Your ledger is protected by server checks.'];
  let index = 0;
  const paint = () => {
    node.classList.remove('ticker-swap');
    void node.offsetWidth;
    node.innerHTML = `<span class="ticker-dot"></span><span>${messages[index]}</span>`;
    node.classList.add('ticker-swap');
    index = (index + 1) % messages.length;
  };
  paint();
  if (!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    state.tickerTimer = setInterval(paint, 4800);
  }
}
function openTransactionDetail(item) {
  const dialog = $('#transaction-detail');
  if (!dialog) return;
  state.selectedTransaction = item;
  const spin = item.game === 'spin';
  const constellation = item.game === 'constellation';
  const memory = item.game === 'rune_memory';
  const meteor = item.game === 'meteor_dodge';
  const orbit = item.game === 'orbit_lock';
  const prism = item.game === 'prism_sort';
  const signal = item.game === 'signal_trace';
  const duo = item.game === 'duo_relay';
  setText('#transaction-detail-title', `${gameLabel(item.game)} receipt`);
  setText('#transaction-detail-copy', duo ? 'Your two-player relay was settled by the server and written to the secure ledger.' : signal ? 'Your directional reaction run was verified and written to the secure ledger.' : prism ? 'Your color-sorting run was verified and written to the secure ledger.' : orbit ? 'Your orbit timing run was verified and written to the secure ledger.' : meteor ? 'Your survival run was verified and written to the secure ledger.' : memory ? 'Your rune sequence was verified and written to the secure ledger.' : constellation ? 'Your constellation run was verified and written to the secure ledger.' : spin ? 'Your cosmic result was signed and written to the secure ledger.' : 'Your daily vault result was signed and written to the secure ledger.');
  setText('#transaction-detail-amount', `+${coins(item.amount)} COINS`);
  setText('#transaction-detail-type', gameLabel(item.game));
  setText('#transaction-detail-time', formatDate(item.created_at));
  setText('#transaction-detail-id', item.id ? String(item.id).slice(0, 18) : 'Server event');
  const copyButton = $('#copy-transaction-ref');
  if (copyButton) copyButton.disabled = !item.id;
  const icon = $('#transaction-detail-icon');
  if (icon) { icon.textContent = duo ? '⚔' : signal ? '↯' : prism ? '⬢' : orbit ? '◎' : meteor ? '☄' : memory ? '◈' : constellation ? '✦' : spin ? '✹' : '☀'; icon.classList.toggle('spin-receipt', spin); icon.classList.toggle('constellation-receipt', constellation); icon.classList.toggle('memory-receipt', memory); icon.classList.toggle('meteor-receipt', meteor); icon.classList.toggle('orbit-receipt', orbit); icon.classList.toggle('prism-receipt', prism); icon.classList.toggle('signal-receipt', signal); icon.classList.toggle('duo-receipt', duo); }
  if (dialog.showModal) dialog.showModal();
}
async function copyTransactionReference() {
  const reference = state.selectedTransaction?.id;
  if (!reference) { showToast('This receipt has no public reference.', true); return; }
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(String(reference));
    showToast('Receipt reference copied');
  } catch (_) {
    try {
      const input = document.createElement('textarea');
      input.value = reference;
      input.style.position = 'fixed'; input.style.opacity = '0';
      document.body.append(input); input.select();
      const copied = document.execCommand?.('copy');
      input.remove();
      if (!copied) throw new Error('copy unavailable');
      showToast('Receipt reference copied');
    } catch (__) {
      showToast('Copy is unavailable in this browser.', true);
    }
  }
}
function downloadReceipt() {
  const item = state.selectedTransaction;
  if (!item) return;
  const receipt = {
    event_id: item.id || null,
    game: gameLabel(item.game),
    amount: Number(item.amount) || 0,
    recorded_at: item.created_at || null,
    verification: 'server-confirmed',
  };
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], { type: 'application/json' }));
  link.download = `summon-receipt-${String(item.id || 'event').slice(0, 24)}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast('Receipt saved locally');
}
function downloadHistory() {
  const history = visibleTransactions(state.data?.history || []);
  if (!history.length) { showToast('There are no matching transactions to export.', true); return; }
  const rows = [['event_id', 'game', 'amount', 'created_at'], ...history.map((item) => [item.id || '', item.game || '', item.amount || 0, item.created_at || ''])];
  const csv = rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  link.download = `summon-ledger-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(`${history.length} ledger event${history.length === 1 ? '' : 's'} exported`);
}
function renderMissions(history = []) {
  const totalCoins = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const uniqueModes = new Set(history.map((item) => item.game).filter(Boolean)).size;
  const values = {
    signal: { value: Math.min(1, history.length), goal: 1 },
    modes: { value: Math.min(4, uniqueModes), goal: 4 },
    coins: { value: Math.min(1000, totalCoins), goal: 1000 },
    prism: { value: Math.min(1, history.filter((item) => item.game === 'prism_sort').length), goal: 1 },
    'signal-trace': { value: Math.min(1, history.filter((item) => item.game === 'signal_trace').length), goal: 1 },
    'duo-relay': { value: Math.min(1, history.filter((item) => item.game === 'duo_relay').length), goal: 1 },
  };
  let complete = 0;
  Object.entries(values).forEach(([key, mission]) => {
    const percent = Math.min(100, Math.round((mission.value / mission.goal) * 100));
    if (percent >= 100) complete += 1;
    setText(`#mission-${key}-value`, key === 'coins' ? coins(mission.value) : mission.value);
    setText(`#mission-${key}-status`, `${percent}%`);
    const bar = $(`#mission-${key}-bar`);
    if (bar) bar.style.transform = `scaleX(${percent / 100})`;
  });
  setText('#mission-complete', `${complete}/6`);
}
function renderIntel(history = [], source = state) {
  const data = source?.data || {};
  const cooldowns = data.cooldowns || {};
  const total = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const counts = new Map();
  history.forEach((item) => counts.set(item.game, (counts.get(item.game) || 0) + 1));
  const modes = [
    ['daily', 'Daily vault', '☀', 'daily'],
    ['spin', 'Cosmic spin', '✹', 'spin'],
    ['constellation', 'Constellation hunt', '✦', 'constellation'],
    ['rune_memory', 'Rune recall', '◈', 'memory'],
    ['meteor_dodge', 'Meteor dodge', '☄', 'meteor'],
    ['orbit_lock', 'Orbit lock', '◎', 'orbit'],
    ['prism_sort', 'Prism sort', '⬢', 'prism'],
    ['signal_trace', 'Signal trace', '↯', 'signal'],
    ['duo_relay', 'Duo relay', '⚔', 'duo'],
  ];
  const ranked = modes.map(([game, label, icon, style]) => ({ game, label, icon, style, count: counts.get(game) || 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  const list = $('#intel-mode-list');
  if (list) {
    list.replaceChildren();
    const max = Math.max(...ranked.map((item) => item.count), 1);
    if (!history.length) {
      const empty = document.createElement('div');
      empty.className = 'intel-empty';
      empty.innerHTML = '<span>⌁</span><b>No signal yet</b><small>Your first verified run will appear here.</small>';
      list.append(empty);
    } else {
      ranked.filter((item) => item.count > 0).forEach((item) => {
        const row = document.createElement('div');
        row.className = 'intel-mode-row';
        const icon = document.createElement('span');
        icon.className = `intel-mode-icon ${item.style}`;
        icon.textContent = item.icon;
        const copy = document.createElement('span');
        copy.className = 'intel-mode-copy';
        const name = document.createElement('b');
        name.textContent = item.label;
        const track = document.createElement('i');
        const fill = document.createElement('em');
        fill.style.width = `${Math.max(10, (item.count / max) * 100)}%`;
        track.append(fill);
        copy.append(name, track);
        const count = document.createElement('strong');
        count.textContent = `${item.count}×`;
        row.append(icon, copy, count);
        list.append(row);
      });
    }
  }
  setText('#intel-events', history.length);
  setText('#intel-total-coins', coins(total));
  setText('#intel-mode-count', new Set(history.map((item) => item.game).filter(Boolean)).size);
  setText('#intel-streak', data.streak?.current || 0);
  const ready = Object.values(cooldowns).filter((item) => item?.available).length;
  const totalWindows = Math.max(9, Object.keys(cooldowns).length);
  setText('#intel-ready-count', `${ready}/${totalWindows}`);
  const readyBar = $('#intel-ready-bar');
  if (readyBar) readyBar.style.width = `${Math.round((ready / totalWindows) * 100)}%`;
  const nextReady = ranked.find((item) => !counts.get(item.game)) || ranked[0];
  const nextLocked = Object.entries(cooldowns).filter(([, item]) => item && !item.available).sort((a, b) => (a[1].remaining_seconds || 0) - (b[1].remaining_seconds || 0))[0];
  if (nextReady) {
    setText('#intel-next-mode', nextReady.count ? `${nextReady.label} again` : nextReady.label);
    setText('#intel-next-copy', nextLocked ? `${gameLabel(nextLocked[0])} unlocks in ${duration(nextLocked[1].remaining_seconds)}.` : 'A fresh route is ready to shape your next signal.');
  }
}
function render(data) {
  setGuestMode(false);
  state.data = data;
  const user = data.user || {};
  const collection = data.collection || {};
  const streak = data.streak || {};
  const history = data.history || [];
  const name = user.first_name || 'Summoner';
  const percent = Number(collection.percent || 0);
  setText('#welcome-copy', 'Your collection is waiting for its next legendary pull.');
  setText('#name', name);
  setText('#hero-avatar', initials(name));
  setText('#avatar', initials(name));
  setText('#account-avatar', initials(name));
  setText('#account-name', name);
  setText('#account-handle', user.username ? `@${user.username}` : 'Telegram WebApp session');
  animateNumber('#balance', data.balance, coins, 850);
  setText('#balance-change', history.length ? `+${coins(history[0]?.amount)} last reward` : '● synced');
  setText('#rank', data.rank ? `#${fmt.format(data.rank)}` : 'Unranked');
  setText('#streak', `${fmt.format(streak.current || 0)} days`);
  setText('#collection', `${fmt.format(collection.unique || 0)}/${fmt.format(collection.catalogue || 0)}`);
  setText('#copies', fmt.format(collection.copies || 0));
  setText('#collection-percent', `${percent}% complete`);
  setText('#progress-percent', Math.round(percent));
  setText('#ring-value', `${percent}%`);
  setText('#owned', `${fmt.format(collection.unique || 0)} owned`);
  setText('#catalogue', `${fmt.format(collection.catalogue || 0)} in catalogue`);
  setText('#reward-count', history.length);
  setText('#leaderboard-badge', '✓ SECURE');
  setText('#last-sync', `Synced ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
  setProgress('#collection-bar', percent);
  setProgress('#wide-bar', percent);
  renderGames(data.cooldowns);
  renderTransactions('#recent', history, 4);
  renderTransactions('#history', history);
  renderSparkline(history);
  renderStreak(streak);
  renderInsights(history, data.cooldowns || {});
  renderPulse(history, streak);
  renderMissions(history);
  renderIntel(history, state);
  updateLiveTicker(history);
  startCooldownTicker();
}
function renderPublic(data) {
  setGuestMode(true);
  if (state.practice.active) finishPracticeGame(true);
  if (state.memory.active) finishMemoryGame(false, true);
  if (state.memory.verifying) { state.memory.verifying = false; memoryState('idle'); }
  if (state.meteor.active) finishMeteorGame(false, true);
  if (state.meteor.verifying) { state.meteor.verifying = false; meteorState('idle'); }
  if (state.orbit.active) finishOrbitGame(false, true);
  if (state.orbit.verifying) { state.orbit.verifying = false; orbitState('idle'); }
  if (state.prism.active) finishPrismGame(false, true);
  if (state.prism.verifying) { state.prism.verifying = false; prismState('idle'); }
  if (state.signal.active) finishSignalGame(false, true);
  if (state.signal.verifying) { state.signal.verifying = false; signalState('idle'); }
  arenaResetLocal();
  clearInterval(state.cooldownTimer);
  state.cooldownTimer = null;
  state.data = data;
  const catalogue = data.catalogue || {};
  setText('#welcome-copy', 'Explore the public catalogue and see who leads the world.');
  setText('#name', 'Guest Explorer');
  setText('#hero-avatar', 'G');
  setText('#avatar', 'G');
  setText('#guest-catalogue', fmt.format(catalogue.total || 0));
  setText('#leaderboard-badge', '✓ PUBLIC');
  setText('#last-sync', 'Public data synced');
  renderRarities(catalogue.rarities || []);
  renderLeaders(data.leaderboard || []);
  updateLiveTicker([]);
  navigate('home');
}

async function loadPublic({ quiet = false } = {}) {
  if (!quiet) setConnection('', 'Connecting');
  try {
    const data = await api('/api/miniapp/public');
    renderPublic(data);
    setConnection('ready', 'Public');
    $('#alert').hidden = true;
    if (!quiet) showToast('Public preview synced');
    return data;
  } catch (error) {
    setConnection('error', 'Offline');
    $('#alert').hidden = false;
    setText('#alert-text', error.message || 'Public preview is unavailable.');
    if (!quiet) showToast(error.message || 'Could not load public preview', true);
    throw error;
  }
}
async function load({ quiet = false } = {}) {
  if (!initData) return loadPublic({ quiet });
  if (!quiet) setConnection('', 'Connecting');
  try {
    const data = await api('/api/miniapp/me');
    render(data);
    setConnection('ready', 'Secure');
    $('#alert').hidden = true;
    if (!quiet) showToast('Secure dashboard synced');
    try { renderLeaders((await api('/api/miniapp/leaderboard')).entries); } catch (_) { renderLeaders([]); }
    return data;
  } catch (error) {
    if (error.status === 401) return loadPublic({ quiet });
    setConnection('error', 'Offline');
    $('#alert').hidden = false;
    setText('#alert-text', error.message || 'Open this page inside Telegram to authenticate.');
    if (!quiet) showToast(error.message || 'Could not sync dashboard', true);
    throw error;
  }
}

function launchConfetti() {
  const node = $('#confetti');
  if (!node) return;
  node.replaceChildren();
  const colors = ['#8c7bff', '#64e8f3', '#ff73b7', '#ffd66b', '#6ee3a6'];
  for (let index = 0; index < 30; index += 1) {
    const bit = document.createElement('i');
    bit.style.setProperty('--x', `${(Math.random() * 180) - 90}px`);
    bit.style.setProperty('--y', `${-40 - (Math.random() * 150)}px`);
    bit.style.setProperty('--r', `${Math.random() * 720 - 360}deg`);
    bit.style.setProperty('--c', colors[index % colors.length]);
    bit.style.setProperty('--d', `${Math.random() * 300}ms`);
    node.append(bit);
  }
  setTimeout(() => node.replaceChildren(), 1400);
}
function showReward(game, amount) {
  const dialog = $('#reward');
  setText('#reward-title', game === 'spin' ? 'Cosmic hit!' : game === 'constellation' ? 'Constellation secured!' : game === 'rune_memory' ? 'Rune vault opened!' : game === 'meteor_dodge' ? 'Storm cleared!' : game === 'orbit_lock' ? 'Orbit secured!' : game === 'prism_sort' ? 'Prism run cleared!' : game === 'signal_trace' ? 'Signal traced!' : 'Daily vault opened');
  setText('#reward-amount', `+${coins(amount)}`);
  launchConfetti();
  haptic('heavy');
  if (dialog?.showModal) dialog.showModal();
  else showToast(`You won ${coins(amount)} coins.`);
}
async function play(game) {
  if (state.guest) { showToast('Sign in through Telegram to earn rewards.', true); return; }
  if (state.busy) return;
  state.busy = true;
  renderGames(state.data?.cooldowns);
  haptic('medium');
  document.body.classList.add('playing');
  try {
    const result = await api('/api/miniapp/game', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game, event_id: eventId() }),
    });
    showReward(game, result.winnings);
    await load({ quiet: true });
  } catch (error) {
    showToast(error.message || 'Reward could not be recorded', true);
    if (error.status === 409) await load({ quiet: true }).catch(() => {});
  } finally {
    state.busy = false;
    document.body.classList.remove('playing');
    renderGames(state.data?.cooldowns);
  }
}

function navigate(screen) {
  let valid = ['home', 'arcade', 'missions', 'arena', 'intel', 'progress'].includes(screen) ? screen : 'home';
  if (state.guest && ['arcade', 'missions', 'arena', 'intel'].includes(valid)) valid = 'home';
  state.screen = valid;
  history.replaceState(null, '', `#${valid}`);
  localStorage.setItem('summon-screen', valid);
  $$('[data-screen]').forEach((section) => { section.hidden = section.dataset.screen !== valid; });
  $$('[data-go]').forEach((button) => button.classList.toggle('selected', button.dataset.go === valid));
  document.body.dataset.screen = valid;
  if (tg?.BackButton) {
    if (valid === 'home') tg.BackButton.hide();
    else { tg.BackButton.show(); tg.BackButton.onClick(() => navigate('home')); }
  }
}
function toggleTheme() {
  const root = document.documentElement;
  const next = root.dataset.theme === 'light' ? 'dark' : 'light';
  root.dataset.theme = next;
  localStorage.setItem('summon-theme', next);
  setText('#theme-icon', next === 'light' ? '☀' : '☾');
}
function setupRevealObserver() {
  const items = $$('.reveal');
  if (!('IntersectionObserver' in window) || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    items.forEach((item) => item.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }), { threshold: 0.12 });
  items.forEach((item) => observer.observe(item));
}

$$('[data-go]').forEach((button) => button.addEventListener('click', () => { haptic(); navigate(button.dataset.go); }));
$$('[data-game]').forEach((button) => button.addEventListener('click', () => play(button.dataset.game)));
$('#practice-start')?.addEventListener('click', startPracticeGame);
$('#practice-target')?.addEventListener('click', hitPracticeTarget);
$('#memory-start')?.addEventListener('click', startMemoryGame);
$$('[data-memory-tile]').forEach((tile) => tile.addEventListener('click', hitMemoryTile));
$('#meteor-start')?.addEventListener('click', startMeteorGame);
$$('[data-meteor-move]').forEach((button) => button.addEventListener('click', () => meteorMove(button.dataset.meteorMove === 'left' ? -1 : 1)));
$('#orbit-start')?.addEventListener('click', startOrbitGame);
$('#orbit-lock')?.addEventListener('click', lockOrbit);
$('#orbit-board')?.addEventListener('click', (event) => {
  if (event.target.closest('#orbit-lock')) return;
  lockOrbit();
});
$('#prism-start')?.addEventListener('click', startPrismGame);
$$('[data-prism-color]').forEach((button) => button.addEventListener('click', choosePrism));
$('#signal-start')?.addEventListener('click', startSignalGame);
$$('[data-signal-direction]').forEach((button) => button.addEventListener('click', chooseSignal));
$('#arena-create')?.addEventListener('click', createArenaRoom);
$('#arena-join-form')?.addEventListener('submit', joinArenaRoom);
$('#arena-ready')?.addEventListener('click', toggleArenaReady);
$('#arena-start-run')?.addEventListener('click', arenaStartRun);
$('#arena-leave')?.addEventListener('click', leaveArenaRoom);
$('#arena-copy-code')?.addEventListener('click', copyArenaCode);
$$('[data-arena-direction]').forEach((button) => button.addEventListener('click', arenaChoose));
let meteorTouchX = null;
$('#meteor-arena')?.addEventListener('touchstart', (event) => {
  meteorTouchX = event.changedTouches?.[0]?.clientX ?? null;
}, { passive: true });
$('#meteor-arena')?.addEventListener('touchend', (event) => {
  if (meteorTouchX == null) return;
  const endX = event.changedTouches?.[0]?.clientX ?? meteorTouchX;
  const delta = endX - meteorTouchX;
  meteorTouchX = null;
  if (Math.abs(delta) > 24) meteorMove(delta < 0 ? -1 : 1);
}, { passive: true });
document.addEventListener('keydown', (event) => {
  if (!state.meteor.active) return;
  if (event.key === 'ArrowLeft' || event.key.toLowerCase() === 'a') { event.preventDefault(); meteorMove(-1); }
  if (event.key === 'ArrowRight' || event.key.toLowerCase() === 'd') { event.preventDefault(); meteorMove(1); }
});
document.addEventListener('keydown', (event) => {
  if (!state.orbit.active || (event.key !== ' ' && event.key !== 'Enter')) return;
  const target = event.target;
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
  event.preventDefault();
  lockOrbit();
});
document.addEventListener('keydown', (event) => {
  if (!state.prism.active || !['1', '2', '3'].includes(event.key)) return;
  event.preventDefault();
  const button = $(`[data-prism-color="${Number(event.key) - 1}"]`);
  button?.click();
});
document.addEventListener('keydown', (event) => {
  if (!state.signal.active) return;
  const keyMap = { ArrowUp: 'up', ArrowRight: 'right', ArrowDown: 'down', ArrowLeft: 'left', w: 'up', d: 'right', s: 'down', a: 'left' };
  const direction = keyMap[event.key] || keyMap[event.key.toLowerCase()];
  if (!direction) return;
  event.preventDefault();
  const button = $(`[data-signal-direction="${direction}"]`);
  button?.click();
});
document.addEventListener('keydown', (event) => {
  if (!state.arena.running) return;
  const keyMap = { ArrowUp: 'up', ArrowRight: 'right', ArrowDown: 'down', ArrowLeft: 'left', w: 'up', d: 'right', s: 'down', a: 'left' };
  const direction = keyMap[event.key] || keyMap[event.key.toLowerCase()];
  if (!direction) return;
  event.preventDefault();
  const button = $(`[data-arena-direction="${direction}"]`);
  button?.click();
});
function refreshLedgerView() {
  renderTransactions('#recent', state.data?.history || [], 4);
  renderTransactions('#history', state.data?.history || []);
}
$$('[data-transaction-filter]').forEach((button) => button.addEventListener('click', () => {
  state.transactionFilter = button.dataset.transactionFilter || 'all';
  $$('[data-transaction-filter]').forEach((item) => item.classList.toggle('active', item === button));
  refreshLedgerView();
}));
$('#transaction-search')?.addEventListener('input', (event) => {
  state.transactionSearch = event.target.value || '';
  $('#clear-transaction-search').hidden = !state.transactionSearch;
  refreshLedgerView();
});
$('#clear-transaction-search')?.addEventListener('click', () => {
  state.transactionSearch = '';
  const input = $('#transaction-search'); if (input) { input.value = ''; input.focus(); }
  $('#clear-transaction-search').hidden = true;
  refreshLedgerView();
});
$('#transaction-sort')?.addEventListener('change', (event) => { state.transactionSort = event.target.value || 'newest'; refreshLedgerView(); });
$('#transaction-range')?.addEventListener('change', (event) => { state.transactionRange = event.target.value || 'all'; refreshLedgerView(); });
$('#export-history')?.addEventListener('click', downloadHistory);
$('#copy-transaction-ref')?.addEventListener('click', copyTransactionReference);
$('#download-transaction-receipt')?.addEventListener('click', downloadReceipt);
$('#close-transaction')?.addEventListener('click', () => $('#transaction-detail')?.close());
$('#close-transaction-action')?.addEventListener('click', () => $('#transaction-detail')?.close());
$('#transaction-detail')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
async function refreshDashboard() {
  const buttons = [$('#refresh'), $('#hero-refresh')].filter(Boolean);
  buttons.forEach((button) => button.classList.add('is-loading'));
  try { await load(); } catch (_) {} finally { buttons.forEach((button) => button.classList.remove('is-loading')); }
}
$('#refresh')?.addEventListener('click', refreshDashboard);
$('#hero-refresh')?.addEventListener('click', refreshDashboard);
$('#retry')?.addEventListener('click', () => load().catch(() => {}));
$('#theme')?.addEventListener('click', toggleTheme);
$('#avatar')?.addEventListener('click', () => navigate('progress'));
$('#close-reward')?.addEventListener('click', () => $('#reward')?.close());
$('#reward')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
window.addEventListener('hashchange', () => navigate(location.hash.slice(1) || 'home'));
function setPalette(open) {
  const palette = $('#command-palette');
  if (!palette) return;
  palette.hidden = !open;
  if (open) { $('#palette-input')?.focus(); }
}
async function runPaletteAction(action) {
  if (action === 'theme') toggleTheme();
  else if (action === 'sync') await refreshDashboard();
  else if (action === 'search') {
    navigate('arcade');
    setTimeout(() => $('#transaction-search')?.focus(), 0);
  } else if (action === 'export') downloadHistory();
  else navigate(action);
}
$$('[data-close-palette]').forEach((node) => node.addEventListener('click', () => setPalette(false)));
$$('[data-palette-action]').forEach((button) => button.addEventListener('click', async () => {
  await runPaletteAction(button.dataset.paletteAction);
  setPalette(false);
}));
$('#palette-input')?.addEventListener('input', (event) => {
  const query = String(event.target.value || '').toLowerCase();
  $$('.palette-items button').forEach((button) => { button.hidden = query && !button.textContent.toLowerCase().includes(query); });
});
window.addEventListener('keydown', (event) => {
  const key = event.key.toLowerCase();
  if ((event.ctrlKey || event.metaKey) && key === 'k') { event.preventDefault(); setPalette(true); return; }
  if (event.key === 'Escape') { setPalette(false); $('#transaction-detail')?.close(); $('#reward')?.close(); return; }
  const target = event.target;
  const typing = target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
  if (!typing && key === '/' && !state.guest) {
    event.preventDefault();
    navigate('arcade');
    setTimeout(() => $('#transaction-search')?.focus(), 0);
    return;
  }
  const shortcut = { h: 'home', a: 'arcade', m: 'missions', d: 'arena', i: 'intel', p: 'progress', r: 'sync', t: 'theme', e: 'export' }[key];
  if (!typing && !event.ctrlKey && !event.metaKey && !event.altKey && shortcut) {
    event.preventDefault();
    runPaletteAction(shortcut);
  }
});
$$('.game-card, .arcade-game, .stat-card').forEach((card) => card.addEventListener('pointermove', (event) => {
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || window.innerWidth < 700) return;
  const rect = card.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width - .5) * 5;
  const y = ((event.clientY - rect.top) / rect.height - .5) * -5;
  card.style.setProperty('--tilt-x', `${y}deg`);
  card.style.setProperty('--tilt-y', `${x}deg`);
}));
$$('.game-card, .arcade-game, .stat-card').forEach((card) => card.addEventListener('pointerleave', () => { card.style.removeProperty('--tilt-x'); card.style.removeProperty('--tilt-y'); }));

const savedTheme = localStorage.getItem('summon-theme');
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
setText('#theme-icon', document.documentElement.dataset.theme === 'light' ? '☀' : '☾');
setupTelegram();
setupRevealObserver();
practiceState('idle');
memoryState('idle');
meteorState('idle');
orbitState('idle');
prismState('idle');
signalState('idle');
arenaState('idle');
navigate(initData && ['home', 'arcade', 'missions', 'arena', 'intel', 'progress'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home');
loadMotionLibraries().catch(() => {});
load().catch(() => {});
