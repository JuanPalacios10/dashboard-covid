import { useState, useEffect, useMemo } from 'react';
import Rail from '../components/Rail.jsx';
import { Icon } from '../components/ui/Icons.jsx';
import { useAuth } from '../context/auth.js';
import { DEPTS, getView } from '../data/mock.js';
import { roleLabel } from '../utils/roles.js';
import Informes from './Informes.jsx';
import Proyecciones from './Proyecciones.jsx';
import Resumen from './Resumen.jsx';

export default function Dashboard({ onExit, toast }) {
  const { user } = useAuth();
  const [tab, setTab] = useState('resumen');
  const [range, setRange] = useState(60);
  const [terr, setTerr] = useState('all');
  const [sim, setSim] = useState({ R: 1.3, m: 40 });
  const [live, setLive] = useState(() => ({ lat: 238, extra: 0, t: new Date(), flash: 0 }));
  useEffect(() => {
    const id = setInterval(
      () =>
        setLive((p) => ({
          lat: 180 + Math.floor(Math.random() * 240),
          extra: p.extra + Math.floor(Math.random() * 7),
          t: new Date(),
          flash: p.flash + 1,
        })),
      5000,
    );
    return () => clearInterval(id);
  }, []);
  const view = useMemo(() => getView(terr), [terr]);
  const hhmm = live.t.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const tabs = [
    ['resumen', 'Resumen'],
    ['proyecciones', 'Proyecciones'],
    ['informes', 'Informes'],
  ];
  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <i></i>
          <span>Dashboard</span>
          <span className="l">covid-19</span>
        </div>
        <nav className="tabs" role="tablist" aria-label="Secciones">
          {tabs.map((t) => (
            <button
              key={t[0]}
              role="tab"
              className="tab"
              aria-selected={tab === t[0]}
              onClick={() => setTab(t[0])}
            >
              {t[1]}
            </button>
          ))}
          <button className="tab" disabled title="Sin permiso para este rol">
            {Icon.lock}Microdatos
          </button>
          <button className="tab" disabled title="Sin permiso para este rol">
            {Icon.lock}Administración
          </button>
        </nav>
        <span className="sp"></span>
        <span className="live num" title="Valores simulados">
          <b></b>En vivo · {live.lat} ms · {hhmm}
        </span>
        <span className="role">
          {user?.full_name ? `${user.full_name} · ` : ''}Rol: <strong>{roleLabel(user?.role)}</strong>
        </span>
        <button className="link" onClick={onExit}>
          Cerrar sesión
        </button>
      </header>
      <div className="filters">
        <div className="fgroup">
          <span className="flabel" id="f-per">
            Período
          </span>
          <div className="chips" role="group" aria-labelledby="f-per">
            {[30, 60, 90, 120].map((r) => (
              <button key={r} className="chip" aria-pressed={range === r} onClick={() => setRange(r)}>
                {r} días
              </button>
            ))}
          </div>
        </div>
        <div className="fgroup">
          <label className="flabel" htmlFor="f-terr">
            Territorio
          </label>
          <select id="f-terr" value={terr} onChange={(e) => setTerr(e.target.value)}>
            <option value="all">Nacional (todos los departamentos)</option>
            {DEPTS.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="shell">
        <Rail view={view} live={live} />
        {tab === 'resumen' && <Resumen view={view} range={range} terr={terr} />}
        {tab === 'proyecciones' && <Proyecciones view={view} sim={sim} setSim={setSim} />}
        {tab === 'informes' && <Informes view={view} terr={terr} sim={sim} toast={toast} />}
      </div>
      <footer className="foot">
        <span>Datos de ejemplo generados localmente, sin relación con cifras oficiales.</span>
        <span>Este rol no accede a microdatos individuales ni a administración e ingesta.</span>
      </footer>
    </div>
  );
}
