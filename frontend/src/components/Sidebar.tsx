import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Boxes,
  Barcode,
  LineChart,
  ShoppingCart,
  Cpu,
  BrainCircuit,
  FileText,
  Settings as SettingsIcon,
  Warehouse,
  Users,
  UserCog,
  ShieldCheck
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const menuItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Inventory', path: '/inventory', icon: Boxes },
    { name: 'Warehouse & Space', path: '/space', icon: Warehouse },
    { name: 'Customers', path: '/customers', icon: Users },
    { name: 'Workforce', path: '/workforce', icon: UserCog },
    { name: 'Compliance', path: '/compliance', icon: ShieldCheck },
    { name: 'Products', path: '/products', icon: Barcode },
    { name: 'Forecasting', path: '/forecasting', icon: LineChart },
    { name: 'Procurement', path: '/procurement', icon: ShoppingCart },
    { name: 'Operations', path: '/operations', icon: Cpu },
    { name: 'Operational Insights', path: '/ai-insights', icon: BrainCircuit },
    { name: 'Reports', path: '/reports', icon: FileText },
    { name: 'Settings', path: '/settings', icon: SettingsIcon },
  ];

  return (
    <aside className="w-64 bg-card border-r border-border h-screen flex flex-col fixed left-0 top-0 z-30">
      <div className="p-6 border-b border-border flex items-center gap-2.5">
        <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-white font-bold text-lg shadow-sm">
          P
        </div>
        <div>
          <span className="font-bold text-text-primary text-lg tracking-tight block">PRISM</span>
          <span className="text-[10px] font-bold text-primary block -mt-1 uppercase tracking-wider">Intelligence Platform</span>
        </div>
      </div>
      
      <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
        {menuItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-primary text-white shadow-sm shadow-primary/20'
                    : 'text-text-secondary hover:text-text-primary hover:bg-slate-50'
                }`
              }
            >
              <Icon className="w-4.5 h-4.5" />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="p-4 border-t border-border bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center text-primary font-bold text-[9px]">
            DEMO
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-text-primary truncate">Local Demo User</p>
            <p className="text-[10px] text-text-secondary truncate">Authentication not configured</p>
          </div>
        </div>
      </div>
    </aside>
  );
};
