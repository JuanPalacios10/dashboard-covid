import { Link } from 'react-router-dom';

const cloud = (
  <svg viewBox="0 0 340 240" aria-hidden="true">
    <circle cx="40" cy="30" r="150" />
    <circle cx="170" cy="-20" r="110" />
    <circle cx="20" cy="150" r="70" />
  </svg>
);

export default function AuthShell({ children }) {
  return (
    <div className="auth-page">
      <div className="cloud tl">{cloud}</div>
      <div className="cloud br">{cloud}</div>
      <section className="auth-card">
        <Link to="/" className="auth-back">
          ← Volver al inicio
        </Link>
        {children}
      </section>
    </div>
  );
}
