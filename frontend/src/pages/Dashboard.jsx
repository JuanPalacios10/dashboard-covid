import { useState, useEffect, useMemo } from 'react';
import Rail from '../components/Rail.jsx';
import { Icon } from '../components/ui/Icons.jsx';
import { useAuth } from '../context/auth.js';
import { getView } from '../data/mock.js';
import { dashboardApi, getApiErrorMessage } from '../utils/api.js';
import { dLong } from '../utils/format.js';
import { roleLabel } from '../utils/roles.js';
import Informes from './Informes.jsx';
import Proyecciones from './Proyecciones.jsx';
import Resumen from './Resumen.jsx';

const PERIODOS = [
  ['acumulado', 'Acumulado'],
  ['2020', '2020'],
  ['2021', '2021'],
  ['2022', '2022'],
  ['2023', '2023'],
  ['2024', '2024'],
];

export default function Dashboard({ onExit, toast }) {
  const { user, token } = useAuth();
  const [tab, setTab] = useState('resumen');
  const [anio, setAnio] = useState('acumulado');
  const [terr, setTerr] = useState('all');
  const [sim, setSim] = useState({ R: 1.3, m: 40 });
  const [data, setData] = useState(null);
  const [loadState, setLoadState] = useState({ loading: true, error: '' });

  useEffect(() => {
    if (!token) return undefined;

    const controller = new AbortController();

    dashboardApi
      .resumen(token, {
        anio,
        departamento: terr === 'all' ? undefined : terr,
        signal: controller.signal,
      })
      .then((payload) => {
        if (controller.signal.aborted) return;
        setData(payload);
        setLoadState({ loading: false, error: '' });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setData(null);
        setLoadState({ loading: false, error: getApiErrorMessage(error) });
      });

    return () => controller.abort();
  }, [token, anio, terr]);

  const changeAnio = (value) => {
    setAnio(value);
    setLoadState({ loading: true, error: '' });
  };
  const changeTerr = (event) => {
    setTerr(event.target.value);
    setLoadState({ loading: true, error: '' });
  };

  // Proyecciones e informes siguen usando el modelo demostrativo.
  const view = useMemo(() => getView('all'), []);
  const fechaCorte = data?.fecha_corte
    ? dLong(new Date(`${data.fecha_corte}T00:00:00`))
    : null;
  const actualizado = data?.actualizado_en
    ? new Date(data.actualizado_en).toLocaleTimeString('es-CO', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : null;
  const departamentos = data?.territorios?.departamentos ?? [];
  const terrName =
    terr === 'all'
      ? 'Nacional'
      : departamentos.find((item) => item.codigo === terr)?.nombre ?? 'Departamento';
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
        <span
          className="live num"
          title={
            actualizado
              ? `Indicadores actualizados a las ${actualizado}`
              : 'Estado de los indicadores'
          }
        >
          <b></b>
          {loadState.loading
            ? 'Cargando indicadores…'
            : data
              ? `Datos al ${fechaCorte}`
              : 'Indicadores no disponibles'}
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
            {PERIODOS.map(([value, label]) => (
              <button
                key={value}
                className="chip"
                aria-pressed={anio === value}
                onClick={() => changeAnio(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="fgroup">
          <label className="flabel" htmlFor="f-terr">
            Territorio
          </label>
          <select id="f-terr" value={terr} onChange={changeTerr}>
            <option value="all">Nacional (todos los departamentos)</option>
            {departamentos.map((d) => (
              <option key={d.codigo} value={d.codigo}>
                {d.nombre}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="shell">
        <Rail
          kpis={data?.kpis}
          periodo={data?.periodo ?? anio}
          anio={data?.anio}
          loading={loadState.loading}
          error={loadState.error}
        />
        {tab === 'resumen' && (
          <Resumen
            data={data}
            loading={loadState.loading}
            error={loadState.error}
            terr={terr}
            terrName={terrName}
          />
        )}
        {tab === 'proyecciones' && (
          <Proyecciones
            token={token}
            anio={anio}
            terr={terr}
            terrName={terrName}
            sim={sim}
            setSim={setSim}
          />
        )}
        {tab === 'informes' && (
          <Informes view={view} terrName={terrName} sim={sim} toast={toast} />
        )}
      </div>
      <footer className="foot">
        <span>
          KPIs, tendencia, territorio, sexo, edad, mapa de calor y proyecciones desde MongoDB.
          Informes sigue siendo demostrativo.
        </span>
        <span>Este rol no accede a microdatos individuales ni a administración e ingesta.</span>
      </footer>
    </div>
  );
}
