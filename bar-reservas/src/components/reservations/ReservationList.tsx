import { Reservation } from '@/types/reservation';
import { ReservationCard } from './ReservationCard';
import { formatShortDate, isToday } from '@/lib/utils/date';

interface ReservationListProps {
  reservations: Reservation[];
  selectedDate: string;
  showAll: boolean;
  onToggleView: () => void;
  onCancel: (id: string) => void;
}

export function ReservationList({
  reservations,
  selectedDate,
  showAll,
  onToggleView,
  onCancel,
}: ReservationListProps) {
  // Sort by time
  const sorted = [...reservations].sort((a, b) => a.time.localeCompare(b.time));

  const dateLabel = showAll
    ? 'Todas las reservas'
    : `Reservas del ${isToday(selectedDate) ? 'hoy' : formatShortDate(selectedDate)}`;

  return (
    <section>
      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <h2 className="text-white font-semibold">{dateLabel}</h2>
          <span className="text-slate-500 text-sm">({sorted.length})</span>
        </div>

        <button
          onClick={onToggleView}
          className="text-amber-400 hover:text-amber-300 text-xs font-medium transition-colors cursor-pointer"
        >
          {showAll ? 'Ver fecha seleccionada' : 'Ver todas'}
        </button>
      </div>

      {/* Empty state */}
      {sorted.length === 0 && (
        <div className="flex flex-col items-center justify-center py-14 bg-slate-800 border border-slate-700 rounded-xl text-center">
          <span className="text-4xl mb-3">🗓</span>
          <p className="text-slate-300 font-medium">Sin reservas</p>
          <p className="text-slate-500 text-sm mt-1">
            {showAll
              ? 'No hay ninguna reserva en el sistema'
              : 'No hay reservas para esta fecha. Añade una desde el formulario.'}
          </p>
        </div>
      )}

      {/* Cards grid */}
      {sorted.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {sorted.map((r) => (
            <ReservationCard key={r.id} reservation={r} onCancel={onCancel} />
          ))}
        </div>
      )}
    </section>
  );
}
