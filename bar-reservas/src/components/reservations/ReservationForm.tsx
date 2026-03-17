'use client';

import { useState, FormEvent } from 'react';
import { CreateReservationInput } from '@/types/reservation';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { todayString } from '@/lib/utils/date';

interface ReservationFormProps {
  defaultDate?: string;
  onSubmit: (input: CreateReservationInput) => Promise<void>;
}

const EMPTY_FORM = {
  name: '',
  guests: '',
  time: '',
  date: '',
  phone: '',
  notes: '',
};

export function ReservationForm({ defaultDate, onSubmit }: ReservationFormProps) {
  const [fields, setFields] = useState({ ...EMPTY_FORM, date: defaultDate ?? todayString() });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    setFields((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    setError('');
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const guests = parseInt(fields.guests, 10);

    if (!fields.name.trim()) { setError('El nombre es obligatorio.'); return; }
    if (!guests || guests < 1) { setError('Indica un número válido de personas.'); return; }
    if (!fields.time) { setError('La hora es obligatoria.'); return; }
    if (!fields.date) { setError('La fecha es obligatoria.'); return; }

    setLoading(true);
    try {
      await onSubmit({
        name: fields.name.trim(),
        guests,
        time: fields.time,
        date: fields.date,
        phone: fields.phone.trim() || undefined,
        notes: fields.notes.trim() || undefined,
        status: 'confirmed',
      });
      setFields({ ...EMPTY_FORM, date: fields.date });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2500);
    } catch {
      setError('Error al guardar la reserva.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <h2 className="text-white font-semibold text-sm">Nueva Reserva</h2>
        </div>
      </CardHeader>

      <CardBody>
        <form onSubmit={handleSubmit} className="space-y-3" noValidate>
          {/* Name */}
          <Field label="Nombre de la reserva *">
            <input
              name="name"
              type="text"
              value={fields.name}
              onChange={handleChange}
              placeholder="Ej: Mesa García"
              className={INPUT_CLASS}
              autoComplete="off"
            />
          </Field>

          {/* Date + Time row */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Fecha *">
              <input
                name="date"
                type="date"
                value={fields.date}
                onChange={handleChange}
                className={INPUT_CLASS}
              />
            </Field>
            <Field label="Hora *">
              <input
                name="time"
                type="time"
                value={fields.time}
                onChange={handleChange}
                className={INPUT_CLASS}
              />
            </Field>
          </div>

          {/* Guests */}
          <Field label="Número de personas *">
            <input
              name="guests"
              type="number"
              min={1}
              max={200}
              value={fields.guests}
              onChange={handleChange}
              placeholder="4"
              className={INPUT_CLASS}
            />
          </Field>

          {/* Phone (optional) */}
          <Field label="Teléfono">
            <input
              name="phone"
              type="tel"
              value={fields.phone}
              onChange={handleChange}
              placeholder="612 345 678"
              className={INPUT_CLASS}
            />
          </Field>

          {/* Notes (optional) */}
          <Field label="Notas">
            <textarea
              name="notes"
              value={fields.notes}
              onChange={handleChange}
              placeholder="Alergias, preferencias, ocasión especial…"
              rows={2}
              className={`${INPUT_CLASS} resize-none`}
            />
          </Field>

          {/* Error */}
          {error && (
            <p className="text-rose-400 text-xs bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {/* Success */}
          {success && (
            <p className="text-emerald-400 text-xs bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
              ✓ Reserva añadida correctamente
            </p>
          )}

          <Button
            type="submit"
            fullWidth
            size="lg"
            loading={loading}
          >
            + Añadir Reserva
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

const INPUT_CLASS =
  'w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30 transition-colors';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-slate-400 text-xs font-medium mb-1">{label}</label>
      {children}
    </div>
  );
}
