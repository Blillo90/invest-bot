/**
 * Reservation service layer.
 *
 * This module exposes a single `reservationService` object that the rest of
 * the app imports. Swapping the mock for a real backend (Supabase, REST API,
 * AWS AppSync…) only requires changing the import below — no consumer code
 * needs to change.
 *
 * Future implementations to drop in:
 *   import { supabaseReservationService } from './supabase-reservations';
 *   import { restReservationService } from './rest-reservations';
 */

import { Reservation, CreateReservationInput, UpdateReservationInput } from '@/types/reservation';
import { mockReservationService } from '@/lib/mock/reservations.mock';

export interface IReservationService {
  getAll(): Promise<Reservation[]>;
  getByDate(date: string): Promise<Reservation[]>;
  getById(id: string): Promise<Reservation | null>;
  create(input: CreateReservationInput): Promise<Reservation>;
  update(id: string, updates: UpdateReservationInput): Promise<Reservation>;
  cancel(id: string): Promise<Reservation>;
  remove(id: string): Promise<void>;
}

// Active service — replace this line to switch backend
export const reservationService: IReservationService = mockReservationService;
