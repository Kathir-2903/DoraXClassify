import axios from 'axios';

const TOKEN_KEY = 'dora-x-classify.token';

export const tokenStore = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable (private mode) — session-only auth */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config?.url?.includes('/api/auth/login')) {
      tokenStore.clear();
      window.dispatchEvent(new CustomEvent('dxc:unauthorized'));
    }
    return Promise.reject(error);
  },
);

/** Normalise the backend error envelope into something the UI can render. */
export function parseError(error, fallback = 'Something went wrong') {
  const data = error?.response?.data?.error;
  if (data) {
    return {
      message: data.message || fallback,
      reason: data.reason || null,
      hint: data.hint || null,
      code: data.code,
      fields: (data.details?.fields || []).reduce((acc, f) => ({ ...acc, [f.field]: f.message }), {}),
      status: error.response.status,
    };
  }
  if (error?.code === 'ECONNABORTED') return { message: 'The request timed out. Please try again.', fields: {} };
  if (!error?.response) return { message: 'Cannot reach the server. Check your connection.', fields: {} };
  return { message: fallback, fields: {} };
}

export function errorText(error, fallback) {
  const e = parseError(error, fallback);
  return [e.message, e.reason].filter(Boolean).join(' — ');
}

/** Download a server-generated file (CSV/PDF/TXT) with the auth header. */
export async function downloadFile(url, params = {}, fallbackName = 'download') {
  const response = await api.get(url, { params, responseType: 'blob', timeout: 120000 });
  const disposition = response.headers['content-disposition'] || '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const name = match ? match[1] : fallbackName;
  const href = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export function cleanParams(params) {
  return Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== '' && v !== null && v !== undefined));
}
