const numberFmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });
const compactFmt = new Intl.NumberFormat('es-CO', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

/** Suma una lista de números. */
export const sum = (values) => values.reduce((total, value) => total + value, 0);

/** Formatea un número entero con separadores de miles (es-CO). */
export const fmt = (value) => numberFmt.format(Number(value) || 0);

/** Formatea un número con una cantidad fija de decimales. */
export const dec = (value, digits = 1) =>
  Number(value || 0).toLocaleString('es-CO', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

/** Formatea un porcentaje. */
export const pct = (value, digits = 1) => `${dec(value, digits)} %`;

/** Formatea números grandes de forma compacta (ej. 6,4 M). */
export const compact = (value) => compactFmt.format(Number(value) || 0);

/** Redondea hacia arriba a un máximo "agradable" para ejes de gráficas. */
export function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;

  const exponent = Math.floor(Math.log10(value));
  const base = 10 ** exponent;
  const fraction = value / base;
  const niceFraction =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;

  return niceFraction * base;
}

/** Fecha corta, por ejemplo "4 nov". */
export const dShort = (date) =>
  date.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' }).replace('.', '');

/** Fecha larga, por ejemplo "4 de noviembre de 2026". */
export const dLong = (date) =>
  date.toLocaleDateString('es-CO', { day: 'numeric', month: 'long', year: 'numeric' });
