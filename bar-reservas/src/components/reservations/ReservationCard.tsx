'use client';

import { Reservation } from '@/types/reservation';
import { StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';

interface ReservationCardProps {
  reservation: Reservation;
  onCancel?: (id: string) => void;
}

export function ReservationCard({ reservation, onCancel }: ReservationCardProps) {
  const { id, name, guests, time, status, notes, phone } = reservation;
  const isCancelled = status === 'cancelled';

  return (
    <div
      className={`
        relative bg-slate-800 border rounded-xl p-4 transition-all duration-200
        ${isCancelled
          ? 'border-slate-700 opacity-60'
          : 'border-slate-700 hover:border-slate-500 hover:shadow-lg hover:shadow-black/20'
        }
      `}
    >
      {/* Time accent stripe */}
      <div
        className={`
          absolute left-0 top-4 bottom-4 w-1 rounded-r-full
          ${status === 'confirmed' ? 'bg-emerald-500' : status === 'pending' ? 'bg-amber-500' : 'bg-slate-600'}
        `}
      />

      <div className="pl-3">
        {/* Top row */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <h3 className="text-white font-semibold leading-tight">{name}</h3>
            {phone && (
              <p className="text-slate-500 text-xs mt-0.5">{phone}</p>
            )}
          </div>
          <StatusBadge status={status} />
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 mb-3">
          {/* Time */}
          <div className="flex items-center gap-1.5">
            <ClockIcon />
            <span className="text-amber-400 font-bold text-base">{time}</span>
          </div>

          {/* Guests */}
          <div className="flex items-center gap-1.5">
            <PeopleIcon />
            <span className="text-slate-300 text-sm font-medium">{guests} pax</span>
          </div>
        </div>

        {/* Notes */}
        {notes && (
          <p className="text-slate-500 text-xs bg-slate-900/50 rounded-lg px-3 py-2 mb-3">
            {notes}
          </p>
        )}

        {/* Actions */}
        {!isCancelled && onCancel && (
          <div className="flex justify-end">
            <Button
              variant="danger"
              size="sm"
              onClick={() => onCancel(id)}
            >
              Cancelar
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function ClockIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" strokeWidth="2" />
      <polyline points="12,6 12,12 16,14" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PeopleIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" strokeWidth="2" strokeLinecap="round" />
      <circle cx="9" cy="7" r="4" strokeWidth="2" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" strokeWidth="2" strokeLinecap="round" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
