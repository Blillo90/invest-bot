'use client';

import { useReservations } from '@/hooks/useReservations';
import { Header } from './Header';
import { SummaryPanel } from './SummaryPanel';
import { ReservationCalendar } from '@/components/calendar/ReservationCalendar';
import { ReservationForm } from '@/components/reservations/ReservationForm';
import { ReservationList } from '@/components/reservations/ReservationList';
import { formatShortDate, isToday } from '@/lib/utils/date';

export function DashboardView() {
  const {
    allReservations,
    filteredReservations,
    summary,
    selectedDate,
    showAll,
    isLoading,
    selectDate,
    toggleShowAll,
    addReservation,
    cancelReservation,
  } = useReservations();

  const summaryDateLabel = showAll
    ? 'Todas'
    : isToday(selectedDate)
    ? 'Hoy'
    : formatShortDate(selectedDate);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header selectedDate={selectedDate} />

      <main className="max-w-7xl mx-auto px-4 py-6 lg:px-8">
        {isLoading ? (
          <LoadingState />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* ── LEFT COLUMN (2/3) ── */}
            <div className="lg:col-span-2 space-y-6">
              {/* Calendar */}
              <ReservationCalendar
                reservations={allReservations}
                selectedDate={selectedDate}
                onSelectDate={selectDate}
              />

              {/* Reservation list */}
              <ReservationList
                reservations={filteredReservations}
                selectedDate={selectedDate}
                showAll={showAll}
                onToggleView={toggleShowAll}
                onCancel={cancelReservation}
              />
            </div>

            {/* ── RIGHT COLUMN (1/3) ── */}
            <div className="space-y-6">
              {/* Summary */}
              <SummaryPanel summary={summary} dateLabel={summaryDateLabel} />

              {/* Quick stats — total across all dates */}
              <AllTimeStats reservations={allReservations} />

              {/* New reservation form */}
              <ReservationForm
                defaultDate={selectedDate}
                onSubmit={addReservation}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function AllTimeStats({ reservations }: { reservations: { guests: number; status: string }[] }) {
  const active = reservations.filter((r) => r.status !== 'cancelled');
  const totalGuests = active.reduce((s, r) => s + r.guests, 0);

  return (
    <div className="grid grid-cols-2 gap-3">
      <StatCard label="Reservas totales" value={active.length} icon="📋" />
      <StatCard label="Personas totales" value={totalGuests} icon="👥" />
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: number; icon: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 text-center">
      <span className="text-2xl">{icon}</span>
      <p className="text-2xl font-bold text-amber-400 mt-1">{value}</p>
      <p className="text-slate-400 text-xs mt-0.5">{label}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-32">
      <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mb-4" />
      <p className="text-slate-400 text-sm">Cargando reservas…</p>
    </div>
  );
}
