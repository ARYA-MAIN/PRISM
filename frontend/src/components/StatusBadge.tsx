import React from 'react';

interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const getStyles = () => {
    const s = status.toLowerCase();
    if (['healthy', 'active', 'completed', 'approved', 'normal', 'stable', 'info'].includes(s)) {
      return 'bg-green-50 text-success border-green-100';
    }
    if (['low stock', 'waiting', 'pending', 'warning'].includes(s)) {
      return 'bg-amber-50 text-warning border-amber-100';
    }
    if (['critical', 'dead stock', 'ignored', 'danger'].includes(s)) {
      return 'bg-red-50 text-danger border-red-100';
    }
    return 'bg-slate-50 text-text-secondary border-slate-100';
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${getStyles()}`}>
      {status}
    </span>
  );
};
