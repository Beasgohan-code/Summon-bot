const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const initData = tg?.initData || '';
const fmt = new Intl.NumberFormat();
const shortFmt = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });
const PROTOCOLS = {
  quantum_lock: { title: 'Quantum Lock', icon: '⌘', accent: 'quantum', kind: 'grid', page: 'solo' },
  vector_breach: { title: 'Vector Breach', icon: '⌁', accent: 'vector', kind: 'path', page: 'solo' },
  chrono_tactics: { title: 'Chrono Tactics', icon: '◷', accent: 'chrono', kind: 'choice', page: 'solo' },
  neural_forge: { title: 'Neural Forge', icon: '✦', accent: 'neural', kind: 'choice', page: 'solo' },
  aegis_matrix: { title: 'Aegis Matrix', icon: '⬢', accent: 'aegis', kind: 'grid', page: 'solo' },
  pulse_cartography: { title: 'Pulse Cartography', icon: '↯', accent: 'pulse', kind: 'path', page: 'solo' },
  cipher_exchange: { title: 'Cipher Exchange', icon: '◇', accent: 'cipher', kind: 'choice', page: 'solo' },
  helix_protocol: { title: 'Helix Protocol', icon: '∞', accent: 'helix', kind: 'grid', page: 'solo' },
  zero_day_run: { title: 'Zero-Day Run', icon: '⚡', accent: 'zero', kind: 'path', page: 'solo' },
  tactical_draft: { title: 'Tactical Draft', icon: '◆', accent: 'tactical', kind: 'choice', page: 'solo' },
  sentinel_grid: { title: 'Sentinel Grid', icon: '◉', accent: 'sentinel', kind: 'grid', page: 'solo' },
  nova_sequence: { title: 'Nova Sequence', icon: '✹', accent: 'nova', kind: 'path', page: 'solo' },
  command_duel: { title: 'Command Duel', icon: '⚔', accent: 'duel', kind: 'choice', page: 'bots', bot: true },
  adaptive_nemesis: { title: 'Adaptive Nemesis', icon: '◈', accent: 'nemesis', kind: 'path', page: 'bots', bot: true },
  bastion_siege: { title: 'Bastion Siege', icon: '♜', accent: 'bastion', kind: 'choice', page: 'bots', bot: true },
};
const state = {
  data: null,
  guest: false,
  screen: location.hash.slice(1) || 'home',
  toastTimer: null,
  cooldownTimer: null,
  tickerTimer: null,
  selectedTransaction: null,
  transactionFilter: 'all',
  transactionSearch: '',
  transactionSort: 'newest',
  transactionRange: 'all',
  protocol: { session: null, armed: false, answer: [], timer: null },
  arena: { room: null, pollTimer: null, choices: [], submitted: false, mode: 'duo_relay' },
};

function setText(selector, value) { const node = $(selector); if (node) node.textContent = value == null ? '—' : String(value); }
function coins(value) { return fmt.format(Math.max(0, Number(value) || 0)); }
function initials(value) { return String(value || 'S').trim().slice(0, 1).toUpperCase() || 'S'; }
function haptic(type = 'light') { try { tg?.HapticFeedback?.impactOccurred(type); } catch (_) {} }
function reducedMotion() { return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches); }
function showToast(message, error = false) {
  const node = $('#toast'); if (!node) return;
  node.textContent = message; node.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => { node.className = 'toast'; }, 3800);
}
function setConnection(mode, label) { const node = $('#connection'); if (!node) return; node.className = `connection ${mode}`; setText('#connection-label', label); }
function setProgress(selector, percent) { const node = $(selector); if (node) node.style.transform = `scaleX(${Math.max(0, Math.min(100, Number(percent) || 0)) / 100})`; }
function eventId() { return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
function parseTimestamp(value) {
  if (!value) return null;
  const text = String(value);
  const parsed = new Date(text.includes('T') ? text : `${text.replace(' ', 'T')}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
function relative(value) {
  const date = parseTimestamp(value); if (!date) return 'Recently';
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'Just now'; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`; return `${Math.floor(seconds / 86400)}d ago`;
}
function formatDate(value) { const date = parseTimestamp(value); return date ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Recently'; }
function duration(seconds) { const value = Math.max(0, Number(seconds) || 0); const minutes = Math.floor(value / 60); return minutes ? `${minutes}m left` : `${Math.max(1, value)}s left`; }
function gameLabel(game) {
  const labels = {
    quantum_lock: 'Quantum Lock', vector_breach: 'Vector Breach', chrono_tactics: 'Chrono Tactics', neural_forge: 'Neural Forge', aegis_matrix: 'Aegis Matrix', pulse_cartography: 'Pulse Cartography', cipher_exchange: 'Cipher Exchange', helix_protocol: 'Helix Protocol', zero_day_run: 'Zero-Day Run', tactical_draft: 'Tactical Draft', sentinel_grid: 'Sentinel Grid', nova_sequence: 'Nova Sequence', command_duel: 'Command Duel', adaptive_nemesis: 'Adaptive Nemesis', bastion_siege: 'Bastion Siege', duo_relay: 'Squad Relay',
  };
  return labels[game] || 'Verified protocol';
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, cache: 'no-store', credentials: 'same-origin', headers: { 'X-Telegram-Init-Data': initData, ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({ ok: false, error: 'Invalid server response' }));
  if (!response.ok || data.ok === false) { const error = new Error(data.error || `Request failed (${response.status})`); error.status = response.status; throw error; }
  return data;
}
function setupTelegram() {
  if (!tg) return;
  tg.ready(); tg.expand();
  try { tg.setHeaderColor(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()); tg.setBackgroundColor(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()); } catch (_) {}
}
function setGuestMode(guest) {
  state.guest = Boolean(guest); document.body.classList.toggle('guest-mode', state.guest);
  $$('[data-private]').forEach((node) => { node.hidden = state.guest; });
  const banner = $('#guest-banner'); if (banner) banner.hidden = !state.guest;
  const overview = $('#guest-overview'); if (overview) overview.hidden = !state.guest;
  const privateTitle = $('#private-progress-title'); if (privateTitle) privateTitle.hidden = state.guest;
  const guestTitle = $('#guest-progress-title'); if (guestTitle) guestTitle.hidden = !state.guest;
}
function animateNumber(selector, target, formatter = coins) {
  const node = $(selector); if (!node) return;
  const value = Number(target) || 0;
  if (reducedMotion()) { node.textContent = formatter(value); return; }
  const from = Number(node.dataset.value || 0); node.dataset.value = String(value);
  const started = performance.now();
  const tick = (now) => { const progress = Math.min(1, (now - started) / 650); const eased = 1 - ((1 - progress) ** 3); node.textContent = formatter(from + ((value - from) * eased)); if (progress < 1) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}
function applyTheme() {
  const theme = document.documentElement.dataset.theme || 'light';
  setText('#theme-icon', theme === 'light' ? '☀' : '☾');
  try { tg?.setHeaderColor(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()); tg?.setBackgroundColor(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()); } catch (_) {}
}
function toggleTheme() { const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'; document.documentElement.dataset.theme = next; localStorage.setItem('summon-theme', next); applyTheme(); }
function scrollTop() { window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' }); }
function navigate(screen) {
  const allowed = ['home', 'arcade', 'solo', 'bots', 'missions', 'arena', 'intel', 'progress'];
  let next = allowed.includes(screen) ? screen : 'home';
  if (state.guest && ['arcade', 'solo', 'bots', 'missions', 'arena', 'intel'].includes(next)) next = 'home';
  state.screen = next; history.replaceState(null, '', `#${next}`); localStorage.setItem('summon-screen', next);
  $$('[data-screen]').forEach((section) => { section.hidden = section.dataset.screen !== next; });
  $$('[data-go]').forEach((button) => button.classList.toggle('selected', button.dataset.go === next));
  document.body.dataset.screen = next; scrollTop();
  if (tg?.BackButton) { if (next === 'home') tg.BackButton.hide(); else { tg.BackButton.show(); tg.BackButton.onClick(() => navigate('home')); } }
}

function renderSparkline(items = []) {
  const svg = $('#balance-sparkline'); if (!svg) return; svg.replaceChildren();
  const values = items.slice(0, 8).reverse().map((item) => Math.max(0, Number(item.amount) || 0)); const points = values.length > 1 ? values : [0, 0, 0, 0, 0, 0]; const max = Math.max(...points, 1);
  const coords = points.map((value, index) => [index / Math.max(1, points.length - 1) * 220, 62 - (value / max * 42)]);
  const path = coords.map(([x, y], index) => `${index ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  svg.innerHTML = `<defs><linearGradient id="spark-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#8c7bff" stop-opacity=".35"/><stop offset="1" stop-color="#8c7bff" stop-opacity="0"/></linearGradient></defs><path class="spark-area" d="${path} L 220 72 L 0 72 Z"/><path class="spark-line" d="${path}"/>`;
}
function renderRarities(items = []) { const node = $('#guest-rarities'); if (!node) return; node.replaceChildren(); (items.length ? items : [{ name: 'Network', count: 0 }]).forEach((item) => { const pill = document.createElement('span'); pill.className = 'rarity-pill'; pill.textContent = `${item.name}: ${fmt.format(item.count || 0)}`; node.append(pill); }); }
function renderLeaders(entries = []) {
  const node = $('#leaders'); if (!node) return; node.replaceChildren();
  if (!entries.length) { node.innerHTML = '<div class="empty-state"><span>◌</span><b>No leaderboard data yet</b><small>The first legends are still entering the network.</small></div>'; return; }
  entries.forEach((entry) => { const row = document.createElement('article'); row.className = 'leader-row'; row.innerHTML = `<span class="leader-rank">${String(entry.rank).padStart(2, '0')}</span><span class="leader-avatar">${initials(entry.name)}</span><span class="leader-name"><b>${entry.name}</b><small>${entry.is_you ? 'That’s you' : entry.username ? `@${entry.username}` : 'Summoner'}</small></span><span class="leader-coins"><b>${shortFmt.format(entry.balance || 0)}</b><small> 🪙</small></span>`; node.append(row); });
}
function renderStreak(streak = {}) {
  const current = Number(streak.current) || 0; const best = Number(streak.best) || 0;
  setText('#streak-message', current ? `${current} day${current === 1 ? '' : 's'} stable` : 'Start your chain'); setText('#streak-detail', current ? `Best run: ${best} days. Keep the chain alive.` : 'Complete a verified protocol to build momentum.'); setText('#best', best); setText('#streak', `${fmt.format(current)} days`); setText('#streak-ring-value', current); setText('#next-milestone', `${current < 3 ? 3 : current < 7 ? 7 : current + 7} day streak`); const next = current < 3 ? 3 : current < 7 ? 7 : current + 7; const bar = $('#milestone-bar'); if (bar) bar.style.width = `${Math.min(100, current / next * 100)}%`;
}
function modeCounts(history = []) { const counts = new Map(); history.forEach((item) => counts.set(item.game, (counts.get(item.game) || 0) + 1)); return counts; }
function renderInsights(history = [], cooldowns = {}) {
  const total = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0); const today = new Date().toLocaleDateString();
  const todayTotal = history.filter((item) => parseTimestamp(item.created_at)?.toLocaleDateString() === today).reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const counts = modeCounts(history); const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]); const favourite = ranked[0] ? gameLabel(ranked[0][0]) : '—';
  setText('#earned-total', coins(todayTotal)); setText('#average-reward', coins(history.length ? Math.round(total / history.length) : 0)); setText('#favorite-mode', favourite); setText('#favorite-detail', history.length ? `${history.length} verified events` : 'waiting for activity');
  const ready = Object.values(cooldowns).some((item) => item?.available); const locked = Object.entries(cooldowns).filter(([, item]) => item && !item.available).sort((a, b) => (a[1].remaining_seconds || 0) - (b[1].remaining_seconds || 0))[0];
  setText('#next-window', ready ? 'Ready' : locked ? duration(locked[1].remaining_seconds) : 'Ready'); setText('#next-window-detail', locked ? `${gameLabel(locked[0])} unlocks next.` : 'A fresh protocol is available.');
}
function transactionMatches(item) {
  const query = state.transactionSearch.trim().toLowerCase(); const mode = state.transactionFilter === 'all' || item.game === state.transactionFilter; const text = `${gameLabel(item.game)} ${item.game} ${item.amount} ${item.id}`.toLowerCase();
  if (!mode || query && !text.includes(query)) return false; const date = parseTimestamp(item.created_at);
  if (state.transactionRange === 'today' && (!date || date.toLocaleDateString() !== new Date().toLocaleDateString())) return false;
  if (state.transactionRange === '7d' && (!date || Date.now() - date.getTime() > 7 * 86400000)) return false; return true;
}
function visibleTransactions(items = []) { return items.filter(transactionMatches).sort((a, b) => state.transactionSort === 'largest' ? (Number(b.amount) || 0) - (Number(a.amount) || 0) : state.transactionSort === 'mode' ? gameLabel(a.game).localeCompare(gameLabel(b.game)) : (parseTimestamp(b.created_at)?.getTime() || 0) - (parseTimestamp(a.created_at)?.getTime() || 0)); }
function transactionItem(item) {
  const row = document.createElement('article'); row.className = 'transaction-item transaction-clickable'; row.tabIndex = 0; row.setAttribute('role', 'button'); row.dataset.eventId = item.id || '';
  const icon = item.game === 'quantum_lock' ? '⌘' : item.game === 'vector_breach' ? '⌁' : item.game === 'chrono_tactics' ? '◷' : item.game === 'duo_relay' ? '⚔' : '◈';
  row.innerHTML = `<span class="transaction-icon ${item.game || 'legacy'}">${icon}</span><span class="transaction-copy"><b>${gameLabel(item.game)}</b><small>${relative(item.created_at)} · server confirmed</small></span><span class="transaction-value"><strong>+${coins(item.amount)}</strong><small>COINS</small></span>`;
  const open = () => openTransactionDetail(item); row.addEventListener('click', open); row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } }); return row;
}
function renderTransactions(selector, items = [], limit = Infinity) {
  const node = $(selector); if (!node) return; const visible = visibleTransactions(items); if (selector === '#history') { setText('#ledger-result-count', visible.length ? `${visible.length} matching event${visible.length === 1 ? '' : 's'}` : 'No matching events'); setText('#ledger-total', `${coins(visible.reduce((sum, item) => sum + (Number(item.amount) || 0), 0))} coins in view`); }
  node.replaceChildren(); if (!visible.length) { node.innerHTML = '<div class="empty-state"><span>◌</span><b>No matching receipts</b><small>Try another filter or wait for a verified event.</small></div>'; return; } visible.slice(0, limit).forEach((item) => node.append(transactionItem(item)));
}
function renderMissions(history = []) {
  const counts = modeCounts(history); const total = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0); const families = ['quantum_lock', 'vector_breach', 'chrono_tactics', 'duo_relay'].filter((key) => counts.get(key)).length;
  const values = { events: { value: Math.min(1, history.length), goal: 1 }, modes: { value: Math.min(4, families), goal: 4 }, coins: { value: Math.min(1000, total), goal: 1000 }, quantum: { value: Math.min(1, counts.get('quantum_lock') || 0), goal: 1 }, vector: { value: Math.min(1, counts.get('vector_breach') || 0), goal: 1 }, chrono: { value: Math.min(1, counts.get('chrono_tactics') || 0), goal: 1 }, squad: { value: Math.min(1, counts.get('duo_relay') || 0), goal: 1 } };
  let complete = 0; Object.entries(values).forEach(([key, mission]) => { const percent = Math.round(mission.value / mission.goal * 100); if (percent >= 100) complete += 1; setText(`#mission-${key}-value`, key === 'coins' ? coins(mission.value) : mission.value); setText(`#mission-${key}-status`, `${percent}%`); const bar = $(`#mission-${key}-bar`); if (bar) bar.style.transform = `scaleX(${percent / 100})`; }); setText('#mission-complete', `${complete}/7`);
}
function renderIntel(history = [], source = state) {
  const cooldowns = source.data?.cooldowns || {}; const counts = modeCounts(history); const total = history.reduce((sum, item) => sum + (Number(item.amount) || 0), 0);
  const modes = ['quantum_lock', 'vector_breach', 'chrono_tactics', 'neural_forge', 'aegis_matrix', 'pulse_cartography', 'cipher_exchange', 'helix_protocol', 'zero_day_run', 'tactical_draft', 'sentinel_grid', 'nova_sequence', 'command_duel', 'adaptive_nemesis', 'bastion_siege', 'duo_relay'].map((game) => ({ game, label: gameLabel(game), count: counts.get(game) || 0 })); const list = $('#intel-mode-list');
  if (list) { list.replaceChildren(); const active = modes.filter((item) => item.count).sort((a, b) => b.count - a.count); if (!active.length) list.innerHTML = '<div class="intel-empty"><span>⌁</span><b>No signal yet</b><small>Your first server receipt will appear here.</small></div>'; else active.forEach((item) => { const row = document.createElement('div'); row.className = 'intel-mode-row'; row.innerHTML = `<span class="intel-mode-icon">${PROTOCOLS[item.game]?.icon || '◈'}</span><span class="intel-mode-copy"><b>${item.label}</b><i><em style="width:${Math.max(12, item.count / Math.max(...active.map((entry) => entry.count)) * 100)}%"></em></i></span><strong>${item.count}×</strong>`; list.append(row); }); }
  setText('#intel-events', history.length); setText('#intel-total-coins', coins(total)); setText('#intel-mode-count', new Set(history.map((item) => item.game)).size); setText('#intel-streak', source.data?.streak?.current || 0);
  const ready = Object.values(cooldowns).filter((item) => item?.available).length; const totalWindows = Math.max(13, Object.keys(cooldowns).length); setText('#intel-ready-count', `${ready}/${totalWindows}`); const readyBar = $('#intel-ready-bar'); if (readyBar) readyBar.style.width = `${ready / totalWindows * 100}%`;
  const next = modes.find((item) => !item.count) || modes[0]; setText('#intel-next-mode', next ? next.label : 'Ready'); setText('#intel-next-copy', 'Issue a server-owned protocol and let the receipt set your direction.');
}
function updateTicker(history = []) { const node = $('.live-ticker'); if (!node) return; clearInterval(state.tickerTimer); const messages = history.length ? history.slice(0, 5).map((item) => `${gameLabel(item.game)} · +${coins(item.amount)} coins · ${relative(item.created_at)}`) : ['Challenge authority: online', 'No local scores accepted', 'Immutable ledger: synced']; let index = 0; const paint = () => { node.innerHTML = `<span class="ticker-dot"></span><span>${messages[index]}</span>`; index = (index + 1) % messages.length; }; paint(); if (!reducedMotion()) state.tickerTimer = setInterval(paint, 4800); }

function render(data) {
  setGuestMode(false); state.data = data; const user = data.user || {}; const collection = data.collection || {}; const streak = data.streak || {}; const history = data.history || []; const name = user.first_name || 'Summoner'; const percent = Number(collection.percent || 0);
  setText('#name', name); setText('#hero-avatar', initials(name)); setText('#avatar', initials(name)); setText('#account-avatar', initials(name)); setText('#account-name', name); setText('#account-handle', user.username ? `@${user.username}` : 'Telegram WebApp session'); setText('#welcome-copy', 'Your next protocol is waiting in the secure queue. No local score. No simulated outcomes. Every decision is settled by the server.'); animateNumber('#balance', data.balance); setText('#balance-change', history.length ? `+${coins(history[0]?.amount)} last receipt` : '● synced'); setText('#rank', data.rank ? `#${fmt.format(data.rank)}` : 'Unranked'); setText('#collection', `${fmt.format(collection.unique || 0)}/${fmt.format(collection.catalogue || 0)}`); setText('#copies', fmt.format(collection.copies || 0)); setText('#collection-percent', `${percent}% complete`); setText('#progress-percent', Math.round(percent)); setText('#ring-value', `${percent}%`); setText('#owned', `${fmt.format(collection.unique || 0)} owned`); setText('#catalogue', `${fmt.format(collection.catalogue || 0)} in catalogue`); setText('#reward-count', history.length); setText('#leaderboard-badge', '✓ SECURE'); setText('#last-sync', `Synced ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`); setProgress('#collection-bar', percent); setProgress('#wide-bar', percent);
  renderTransactions('#recent', history, 4); renderTransactions('#history', history); renderSparkline(history); renderStreak(streak); renderInsights(history, data.cooldowns || {}); renderMissions(history); renderIntel(history, state); updateTicker(history); startCooldownTicker();
}
function renderPublic(data) { setGuestMode(true); state.data = data; const catalogue = data.catalogue || {}; setText('#name', 'Guest Explorer'); setText('#avatar', 'G'); setText('#guest-catalogue', fmt.format(catalogue.total || 0)); setText('#leaderboard-badge', '✓ PUBLIC'); setText('#last-sync', 'Public data synced'); setText('#welcome-copy', 'Explore the public protocol layer and see who leads the world.'); renderRarities(catalogue.rarities || []); renderLeaders(data.leaderboard || []); updateTicker([]); navigate('home'); }
function startCooldownTicker() { clearInterval(state.cooldownTimer); state.cooldownTimer = setInterval(() => { if (state.guest || !state.data?.cooldowns) return; let changed = false; Object.values(state.data.cooldowns).forEach((info) => { if (info?.available) return; info.remaining_seconds = Math.max(0, (Number(info.remaining_seconds) || 0) - 1); if (!info.remaining_seconds) info.available = true; changed = true; }); if (changed) { renderInsights(state.data.history || [], state.data.cooldowns); renderIntel(state.data.history || [], state); } }, 1000); }

function protocolApi(action, payload = {}) { return api('/api/miniapp/protocol', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, ...payload }) }).then((result) => result.protocol); }
function clearProtocolTimer() { clearInterval(state.protocol.timer); state.protocol.timer = null; }
function resetProtocolLocal() { clearProtocolTimer(); state.protocol = { session: null, armed: false, answer: [], timer: null }; }
function protocolStatus(message, error = false) { const node = $('#protocol-status'); if (node) { node.textContent = message; node.className = `console-status${error ? ' error' : ''}`; } }
function protocolInputReady() { const session = state.protocol.session; if (!session) return false; const challenge = session.challenge || {}; if (challenge.kind === 'choice') return state.protocol.answer.length === (challenge.scenarios || []).length && state.protocol.answer.every((item) => Number.isInteger(item)); return state.protocol.answer.length === (challenge.preview_cells || challenge.preview_path || []).length; }
function updateProtocolMeta() { const session = state.protocol.session; setText('#protocol-session', session ? String(session.session_id).slice(0, 8).toUpperCase() : '—'); setText('#protocol-attempts', session ? `${session.attempts_left} left` : '—'); }
function renderProtocolStage() {
  const session = state.protocol.session; const stage = $('#protocol-stage'); if (!stage || !session) return; stage.replaceChildren(); const challenge = session.challenge || {}; const meta = PROTOCOLS[session.game] || PROTOCOLS.quantum_lock; $('#protocol-console').dataset.state = state.protocol.armed ? 'armed' : challenge.kind === 'choice' ? 'choice' : 'preview';
  if (challenge.kind === 'grid') {
    const grid = document.createElement('div'); grid.className = 'protocol-grid'; for (let index = 0; index < Number(challenge.size || 25); index += 1) { const button = document.createElement('button'); button.type = 'button'; button.className = `protocol-cell${(challenge.preview_cells || []).includes(index) && !state.protocol.armed ? ' preview' : ''}${state.protocol.answer.includes(index) ? ' selected' : ''}`; button.dataset.protocolCell = index; const previewOrder = (challenge.preview_cells || []).indexOf(index); button.innerHTML = `<span>${String(index + 1).padStart(2, '0')}</span><small>${previewOrder >= 0 && !state.protocol.armed ? previewOrder + 1 : ''}</small>`; button.disabled = !state.protocol.armed; grid.append(button); } stage.append(grid); const hint = document.createElement('small'); hint.className = 'stage-hint'; hint.textContent = state.protocol.armed ? 'Select the entangled cells in the order they appeared.' : `Preview locked · memorise ${challenge.preview_cells?.length || 0} nodes`; stage.append(hint);
  } else if (challenge.kind === 'path') {
    const path = document.createElement('div'); path.className = 'protocol-nodes'; const preview = challenge.preview_path || []; (challenge.nodes || []).forEach((label, index) => { const button = document.createElement('button'); button.type = 'button'; button.className = `protocol-node${preview.includes(index) && !state.protocol.armed ? ' preview' : ''}${state.protocol.answer.includes(index) ? ' selected' : ''}`; button.dataset.protocolNode = index; const previewOrder = preview.indexOf(index); button.innerHTML = `<b>${label}</b><small>${previewOrder >= 0 && !state.protocol.armed ? `STEP ${previewOrder + 1}` : String(index + 1).padStart(2, '0')}</small>`; button.disabled = !state.protocol.armed; path.append(button); }); stage.append(path); const hint = document.createElement('small'); hint.className = 'stage-hint'; hint.textContent = state.protocol.armed ? 'Replay the route in sequence.' : `Route preview locked · ${preview.length} vectors`; stage.append(hint);
  } else {
    const scenarios = document.createElement('div'); scenarios.className = 'scenario-stack'; (challenge.scenarios || []).forEach((scenario, round) => { const card = document.createElement('article'); card.className = 'scenario-card'; card.innerHTML = `<div class="scenario-number">0${round + 1}</div><div class="scenario-body"><b>${scenario.prompt}</b><div class="scenario-options"></div></div>`; const options = $('.scenario-options', card); (scenario.options || []).forEach((option, index) => { const button = document.createElement('button'); button.type = 'button'; button.textContent = option; button.dataset.scenarioRound = round; button.dataset.scenarioOption = index; button.className = state.protocol.answer[round] === index ? 'selected' : ''; options.append(button); }); scenarios.append(card); }); stage.append(scenarios); state.protocol.armed = true;
  }
  $$('#protocol-submit').forEach((button) => { button.disabled = !protocolInputReady() || state.protocol.session.status !== 'active'; });
  const arm = $('#protocol-arm'); if (arm) arm.hidden = challenge.kind === 'choice' || state.protocol.armed; updateProtocolMeta();
}
function renderProtocolSession(message) {
  const session = state.protocol.session; const consoleNode = $('#protocol-console'); if (!consoleNode) return; consoleNode.hidden = !session; if (!session) return; const meta = PROTOCOLS[session.game] || PROTOCOLS.quantum_lock; setText('#protocol-kicker', `${meta.title.toUpperCase()} // SERVER SESSION`); setText('#protocol-title', meta.title); setText('#protocol-subtitle', session.challenge?.opponent ? `${session.challenge.subtitle} · opponent ${session.challenge.opponent.name}` : session.challenge?.subtitle || 'Server-owned challenge'); setText('#protocol-timer', session.expires_in ? duration(session.expires_in) : 'Closed'); updateProtocolMeta(); protocolStatus(message || (session.status === 'complete' ? 'Session settled. Receipt committed.' : session.status === 'failed' ? 'Session closed. Issue a new challenge after cooldown.' : 'Preview received. Arm your response when ready.')); renderProtocolStage(); }
async function issueProtocol(game) {
  if (state.guest) { showToast('Open the Mini App in Telegram to issue a protocol.', true); return; }
  resetProtocolLocal(); const consoleNode = $('#protocol-console'); if (consoleNode) { consoleNode.hidden = false; consoleNode.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' }); } protocolStatus('Requesting an encrypted challenge…');
  try { state.protocol.session = await protocolApi('issue', { game }); renderProtocolSession(); state.protocol.timer = setInterval(() => { if (!state.protocol.session) return; state.protocol.session.expires_in = Math.max(0, state.protocol.session.expires_in - 1); setText('#protocol-timer', duration(state.protocol.session.expires_in)); if (!state.protocol.session.expires_in) { clearProtocolTimer(); protocolStatus('The server session expired. Issue a fresh challenge.', true); } }, 1000); haptic('medium'); } catch (error) { if (consoleNode) consoleNode.hidden = true; showToast(error.message || 'Could not issue that protocol.', true); }
}
function armProtocol() { if (!state.protocol.session) return; state.protocol.armed = true; state.protocol.answer = []; renderProtocolSession('Response layer armed. Submit the sequence to the server when complete.'); haptic('light'); }
function protocolCellClick(event) { if (!state.protocol.armed) return; const index = Number(event.currentTarget.dataset.protocolCell); if (state.protocol.answer.includes(index)) return; state.protocol.answer.push(index); renderProtocolStage(); haptic('light'); }
function protocolNodeClick(event) { if (!state.protocol.armed) return; const index = Number(event.currentTarget.dataset.protocolNode); if (state.protocol.answer.includes(index)) return; state.protocol.answer.push(index); renderProtocolStage(); haptic('light'); }
function scenarioClick(event) { const button = event.target.closest('[data-scenario-round]'); if (!button) return; const round = Number(button.dataset.scenarioRound); state.protocol.answer[round] = Number(button.dataset.scenarioOption); renderProtocolStage(); haptic('light'); }
async function submitProtocol() {
  const session = state.protocol.session; if (!session || !protocolInputReady()) return; const submit = $('#protocol-submit'); if (submit) { submit.disabled = true; submit.innerHTML = 'Sealing with server…'; }
  try { const result = await protocolApi('submit', { session_id: session.session_id, answer: state.protocol.answer }); state.protocol.session = result; if (result.solved) { showReward(result.game, result.winnings); await load({ quiet: true }); renderProtocolSession('Protocol complete. The receipt is immutable.'); } else if (result.status === 'active') { state.protocol.answer = []; state.protocol.armed = false; renderProtocolSession(`Decision rejected. ${result.attempts_left} attempt${result.attempts_left === 1 ? '' : 's'} remain.`); } else renderProtocolSession('Session closed. The server recorded a failed attempt.'); } catch (error) { showToast(error.message || 'The server could not settle this session.', true); } finally { if (submit) submit.innerHTML = 'Submit to server <span>↗</span>'; renderProtocolStage(); }
}
async function closeProtocol() { if (state.protocol.session?.session_id && state.protocol.session.status === 'active') { try { await protocolApi('abandon', { session_id: state.protocol.session.session_id }); } catch (_) {} } resetProtocolLocal(); const consoleNode = $('#protocol-console'); if (consoleNode) consoleNode.hidden = true; }

function arenaApi(action, payload = {}) { return api('/api/miniapp/arena', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, ...payload }) }).then((result) => result.room); }
function arenaMe(room = state.arena.room) { return room?.players?.find((player) => player.is_you) || null; }
function arenaOpponents(room = state.arena.room) { return (room?.players || []).filter((player) => !player.is_you); }
function arenaStopPolling() { clearInterval(state.arena.pollTimer); state.arena.pollTimer = null; }
function arenaReset() { arenaStopPolling(); state.arena = { room: null, pollTimer: null, choices: [], submitted: false, mode: 'duo_relay' }; $('#arena-lobby').hidden = state.guest; $('#arena-room').hidden = true; syncArenaModeButtons(); }
function renderArenaPlayers(room) { const node = $('#arena-players'); if (!node) return; node.replaceChildren(); const players = room?.players || []; const slots = Math.min(4, Number(room?.max_players) || 4); Array.from({ length: slots }, (_, index) => players[index]).forEach((player, index) => { const card = document.createElement('article'); card.className = `arena-player ${player?.is_you ? 'you' : ''} ${player ? '' : 'empty'}`; card.innerHTML = `<span class="arena-player-badge">${player ? player.is_you ? 'YOU' : `PLAYER 0${index + 1}` : `SLOT 0${index + 1}`}</span><span class="arena-player-avatar">${player ? initials(player.name) : '+'}</span><span class="arena-player-copy"><b>${player ? player.name : 'Open slot'}</b><small>${player ? room.status === 'complete' ? `${player.score ?? 0} points` : player.submitted ? 'Answer sealed' : player.ready ? 'Ready signal locked' : 'Preparing' : 'Share the code to invite'}</small></span><span class="arena-player-state ${player?.ready ? 'ready' : ''}">${player?.ready ? '✓' : player ? '…' : '·'}</span>`; node.append(card); }); }
function renderArenaChallenge(room) { const box = $('#arena-challenge'); if (!box) return; const challenge = room?.challenge; const me = arenaMe(room); const allReady = Boolean(me?.ready && arenaOpponents(room).length && room.players.every((player) => player.ready)); const available = challenge && ['ready', 'running'].includes(room.status) && !me?.submitted; box.hidden = !available; if (!available) return; const rounds = $('#arena-rounds'); rounds.replaceChildren(); const choices = state.arena.choices.length ? state.arena.choices : Array(challenge.rounds).fill(null); state.arena.choices = choices; challenge.scenarios.forEach((scenario, round) => { const card = document.createElement('article'); card.className = 'scenario-card arena-scenario'; card.innerHTML = `<div class="scenario-number">0${round + 1}</div><div class="scenario-body"><b>${scenario.prompt}</b><div class="scenario-options"></div></div>`; const options = $('.scenario-options', card); scenario.options.forEach((option, index) => { const button = document.createElement('button'); button.type = 'button'; button.textContent = option; button.dataset.arenaRound = round; button.dataset.arenaOption = index; button.className = choices[round] === index ? 'selected' : ''; button.disabled = state.arena.submitted; options.append(button); }); rounds.append(card); }); setText('#arena-round-count', `${challenge.rounds} SERVER ROUNDS`); $('#arena-submit').disabled = state.arena.submitted || choices.some((choice) => !Number.isInteger(choice)); }
function renderArena(room) { if (!room) return; state.arena.room = room; state.arena.mode = room.game || 'duo_relay'; syncArenaModeButtons(); $('#arena-lobby').hidden = true; $('#arena-room').hidden = false; setText('#arena-room-title', room.title || (state.arena.mode === 'cipher_race' ? 'Cipher Race' : state.arena.mode === 'bastion_breach' ? 'Bastion Breach' : 'Squad Relay')); setText('#arena-room-code', room.code); setText('#arena-room-expiry', `${Math.floor((room.expires_in || 0) / 60)}:${String((room.expires_in || 0) % 60).padStart(2, '0')}`); renderArenaPlayers(room); const me = arenaMe(room); const opponents = arenaOpponents(room); const allReady = Boolean(me?.ready && opponents.length && room.players.every((player) => player.ready)); setText('#arena-room-status', room.status === 'complete' ? 'Match settled · ledger updated' : !opponents.length ? 'Waiting for more players…' : !allReady ? 'Every player must lock ready state.' : room.status === 'running' ? `${room.title || 'Match'} in progress · answers are sealed` : 'Room is ready for deployment'); const waiting = $('#arena-waiting'); waiting.hidden = room.status === 'complete' || allReady; setText('#arena-waiting-title', !opponents.length ? 'Waiting for more players' : !me?.ready ? 'Lock your ready signal' : 'Waiting for the room to ready up'); setText('#arena-waiting-copy', !opponents.length ? 'Share the room code with two or three more players.' : 'Every player must be ready before the server challenge unlocks.'); const actions = $('#arena-ready-actions'); actions.hidden = room.status === 'complete' || Boolean(me?.submitted); const ready = $('#arena-ready'); ready.disabled = !opponents.length || allReady || room.status === 'complete'; ready.innerHTML = me?.ready ? 'Ready signal locked <span>✓</span>' : 'Mark ready <span>✓</span>'; renderArenaChallenge(room); const result = $('#arena-result'); result.hidden = room.status !== 'complete'; if (room.status === 'complete') { setText('#arena-result-title', room.winner === 'you' ? `${room.title || 'Match'} lead secured` : room.winner === 'tie' ? 'Perfectly matched squad' : `${room.title || 'Match'} complete`); setText('#arena-result-copy', room.winner === 'you' ? `${room.winner_name || 'Your run'} took the lead. Your receipt is final.` : room.winner === 'tie' ? 'The top signals aligned. The server issued a tie reward.' : `${room.winner_name || 'Another player'} took the lead. Your participation reward is secured.`); setText('#arena-result-reward', `+${coins(room.reward)} COINS`); arenaStopPolling(); } }
async function arenaRefresh() { if (!state.arena.room?.code || state.guest) return; try { renderArena(await arenaApi('get', { code: state.arena.room.code })); } catch (error) { if (error.status === 404 || error.status === 400) arenaReset(); } }
function arenaStartPolling() { arenaStopPolling(); state.arena.pollTimer = setInterval(() => arenaRefresh(), 1500); }
function syncArenaModeButtons() { $$('[data-arena-mode]').forEach((button) => { const selected = button.dataset.arenaMode === state.arena.mode; button.classList.toggle('selected', selected); const badge = $('i', button); if (badge) badge.textContent = selected ? 'SELECTED' : '2–4 PLAYERS'; }); }
function selectArenaMode(mode) { if (state.arena.room) return; state.arena.mode = mode || 'duo_relay'; syncArenaModeButtons(); haptic('light'); }
async function createArenaRoom() { const button = $('#arena-create'); button.disabled = true; try { renderArena(await arenaApi('create', { game: state.arena.mode })); arenaStartPolling(); showToast(`${state.arena.room?.title || 'Multiplayer'} room created. Share the code.`); } catch (error) { showToast(error.message || 'Could not create a room.', true); } finally { button.disabled = false; } }
async function joinArenaRoom(event) { event.preventDefault(); const input = $('#arena-code'); const code = String(input.value || '').trim().toUpperCase(); if (!code) return; try { renderArena(await arenaApi('join', { code })); arenaStartPolling(); input.value = ''; showToast('Joined the squad room.'); } catch (error) { showToast(error.message || 'Could not join that room.', true); } }
async function toggleArenaReady() { const room = state.arena.room; const me = arenaMe(room); if (!room || !me) return; try { renderArena(await arenaApi('ready', { code: room.code, ready: !me.ready })); } catch (error) { showToast(error.message || 'Could not update ready state.', true); } }
async function submitArena() { const room = state.arena.room; if (!room || state.arena.choices.some((choice) => !Number.isInteger(choice))) return; state.arena.submitted = true; renderArenaChallenge(room); try { renderArena(await arenaApi('submit_action', { code: room.code, choices: state.arena.choices })); showToast(`${room.title || 'Multiplayer'} answer sealed by the server.`); await load({ quiet: true }); } catch (error) { state.arena.submitted = false; showToast(error.message || 'The server rejected that answer.', true); renderArena(state.arena.room); } }
async function leaveArena() { const code = state.arena.room?.code; if (code) { try { await arenaApi('leave', { code }); } catch (_) {} } arenaReset(); showToast('You left the squad room.'); }
async function copyArenaCode() { const code = state.arena.room?.code; if (!code) return; try { await navigator.clipboard.writeText(code); showToast('Room code copied'); } catch (_) { showToast(`Share code ${code} with your squad.`); } }

function openTransactionDetail(item) { const dialog = $('#transaction-detail'); if (!dialog) return; state.selectedTransaction = item; setText('#transaction-detail-title', `${gameLabel(item.game)} receipt`); setText('#transaction-detail-copy', 'This event was confirmed by the server and written to the immutable ledger.'); setText('#transaction-detail-amount', `+${coins(item.amount)} COINS`); setText('#transaction-detail-type', gameLabel(item.game)); setText('#transaction-detail-time', formatDate(item.created_at)); setText('#transaction-detail-id', item.id ? String(item.id).slice(0, 22) : 'Server event'); if (dialog.showModal) dialog.showModal(); }
function downloadHistory() { const rows = [['event_id', 'game', 'amount', 'created_at'], ...visibleTransactions(state.data?.history || []).map((item) => [item.id || '', item.game || '', item.amount || 0, item.created_at || ''])]; if (rows.length === 1) { showToast('No matching receipts to export.', true); return; } const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' })); link.download = `summon-ledger-${new Date().toISOString().slice(0, 10)}.csv`; link.click(); URL.revokeObjectURL(link.href); showToast('Ledger export saved'); }
function copyReference() { const value = state.selectedTransaction?.id; if (!value) return; navigator.clipboard?.writeText(String(value)).then(() => showToast('Receipt reference copied')).catch(() => showToast('Copy is unavailable.', true)); }
function saveReceipt() { const item = state.selectedTransaction; if (!item) return; const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([JSON.stringify({ event_id: item.id || null, game: gameLabel(item.game), amount: Number(item.amount) || 0, created_at: item.created_at || null, verification: 'server-confirmed' }, null, 2)], { type: 'application/json' })); link.download = `summon-receipt-${String(item.id || 'event').slice(0, 24)}.json`; link.click(); URL.revokeObjectURL(link.href); showToast('Receipt saved'); }
function launchConfetti() { const node = $('#confetti'); if (!node) return; node.replaceChildren(); ['#8c7bff', '#64e8f3', '#ff73b7', '#ffd66b', '#6ee3a6'].forEach((color, colorIndex) => { for (let index = 0; index < 7; index += 1) { const bit = document.createElement('i'); bit.style.setProperty('--x', `${Math.random() * 180 - 90}px`); bit.style.setProperty('--y', `${-40 - Math.random() * 150}px`); bit.style.setProperty('--r', `${Math.random() * 720 - 360}deg`); bit.style.setProperty('--c', color); bit.style.setProperty('--d', `${colorIndex * 40 + Math.random() * 220}ms`); node.append(bit); } }); setTimeout(() => node.replaceChildren(), 1500); }
function showReward(game, amount) { setText('#reward-title', `${gameLabel(game)} complete`); setText('#reward-copy', 'The server accepted the outcome and credited your bot balance.'); setText('#reward-amount', `+${coins(amount)}`); launchConfetti(); haptic('heavy'); $('#reward')?.showModal?.(); }
async function load({ quiet = false } = {}) { if (!initData) return loadPublic({ quiet }); if (!quiet) setConnection('', 'Connecting'); try { const data = await api('/api/miniapp/me'); render(data); setConnection('ready', 'Secure'); $('#alert').hidden = true; try { renderLeaders((await api('/api/miniapp/leaderboard')).entries); } catch (_) { renderLeaders([]); } if (!quiet) showToast('Secure command state synced'); return data; } catch (error) { if (error.status === 401) return loadPublic({ quiet }); setConnection('error', 'Offline'); $('#alert').hidden = false; setText('#alert-text', error.message || 'Could not sync command state.'); if (!quiet) showToast(error.message || 'Could not sync command state.', true); throw error; } }
async function loadPublic({ quiet = false } = {}) { if (!quiet) setConnection('', 'Connecting'); try { const data = await api('/api/miniapp/public'); renderPublic(data); setConnection('ready', 'Public'); $('#alert').hidden = true; return data; } catch (error) { setConnection('error', 'Offline'); $('#alert').hidden = false; setText('#alert-text', error.message || 'Public preview unavailable.'); if (!quiet) showToast(error.message || 'Public preview unavailable.', true); throw error; } }
async function refreshDashboard() { const buttons = [$('#refresh'), $('#hero-refresh')].filter(Boolean); buttons.forEach((button) => button.classList.add('is-loading')); try { await load(); } catch (_) {} finally { buttons.forEach((button) => button.classList.remove('is-loading')); } }
function setupReveals() { const items = $$('.reveal'); if (!('IntersectionObserver' in window) || reducedMotion()) { items.forEach((item) => item.classList.add('is-visible')); return; } const observer = new IntersectionObserver((entries) => entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); observer.unobserve(entry.target); } }), { threshold: .1 }); items.forEach((item) => observer.observe(item)); }

$$('[data-go]').forEach((button) => button.addEventListener('click', () => { haptic(); navigate(button.dataset.go); }));
$$('[data-protocol]').forEach((button) => button.addEventListener('click', () => { navigate('arcade'); setTimeout(() => issueProtocol(button.dataset.protocol), 80); }));
$('#protocol-arm')?.addEventListener('click', armProtocol); $('#protocol-submit')?.addEventListener('click', submitProtocol); $('#protocol-close')?.addEventListener('click', closeProtocol); $('#protocol-stage')?.addEventListener('click', (event) => { if (event.target.closest('[data-protocol-cell]')) protocolCellClick({ currentTarget: event.target.closest('[data-protocol-cell]') }); else if (event.target.closest('[data-protocol-node]')) protocolNodeClick({ currentTarget: event.target.closest('[data-protocol-node]') }); else if (event.target.closest('[data-scenario-round]')) scenarioClick(event); });
$('#arena-create')?.addEventListener('click', createArenaRoom); $$('[data-arena-mode]').forEach((button) => button.addEventListener('click', () => selectArenaMode(button.dataset.arenaMode))); $('#arena-join-form')?.addEventListener('submit', joinArenaRoom); $('#arena-ready')?.addEventListener('click', toggleArenaReady); $('#arena-submit')?.addEventListener('click', submitArena); $('#arena-leave')?.addEventListener('click', leaveArena); $('#arena-copy-code')?.addEventListener('click', copyArenaCode);
$$('[data-transaction-filter]').forEach((button) => button.addEventListener('click', () => { state.transactionFilter = button.dataset.transactionFilter || 'all'; $$('[data-transaction-filter]').forEach((item) => item.classList.toggle('active', item === button)); renderTransactions('#recent', state.data?.history || [], 4); renderTransactions('#history', state.data?.history || []); })); $('#transaction-search')?.addEventListener('input', (event) => { state.transactionSearch = event.target.value || ''; $('#clear-transaction-search').hidden = !state.transactionSearch; renderTransactions('#history', state.data?.history || []); }); $('#clear-transaction-search')?.addEventListener('click', () => { state.transactionSearch = ''; $('#transaction-search').value = ''; $('#clear-transaction-search').hidden = true; renderTransactions('#history', state.data?.history || []); }); $('#transaction-sort')?.addEventListener('change', (event) => { state.transactionSort = event.target.value; renderTransactions('#history', state.data?.history || []); }); $('#transaction-range')?.addEventListener('change', (event) => { state.transactionRange = event.target.value; renderTransactions('#history', state.data?.history || []); }); $('#export-history')?.addEventListener('click', downloadHistory); $('#copy-transaction-ref')?.addEventListener('click', copyReference); $('#download-transaction-receipt')?.addEventListener('click', saveReceipt); $('#close-transaction')?.addEventListener('click', () => $('#transaction-detail')?.close()); $('#close-transaction-action')?.addEventListener('click', () => $('#transaction-detail')?.close()); $('#transaction-detail')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
$('#refresh')?.addEventListener('click', refreshDashboard); $('#hero-refresh')?.addEventListener('click', refreshDashboard); $('#retry')?.addEventListener('click', () => load().catch(() => {})); $('#theme')?.addEventListener('click', toggleTheme); $('#avatar')?.addEventListener('click', () => navigate('progress')); $('#close-reward')?.addEventListener('click', () => $('#reward')?.close()); $('#reward')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); }); window.addEventListener('hashchange', () => navigate(location.hash.slice(1) || 'home'));
const savedTheme = localStorage.getItem('summon-theme'); if (savedTheme) document.documentElement.dataset.theme = savedTheme; applyTheme(); setupTelegram(); setupReveals(); navigate(initData && ['home', 'arcade', 'solo', 'bots', 'missions', 'arena', 'intel', 'progress'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home'); load().catch(() => {});
