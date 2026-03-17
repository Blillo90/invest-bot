// Date helpers — keep formatting logic out of components

const LOCALE = 'es-ES';

export const DAYS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
export const MONTHS_ES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

/** "YYYY-MM-DD" from a Date object */
export function toDateString(d: Date): string {
  return d.toISOString().split('T')[0];
}

/** Today's date string */
export function todayString(): string {
  return toDateString(new Date());
}

/** Format "YYYY-MM-DD" → "Lunes, 17 de Marzo" */
export function formatFullDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' });
}

/** Format "YYYY-MM-DD" → "17 Mar" */
export function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short' });
}

/** Get Monday of the week containing the given date */
export function getWeekMonday(d: Date): Date {
  const day = d.getDay(); // 0 = Sun
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(d);
  monday.setDate(d.getDate() + diff);
  return monday;
}

/** Generate N days starting from startDate */
export function generateDays(startDate: Date, count: number): string[] {
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    return toDateString(d);
  });
}

/** Day-of-week short name for a "YYYY-MM-DD" string */
export function getDayLabel(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  // getDay: 0=Sun,1=Mon,...,6=Sat → map to Mon-first
  const idx = (d.getDay() + 6) % 7;
  return DAYS_ES[idx];
}

/** Day number (1-31) */
export function getDayNumber(dateStr: string): number {
  return new Date(dateStr + 'T00:00:00').getDate();
}

/** Compare two date strings */
export function isSameDate(a: string, b: string): boolean {
  return a === b;
}

/** Is the given date string today? */
export function isToday(dateStr: string): boolean {
  return dateStr === todayString();
}

/** Sort comparator for reservations by time */
export function compareByTime(a: string, b: string): number {
  return a.localeCompare(b);
}
