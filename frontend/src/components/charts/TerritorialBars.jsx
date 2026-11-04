import { useState } from 'react';
import Card from '../ui/Card.jsx';
import Seg from '../ui/Seg.jsx';
import { DEPTS } from '../../data/mock.js';
import { dec, fmt, sum } from '../../lib/format.js';

export default function TerritorialBars({ range, terr }) {
  const [metric, setMetric] = useState('casos');
  const rows = DEPTS.map((d) => {
    const c = sum(d.series.slice(-range));
    return { d, c, inc: c / (d.pop * 10) };
  }).sort((a, b) => (metric === 'casos' ? b.c - a.c : b.inc - a.inc));
  const max = Math.max(...rows.map((r) => (metric === 'casos' ? r.c : r.inc)));
  return (
    <Card
      title="Distribución territorial"
      sub={'Últimos ' + range + ' días'}
      right={
        <Seg
          label="Métrica"
          value={metric}
          onChange={setMetric}
          options={[
            ['casos', 'Casos'],
            ['inc', 'Por 100 mil'],
          ]}
        />
      }
    >
      <div>
        {rows.map((r) => {
          const v = metric === 'casos' ? r.c : r.inc;
          return (
            <div
              key={r.d.id}
              className={'brow' + (terr === r.d.id ? ' sel' : '')}
              title={
                r.d.name + ': ' + (metric === 'casos' ? fmt(v) + ' casos' : dec(v, 1) + ' por 100 mil hab.')
              }
            >
              <span className="n">{r.d.name}</span>
              <div>
                <div className="bar" style={{ width: Math.max(2, (v / max) * 100) + '%' }}></div>
              </div>
              <span className="v num">{metric === 'casos' ? fmt(v) : dec(v, 1)}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
