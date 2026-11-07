import axios from 'axios';

/** URL base del backend. Se puede cambiar con VITE_API_URL en frontend/.env. */
export const API_BASE_URL = (
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1'
).replace(/\/+$/, '');

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
});

/** Extrae un mensaje legible de los errores de FastAPI o de red. */
export function getApiErrorMessage(error) {
  const detail = error?.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg)
      .filter(Boolean)
      .join('. ');
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (error?.code === 'ERR_NETWORK') {
    return 'No se pudo conectar con el servidor. Verifica que el backend esté en ejecución.';
  }

  return 'Ocurrió un error inesperado. Intenta nuevamente.';
}

export const authApi = {
  login: async (credentials) => {
    const { data } = await api.post('/auth/login', credentials);
    return data;
  },
  register: async (payload) => {
    const { data } = await api.post('/auth/register', payload);
    return data;
  },
  me: async (token, signal) => {
    const { data } = await api.get('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });
    return data;
  },
};

export const kpiApi = {
  gerenciales: async (token, { anio = 'acumulado', signal } = {}) => {
    const { data } = await api.get('/kpis/gerenciales', {
      headers: { Authorization: `Bearer ${token}` },
      params: { anio },
      signal,
    });
    return data;
  },
};

export const dashboardApi = {
  resumen: async (token, { anio = 'acumulado', departamento, signal } = {}) => {
    const { data } = await api.get('/dashboard', {
      headers: { Authorization: `Bearer ${token}` },
      params: {
        anio,
        ...(departamento ? { departamento } : {}),
      },
      signal,
    });
    return data;
  },
};
