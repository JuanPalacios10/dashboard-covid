export default function Landing({ onLogin, onRegister }) {
  const cloud = (
    <svg viewBox="0 0 340 240" aria-hidden="true">
      <circle cx="40" cy="30" r="150" />
      <circle cx="170" cy="-20" r="110" />
      <circle cx="20" cy="150" r="70" />
    </svg>
  );
  return (
    <div className="wrap landing-page">
      <section className="landing">
        <div className="cloud tl">{cloud}</div>
        <div className="cloud br">{cloud}</div>
        <div style={{ position: 'relative' }}>
          <h1>Dashboard</h1>
          <p className="sub">covid-19</p>
          <div className="cta">
            <button className="pill" onClick={onRegister}>
              Registrarse
            </button>
            <button className="pill" onClick={onLogin}>
              Iniciar sesión
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
