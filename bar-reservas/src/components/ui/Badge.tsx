import { ReservationStatus } from '@/types/reservation';

const STATUS_CONFIG: Record<ReservationStatus, { label: string; className: string }> = {
  confirmed: {
    label: 'Confirmada',
    className: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  },
  pending: {
    label: 'Pendiente',
    className: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  },
  cancelled: {
    label: 'Cancelada',
    className: 'bg-rose-500/20 text-rose-400 border border-rose-500/30',
  },
};

interface StatusBadgeProps {
  status: ReservationStatus;
  size?: 'sm' | 'md';
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const { label, className } = STATUS_CONFIG[status];
  const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1';
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizeClass} ${className}`}>
      {label}
    </span>
  );
}

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'amber' | 'slate';
  size?: 'sm' | 'md';
}

export function Badge({ children, variant = 'default', size = 'sm' }: BadgeProps) {
  const variantClass = {
    default: 'bg-slate-700 text-slate-300',
    amber: 'bg-amber-500/20 text-amber-400',
    slate: 'bg-slate-600 text-slate-300',
  }[variant];
  const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1';
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizeClass} ${variantClass}`}>
      {children}
    </span>
  );
}
