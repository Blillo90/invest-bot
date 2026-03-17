import { Reservation } from '@/types/reservation';

// Dates relative to today for a realistic demo
const today = new Date();
const fmt = (d: Date) => d.toISOString().split('T')[0];
const addDays = (d: Date, n: number) => {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
};

const d0 = fmt(today);
const d1 = fmt(addDays(today, 1));
const d2 = fmt(addDays(today, 2));
const d3 = fmt(addDays(today, 3));

// Module-level mutable array — replaced by a real repository in production
let _reservations: Reservation[] = [
  {
    id: '1',
    name: 'Mesa García',
    guests: 4,
    time: '20:00',
    date: d0,
    status: 'confirmed',
    phone: '612 345 678',
    notes: 'Cumpleaños, pedir tarta',
    createdAt: new Date().toISOString(),
  },
  {
    id: '2',
    name: 'Grupo Martínez',
    guests: 8,
    time: '21:30',
    date: d0,
    status: 'confirmed',
    phone: '699 112 233',
    createdAt: new Date().toISOString(),
  },
  {
    id: '3',
    name: 'López & Rodríguez',
    guests: 2,
    time: '22:00',
    date: d0,
    status: 'pending',
    notes: 'Confirmar antes de las 18h',
    createdAt: new Date().toISOString(),
  },
  {
    id: '4',
    name: 'Cena Empresa ABC',
    guests: 12,
    time: '20:30',
    date: d1,
    status: 'confirmed',
    phone: '911 000 111',
    notes: 'Sala privada si está disponible',
    createdAt: new Date().toISOString(),
  },
  {
    id: '5',
    name: 'Aniversario Ruiz',
    guests: 2,
    time: '21:00',
    date: d1,
    status: 'confirmed',
    phone: '634 567 890',
    createdAt: new Date().toISOString(),
  },
  {
    id: '6',
    name: 'Santos - Despedida',
    guests: 6,
    time: '21:00',
    date: d2,
    status: 'pending',
    phone: '677 890 123',
    notes: 'Decoración especial solicitada',
    createdAt: new Date().toISOString(),
  },
  {
    id: '7',
    name: 'Grupo Universitario',
    guests: 10,
    time: '22:30',
    date: d2,
    status: 'confirmed',
    createdAt: new Date().toISOString(),
  },
  {
    id: '8',
    name: 'Reserva Pérez',
    guests: 4,
    time: '20:00',
    date: d3,
    status: 'confirmed',
    phone: '655 321 987',
    createdAt: new Date().toISOString(),
  },
];

// Simple in-memory CRUD — mirrors the shape of a real async repository

export const mockReservationService = {
  async getAll(): Promise<Reservation[]> {
    return [..._reservations];
  },

  async getByDate(date: string): Promise<Reservation[]> {
    return _reservations.filter((r) => r.date === date);
  },

  async getById(id: string): Promise<Reservation | null> {
    return _reservations.find((r) => r.id === id) ?? null;
  },

  async create(input: Omit<Reservation, 'id' | 'createdAt'>): Promise<Reservation> {
    const reservation: Reservation = {
      ...input,
      status: input.status ?? 'confirmed',
      id: String(Date.now()),
      createdAt: new Date().toISOString(),
    };
    _reservations = [..._reservations, reservation];
    return reservation;
  },

  async update(id: string, updates: Partial<Omit<Reservation, 'id' | 'createdAt'>>): Promise<Reservation> {
    const index = _reservations.findIndex((r) => r.id === id);
    if (index === -1) throw new Error(`Reservation ${id} not found`);
    const updated = { ..._reservations[index], ...updates };
    _reservations = _reservations.map((r) => (r.id === id ? updated : r));
    return updated;
  },

  async cancel(id: string): Promise<Reservation> {
    return mockReservationService.update(id, { status: 'cancelled' });
  },

  async remove(id: string): Promise<void> {
    _reservations = _reservations.filter((r) => r.id !== id);
  },
};
