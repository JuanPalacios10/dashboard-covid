import { sum } from '../lib/format.js';

/* Datos de ejemplo. Reemplazar por llamadas al backend (ver README). */
/* ======================================================================
   CAPA DE DATOS (MOCK)
   Todo lo que está en esta sección se reemplaza luego por llamadas al backend.
   Endpoints sugeridos:
     GET  /api/kpis?territorio=          -> confirmados, fallecidos, recuperados, activos
     GET  /api/series?territorio=        -> casos diarios
     GET  /api/territorios/incidencia    -> casos por departamento y semana
     GET  /api/demografia?territorio=    -> sexo y grupos etarios
     POST /api/proyecciones              -> { R, medidas, territorio } -> 3 escenarios + simulación
     POST /api/informes/pdf              -> genera PDF con membrete, fecha y firma digital
     WS   /ws/kpis                       -> métricas en tiempo real (latencia < 500 ms)
   ====================================================================== */
export function rng(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export const DAYS = 120,
  TODAY = new Date(2026, 10, 4);
export const dateAt = (i) => new Date(2026, 10, 4 - (DAYS - 1 - i));
export const WD = [0.78, 1.08, 1.1, 1.05, 1.05, 1.0, 0.9];
export const NATIONAL_CONFIRMED = 6412380;

export const DEPTS = [
  { id: 'bog', name: 'Bogotá D.C.', share: 0.215, pop: 7.9, cfr: 0.0198, c: 104, w: 30, f: 0.531 },
  { id: 'ant', name: 'Antioquia', share: 0.14, pop: 6.9, cfr: 0.0231, c: 98, w: 28, f: 0.524 },
  { id: 'val', name: 'Valle del Cauca', share: 0.085, pop: 4.6, cfr: 0.0219, c: 96, w: 30, f: 0.528 },
  { id: 'atl', name: 'Atlántico', share: 0.062, pop: 2.8, cfr: 0.0247, c: 108, w: 26, f: 0.519 },
  { id: 'cun', name: 'Cundinamarca', share: 0.058, pop: 3.3, cfr: 0.0204, c: 106, w: 30, f: 0.516 },
  { id: 'san', name: 'Santander', share: 0.052, pop: 2.3, cfr: 0.0236, c: 94, w: 28, f: 0.522 },
  { id: 'bol', name: 'Bolívar', share: 0.041, pop: 2.2, cfr: 0.0241, c: 110, w: 26, f: 0.515 },
  { id: 'nar', name: 'Nariño', share: 0.03, pop: 1.7, cfr: 0.0262, c: 90, w: 30, f: 0.509 },
  { id: 'cor', name: 'Córdoba', share: 0.028, pop: 1.9, cfr: 0.0252, c: 102, w: 28, f: 0.512 },
  { id: 'nor', name: 'Norte de Santander', share: 0.03, pop: 1.6, cfr: 0.0258, c: 100, w: 30, f: 0.518 },
  { id: 'otr', name: 'Otros departamentos', share: 0, pop: 12.4, cfr: 0.0233, c: 100, w: 32, f: 0.521 },
];
DEPTS[10].share = 1 - sum(DEPTS.slice(0, 10).map((d) => d.share));
(function build() {
  const r = rng(20261104);
  DEPTS.forEach((d) => {
    d.series = Array.from({ length: DAYS }, (_, i) => {
      const wave = 1100 + 1500 * Math.exp(-(((i - d.c) / d.w) ** 2));
      return Math.max(0, Math.round(d.share * wave * WD[dateAt(i).getDay()] * (0.93 + r() * 0.14)));
    });
    d.conf = Math.round(NATIONAL_CONFIRMED * d.share);
    d.deaths = Math.round(d.conf * d.cfr);
    d.cap = Math.round(d.pop * 25); // camas UCI de referencia
  });
})();

export const AGE = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80+'];
export const AGE_SHARE = [4, 9, 19, 21, 17, 13, 9, 5, 3];
export const AGE_CFR = [0.1, 0.05, 0.1, 0.3, 0.8, 2.1, 5.5, 12.5, 24];

export function getView(terr) {
  const ds = terr === 'all' ? DEPTS : DEPTS.filter((d) => d.id === terr);
  const series = Array.from({ length: DAYS }, (_, i) => sum(ds.map((d) => d.series[i])));
  const avg7 = series.map((_, i) => (i < 6 ? null : sum(series.slice(i - 6, i + 1)) / 7));
  const actS = series.map((_, i) => (i < 11 ? null : Math.round(0.85 * sum(series.slice(i - 11, i + 1)))));
  const conf = sum(ds.map((d) => d.conf)),
    deaths = sum(ds.map((d) => d.deaths));
  const act = actS[DAYS - 1],
    rec = conf - deaths - act;
  const last7 = sum(series.slice(-7)),
    prev7 = sum(series.slice(-14, -7));
  const pop = sum(ds.map((d) => d.pop)),
    cap = sum(ds.map((d) => d.cap));
  const femShare = sum(ds.map((d) => d.f * d.conf)) / conf;
  const idx = ds.length === 1 ? DEPTS.indexOf(ds[0]) : -1;
  let ageShare = AGE_SHARE.map((v, i) => (idx < 0 ? v : v * (1 + 0.1 * Math.sin(idx * 1.7 + i))));
  const tot = sum(ageShare);
  ageShare = ageShare.map((v) => (v / tot) * 100);
  return {
    ds,
    series,
    avg7,
    actS,
    conf,
    deaths,
    act,
    rec,
    last7,
    prev7,
    pop,
    cap,
    femShare,
    ageShare,
    g: avg7[DAYS - 1] / act,
  };
}

/* Modelo SIR simplificado, solo para demostración. */
export function simulate(view, R, m, days = 60) {
  const Re = R * (1 - (0.5 * m) / 100),
    g = view.g;
  let I = view.act,
    S = view.pop * 1e6 * 0.1;
  const N = S + I;
  const nw = [],
    ac = [],
    icu = [];
  for (let t = 0; t < days; t++) {
    const Rt = 1 + (Re - 1) * Math.min(1, (t + 1) / 10);
    const nc = (Rt * g * S * I) / N;
    S -= nc;
    I = I + nc - g * I;
    nw.push(nc);
    ac.push(I);
    icu.push(I * 0.004);
  }
  return { Re, nw, ac, icu };
}
export const PRESETS = [
  { id: 'opt', name: 'Optimista', R: 1.0, m: 80, v: '--s-opt' },
  { id: 'mod', name: 'Moderado', R: 1.3, m: 40, v: '--s-mod' },
  { id: 'pes', name: 'Pesimista', R: 1.6, m: 10, v: '--s-pes' },
];
export function summarize(view, res) {
  let pk = 0;
  res.ac.forEach((v, i) => {
    if (v > res.ac[pk]) pk = i;
  });
  const sat = res.icu.findIndex((v) => v > view.cap);
  return {
    peak: res.ac[pk],
    peakDay: pk + 1,
    peakDate: new Date(2026, 10, 4 + pk + 1),
    satDate: sat < 0 ? null : new Date(2026, 10, 4 + sat + 1),
    icuMax: Math.max(...res.icu),
    cum60: sum(res.nw),
    cum30: sum(res.nw.slice(0, 30)),
  };
}
