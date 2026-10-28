import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';
export const api = axios.create({ baseURL, timeout: 20000 });

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('ims_access');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing = false;
let waiting = [];
const settleWaiting = (error, token = null) => {
  waiting.forEach(({ resolve, reject }) => error ? reject(error) : resolve(token));
  waiting = [];
};
api.interceptors.response.use((response) => response, async (error) => {
  const original = error.config;
  if (error.response?.status === 401 && !original?._retry && !original?.url?.includes('/auth/token')) {
    const refresh = sessionStorage.getItem('ims_refresh');
    if (!refresh) {
      sessionStorage.removeItem('ims_access');
      sessionStorage.removeItem('ims_refresh');
      window.dispatchEvent(new Event('ims:unauthorized'));
      return Promise.reject(error);
    }
    if (refreshing) {
      return new Promise((resolve, reject) => waiting.push({ resolve, reject })).then((token) => {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      });
    }
    original._retry = true;
    refreshing = true;
    try {
      const response = await axios.post(`${baseURL}/auth/token/refresh/`, { refresh });
      const token = response.data.access;
      sessionStorage.setItem('ims_access', token);
      if (response.data.refresh) sessionStorage.setItem('ims_refresh', response.data.refresh);
      settleWaiting(null, token);
      original.headers.Authorization = `Bearer ${token}`;
      return api(original);
    } catch (refreshError) {
      settleWaiting(refreshError);
      sessionStorage.removeItem('ims_access');
      sessionStorage.removeItem('ims_refresh');
      window.dispatchEvent(new Event('ims:unauthorized'));
      return Promise.reject(refreshError);
    } finally { refreshing = false; }
  }
  return Promise.reject(error);
});

export const authApi = {
  async login(username, password) {
    const { data } = await api.post('/auth/token/', { username, password });
    sessionStorage.setItem('ims_access', data.access);
    sessionStorage.setItem('ims_refresh', data.refresh);
    const current = await api.get('/auth/me/');
    return current.data;
  },
  async me() { return (await api.get('/auth/me/')).data; },
  logout() { sessionStorage.removeItem('ims_access'); sessionStorage.removeItem('ims_refresh'); },
  isAuthenticated() { return !!sessionStorage.getItem('ims_access'); },
};

export const endpoint = (path) => `/${path.replace(/^\//, '')}`;
export const getList = async (path, params = {}) => {
  const { data } = await api.get(endpoint(path), { params });
  return Array.isArray(data) ? data : (data.results || []);
};
export const getErrorMessage = (error) => {
  const data = error?.response?.data;
  if (!data) return error?.message || 'Something went wrong. Please try again.';
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  return Object.entries(data).map(([field, value]) => `${field.replaceAll('_', ' ')}: ${Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : value}`).join(' · ');
};

export async function downloadReport(name, format = 'csv') {
  const response = await api.get(`/reports/${name}/`, { params: { format }, responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `internship-${name}.${format}`;
  document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
}

export async function downloadPrivateFile(fileUrl, filename = 'attachment') {
  const path = fileUrl.startsWith('http') ? new URL(fileUrl).pathname.replace('/api', '') : fileUrl.replace('/api', '');
  const response = await api.get(path, { responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
}
