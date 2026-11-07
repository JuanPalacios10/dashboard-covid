import { useState } from 'react';
import { useSize } from '../../hooks/useSize.js';
import { compact, fmt, niceMax } from '../../utils/format.js';

export default function LinesChart({ short, long, series, height = 250, hline, marker, endLabels, aria }) {
  const [ref, w] = useSize();
  const [hi, setHi] = useState(null);
  const m = { l: 44, r: endLabels ? 96 : 14, t: 14, b: 26 };
  const iw = Math.max(10, w - m.l - m.r),
    ih = height - m.t - m.b,
    n = short.length;
  const vals = series.flatMap((s) => s.values).filter((v) => v != null);
  const top = niceMax(Math.max(...vals, hline ? hline.v : 0, 1) * 1.04);
  const X = (i) => m.l + (iw * i) / (n - 1),
    Y = (v) => m.t + ih * (1 - v / top);
  const ticks = [0, 1, 2, 3, 4].map((k) => (top * k) / 4);
  const xt = [0, 1, 2, 3, 4].map((k) => Math.round(((n - 1) * k) / 4));
  const path = (s) => {
    let d = '',
      pen = false;
    s.values.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1);
      pen = true;
    });
    return d;
  };
  const area = (s) => {
    const ix = s.values.map((v, i) => (v == null ? -1 : i)).filter((i) => i >= 0);
    return (
      path(s) +
      'L' +
      X(ix[ix.length - 1]).toFixed(1) +
      ' ' +
      Y(0) +
      'L' +
      X(ix[0]).toFixed(1) +
      ' ' +
      Y(0) +
      'Z'
    );
  };
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    setHi(Math.max(0, Math.min(n - 1, Math.round(((e.clientX - r.left - m.l) / iw) * (n - 1)))));
  };
  // etiquetas directas al final de cada línea, sin solaparse
  let ends = [];
  if (endLabels) {
    ends = series
      .filter((s) => s.end)
      .map((s) => {
        const last = s.values.length - 1;
        return { s, y: Y(s.values[last]) };
      })
      .sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 15) ends[i].y = ends[i - 1].y + 15;
  }
  const tipX = hi == null ? 0 : Math.min(Math.max(X(hi), 92), w - 92);
  return (
    <div ref={ref} className="chartwrap" style={{ height }}>
      <svg
        width={w}
        height={height}
        role="img"
        aria-label={aria}
        style={{ display: 'block', touchAction: 'pan-y' }}
        onPointerMove={onMove}
        onPointerLeave={() => setHi(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={m.l} x2={w - m.r} y1={Y(t)} y2={Y(t)} />
            <text className="axis" x={m.l - 8} y={Y(t) + 4} textAnchor="end">
              {compact(t)}
            </text>
          </g>
        ))}
        {xt.map((i) => (
          <text
            key={i}
            className="axis"
            x={X(i)}
            y={height - 6}
            textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
          >
            {short[i]}
          </text>
        ))}
        {hline && (
          <g>
            <line
              x1={m.l}
              x2={w - m.r}
              y1={Y(hline.v)}
              y2={Y(hline.v)}
              style={{ stroke: 'var(--ink2)' }}
              strokeWidth="1.5"
              strokeDasharray="2 4"
            />
            <text className="lbl" x={m.l + 6} y={Y(hline.v) - 6}>
              {hline.label}
            </text>
          </g>
        )}
        {marker != null && (
          <g>
            <line
              x1={X(marker)}
              x2={X(marker)}
              y1={m.t}
              y2={m.t + ih}
              style={{ stroke: 'var(--muted)' }}
              strokeDasharray="3 3"
            />
            <text className="axis" x={X(marker) - 5} y={m.t + 10} textAnchor="end">
              Hoy
            </text>
          </g>
        )}
        {series
          .filter((s) => s.fill)
          .map((s) => (
            <path key={'a' + s.name} d={area(s)} style={{ fill: s.color, opacity: 0.12 }} />
          ))}
        {series.map((s) => (
          <path
            key={s.name}
            d={path(s)}
            fill="none"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeWidth={s.width || 2}
            strokeDasharray={s.dash || undefined}
            style={{ stroke: s.color, opacity: s.faint ? 0.55 : 1 }}
          />
        ))}
        {ends.map((e) => (
          <g key={e.s.name}>
            <circle cx={X(n - 1) + 10} cy={e.y} r="4" style={{ fill: e.s.color }} />
            <text className="lbl" x={X(n - 1) + 18} y={e.y + 4}>
              {e.s.end}
            </text>
          </g>
        ))}
        {hi != null && (
          <g>
            <line
              x1={X(hi)}
              x2={X(hi)}
              y1={m.t}
              y2={m.t + ih}
              style={{ stroke: 'var(--ink2)' }}
              strokeWidth="1"
            />
            {series.map((s) =>
              s.values[hi] == null ? null : (
                <circle
                  key={s.name}
                  cx={X(hi)}
                  cy={Y(s.values[hi])}
                  r="4.5"
                  strokeWidth="2"
                  style={{ fill: s.color, stroke: 'var(--surface)' }}
                />
              ),
            )}
          </g>
        )}
      </svg>
      {hi != null && (
        <div className="tip num" style={{ left: tipX, transform: 'translateX(-50%)', top: 4 }}>
          <b>{long[hi]}</b>
          {series
            .filter((s) => s.values[hi] != null)
            .map((s) => (
              <div key={s.name}>
                <span>
                  <i className="dot" style={{ background: s.color }}></i>
                  {s.name}
                </span>
                <span>{(s.fmt || fmt)(s.values[hi])}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
