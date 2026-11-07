import { Icon } from './ui/Icons.jsx';
import { fmt, pct } from '../utils/format.js';

const EMPTY = '—';

export default function Rail({ kpis, periodo, anio, loading, error }) {
  const available = Boolean(kpis) && !loading;
  const anual = periodo === 'anual' && anio;
  const k = [
    {
      l: 'Casos confirmados',
      i: Icon.virus,
      v: available ? fmt(kpis.casos_confirmados) : EMPTY,
      s: available
        ? anual
          ? `Reportados en ${anio}`
          : 'Acumulado al corte'
        : ' ',
    },
    {
      l: 'Tasa de letalidad',
      i: Icon.pct,
      v: available ? pct(kpis.tasa_letalidad * 100, 2) : EMPTY,
      s: available ? `${fmt(kpis.fallecidos)} fallecidos` : ' ',
    },
    {
      l: 'Total de recuperados',
      i: Icon.check,
      v: available ? fmt(kpis.recuperados) : EMPTY,
      s: available
        ? `${pct(kpis.tasa_recuperacion * 100)} de los confirmados`
        : ' ',
    },
    {
      l: 'Casos activos',
      i: Icon.pulse,
      v: available ? fmt(kpis.activos) : EMPTY,
      s: available
        ? anual
          ? `Al cierre de ${anio}`
          : 'Al corte del dataset'
        : ' ',
    },
  ];
  return (
    <aside
      className={`rail${loading ? ' is-loading' : ''}`}
      aria-label="Indicadores principales"
      aria-busy={loading}
    >
      {k.map((x) => (
        <div key={x.l} className="kpi">
          <div className="k-l">
            {x.i}
            {x.l}
          </div>
          <div className="k-v num" aria-live="polite">
            {x.v}
          </div>
          <div className="k-s num">{x.s}</div>
        </div>
      ))}
      {error ? (
        <div className="note" role="alert">
          {error}
        </div>
      ) : (
        <div className="note">
          {loading
            ? 'Consultando indicadores nacionales…'
            : 'Indicadores nacionales. El filtro territorial detalla los municipios en la tendencia y resalta el departamento.'}
        </div>
      )}
    </aside>
  );
}
