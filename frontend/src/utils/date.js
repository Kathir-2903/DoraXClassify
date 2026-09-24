export const DEFAULT_TZ = 'Asia/Kolkata';

const cache = new Map();
function fmt(options) {
  const key = JSON.stringify(options);
  if (!cache.has(key)) cache.set(key, new Intl.DateTimeFormat('en-IN', { timeZone: DEFAULT_TZ, ...options }));
  return cache.get(key);
}

const toDate = (v) => (v instanceof Date ? v : v ? new Date(v) : null);
const valid = (d) => d && !Number.isNaN(d.getTime());

export function formatDate(value) {
  const d = toDate(value);
  return valid(d) ? fmt({ day: '2-digit', month: 'short', year: 'numeric' }).format(d) : '—';
}

export function formatTime(value) {
  const d = toDate(value);
  return valid(d) ? fmt({ hour: '2-digit', minute: '2-digit', hour12: true }).format(d).toUpperCase() : '—';
}

export function formatTimeSeconds(value) {
  const d = toDate(value);
  return valid(d) ? fmt({ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(d) : '';
}

export function formatDateTime(value) {
  const d = toDate(value);
  return valid(d) ? `${formatDate(d)}, ${formatTime(d)}` : '—';
}

export function formatShortDate(value) {
  const d = toDate(value);
  return valid(d) ? fmt({ day: '2-digit', month: 'short' }).format(d) : '—';
}

export function formatWeekday(value) {
  const d = toDate(value);
  return valid(d) ? fmt({ weekday: 'short', day: '2-digit', month: 'short' }).format(d) : '—';
}

/** YYYY-MM-DD for "today" in Asia/Kolkata (for <input type="date">). */
export function todayLocalISO(offsetDays = 0) {
  const d = new Date(Date.now() + offsetDays * 86400000);
  const parts = fmt({ year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(d);
  const get = (t) => parts.find((p) => p.type === t).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

/** Current HH:MM in Asia/Kolkata. */
export function nowLocalTime() {
  const parts = fmt({ hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(new Date());
  const get = (t) => parts.find((p) => p.type === t).value;
  return `${get('hour') === '24' ? '00' : get('hour')}:${get('minute')}`;
}

/** Convert a local (Asia/Kolkata, +05:30, no DST) date + time to a Date. */
export function localToDate(dateStr, timeStr) {
  if (!dateStr || !timeStr) return null;
  return new Date(`${dateStr}T${timeStr}:00+05:30`);
}

export function relativeTime(value) {
  const d = toDate(value);
  if (!valid(d)) return '—';
  const diff = (d.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (abs < 60) return rtf.format(Math.round(diff), 'second');
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), 'day');
  return formatDate(d);
}

export function greeting() {
  const hour = Number(fmt({ hour: '2-digit', hour12: false }).format(new Date()));
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

export function offsetClock(seconds) {
  if (seconds === null || seconds === undefined) return '';
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h ? `${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}
