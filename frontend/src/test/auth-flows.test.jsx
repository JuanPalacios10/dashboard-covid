import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App.jsx';
import { AuthProvider } from '../context/AuthContext.jsx';
import { authApi } from '../utils/api.js';

vi.mock('../utils/api.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    authApi: {
      login: vi.fn(),
      register: vi.fn(),
      me: vi.fn(),
    },
  };
});

vi.mock('../pages/Dashboard.jsx', () => ({
  default: ({ onExit }) => (
    <main>
      <h1>Panel principal de pruebas</h1>
      <button onClick={onExit}>Salir del panel</button>
    </main>
  ),
}));

const STORAGE_KEY = 'covid-dashboard-session';
const validUser = { full_name: 'Ana Gómez', role: 'analista' };

function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('flujos de autenticación y rutas', () => {
  beforeEach(() => {
    authApi.login.mockReset();
    authApi.register.mockReset();
    authApi.me.mockReset();
  });

  it('redirige al inicio de sesión al intentar abrir el dashboard sin sesión', async () => {
    renderApp('/dashboard');

    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Panel principal de pruebas' })).not.toBeInTheDocument();
  });

  it('inicia sesión, normaliza el correo y persiste la sesión', async () => {
    const user = userEvent.setup();
    authApi.login.mockResolvedValue({
      access_token: 'token-de-prueba',
      user: validUser,
    });

    renderApp('/login');
    await user.type(screen.getByLabelText('Correo electrónico'), '  ana@example.com  ');
    await user.type(screen.getByLabelText('Contraseña'), 'Secreto123');
    await user.click(screen.getByRole('button', { name: 'Ingresar al dashboard' }));

    expect(await screen.findByRole('heading', { name: 'Panel principal de pruebas' })).toBeInTheDocument();
    expect(authApi.login).toHaveBeenCalledWith({
      email: 'ana@example.com',
      password: 'Secreto123',
    });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({
      token: 'token-de-prueba',
      user: validUser,
    });
  });

  it('muestra errores del servidor si el inicio de sesión falla', async () => {
    const user = userEvent.setup();
    authApi.login.mockRejectedValue({
      response: { data: { detail: 'Credenciales inválidas' } },
    });

    renderApp('/login');
    await user.type(screen.getByLabelText('Correo electrónico'), 'ana@example.com');
    await user.type(screen.getByLabelText('Contraseña'), 'incorrecta');
    await user.click(screen.getByRole('button', { name: 'Ingresar al dashboard' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Credenciales inválidas');
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('evita enviar el registro cuando las contraseñas no coinciden', async () => {
    const user = userEvent.setup();
    renderApp('/register');

    await user.type(screen.getByLabelText('Nombre completo'), 'Ana Gómez');
    await user.type(screen.getByLabelText('Correo electrónico'), 'ana@example.com');
    await user.type(screen.getByLabelText('Contraseña'), 'Secreto123');
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'OtroSecreto123');
    await user.click(screen.getByRole('button', { name: 'Crear cuenta y entrar' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Las contraseñas no coinciden.');
    expect(authApi.register).not.toHaveBeenCalled();
  });

  it('crea cuenta con los datos normalizados y entra al dashboard', async () => {
    const user = userEvent.setup();
    authApi.register.mockResolvedValue({
      access_token: 'token-nuevo',
      user: validUser,
    });
    renderApp('/register');

    await user.type(screen.getByLabelText('Nombre completo'), '  Ana Gómez  ');
    await user.type(screen.getByLabelText('Correo electrónico'), '  ana@example.com ');
    await user.selectOptions(screen.getByLabelText('Rol'), 'ejecutivo');
    await user.type(screen.getByLabelText('Contraseña'), 'Secreto123');
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'Secreto123');
    await user.click(screen.getByRole('button', { name: 'Crear cuenta y entrar' }));

    expect(await screen.findByRole('heading', { name: 'Panel principal de pruebas' })).toBeInTheDocument();
    expect(authApi.register).toHaveBeenCalledWith({
      full_name: 'Ana Gómez',
      email: 'ana@example.com',
      role: 'ejecutivo',
      password: 'Secreto123',
    });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({
      token: 'token-nuevo',
      user: validUser,
    });
  });

  it('valida la sesión guardada y envía a login si el token expiró', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: 'token-expirado', user: validUser }),
    );
    authApi.me.mockRejectedValue(new Error('Unauthorized'));

    renderApp('/dashboard');

    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    await waitFor(() => {
      expect(authApi.me).toHaveBeenCalledWith('token-expirado', expect.any(AbortSignal));
      expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });
  });

  it('restaura una sesión válida y redirige desde login al dashboard', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: 'token-válido', user: { full_name: 'Anterior', role: 'analista' } }),
    );
    authApi.me.mockResolvedValue(validUser);

    renderApp('/login');

    expect(await screen.findByRole('heading', { name: 'Panel principal de pruebas' })).toBeInTheDocument();
    expect(authApi.me).toHaveBeenCalledWith('token-válido', expect.any(AbortSignal));
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual({
        token: 'token-válido',
        user: validUser,
      });
    });
  });
});
