const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { data: null, screen: location.hash.slice(1) || 'home', busy: false, toast: null };
const initData = tg ? tg.initData : '';
const fmt = new Intl.NumberFormat();
const shortFmt = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });

function setText(selector, value) { const node = $(selector); if (node) node.textContent = value == null ? '—' : String(value); }
function coins(value) { return fmt.format(Math.max(0, Number(value) || 0)); }
function initials(value) { return String(value || 'S').trim().slice(0, 1).toUpperCase() || 'S'; }
function haptic(type = 'light') { try { tg?.HapticFeedback?.impactOccurred(type); } catch (_) {} }
function showToast(message, error = false) { const node = $('#toast'); if (!node) return; node.textContent = message; node.className = `toast show${error ? ' error' : ''}`; clearTimeout(state.toast); state.toast = setTimeout(() => { node.className = 'toast'; }, 3500); }
function setConnection(mode, label) { const node = $('#connection'); if (!node) return; node.className = `connection ${mode}`; node.lastChild.textContent = ` ${label}`; }
function setProgress(selector, percent) { const node = $(selector); if (node) node.style.transform = `scaleX(${Math.max(0, Math.min(100, Number(percent) || 0)) / 100})`; }

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, cache: 'no-store', credentials: 'same-origin', headers: { 'X-Telegram-Init-Data': initData, ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({ ok: false, error: 'Invalid server response' }));
  if (!response.ok || data.ok === false) { const error = new Error(data.error || `Request failed (${response.status})`); error.status = response.status; throw error; }
  return data;
}

function applyTelegramTheme() {
  if (!tg?.themeParams) return;
  const root = document.documentElement; const colors = tg.themeParams;
  if (colors.bg_color) root.style.setProperty('--bg', colors.bg_color);
  if (colors.secondary_bg_color) root.style.setProperty('--panel2', colors.secondary_bg_color);
  if (colors.text_color) root.style.setProperty('--text', colors.text_color);
  if (colors.hint_color) root.style.setProperty('--muted', colors.hint_color);
  if (colors.button_color) root.style.setProperty('--purple', colors.button_color);
}

function setupTelegram() { if (!tg) return; tg.ready(); tg.expand(); applyTelegramTheme(); try { tg.setHeaderColor(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()); tg.setBackgroundColor(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()); tg.onEvent?.('themeChanged', applyTelegramTheme); } catch (_) {} }
function relative(value) { if (!value) return 'Recently'; const parsed = new Date(String(value).replace(' ', 'T') + (String(value).includes('Z') ? '' : 'Z')); if (Number.isNaN(parsed.getTime())) return 'Recently'; const seconds = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000)); if (seconds < 60) return 'Just now'; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`; if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`; return `${Math.floor(seconds / 86400)}d ago`; }
function duration(seconds) { const value = Math.max(0, Number(seconds) || 0); const h = Math.floor(value / 3600); const m = Math.floor((value % 3600) / 60); return h ? `${h}h ${m}m left` : `${Math.max(1, m)}m left`; }
function eventId() { return crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`; }

function activityItem(item) { const row = document.createElement('div'); row.className = 'activity-item'; const icon = document.createElement('div'); icon.className = `activity-icon ${item.game === 'spin' ? 'spin' : ''}`; icon.textContent = item.game === 'spin' ? '✹' : '☀'; const copy = document.createElement('div'); copy.className = 'activity-copy'; const title = document.createElement('b'); title.textContent = item.game === 'spin' ? 'Cosmic reel spin' : 'Daily vault claim'; const time = document.createElement('small'); time.textContent = relative(item.created_at); copy.append(title, time); const amount = document.createElement('span'); amount.className = 'amount'; amount.textContent = `+${coins(item.amount)}`; row.append(icon, copy, amount); return row; }
function renderActivity(selector, items) { const node = $(selector); if (!node) return; node.replaceChildren(); if (!items?.length) { const empty = document.createElement('div'); empty.className = 'loading'; empty.textContent = 'No verified rewards yet.'; node.append(empty); return; } items.forEach((item) => node.append(activityItem(item))); }

function renderGames(cooldowns = {}) { ['daily', 'spin'].forEach((game) => { const info = cooldowns[game] || { available: true, remaining_seconds: 0 }; $$(`[data-status="${game}"]`).forEach((status) => { const ready = Boolean(info.available); status.textContent = ready ? 'Ready to play' : duration(info.remaining_seconds); status.className = ready ? 'ready' : 'locked'; }); $$(`[data-game="${game}"]`).forEach((button) => { button.disabled = !info.available || state.busy; }); }); }
function render(data) { state.data = data; const user = data.user || {}; const collection = data.collection || {}; const streak = data.streak || {}; const name = user.first_name || 'Summoner'; const percent = Number(collection.percent || 0); setText('#name', name); setText('#balance', coins(data.balance)); setText('#rank', data.rank ? `#${fmt.format(data.rank)}` : 'Unranked'); setText('#streak', `${fmt.format(streak.current || 0)} days`); setText('#collection', `${fmt.format(collection.unique || 0)}/${fmt.format(collection.catalogue || 0)}`); setText('#copies', fmt.format(collection.copies || 0)); setText('#percent', `${percent}% complete`); setText('#best', fmt.format(streak.best || 0)); setText('#progress-percent', percent); setText('#ring-value', `${percent}%`); setText('#owned', `${fmt.format(collection.unique || 0)} owned`); setText('#catalogue', `${fmt.format(collection.catalogue || 0)} in catalogue`); setText('#account-name', name); setText('#account-handle', user.username ? `@${user.username}` : 'Telegram WebApp session'); ['#avatar', '#hero-avatar', '#account-avatar'].forEach((selector) => setText(selector, initials(name))); setProgress('#collection-bar', percent); setProgress('#wide-bar', percent); renderGames(data.cooldowns); renderActivity('#recent', (data.history || []).slice(0, 4)); renderActivity('#history', data.history || []); }

function renderLeaders(entries) { const node = $('#leaders'); if (!node) return; node.replaceChildren(); if (!entries?.length) { const empty = document.createElement('div'); empty.className = 'loading'; empty.textContent = 'No leaderboard data yet.'; node.append(empty); return; } entries.forEach((entry) => { const row = document.createElement('div'); row.className = 'leader'; const rank = document.createElement('span'); rank.className = 'leader-rank'; rank.textContent = `#${entry.rank}`; const avatar = document.createElement('span'); avatar.className = 'leader-avatar'; avatar.textContent = initials(entry.name); const name = document.createElement('div'); name.className = 'leader-name'; const primary = document.createElement('b'); primary.textContent = entry.name; const secondary = document.createElement('small'); secondary.textContent = entry.is_you ? 'That’s you' : (entry.username ? `@${entry.username}` : 'Summoner'); name.append(primary, secondary); const balance = document.createElement('span'); balance.className = 'leader-coins'; balance.textContent = `${shortFmt.format(entry.balance || 0)} 🪙`; row.append(rank, avatar, name, balance); node.append(row); }); }

async function load({ quiet = false } = {}) { if (!quiet) setConnection('', ' Connecting'); try { const data = await api('/api/miniapp/me'); render(data); setConnection('ready', ' Secure'); $('#alert').hidden = true; if (!quiet) showToast('Secure dashboard synced'); try { renderLeaders((await api('/api/miniapp/leaderboard')).entries); } catch (_) { renderLeaders([]); } } catch (error) { setConnection('error', ' Offline'); $('#alert').hidden = false; setText('#alert-text', error.message || 'Open this page inside Telegram to authenticate.'); if (!quiet) showToast(error.message || 'Could not sync dashboard', true); throw error; } }

async function play(game) { if (state.busy) return; state.busy = true; renderGames(state.data?.cooldowns); haptic('medium'); try { const result = await api('/api/miniapp/game', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, event_id: eventId() }) }); haptic('heavy'); const dialog = $('#reward'); setText('#reward-title', game === 'spin' ? 'Cosmic hit!' : 'Daily vault opened'); setText('#reward-amount', `+${coins(result.winnings)}`); if (dialog?.showModal) dialog.showModal(); else showToast(`You won ${coins(result.winnings)} coins.`); await load({ quiet: true }); } catch (error) { showToast(error.message || 'Reward could not be recorded', true); if (error.status === 409) await load({ quiet: true }).catch(() => {}); } finally { state.busy = false; renderGames(state.data?.cooldowns); } }

function navigate(screen) { const valid = ['home', 'arcade', 'progress'].includes(screen) ? screen : 'home'; state.screen = valid; history.replaceState(null, '', `#${valid}`); localStorage.setItem('summon-screen', valid); $$('[data-screen]').forEach((section) => { section.hidden = section.dataset.screen !== valid; }); $$('[data-go]').forEach((button) => button.classList.toggle('selected', button.dataset.go === valid)); if (tg?.BackButton) { if (valid === 'home') tg.BackButton.hide(); else { tg.BackButton.show(); tg.BackButton.onClick(() => navigate('home')); } } }
function toggleTheme() { const root = document.documentElement; const next = root.dataset.theme === 'light' ? 'dark' : 'light'; root.dataset.theme = next; localStorage.setItem('summon-theme', next); setText('#theme', next === 'light' ? '☀' : '☾'); }

$$('[data-go]').forEach((button) => button.addEventListener('click', () => { haptic(); navigate(button.dataset.go); }));
$$('[data-game]').forEach((button) => button.addEventListener('click', () => play(button.dataset.game)));
$('#refresh')?.addEventListener('click', async () => { $('#refresh').classList.add('spin'); try { await load(); } catch (_) {} $('#refresh').classList.remove('spin'); });
$('#retry')?.addEventListener('click', () => load().catch(() => {}));
$('#theme')?.addEventListener('click', toggleTheme);
$('#avatar')?.addEventListener('click', () => navigate('progress'));
$('#close-reward')?.addEventListener('click', () => $('#reward')?.close());
$('#reward')?.addEventListener('click', (event) => { if (event.target === event.currentTarget) event.currentTarget.close(); });
const savedTheme = localStorage.getItem('summon-theme'); if (savedTheme) document.documentElement.dataset.theme = savedTheme; setText('#theme', document.documentElement.dataset.theme === 'light' ? '☀' : '☾');
setupTelegram(); navigate(['home', 'arcade', 'progress'].includes(location.hash.slice(1)) ? location.hash.slice(1) : (localStorage.getItem('summon-screen') || 'home')); load().catch(() => {});
