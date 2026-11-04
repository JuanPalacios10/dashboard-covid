import { useState } from 'react';
import Card from '../ui/Card.jsx';
import Seg from '../ui/Seg.jsx';
import { AGE, AGE_CFR } from '../../data/mock.js';
import { dec, fmt, pct, sum } from '../../lib/format.js';

export default function AgeBars({ view, range }) {
  const [metric, setMetric] = useState('casos');
  const vals = metric === 'casos' ? view.ageShare : AGE_CFR;
  const max = Math.max(...vals);
  const total = sum(view.series.slice(-range));
  return (
    <Card
      title="Grupos etarios"
      sub={
        metric === 'casos'
          ? '% de los casos del período'
          : 'Letalidad por grupo (% de fallecidos entre confirmados)'
      }
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
      <div className="age" role="img" aria-label="Barras por grupo etario">
        {vals.map((v, i) => (
          <div
            key={i}
            className="col"
            title={
              AGE[i] +
              ' años: ' +
              (metric === 'casos' ? pct(v) + ' · ' + fmt((total * v) / 100) + ' casos' : pct(v, 2))
            }
          >
            <span className="v num">{metric === 'casos' ? dec(v, 0) : dec(v, v < 1 ? 2 : 1)}</span>
            <div className="b" style={{ height: (v / max) * 100 * 0.78 + '%', minHeight: 2 }}></div>
            <span className="x">{AGE[i]}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
