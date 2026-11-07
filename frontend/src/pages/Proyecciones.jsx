import { useEffect, useMemo, useState } from 'react';
import LinesChart from '../components/charts/LinesChart.jsx';
import Card from '../components/ui/Card.jsx';
import { getApiErrorMessage, proyeccionApi } from '../utils/api.js';
import { compact, dLong, dShort, dec, fmt, pct } from '../utils/format.js';

const HORIZONTES = [30, 60, 90];
const PREVIEW_DAYS = 14;
const COLORS = {
  optimista: 'var(--s-opt)',
  moderado: 'var(--s-mod)',
  pesimista: 'var(--s-pes)',
  personalizado: 'var(--sim)',
};

const parseDate = (value) => new Date(`${value}T00:00:00`);
const clampR = (value) => Math.min(3, Math.max(0.3, Number(value) || 0.3));

export default function Proyecciones({ token, anio, terr, terrName, sim, setSim }) {
  const [data, setData] = useState(null);
  const [horizonte, setHorizonte] = useState(60);
  const [state, setState] = useState({ loading: true, error: '' });

  useEffect(() => {
    if (!token) return undefined;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      setState((current) => ({ ...current, loading: true, error: '' }));
      proyeccionApi
        .obtener(token, {
          anio,
          departamento: terr === 'all' ? undefined : terr,
          horizonte,
          r: sim.R,
          medidas: sim.m,
          signal: controller.signal,
        })
        .then((payload) => {
          if (controller.signal.aborted) return;
          setData(payload);
          setState({ loading: false, error: '' });
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          setData(null);
          setState({ loading: false, error: getApiErrorMessage(error) });
        });
    }, 180);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [token, anio, terr, horizonte, sim.R, sim.m]);

  const posteriorByDate = useMemo(() => {
    const map = new Map();
    const posterior = data?.observado_posterior;
    if (posterior?.fechas) {
      posterior.fechas.forEach((fecha, index) => {
        map.set(fecha, posterior.casos_diarios[index] ?? 0);
      });
    }
    return map;
  }, [data]);

  if (!data && state.loading) {
    return (
      <div className="main">
        <Card className="span2" title="Cargando proyecciones">
          <p className="note">Calculando la proyección con la base histórica del período…</p>
        </Card>
      </div>
    );
  }

  if (!data && state.error) {
    return (
      <div className="main">
        <Card className="span2" title="Proyecciones no disponibles">
          <p className="note" role="alert">
            {state.error}
          </p>
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="main">
        <Card className="span2" title="Proyecciones no disponibles">
          <p className="note">No hay datos para construir la proyección.</p>
        </Card>
      </div>
    );
  }

  const base = data.base;
  const baseDates = base.fechas.slice(-PREVIEW_DAYS);
  const projectionDates = data.fechas_proyeccion;
  const historicalAverage = base.promedio_7d.slice(-PREVIEW_DAYS);
  const historicalActive = base.activos_diarios.slice(-PREVIEW_DAYS);
  const lastAverage = historicalAverage[historicalAverage.length - 1] ?? 0;
  const lastActive = historicalActive[historicalActive.length - 1] ?? base.activos_al_corte;
  const allDates = [...baseDates, ...projectionDates];
  const short = allDates.map((value) => dShort(parseDate(value)));
  const long = allDates.map((value) => dLong(parseDate(value)));
  const baseLength = baseDates.length;
  const projectionLength = projectionDates.length;
  const escenarios = data.escenarios;
  const presets = escenarios.filter((scenario) => scenario.id !== 'personalizado');
  const custom = escenarios.find((scenario) => scenario.id === 'personalizado');
  const fechaCorte = dLong(parseDate(data.fecha_corte));
  const quality = data.calidad;
  const effectiveR = custom?.r_efectivo ?? 0;
  const stateLabel =
    effectiveR < 0.95
      ? ['Decrece', 'var(--good)']
      : effectiveR <= 1.05
        ? ['Estable', 'var(--ink2)']
        : ['Crece', 'var(--bad)'];
  const peakDate = custom ? dLong(parseDate(custom.resumen.fecha_pico)) : '—';
  const noRecentCases = base.casos_diarios.every((value) => value === 0);
  const posteriorValues = projectionDates.map((fecha) =>
    posteriorByDate.has(fecha) ? posteriorByDate.get(fecha) : null,
  );

  const historicalSeries = {
    name: 'Observado',
    color: 'var(--ink2)',
    values: [...historicalAverage, ...Array(projectionLength).fill(null)],
    width: 2.4,
    fmt: (value) => fmt(value),
  };

  const projectedValues = (values, startValue) => [
    ...Array(Math.max(0, baseLength - 1)).fill(null),
    startValue,
    ...values,
  ];

  const scenarioSeries = (scenario, values, startValue) => ({
    name: scenario.id === 'personalizado' ? 'Tu simulación' : scenario.nombre,
    color: COLORS[scenario.id] ?? 'var(--cat-a)',
    values: projectedValues(values, startValue),
    width: scenario.id === 'personalizado' ? 2.6 : 2,
    dash: scenario.id === 'personalizado' ? '6 4' : undefined,
    end: scenario.id === 'personalizado' ? 'Tu simulación' : undefined,
    fmt: (value) => fmt(value),
  });

  const chartSeries = [
    historicalSeries,
    ...presets.map((scenario) => scenarioSeries(scenario, scenario.nuevos, lastAverage)),
    custom ? scenarioSeries(custom, custom.nuevos, lastAverage) : null,
    data.observado_posterior
      ? {
          name: 'Observado posterior',
          color: '#64748b',
          values: [...Array(baseLength).fill(null), ...posteriorValues],
          width: 1.8,
          dash: '3 3',
          fmt: (value) => fmt(value),
        }
      : null,
  ].filter(Boolean);

  const activeSeries = [
    {
      name: 'Observado',
      color: 'var(--ink2)',
      values: [...historicalActive, ...Array(projectionLength).fill(null)],
      width: 2.4,
      fmt: (value) => fmt(value),
    },
    ...presets.map((scenario) =>
      scenarioSeries(scenario, scenario.activos, lastActive),
    ),
    custom ? scenarioSeries(custom, custom.activos, lastActive) : null,
  ].filter(Boolean);

  const customBand = custom
    ? {
        name: 'personalizado',
        color: 'var(--sim)',
        lower: [...Array(baseLength).fill(null), ...custom.banda_nuevos.inferior],
        upper: [...Array(baseLength).fill(null), ...custom.banda_nuevos.superior],
      }
    : null;
  const customActiveBand = custom
    ? {
        name: 'personalizado-activos',
        color: 'var(--sim)',
        lower: [...Array(baseLength).fill(null), ...custom.banda_activos.inferior],
        upper: [...Array(baseLength).fill(null), ...custom.banda_activos.superior],
      }
    : null;

  const backtest = data.backtest;
  const backtestShort = (backtest?.fechas ?? []).map((value) => dShort(parseDate(value)));
  const backtestLong = (backtest?.fechas ?? []).map((value) => dLong(parseDate(value)));
  const backtestSeries = backtest
    ? [
        {
          name: 'Observado',
          color: 'var(--ink2)',
          values: backtest.observado,
          width: 2.4,
          fmt: (value) => fmt(value),
        },
        {
          name: 'Proyectado',
          color: 'var(--s-mod)',
          values: backtest.proyectado,
          width: 2.2,
          dash: '6 4',
          fmt: (value) => fmt(value),
        },
      ]
    : [];

  const updateSim = (patch) =>
    setSim((current) => ({ ...current, ...patch }));

  const legend = (
    <div className="legend">
      <span>
        <i className="sw" style={{ background: 'var(--ink2)' }}></i>Observado
      </span>
      {presets.map((scenario) => (
        <span key={scenario.id}>
          <i className="sw" style={{ background: COLORS[scenario.id] }}></i>
          {scenario.nombre}
        </span>
      ))}
      <span>
        <i className="sw d"></i>Tu simulación
      </span>
      {data.observado_posterior && (
        <span>
          <i className="sw" style={{ background: '#64748b' }}></i>Observado posterior
        </span>
      )}
    </div>
  );

  return (
    <div className="main" aria-busy={state.loading}>
      {state.loading && <p className="note span2">Actualizando proyección…</p>}
      <Card
        title="Simulador de escenarios"
        sub={`Proyección desde ${fechaCorte} · ${terrName}`}
        right={
          <div className="horizon">
            <label className="flabel" htmlFor="proj-horizonte">
              Horizonte
            </label>
            <select
              id="proj-horizonte"
              value={horizonte}
              onChange={(event) => setHorizonte(Number(event.target.value))}
            >
              {HORIZONTES.map((value) => (
                <option key={value} value={value}>
                  {value} días
                </option>
              ))}
            </select>
          </div>
        }
      >
        <div className="ctrl">
          <div>
            <div className="sl">
              <div className="row">
                <label htmlFor="sl-r">Velocidad de contagio (R base)</label>
                <output htmlFor="sl-r" className="num">
                  {dec(sim.R ?? 0, 2)}
                </output>
              </div>
              <input
                id="sl-r"
                type="range"
                min="0.3"
                max="3"
                step="0.05"
                value={sim.R ?? 0.3}
                onChange={(event) => updateSim({ R: Number(event.target.value) })}
              />
              <span className="hint">
                R estimado del período: {dec(data.r_estimado, 2)}.{' '}
                <button
                  type="button"
                  className="link"
                  onClick={() => updateSim({ R: Number(clampR(data.r_estimado).toFixed(2)) })}
                >
                  Usar R estimado
                </button>
              </span>
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
                onChange={(event) => updateSim({ m: Number(event.target.value) })}
              />
              <span className="hint">Mascarillas, aforos, cierres y vacunación de refuerzo.</span>
            </div>
            <div className="sim num">
              <b>R efectivo {dec(effectiveR, 2)}</b>{' '}
              <span className="state" style={{ color: stateLabel[1] }}>
                {stateLabel[0]}
              </span>
              <br />
              Pico de {fmt(custom?.resumen.pico_activos ?? 0)} casos activos el {peakDate}.
            </div>
            <div className="projbase">
              <div>
                <span>Corte</span>
                <b>{fechaCorte}</b>
              </div>
              <div>
                <span>Promedio 7d</span>
                <b>{fmt(lastAverage)}</b>
              </div>
              <div>
                <span>Activos al corte</span>
                <b>{fmt(base.activos_al_corte)}</b>
              </div>
              <div>
                <span>R estimado</span>
                <b>{dec(data.r_estimado, 2)}</b>
              </div>
              <div>
                <span>Calidad</span>
                <b className={`qbadge ${quality.nivel}`}>{quality.nivel}</b>
              </div>
            </div>
            <p className="hint">{quality.mensaje}</p>
            {noRecentCases && base.activos_al_corte === 0 && (
              <p className="note">
                No hay casos en la ventana de proyección; las curvas permanecerán en cero.
              </p>
            )}
            {noRecentCases && base.activos_al_corte > 0 && (
              <p className="note">
                No hay casos nuevos recientes; la proyección de activos parte de{' '}
                {fmt(base.activos_al_corte)} y desciende.
              </p>
            )}
          </div>
          <div className="scen" role="group" aria-label="Escenarios de referencia">
            {presets.map((scenario) => {
              const active =
                Math.abs((sim.R ?? 0) - scenario.r_base) < 0.005 &&
                Math.abs(sim.m - scenario.medidas) < 0.5;
              return (
                <button
                  key={scenario.id}
                  className="sc num"
                  aria-pressed={active}
                  onClick={() => updateSim({ R: scenario.r_base, m: scenario.medidas })}
                >
                  <h4>
                    <i
                      className="sw b"
                      style={{ background: COLORS[scenario.id] }}
                    ></i>
                    {scenario.nombre}
                  </h4>
                  <span>
                    R {dec(scenario.r_base, 2)} · medidas {scenario.medidas} %
                  </span>
                  <span>
                    R efectivo{' '}
                    <b style={{ color: 'var(--ink)' }}>{dec(scenario.r_efectivo, 2)}</b>
                  </span>
                  <span>
                    Pico:{' '}
                    <b style={{ color: 'var(--ink)' }}>
                      {compact(scenario.resumen.pico_activos)}
                    </b>{' '}
                    activos ({dShort(parseDate(scenario.resumen.fecha_pico))})
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <Card
        className="span2"
        title="Casos nuevos diarios proyectados"
        sub={`Observado y proyección a ${horizonte} días`}
      >
        {legend}
        <LinesChart
          short={short}
          long={long}
          marker={baseLength - 1}
          markerLabel="Corte"
          endLabels={true}
          height={280}
          bands={customBand ? [customBand] : []}
          series={chartSeries}
          aria={`Proyección de casos nuevos para ${terrName}`}
        />
      </Card>

      <div className="grid2">
        <Card title="Casos activos proyectados" sub="Personas con infección vigente">
          <LinesChart
            short={short}
            long={long}
            marker={baseLength - 1}
            markerLabel="Corte"
            endLabels={true}
            height={250}
            bands={customActiveBand ? [customActiveBand] : []}
            series={activeSeries}
            aria={`Proyección de casos activos para ${terrName}`}
          />
        </Card>
        <Card
          title="Observado vs proyectado"
          sub={
            backtest
              ? `Escenario moderado · ${backtest.dias_comparados} días comparados`
              : 'Validación histórica'
          }
        >
          {backtest ? (
            <>
              <div className="legend">
                <span>
                  <i className="sw" style={{ background: 'var(--ink2)' }}></i>Observado
                </span>
                <span>
                  <i className="sw" style={{ background: 'var(--s-mod)' }}></i>Proyectado
                </span>
              </div>
              <LinesChart
                short={backtestShort}
                long={backtestLong}
                height={210}
                series={backtestSeries}
                aria="Comparación entre casos observados y proyectados"
              />
              <div className="projmeta num">
                <span>MAE {fmt(backtest.mae)}</span>
                <span>sMAPE {backtest.smape == null ? '—' : pct(backtest.smape)}</span>
                <span>{backtest.dias_comparados} días</span>
              </div>
              {backtest.smape != null && backtest.smape > 80 && (
                <p className="hint">
                  El modelo tiene dificultad para capturar cambios abruptos de tendencia.
                  Use las proyecciones como escenarios, no como pronóstico puntual.
                </p>
              )}
            </>
          ) : (
            <p className="note">
              No hay datos posteriores al corte para comparar. Esto ocurre en 2024 y en la
              vista acumulada.
            </p>
          )}
        </Card>
      </div>

      <Card title="Comparación de escenarios" sub="Valores proyectados">
        <div className="tscroll">
          <table className="tbl num">
            <thead>
              <tr>
                <th>Escenario</th>
                <th>R efectivo</th>
                <th>Nuevos 30 d</th>
                <th>Nuevos 60 d</th>
                <th>Nuevos 90 d</th>
                <th>Pico activos</th>
                <th>Fecha pico</th>
              </tr>
            </thead>
            <tbody>
              {escenarios.map((scenario) => (
                <tr key={scenario.id}>
                  <td>{scenario.nombre}</td>
                  <td>{dec(scenario.r_efectivo, 2)}</td>
                  <td>{fmt(scenario.resumen.nuevos_30d)}</td>
                  <td>{fmt(scenario.resumen.nuevos_60d)}</td>
                  <td>{fmt(scenario.resumen.nuevos_90d)}</td>
                  <td>{fmt(scenario.resumen.pico_activos)}</td>
                  <td>{dShort(parseDate(scenario.resumen.fecha_pico))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
