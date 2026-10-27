import React from 'react';
import * as Icons from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtext?: string;
  iconName: keyof typeof Icons;
  trend?: {
    value: string;
    type: 'up' | 'down' | 'neutral';
  };
}

export const StatCard: React.FC<StatCardProps> = ({ title, value, subtext, iconName, trend }) => {
  const IconComponent = Icons[iconName] as React.ComponentType<{ className?: string }>;

  return (
    <div className="bg-card p-5 rounded-xl border border-border shadow-sm flex items-start justify-between">
      <div>
        <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{title}</p>
        <h3 className="text-2xl font-bold text-text-primary mt-1.5">{value}</h3>
        {(subtext || trend) && (
          <div className="flex items-center gap-1 mt-1.5">
            {trend && (
              <span className={`text-xs font-bold flex items-center ${
                trend.type === 'up' ? 'text-success' : trend.type === 'down' ? 'text-danger' : 'text-text-secondary'
              }`}>
                {trend.value}
              </span>
            )}
            {subtext && <span className="text-xs text-text-secondary">{subtext}</span>}
          </div>
        )}
      </div>
      <div className="p-2.5 bg-slate-50 border border-slate-100 rounded-lg text-text-secondary">
        {IconComponent && <IconComponent className="w-5 h-5" />}
      </div>
    </div>
  );
};
