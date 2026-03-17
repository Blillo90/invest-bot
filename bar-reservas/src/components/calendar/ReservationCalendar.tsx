'use client';

import { Reservation } from '@/types/reservation';
import {
  generateDays,
  getWeekMonday,
  getDayLabel,
  getDayNumber,
  isToday,
  isSameDate,
  MONTHS_ES,
} from '@/lib/utils/date';

interface ReservationCalendarProps {
  reservations: Reservation[];
  selectedDate: string;
  onSelectDate: (date: string) => void;
}

export function ReservationCalendar({
  reservations,
  selectedDate,
  onSelectDate,
}: ReservationCalendarProps) {
  // Show 14 days starting from this week's Monday
  const monday = getWeekMonday(new Date());
  const days = generateDays(monday, 14);

  // Reservation count per date (exclude cancelled)
  const countByDate = reservations.reduce<Record<string, number>>((acc, r) => {
    if (r.status !== 'cancelled') {
      acc[r.date] = (acc[r.date] ?? 0) + 1;
    }
    return acc;
  }, {});

  // Derive month label from the two weeks shown
  const firstDate = new Date(days[0] + 'T00:00:00');
  const lastDate = new Date(days[days.length - 1] + 'T00:00:00');
  const monthLabel =
    firstDate.getMonth() === lastDate.getMonth()
      ? MONTHS_ES[firstDate.getMonth()]
      : `${MONTHS_ES[firstDate.getMonth()]} – ${MONTHS_ES[lastDate.getMonth()]}`;

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <h2 className="text-white font-semibold text-sm">Agenda</h2>
        </div>
        <span className="text-slate-400 text-xs font-medium">{monthLabel} {firstDate.getFullYear()}</span>
      </div>

      {/* Week labels */}
      <div className="grid grid-cols-7 mb-1">
        {['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'].map((d) => (
          <div key={d} className="text-center text-slate-500 text-xs py-1 font-medium">
            {d}
          </div>
        ))}
      </div>

      {/* Week 1 */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {days.slice(0, 7).map((date) => (
          <DayCell
            key={date}
            date={date}
            count={countByDate[date] ?? 0}
            isSelected={isSameDate(date, selectedDate)}
            isToday={isToday(date)}
            onClick={() => onSelectDate(date)}
          />
        ))}
      </div>

      {/* Week 2 */}
      <div className="grid grid-cols-7 gap-1">
        {days.slice(7, 14).map((date) => (
          <DayCell
            key={date}
            date={date}
            count={countByDate[date] ?? 0}
            isSelected={isSameDate(date, selectedDate)}
            isToday={isToday(date)}
            onClick={() => onSelectDate(date)}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 pt-4 border-t border-slate-700">
        <span className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
          Con reservas
        </span>
        <span className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-slate-500 inline-block" />
          Sin reservas
        </span>
      </div>
    </div>
  );
}

interface DayCellProps {
  date: string;
  count: number;
  isSelected: boolean;
  isToday: boolean;
  onClick: () => void;
}

function DayCell({ date, count, isSelected, isToday, onClick }: DayCellProps) {
  const dayNum = getDayNumber(date);
  const hasReservations = count > 0;

  let cellClass = 'relative flex flex-col items-center justify-center rounded-lg py-2 cursor-pointer transition-all duration-150 ';

  if (isSelected) {
    cellClass += 'bg-amber-500 text-slate-900';
  } else if (isToday) {
    cellClass += 'bg-slate-700 text-white ring-1 ring-amber-500/50';
  } else {
    cellClass += 'hover:bg-slate-700 text-slate-300';
  }

  return (
    <button onClick={onClick} className={cellClass}>
      <span className="text-sm font-semibold leading-none">{dayNum}</span>

      {/* Reservation count dot */}
      <div className="h-4 flex items-center justify-center mt-1">
        {hasReservations ? (
          <span
            className={`
              text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none
              ${isSelected ? 'bg-slate-900/40 text-white' : 'bg-amber-500/20 text-amber-400'}
            `}
          >
            {count}
          </span>
        ) : (
          <span className="w-1 h-1 rounded-full bg-slate-600 block" />
        )}
      </div>
    </button>
  );
}
