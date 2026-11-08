import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Dashboard from '../pages/Dashboard.jsx';
import { AuthContext } from '../context/auth.js';
import { dashboardApi } from '../utils/api.js';

vi.mock('../utils/api.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    dashboardApi: {
      resumen: vi.fn(),
    },
  };
});

vi.mock('../components/Rail.jsx', () => ({
  default: ({ loading, error }) => (
    <div data-testid="rail">{loading ? 'Cargando indicadores' : error}</div>
  ),
}));

vi.mock('../pages/Resumen.jsx', () => ({
  default: ({ data, loading, error, terrName }) => (
    <div data-testid="resumen">
      {loading ? 'Cargando resumen' : error || `${terrName}: ${data?.fecha_corte ?? 'sin datos'}`}
    </div>
  ),
}));

const dashboardData = {
  fecha_corte: '2024-06-30',
  actualizado_en: '2024-07-01T10:00:00Z',
  territorios: {
    departamentos: [{ codigo: 'ANT', nombre: 'Antioquia' }],
  },
};

function renderDashboard() {
  return render(
    <AuthContext.Provider
      value={{
        user: { full_name: 'Ana Gómez', role: 'analista' },
        token: 'token-de-prueba',
      }}
    >
      <Dashboard onExit={vi.fn()} toast={vi.fn()} />
    </AuthContext.Provider>,
  );
}

describe('dashboard', () => {
  beforeEach(() => {
    dashboardApi.resumen.mockReset();
  });

  it('carga datos iniciales y consulta de nuevo al filtrar período y territorio', async () => {
    const user = userEvent.setup();
    dashboardApi.resumen.mockResolvedValue(dashboardData);

    renderDashboard();

    expect(await screen.findByTestId('resumen')).toHaveTextContent(
      'Nacional: 2024-06-30',
    );
    expect(dashboardApi.resumen).toHaveBeenNthCalledWith(
      1,
      'token-de-prueba',
      expect.objectContaining({ anio: 'acumulado' }),
    );

    await user.click(screen.getByRole('button', { name: '2021' }));
    await waitFor(() => {
      expect(dashboardApi.resumen).toHaveBeenCalledTimes(2);
      expect(dashboardApi.resumen).toHaveBeenLastCalledWith(
        'token-de-prueba',
        expect.objectContaining({ anio: '2021' }),
      );
    });

    await user.selectOptions(screen.getByLabelText('Territorio'), 'ANT');
    await waitFor(() => {
      expect(dashboardApi.resumen).toHaveBeenCalledTimes(3);
      expect(dashboardApi.resumen).toHaveBeenLastCalledWith(
        'token-de-prueba',
        expect.objectContaining({ anio: '2021', departamento: 'ANT' }),
      );
    });
    expect(await screen.findByTestId('resumen')).toHaveTextContent('Antioquia: 2024-06-30');
  });

  it('presenta el error cuando no puede cargar los indicadores', async () => {
    dashboardApi.resumen.mockRejectedValue({
      response: { data: { detail: 'Servicio temporalmente no disponible' } },
    });

    renderDashboard();

    expect(await screen.findByTestId('resumen')).toHaveTextContent(
      'Servicio temporalmente no disponible',
    );
    expect(screen.getByTestId('rail')).toHaveTextContent(
      'Servicio temporalmente no disponible',
    );
    expect(screen.getByText('Indicadores no disponibles')).toBeInTheDocument();
  });
});
