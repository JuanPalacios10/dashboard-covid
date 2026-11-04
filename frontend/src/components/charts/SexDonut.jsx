import Card from '../ui/Card.jsx';
import { compact, fmt, pct, sum } from '../../lib/format.js';

export default function SexDonut({ view, range }) {
  const total = sum(view.series.slice(-range));
  const F = view.femShare,
    parts = [
      { name: 'Femenino', p: F, color: 'var(--cat-a)' },
      { name: 'Masculino', p: 1 - F, color: 'var(--cat-b)' },
    ];
  const R = 56,
    C = 2 * Math.PI * R;
  let off = 0;
  return (
    <Card title="Casos por sexo" sub={'Últimos ' + range + ' días'}>
      <div className="donutrow">
        <svg
          width="164"
          height="164"
          viewBox="0 0 164 164"
          role="img"
          aria-label={'Femenino ' + pct(F * 100) + ', masculino ' + pct((1 - F) * 100)}
        >
          <g transform="rotate(-90 82 82)">
            {parts.map((s) => {
              const len = s.p * C;
              const el = (
                <circle
                  key={s.name}
                  cx="82"
                  cy="82"
                  r={R}
                  fill="none"
                  strokeWidth="24"
                  strokeDasharray={len - 2 + ' ' + (C - len + 2)}
                  strokeDashoffset={-off}
                  style={{ stroke: s.color }}
                />
              );
              off += len;
              return el;
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
          {parts.map((s) => (
            <div key={s.name}>
              <i className="sw b" style={{ background: s.color }}></i>
              <b>
                {s.name} · {pct(s.p * 100)}
              </b>
              <span className="sub">{fmt(total * s.p)} casos</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
