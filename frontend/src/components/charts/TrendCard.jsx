import LinesChart from './LinesChart.jsx';
import Card from '../ui/Card.jsx';
import { DAYS, dateAt } from '../../data/mock.js';
import { dLong, dShort, fmt } from '../../utils/format.js';

export default function TrendCard({ view, range }) {
  const sl = (a) => a.slice(-range);
  const idx = Array.from({ length: DAYS }, (_, i) => i).slice(-range);
  const short = idx.map((i) => dShort(dateAt(i))),
    long = idx.map((i) => dLong(dateAt(i)));
  const series = [
    {
      name: 'Casos diarios',
      color: 'var(--cat-a)',
      values: sl(view.series),
      width: 1.5,
      faint: true,
      fill: true,
    },
    {
      name: 'Promedio 7 días',
      color: 'var(--cat-b)',
      values: sl(view.avg7).map((v) => (v == null ? null : Math.round(v))),
      width: 2.6,
    },
  ];
  return (
    <Card
      className="span2"
      title="Tendencia de contagios"
      sub={'Casos nuevos confirmados por día · últimos ' + range + ' días'}
    >
      <div className="legend">
        <span>
          <i className="sw" style={{ background: 'var(--cat-a)', opacity: 0.6 }}></i>Casos diarios
        </span>
        <span>
          <i className="sw" style={{ background: 'var(--cat-b)' }}></i>Promedio 7 días
        </span>
      </div>
      <LinesChart
        short={short}
        long={long}
        series={series}
        height={250}
        aria="Casos nuevos por día y promedio de 7 días"
      />
      <details>
        <summary>Ver datos en tabla</summary>
        <div className="tscroll">
          <table className="tbl num">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Casos</th>
                <th>Prom. 7 días</th>
              </tr>
            </thead>
            <tbody>
              {idx
                .slice(-10)
                .reverse()
                .map((i) => (
                  <tr key={i}>
                    <td>{dLong(dateAt(i))}</td>
                    <td>{fmt(view.series[i])}</td>
                    <td>{view.avg7[i] == null ? '–' : fmt(view.avg7[i])}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  );
}
