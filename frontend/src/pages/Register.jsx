import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell from '../components/AuthShell.jsx';
import { useAuth } from '../context/auth.js';
import { getApiErrorMessage } from '../utils/api.js';
import { ROLES } from '../utils/roles.js';

export default function Register() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    role: 'analista',
    password: '',
    confirmPassword: '',
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
    if (error) setError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (form.password !== form.confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }

    setBusy(true);
    try {
      await register({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        role: form.role,
        password: form.password,
      });
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
      <h1>Crear cuenta</h1>
      <p className="auth-sub">Registra tus datos y elige el rol con el que usarás el dashboard.</p>

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <label className="auth-field">
          <span>Nombre completo</span>
          <input
            className="auth-input"
            type="text"
            name="full_name"
            autoComplete="name"
            placeholder="María Gómez"
            value={form.full_name}
            onChange={update('full_name')}
            minLength={2}
            required
          />
        </label>

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
          <span>Rol</span>
          <select className="auth-select" name="role" value={form.role} onChange={update('role')}>
            {ROLES.map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </select>
        </label>

        <div className="auth-row">
          <label className="auth-field">
            <span>Contraseña</span>
            <input
              className="auth-input"
              type="password"
              name="password"
              autoComplete="new-password"
              placeholder="Mínimo 8 caracteres"
              value={form.password}
              onChange={update('password')}
              minLength={8}
              required
            />
          </label>

          <label className="auth-field">
            <span>Confirmar contraseña</span>
            <input
              className="auth-input"
              type="password"
              name="confirmPassword"
              autoComplete="new-password"
              placeholder="Repite la contraseña"
              value={form.confirmPassword}
              onChange={update('confirmPassword')}
              minLength={8}
              required
            />
          </label>
        </div>

        <p className="auth-hint">La contraseña debe tener al menos 8 caracteres, una letra y un número.</p>

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? 'Creando cuenta…' : 'Crear cuenta y entrar'}
        </button>
      </form>

      <p className="auth-switch">
        ¿Ya tienes cuenta? <Link to="/login">Iniciar sesión</Link>
      </p>
    </AuthShell>
  );
}
