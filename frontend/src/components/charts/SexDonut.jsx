import Card from '../ui/Card.jsx';
import { compact, fmt, pct } from '../../utils/format.js';

const COLORS = {
  Femenino: 'var(--cat-a)',
  Masculino: 'var(--cat-b)',
  Indeterminado: '#7c5cff',
  'No informado': '#94a3b8',
};

export default function SexDonut({ demografia, periodo, anio }) {
  if (!demografia?.sexo?.length) {
    return (
      <Card title="Casos por sexo">
        <p className="note">Sin datos demográficos para este período.</p>
      </Card>
    );
  }

  const parts = demografia.sexo
    .filter((item) => item.total > 0)
    .map((item) => ({
      ...item,
      p: item.total / demografia.total,
      color: COLORS[item.nombre] ?? '#64748b',
    }));
  const total = parts.reduce((sum, item) => sum + item.total, 0);
  const R = 56;
  const C = 2 * Math.PI * R;
  const segments = parts.map((item, index) => ({
    ...item,
    length: item.p * C,
    offset: parts
      .slice(0, index)
      .reduce((sum, previous) => sum + previous.p * C, 0),
  }));
  const periodoLabel = periodo === 'anual' ? `Año ${anio}` : 'Acumulado';

  if (!parts.length) {
    return (
      <Card title="Casos por sexo">
        <p className="note">Sin datos demográficos para este período.</p>
      </Card>
    );
  }

  return (
    <Card
      title="Casos por sexo"
      sub={`Distribución nacional de casos · ${periodoLabel}`}
    >
      <div className="donutrow">
        <svg
          width="164"
          height="164"
          viewBox="0 0 164 164"
          role="img"
          aria-label={parts
            .map((item) => `${item.nombre} ${pct(item.porcentaje)}`)
            .join(', ')}
        >
          <g transform="rotate(-90 82 82)">
            {segments.map((item) => {
              const visible = Math.max(item.length - 2, 0);
              return (
                <circle
                  key={item.nombre}
                  cx="82"
                  cy="82"
                  r={R}
                  fill="none"
                  strokeWidth="24"
                  strokeDasharray={visible + ' ' + (C - visible)}
                  strokeDashoffset={-item.offset}
                  style={{ stroke: item.color }}
                />
              );
            })}
          </g>
          <text
            x="82"
            y="80"
            textAnchor="middle"
            style={{ fill: 'var(--ink)', font: '800 20px var(--display)' }}
          >
            {compact(total)}
          </text>
          <text x="82" y="98" textAnchor="middle" className="axis">
            casos
          </text>
        </svg>
        <div className="dl num">
          {parts.map((item) => (
            <div key={item.nombre}>
              <i className="sw b" style={{ background: item.color }}></i>
              <b>
                {item.nombre} · {pct(item.porcentaje)}
              </b>
              <span className="sub">{fmt(item.total)} casos</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
