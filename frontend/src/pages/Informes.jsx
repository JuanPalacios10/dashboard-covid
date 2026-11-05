import { useState, useMemo } from 'react';
import Card from '../components/ui/Card.jsx';
import { DEPTS, TODAY, simulate, summarize } from '../data/mock.js';
import { dec, fmt, pct, sum } from '../utils/format.js';

export default function Informes({ view, terr, sim, toast }) {
  const [dest, setDest] = useState('Consejo de gobierno');
  const [incl, setIncl] = useState(true);
  const terrName = terr === 'all' ? 'Nacional' : DEPTS.find((d) => d.id === terr).name;
  const top5 = DEPTS.map((d) => ({ n: d.name, v: sum(d.series.slice(-7)) / (d.pop * 10) }))
    .sort((a, b) => b.v - a.v)
    .slice(0, 5);
  const proj = useMemo(() => summarize(view, simulate(view, sim.R, sim.m)), [view, sim]);
  const Re = sim.R * (1 - (0.5 * sim.m) / 100);
  const change = view.prev7 ? (view.last7 / view.prev7 - 1) * 100 : 0;
  const fecha = TODAY.toLocaleDateString('es-CO', { day: 'numeric', month: 'long', year: 'numeric' });
  return (
    <div className="rep">
      <Card title="Informe oficial" sub="Resumen gerencial en PDF">
        <div className="field">
          <label htmlFor="dest" className="flabel">
            Dirigido a
          </label>
          <select id="dest" value={dest} onChange={(e) => setDest(e.target.value)}>
            <option>Consejo de gobierno</option>
            <option>Comité de emergencia</option>
          </select>
        </div>
        <div className="field">
          <span className="flabel">Territorio</span>
          <span>
            {terrName} <span className="hint">(según el filtro superior)</span>
          </span>
        </div>
        <label className="chk" htmlFor="incl">
          <input id="incl" type="checkbox" checked={incl} onChange={(e) => setIncl(e.target.checked)} />
          Incluir proyección a 30 días
        </label>
        <button
          className="btn"
          onClick={() =>
            toast(
              'Solicitud enviada (simulada). Aquí se llamará a POST /api/informes/pdf y el servidor devolverá el PDF con membrete y firma digital.',
            )
          }
        >
          Exportar PDF
        </button>
        <p className="hint" style={{ marginTop: 10 }}>
          La vista previa es un ejemplo. El membrete, la fecha oficial y la firma digital los aplica el
          backend.
        </p>
      </Card>
      <article className="paper" aria-label="Vista previa del informe">
        <div className="mh">
          <div className="logo">Logo institucional</div>
          <div>
            <b>[Nombre de la entidad territorial]</b>
            <span>Secretaría de Salud · Observatorio epidemiológico</span>
          </div>
        </div>
        <h2>Informe de situación epidemiológica covid-19</h2>
        <div className="meta">
          <span>Nº INF-2026-1104-001</span>
          <span>Fecha: {fecha}</span>
          <span>Territorio: {terrName}</span>
          <span>Dirigido a: {dest}</span>
        </div>
        <h3>Indicadores consolidados</h3>
        <table className="num">
          <tbody>
            <tr>
              <td>Casos confirmados</td>
              <td>{fmt(view.conf)}</td>
            </tr>
            <tr>
              <td>Casos activos</td>
              <td>{fmt(view.act)}</td>
            </tr>
            <tr>
              <td>Recuperados</td>
              <td>{fmt(view.rec)}</td>
            </tr>
            <tr>
              <td>Fallecidos</td>
              <td>{fmt(view.deaths)}</td>
            </tr>
            <tr>
              <td>Tasa de letalidad</td>
              <td>{pct((view.deaths / view.conf) * 100, 2)}</td>
            </tr>
            <tr>
              <td>Casos nuevos, últimos 7 días</td>
              <td>
                {fmt(view.last7)} ({change >= 0 ? '+' : ''}
                {dec(change, 1)} % vs semana previa)
              </td>
            </tr>
          </tbody>
        </table>
        <h3>Mayor incidencia semanal (por 100 mil hab.)</h3>
        <table className="num">
          <tbody>
            {top5.map((t) => (
              <tr key={t.n}>
                <td>{t.n}</td>
                <td>{dec(t.v, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {incl && (
          <>
            <h3>Proyección a 30 días (escenario simulado)</h3>
            <table className="num">
              <tbody>
                <tr>
                  <td>Parámetros</td>
                  <td>
                    R {dec(sim.R, 2)} · medidas {sim.m} % · R efectivo {dec(Re, 2)}
                  </td>
                </tr>
                <tr>
                  <td>Casos nuevos esperados en 30 días</td>
                  <td>{fmt(proj.cum30)}</td>
                </tr>
                <tr>
                  <td>Pico de casos activos a 60 días</td>
                  <td>{fmt(proj.peak)}</td>
                </tr>
              </tbody>
            </table>
          </>
        )}
        <h3>Observaciones</h3>
        <p style={{ fontSize: 13, margin: 0 }}>
          {terrName}: los casos nuevos {change >= 0 ? 'aumentaron' : 'disminuyeron'}{' '}
          {dec(Math.abs(change), 1)} % frente a la semana previa. Los datos son agregados y de ejemplo.
        </p>
        <div className="firma">
          <div className="sig">Firma digital</div>
          <div>
            Firmado por: [Nombre del funcionario] · [Cargo]
            <br />
            <code>SHA-256 a3f9 c21e 77b0 5d48 e1a2 90cc 4b17 d6f3</code>
            <br />
            {fecha}
          </div>
        </div>
      </article>
    </div>
  );
}
