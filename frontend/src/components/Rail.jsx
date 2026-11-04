import { Icon } from './ui/Icons.jsx';
import { NATIONAL_CONFIRMED } from '../data/mock.js';
import { dec, fmt, pct } from '../lib/format.js';

export default function Rail({ view, live }) {
  const share = view.conf / NATIONAL_CONFIRMED;
  const ex = Math.round(live.extra * share);
  const change = view.prev7 ? (view.last7 / view.prev7 - 1) * 100 : 0;
  const k = [
    {
      l: 'Casos confirmados',
      i: Icon.virus,
      v: fmt(view.conf + ex),
      s: '+' + fmt(view.last7) + ' en los últimos 7 días',
      flash: true,
    },
    {
      l: 'Tasa de letalidad',
      i: Icon.pct,
      v: pct((view.deaths / view.conf) * 100, 2),
      s: fmt(view.deaths) + ' fallecidos',
    },
    {
      l: 'Total de recuperados',
      i: Icon.check,
      v: fmt(view.rec),
      s: pct((view.rec / view.conf) * 100) + ' de los confirmados',
    },
    {
      l: 'Casos activos',
      i: Icon.pulse,
      v: fmt(view.act + ex),
      s: (change >= 0 ? '▲ +' : '▼ ') + dec(change, 1) + ' % vs semana previa',
      flash: true,
    },
  ];
  return (
    <aside className="rail" aria-label="Indicadores principales">
      {k.map((x) => (
        <div key={x.l} className="kpi">
          <div className="k-l">
            {x.i}
            {x.l}
          </div>
          <div className="k-v num" aria-live="polite">
            {x.flash ? (
              <span key={live.flash} className="flash">
                {x.v}
              </span>
            ) : (
              x.v
            )}
          </div>
          <div className="k-s num">{x.s}</div>
        </div>
      ))}
      <div className="note">Rol de consulta: solo indicadores agregados.</div>
    </aside>
  );
}
