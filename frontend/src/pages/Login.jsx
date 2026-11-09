import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
// import { Link, useNavigate } from 'react-router-dom';
import AuthShell from '../components/AuthShell.jsx';
import { useAuth } from '../context/auth.js';
import { getApiErrorMessage } from '../utils/api.js';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
    if (error) setError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setBusy(true);

    try {
      await login({ email: form.email.trim(), password: form.password });
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <span className="auth-eyebrow">Dashboard covid-19</span>
      <h1>Iniciar sesión</h1>
      <p className="auth-sub">Accede con tu cuenta para consultar el panel epidemiológico.</p>

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <label className="auth-field">
          <span>Correo electrónico</span>
          <input
            className="auth-input"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="usuario@covid.com"
            value={form.email}
            onChange={update('email')}
            required
          />
        </label>

        <label className="auth-field">
          <span>Contraseña</span>
          <input
            className="auth-input"
            type="password"
            name="password"
            autoComplete="current-password"
            placeholder="Tu contraseña"
            value={form.password}
            onChange={update('password')}
            required
          />
        </label>

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? 'Ingresando…' : 'Ingresar al dashboard'}
        </button>
      </form>

      {/* Registro oculto temporalmente: solo el administrador puede crear usuarios
      <p className="auth-switch">
        ¿No tienes cuenta? <Link to="/register">Registrarse</Link>
      </p>
      */}
    </AuthShell>
  );
}
