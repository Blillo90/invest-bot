'use client';

import { formatFullDate, todayString } from '@/lib/utils/date';

interface HeaderProps {
  selectedDate: string;
}

export function Header({ selectedDate }: HeaderProps) {
  const isToday = selectedDate === todayString();

  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-slate-700/60">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/30">
          <span className="text-slate-900 font-black text-lg">🍸</span>
        </div>
        <div>
          <h1 className="text-white font-bold text-lg leading-none">Bar Reservas</h1>
          <p className="text-slate-400 text-xs mt-0.5">Panel de Gestión</p>
        </div>
      </div>

      {/* Date info */}
      <div className="text-right">
        <p className="text-white font-medium capitalize">
          {isToday ? 'Hoy — ' : ''}{formatFullDate(selectedDate)}
        </p>
        <p className="text-slate-400 text-xs mt-0.5">Vista activa</p>
      </div>
    </header>
  );
}
