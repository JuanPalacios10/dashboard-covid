import React, { useState } from 'react';
import Card from '../ui/Card.jsx';
import { fmt } from '../../utils/format.js';

export default function Heatmap({ heatmap, periodo, terr }) {
  const [hov, setHov] = useState(null);

  if (!heatmap?.filas?.length) {
    return (
      <Card title="Mapa de calor">
        <p className="note">Sin datos de calor para este período.</p>
      </Card>
    );
  }

  const { columnas } = heatmap;
  const filas = heatmap.filas.slice(0, 12);
  if (terr !== 'all') {
    const selected = heatmap.filas.find((row) => row.codigo === terr);
    if (selected && !filas.some((row) => row.codigo === terr)) {
      filas[filas.length - 1] = selected;
    }
  }
  const visibleCodes = new Set(filas.map((row) => row.codigo));
  const rest = heatmap.filas.filter((row) => !visibleCodes.has(row.codigo));
  if (rest.length) {
    const valores = columnas.map((_, index) =>
      rest.reduce((sum, row) => sum + row.valores[index], 0),
    );
    filas.push({
      codigo: 'otros',
      nombre: 'Otros departamentos',
      total: valores.reduce((sum, value) => sum + value, 0),
      valores,
    });
  }
  const max = Math.max(...filas.flatMap((row) => row.valores), 1);
  const sub =
    periodo === 'anual'
      ? `Casos por departamento y mes (principales + Otros) · Año ${heatmap.anio}`
      : 'Casos por departamento y año (principales + Otros) · Acumulado';
  const hovered = hov ? filas[hov[0]] : null;

  return (
    <Card
      title="Mapa de calor"
      sub={sub}
      right={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
          menos <span className="ramp"></span> más
        </div>
      }
    >
      <div className="hmread num" aria-live="polite">
        {hovered ? (
          <>
            <b>{hovered.nombre}</b> · {columnas[hov[1]]} ·{' '}
            {fmt(hovered.valores[hov[1]])} casos
          </>
        ) : (
          'Pase el cursor sobre una celda para ver el valor.'
        )}
      </div>
      <div
        className="hm"
        style={{
          gridTemplateColumns: '112px repeat(' + columnas.length + ',minmax(0,1fr))',
        }}
      >
        {filas.map((row, rowIndex) => (
          <React.Fragment key={row.codigo}>
            <span className={'rn' + (terr === row.codigo ? ' sel' : '')}>
              {row.nombre}
            </span>
            {row.valores.map((value, columnIndex) => (
              <button
                key={columnIndex}
                className="c"
                aria-label={`${row.nombre}, ${columnas[columnIndex]}: ${fmt(value)} casos`}
                style={{
                  background:
                    'color-mix(in srgb, var(--teal) ' +
                    Math.round(8 + 92 * Math.pow(value / max, 1.1)) +
                    '%, var(--surface))',
                }}
                onPointerEnter={() => setHov([rowIndex, columnIndex])}
                onFocus={() => setHov([rowIndex, columnIndex])}
                onPointerLeave={() => setHov(null)}
              ></button>
            ))}
          </React.Fragment>
        ))}
        <span></span>
        {columnas.map((column, index) => (
          <span key={index} className="axis" style={{ textAlign: 'center' }}>
            {column}
          </span>
        ))}
      </div>
    </Card>
  );
}
