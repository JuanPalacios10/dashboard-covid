import LinesChart from './LinesChart.jsx';
import Card from '../ui/Card.jsx';
import { dLong, dShort, fmt } from '../../utils/format.js';

const PALETTE = [
  'var(--cat-a)',
  'var(--cat-b)',
  '#7c5cff',
  '#f59e0b',
  '#ef4444',
  '#10b981',
  '#64748b',
];

function movingAverage(values, window) {
  return values.map((_, index) => {
    if (index < window - 1) return null;
    const slice = values.slice(index - window + 1, index + 1);
    return Math.round(slice.reduce((total, value) => total + value, 0) / window);
  });
}

function parsePeriodo(value, granularidad) {
  return granularidad === 'diaria'
    ? new Date(`${value}T00:00:00`)
    : new Date(`${value}-01T00:00:00`);
}

export default function TrendCard({ series, periodo, anio, terrName }) {
  if (
    !series?.series?.length ||
    series.series.every((item) => item.total === 0)
  ) {
    return (
      <Card className="span2" title="Tendencia de contagios">
        <p className="note">Sin casos reportados para este período.</p>
      </Card>
    );
  }

  const diaria = series.granularidad === 'diaria';
  const fechas = series.fechas.map((value) => parsePeriodo(value, series.granularidad));
  const short = fechas.map((date) =>
    diaria
      ? dShort(date)
      : date
          .toLocaleDateString('es-CO', { month: 'short', year: '2-digit' })
          .replace('.', ''),
  );
  const long = fechas.map((date) =>
    diaria
      ? dLong(date)
      : date.toLocaleDateString('es-CO', { month: 'long', year: 'numeric' }),
  );

  const nacional = series.tipo === 'nacional';
  let chartSeries;
  let tableSeries;
  let sub;

  if (diaria && nacional) {
    const raw = series.series[0];
    const average = movingAverage(raw.valores, 7);
    chartSeries = [
      {
        name: 'Casos diarios',
        color: PALETTE[0],
        values: raw.valores,
        width: 1.5,
        faint: true,
        fill: true,
      },
      {
        name: 'Promedio 7 días',
        color: PALETTE[1],
        values: average,
        width: 2.6,
      },
    ];
    tableSeries = chartSeries;
    sub = `Casos nuevos confirmados por día · ${terrName}${
      periodo === 'anual' ? ` · ${anio}` : ' · Acumulado'
    }`;
  } else if (diaria) {
    chartSeries = series.series.map((item, index) => ({
      name: item.nombre,
      color: PALETTE[index % PALETTE.length],
      values: movingAverage(item.valores, 7),
      width: 2.2,
    }));
    tableSeries = chartSeries;
    sub = `Promedio móvil de 7 días por municipio · ${terrName}${
      periodo === 'anual' ? ` · ${anio}` : ''
    }`;
  } else {
    chartSeries = series.series.map((item, index) => ({
      name: item.nombre,
      color: PALETTE[index % PALETTE.length],
      values: item.valores,
      width: index === 0 ? 2.6 : 1.8,
    }));
    tableSeries = chartSeries;
    sub = `Casos confirmados por mes · ${terrName} · Acumulado`;
  }

  const tableRows = fechas
    .map((_, index) => index)
    .slice(-10)
    .reverse();

  return (
    <Card className="span2" title="Tendencia de contagios" sub={sub}>
      <div className="legend">
        {chartSeries.map((item) => (
          <span key={item.name}>
            <i className="sw" style={{ background: item.color, opacity: item.faint ? 0.6 : 1 }}></i>
            {item.name}
          </span>
        ))}
      </div>
      <LinesChart
        short={short}
        long={long}
        series={chartSeries}
        height={250}
        aria={`Tendencia de casos para ${terrName}`}
      />
      <details>
        <summary>Ver datos en tabla</summary>
        <div className="tscroll">
          <table className="tbl num">
            <thead>
              <tr>
                <th>{diaria ? 'Fecha' : 'Mes'}</th>
                {tableSeries.map((item) => (
                  <th key={item.name}>{item.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((index) => (
                <tr key={index}>
                  <td>{long[index]}</td>
                  {tableSeries.map((item) => (
                    <td key={item.name}>
                      {item.values[index] == null ? '–' : fmt(item.values[index])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  );
}
