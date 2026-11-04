import React, { useState } from 'react';
import Card from '../ui/Card.jsx';
import { DAYS, DEPTS, dateAt } from '../../data/mock.js';
import { dShort, dec, sum } from '../../lib/format.js';

export default function Heatmap({ terr }) {
  const [hov, setHov] = useState(null);
  const W = 12,
    start = DAYS - W * 7;
  const cells = DEPTS.map((d) =>
    Array.from({ length: W }, (_, k) => sum(d.series.slice(start + 7 * k, start + 7 * k + 7)) / (d.pop * 10)),
  );
  const max = Math.max(...cells.flat());
  const wl = (k) => dShort(dateAt(start + 7 * k)) + ' – ' + dShort(dateAt(start + 7 * k + 6));
  return (
    <Card
      title="Mapa de calor semanal"
      sub="Casos por 100 mil habitantes, últimas 12 semanas"
      right={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
          menos <span className="ramp"></span> más
        </div>
      }
    >
      <div className="hmread num" aria-live="polite">
        {hov ? (
          <>
            <b>{DEPTS[hov[0]].name}</b> · semana {wl(hov[1])} · {dec(cells[hov[0]][hov[1]], 1)} por 100 mil
          </>
        ) : (
          'Pase el cursor sobre una celda para ver el valor.'
        )}
      </div>
      <div className="hm" style={{ gridTemplateColumns: '112px repeat(' + W + ',minmax(0,1fr))' }}>
        {DEPTS.map((d, r) => (
          <React.Fragment key={d.id}>
            <span className={'rn' + (terr === d.id ? ' sel' : '')}>{d.name}</span>
            {cells[r].map((v, k) => (
              <button
                key={k}
                className="c"
                aria-label={d.name + ', semana ' + wl(k) + ': ' + dec(v, 1)}
                style={{
                  background:
                    'color-mix(in srgb, var(--teal) ' +
                    Math.round(8 + 92 * Math.pow(v / max, 1.1)) +
                    '%, var(--surface))',
                }}
                onPointerEnter={() => setHov([r, k])}
                onFocus={() => setHov([r, k])}
                onPointerLeave={() => setHov(null)}
              ></button>
            ))}
          </React.Fragment>
        ))}
        <span></span>
        {Array.from({ length: W }, (_, k) => (
          <span key={k} className="axis" style={{ textAlign: 'center' }}>
            {k % 3 === 0 ? dShort(dateAt(start + 7 * k)) : ''}
          </span>
        ))}
      </div>
    </Card>
  );
}
