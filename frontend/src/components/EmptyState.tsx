import React from 'react';
import { AlertCircle } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ title, description }) => {
  return (
    <div className="flex flex-col items-center justify-center p-10 bg-card rounded-xl border border-dashed border-slate-200 text-center my-4">
      <div className="p-3 bg-slate-50 border border-slate-100 rounded-full text-text-secondary mb-3">
        <AlertCircle className="w-6 h-6 text-text-secondary" />
      </div>
      <h4 className="text-sm font-bold text-text-primary">{title}</h4>
      <p className="text-xs text-text-secondary mt-1 max-w-xs">{description}</p>
    </div>
  );
};
