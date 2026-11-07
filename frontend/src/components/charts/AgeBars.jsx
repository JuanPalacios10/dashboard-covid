import { useState } from 'react';
import Card from '../ui/Card.jsx';
import Seg from '../ui/Seg.jsx';
import { dec, fmt, pct } from '../../utils/format.js';

export default function AgeBars({ demografia, periodo, anio }) {
  const [metric, setMetric] = useState('casos');

  if (!demografia?.edad?.length) {
    return (
      <Card title="Grupos etarios">
        <p className="note">Sin datos de edad para este período.</p>
      </Card>
    );
  }

  const grupos = demografia.edad;
  const values = grupos.map((item) =>
    metric === 'casos' ? item.porcentaje : item.tasa_letalidad * 100,
  );
  const max = Math.max(...values, 1);
  const periodoLabel = periodo === 'anual' ? `Año ${anio}` : 'Acumulado';

  return (
    <Card
      title="Grupos etarios"
      sub={
        (metric === 'casos'
          ? '% de los casos del período'
          : 'Letalidad por grupo (% de fallecidos entre confirmados)') +
        ` · Nacional · ${periodoLabel}`
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
        {values.map((value, index) => {
          const item = grupos[index];
          return (
            <div
              key={item.grupo}
              className="col"
              title={
                metric === 'casos'
                  ? `${item.grupo} años: ${pct(item.porcentaje)} · ${fmt(item.total)} casos`
                  : `${item.grupo} años: ${pct(item.tasa_letalidad * 100, 2)} · ${fmt(
                      item.fallecidos,
                    )} fallecidos de ${fmt(item.total)}`
              }
            >
              <span className="v num">
                {metric === 'casos' ? dec(value, 0) : dec(value, value < 1 ? 2 : 1)}
              </span>
              <div
                className="b"
                style={{ height: (value / max) * 100 * 0.78 + '%', minHeight: 2 }}
              ></div>
              <span className="x">{item.grupo}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
