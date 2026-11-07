import { useState } from 'react';
import Card from '../ui/Card.jsx';
import Seg from '../ui/Seg.jsx';
import { fmt, pct } from '../../utils/format.js';

export default function TerritorialBars({ territorios, periodo, terr }) {
  const [metric, setMetric] = useState('casos');
  if (!territorios?.departamentos?.length) {
    return (
      <Card title="Distribución territorial">
        <p className="note">Sin datos territoriales para este período.</p>
      </Card>
    );
  }

  const allRows = territorios.departamentos;
  const rows = allRows.slice(0, 12);
  if (terr !== 'all') {
    const selected = allRows.find((row) => row.codigo === terr);
    if (selected && !rows.some((row) => row.codigo === terr)) {
      rows[rows.length - 1] = selected;
    }
  }
  const visibleCodes = new Set(rows.map((row) => row.codigo));
  const rest = allRows.filter((row) => !visibleCodes.has(row.codigo));
  if (rest.length) {
    const total = rest.reduce((sum, row) => sum + row.total, 0);
    const fallecidos = rest.reduce((sum, row) => sum + row.fallecidos, 0);
    const participacion = rest.reduce((sum, row) => sum + row.participacion, 0);
    rows.push({
      codigo: 'otros',
      nombre: 'Otros departamentos',
      total,
      fallecidos,
      tasa_letalidad: total ? fallecidos / total : 0,
      participacion,
    });
  }
  const valueOf = (row) =>
    metric === 'casos' ? row.total : row.tasa_letalidad * 100;
  const max = Math.max(...rows.map(valueOf), 1);
  const periodoLabel =
    periodo === 'anual' ? `Año ${territorios.anio}` : 'Acumulado';

  return (
    <Card
      title="Distribución territorial"
      sub={`Casos confirmados por departamento (principales + Otros) · ${periodoLabel}`}
      right={
        <Seg
          label="Métrica"
          value={metric}
          onChange={setMetric}
          options={[
            ['casos', 'Casos'],
            ['let', 'Letalidad'],
          ]}
        />
      }
    >
      <div>
        {rows.map((row) => {
          const value = valueOf(row);
          return (
            <div
              key={row.codigo}
              className={'brow' + (terr === row.codigo ? ' sel' : '')}
              title={
                `${row.nombre}: ${fmt(row.total)} casos · ` +
                `${pct(row.participacion)} del total · ` +
                `letalidad ${pct(row.tasa_letalidad * 100, 2)}`
              }
            >
              <span className="n">{row.nombre}</span>
              <div>
                <div
                  className="bar"
                  style={{ width: Math.max(2, (value / max) * 100) + '%' }}
                ></div>
              </div>
              <span className="v num">
                {metric === 'casos' ? fmt(value) : pct(value, 2)}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
