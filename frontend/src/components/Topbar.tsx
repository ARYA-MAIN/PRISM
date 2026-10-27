import React from 'react';
import { Bell, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface TopbarProps { pageTitle: string }

export const Topbar: React.FC<TopbarProps> = ({ pageTitle }) => {
  const navigate = useNavigate();
  return (
    <header className="h-16 bg-card border-b border-border flex items-center justify-between px-8 sticky top-0 z-20 shadow-sm">
      <div className="flex items-center gap-4 min-w-0">
        <h2 className="text-base font-bold text-text-primary truncate">{pageTitle}</h2>
        <span className="hidden lg:inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-semibold text-text-secondary">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> One-warehouse dataset view
        </span>
      </div>
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/ai-insights')} title="Operational insights" className="p-2 text-text-secondary hover:text-text-primary hover:bg-slate-50 rounded-lg relative transition-all"><Bell className="w-4.5 h-4.5" /></button>
        <button onClick={() => navigate('/settings')} title="System settings" className="p-2 text-text-secondary hover:text-text-primary hover:bg-slate-50 rounded-lg transition-all"><Settings className="w-4.5 h-4.5" /></button>
      </div>
    </header>
  );
};
