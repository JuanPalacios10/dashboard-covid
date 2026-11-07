import { useMemo } from 'react';
import LinesChart from '../components/charts/LinesChart.jsx';
import Card from '../components/ui/Card.jsx';
import { DAYS, PRESETS, dateAt, simulate, summarize } from '../data/mock.js';
import { compact, dLong, dShort, dec, fmt } from '../utils/format.js';

export default function Proyecciones({ view, sim, setSim }) {
  const H = 14,
    n = H + 60;
  const dates = Array.from({ length: n }, (_, i) =>
    i < H ? dateAt(DAYS - H + i) : new Date(2026, 10, 4 + (i - H + 1)),
  );
  const short = dates.map(dShort),
    long = dates.map(dLong);
  const runs = useMemo(() => {
    const all = PRESETS.map((p) => ({ ...p, res: simulate(view, p.R, p.m) }));
    const custom = { id: 'sim', name: 'Tu simulación', res: simulate(view, sim.R, sim.m) };
    return { all, custom };
  }, [view, sim]);
  const histNew = view.avg7.slice(-H),
    histAct = view.actS.slice(-H),
    histIcu = histAct.map((v) => v * 0.004);
  const todayNew = histNew[H - 1],
    todayAct = histAct[H - 1],
    todayIcu = histIcu[H - 1];
  const build = (key, hist, today) => {
    const proj = (r) => [...Array(H - 1).fill(null), today, ...r];
    const s = [
      {
        name: 'Observado',
        color: 'var(--ink2)',
        values: [...hist, ...Array(60).fill(null)],
        width: 2.4,
        fmt: (v) => fmt(v),
      },
    ];
    runs.all.forEach((p) =>
      s.push({ name: p.name, color: 'var(' + p.v + ')', values: proj(p.res[key]), end: p.name, fmt }),
    );
    s.push({
      name: 'Tu simulación',
      color: 'var(--sim)',
      values: proj(runs.custom.res[key]),
      dash: '6 4',
      width: 2.6,
      end: 'Tu simulación',
      fmt,
    });
    return s;
  };
  const sCustom = summarize(view, runs.custom.res);
  const Re = runs.custom.res.Re;
  const state =
    Re < 0.95
      ? ['Decrece', 'var(--good)']
      : Re <= 1.05
        ? ['Estable', 'var(--ink2)']
        : ['Crece', 'var(--bad)'];
  const legend = (
    <div className="legend">
      <span>
        <i className="sw" style={{ background: 'var(--ink2)' }}></i>Observado
      </span>
      {PRESETS.map((p) => (
        <span key={p.id}>
          <i className="sw" style={{ background: 'var(' + p.v + ')' }}></i>
          {p.name}
        </span>
      ))}
      <span>
        <i className="sw d"></i>Tu simulación
      </span>
    </div>
  );
  const when = (d) => dShort(d);
  return (
    <div className="main">
      <Card
        title="Simulador de escenarios"
        sub="Ajuste los controles o elija un escenario de referencia. Modelo de demostración."
      >
        <div className="ctrl">
          <div>
            <div className="sl">
              <div className="row">
                <label htmlFor="sl-r">Velocidad de contagio (R base)</label>
                <output htmlFor="sl-r" className="num">
                  {dec(sim.R, 2)}
                </output>
              </div>
              <input
                id="sl-r"
                type="range"
                min="0.6"
                max="2"
                step="0.05"
                value={sim.R}
                onChange={(e) => setSim({ ...sim, R: +e.target.value })}
              />
              <span className="hint">Contagios que genera cada caso sin medidas adicionales.</span>
            </div>
            <div className="sl">
              <div className="row">
                <label htmlFor="sl-m">Rigor de las medidas sanitarias</label>
                <output htmlFor="sl-m" className="num">
                  {sim.m} %
                </output>
              </div>
              <input
                id="sl-m"
                type="range"
                min="0"
                max="100"
                step="5"
                value={sim.m}
                onChange={(e) => setSim({ ...sim, m: +e.target.value })}
              />
              <span className="hint">Mascarillas, aforos, cierres, vacunación de refuerzo.</span>
            </div>
            <div className="sim num">
              <b>R efectivo {dec(Re, 2)}</b>{' '}
              <span className="state" style={{ color: state[1] }}>
                {state[0]}
              </span>
              <br />
              Pico de {fmt(sCustom.peak)} casos activos el {when(sCustom.peakDate)} ·
              {sCustom.satDate ? (
                <>
                  las camas UCI de referencia ({fmt(view.cap)}) se superan el {when(sCustom.satDate)}.
                </>
              ) : (
                <>sin saturación de camas UCI (capacidad {fmt(view.cap)}).</>
              )}
            </div>
          </div>
          <div className="scen" role="group" aria-label="Escenarios de referencia">
            {runs.all.map((p) => {
              const s = summarize(view, p.res);
              const on = sim.R === p.R && sim.m === p.m;
              return (
                <button
                  key={p.id}
                  className="sc num"
                  aria-pressed={on}
                  onClick={() => setSim({ R: p.R, m: p.m })}
                >
                  <h4>
                    <i className="sw b" style={{ background: 'var(' + p.v + ')' }}></i>
                    {p.name}
                  </h4>
                  <span>
                    R {dec(p.R, 2)} · medidas {p.m} %
                  </span>
                  <span>
                    R efectivo <b style={{ color: 'var(--ink)' }}>{dec(p.res.Re, 2)}</b>
                  </span>
                  <span>
                    Pico: <b style={{ color: 'var(--ink)' }}>{compact(s.peak)}</b> activos ({when(s.peakDate)}
                    )
                  </span>
                  <span>{s.satDate ? 'UCI se satura el ' + when(s.satDate) : 'UCI sin saturación'}</span>
                </button>
              );
            })}
          </div>
        </div>
      </Card>
      <Card
        className="span2"
        title="Casos nuevos diarios proyectados"
        sub="Promedio de 7 días observado y proyección a 60 días"
      >
        {legend}
        <LinesChart
          short={short}
          long={long}
          marker={H - 1}
          endLabels={true}
          height={270}
          series={build('nw', histNew, todayNew)}
          aria="Proyección de casos nuevos por día en tres escenarios y la simulación del usuario"
        />
      </Card>
      <div className="grid2">
        <Card title="Casos activos proyectados" sub="Personas con infección vigente">
          <LinesChart
            short={short}
            long={long}
            marker={H - 1}
            endLabels={true}
            height={250}
            series={build('ac', histAct, todayAct)}
            aria="Proyección de casos activos"
          />
        </Card>
        <Card
          title="Demanda de camas UCI"
          sub={'Frente a la capacidad de referencia (' + fmt(view.cap) + ' camas)'}
        >
          <LinesChart
            short={short}
            long={long}
            marker={H - 1}
            endLabels={true}
            height={250}
            hline={{ v: view.cap, label: 'Capacidad ' + fmt(view.cap) }}
            series={build('icu', histIcu, todayIcu)}
            aria="Proyección de ocupación de camas UCI frente a la capacidad"
          />
        </Card>
      </div>
      <Card title="Comparación de escenarios" sub="Valores proyectados">
        <div className="tscroll">
          <table className="tbl num">
            <thead>
              <tr>
                <th>Escenario</th>
                <th>R efectivo</th>
                <th>Casos nuevos 30 d</th>
                <th>Casos nuevos 60 d</th>
                <th>Pico de activos</th>
                <th>Fecha del pico</th>
                <th>UCI máxima</th>
              </tr>
            </thead>
            <tbody>
              {[...runs.all, runs.custom].map((p) => {
                const s = summarize(view, p.res);
                return (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td>{dec(p.res.Re, 2)}</td>
                    <td>{fmt(s.cum30)}</td>
                    <td>{fmt(s.cum60)}</td>
                    <td>{fmt(s.peak)}</td>
                    <td>{when(s.peakDate)}</td>
                    <td>{fmt(s.icuMax)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
