// Core domain types — update here to evolve the data model everywhere

export type ReservationStatus = 'confirmed' | 'pending' | 'cancelled';

export interface Reservation {
  id: string;
  name: string;
  guests: number;
  time: string;   // "HH:MM" 24h format
  date: string;   // "YYYY-MM-DD"
  status: ReservationStatus;
  notes?: string;
  phone?: string;
  createdAt: string; // ISO string
}

export type CreateReservationInput = {
  name: string;
  guests: number;
  time: string;
  date: string;
  status?: ReservationStatus;
  notes?: string;
  phone?: string;
};

export type UpdateReservationInput = Partial<CreateReservationInput>;

export interface ReservationSummary {
  total: number;
  totalGuests: number;
  confirmed: number;
  pending: number;
  cancelled: number;
}
