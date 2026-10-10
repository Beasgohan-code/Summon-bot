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
function gameLabel(game) { return game === 'spin' ? 'Cosmic spin' : 'Daily vault'; }
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
    }
  }, 1000);
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
  icon.className = `transaction-icon ${item.game === 'spin' ? 'spin' : 'daily'}`;
  icon.textContent = item.game === 'spin' ? '✹' : '☀';
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
  const favourite = daily === spin ? (history.length ? 'Balanced' : '—') : (daily > spin ? 'Daily vault' : 'Cosmic spin');
  setText('#earned-total', coins(todayTotal));
  setText('#average-reward', coins(average));
  setText('#favorite-mode', favourite);
  setText('#favorite-detail', history.length ? `${Math.max(daily, spin)} verified claims` : 'waiting for activity');
  const available = Object.entries(cooldowns).filter(([, value]) => value?.available);
  const next = available.length ? null : Object.entries(cooldowns).sort((a, b) => (a[1]?.remaining_seconds || 0) - (b[1]?.remaining_seconds || 0))[0];
  if (!next) {
    setText('#next-window', 'Ready');
    setText('#next-window-detail', 'Your next reward is available.');
  } else {
    setText('#next-window', duration(next[1]?.remaining_seconds));
    setText('#next-window-detail', next[0] === 'spin' ? 'Cosmic spin unlocks next.' : 'Daily vault unlocks next.');
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
    ? history.slice(0, 4).map((item) => `${item.game === 'spin' ? 'Cosmic spin' : 'Daily vault'} · +${coins(item.amount)} coins · ${relative(item.created_at)}`)
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
  setText('#transaction-detail-title', `${gameLabel(item.game)} receipt`);
  setText('#transaction-detail-copy', spin ? 'Your cosmic result was signed and written to the secure ledger.' : 'Your daily vault result was signed and written to the secure ledger.');
  setText('#transaction-detail-amount', `+${coins(item.amount)} COINS`);
  setText('#transaction-detail-type', gameLabel(item.game));
  setText('#transaction-detail-time', formatDate(item.created_at));
  setText('#transaction-detail-id', item.id ? String(item.id).slice(0, 18) : 'Server event');
  const copyButton = $('#copy-transaction-ref');
  if (copyButton) copyButton.disabled = !item.id;
  const icon = $('#transaction-detail-icon');
  if (icon) { icon.textContent = spin ? '✹' : '☀'; icon.classList.toggle('spin-receipt', spin); }
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
  updateLiveTicker(history);
  startCooldownTicker();
}
function renderPublic(data) {
  setGuestMode(true);
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
  setText('#reward-title', game === 'spin' ? 'Cosmic hit!' : 'Daily vault opened');
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
  let valid = ['home', 'arcade', 'progress'].includes(screen) ? screen : 'home';
  if (state.guest && valid === 'arcade') valid = 'home';
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
  const shortcut = { h: 'home', a: 'arcade', p: 'progress', r: 'sync', t: 'theme', e: 'export' }[key];
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
navigate(initData && ['home', 'arcade', 'progress'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home');
load().catch(() => {});
