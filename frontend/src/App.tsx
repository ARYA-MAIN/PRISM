import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { Dashboard } from './pages/Dashboard';
import { Inventory } from './pages/Inventory';
import { Products } from './pages/Products';
import { Forecasting } from './pages/Forecasting';
import { Procurement } from './pages/Procurement';
import { Operations } from './pages/Operations';
import { AIInsights } from './pages/AIInsights';
import { RecommendationDetail } from './pages/RecommendationDetail';
import { Reports } from './pages/Reports';
import { Settings } from './pages/Settings';
import { Space } from './pages/Space';
import { Customers } from './pages/Customers';
import { Workforce } from './pages/Workforce';
import { Compliance } from './pages/Compliance';
import './App.css';

const LayoutWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();

  const getPageTitle = (pathname: string) => {
    if (pathname.startsWith('/dashboard')) return 'Dashboard Overview';
    if (pathname.startsWith('/inventory')) return 'Inventory Intelligence';
    if (pathname.startsWith('/space')) return 'Warehouse & Space';
    if (pathname.startsWith('/customers')) return 'Customers';
    if (pathname.startsWith('/workforce')) return 'Workforce & Assignments';
    if (pathname.startsWith('/compliance')) return 'Compliance & Certificates';
    if (pathname.startsWith('/products')) return 'Product SKU Catalog';
    if (pathname.startsWith('/forecasting')) return 'Demand Forecasting';
    if (pathname.startsWith('/procurement')) return 'Procurement Intelligence';
    if (pathname.startsWith('/operations')) return 'Operations Intelligence';
    if (pathname.startsWith('/ai-insights/')) return 'Recommendation Review';
    if (pathname.startsWith('/ai-insights')) return 'Operational Insights';
    if (pathname.startsWith('/reports')) return 'Compiled Reports';
    if (pathname.startsWith('/settings')) return 'System Settings';
    return 'PRISM Platform';
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left Sidebar */}
      <Sidebar />
      
      {/* Right Content Area */}
      <div className="flex-1 ml-64 flex flex-col min-h-screen">
        <Topbar pageTitle={getPageTitle(location.pathname)} />
        <main className="flex-1 p-8 overflow-y-auto max-w-7xl w-full">
          {children}
        </main>
      </div>
    </div>
  );
};

export default function App() {
  return (
    <BrowserRouter>
      <LayoutWrapper>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/space" element={<Space />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/workforce" element={<Workforce />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/products" element={<Products />} />
          <Route path="/forecasting" element={<Forecasting />} />
          <Route path="/procurement" element={<Procurement />} />
          <Route path="/operations" element={<Operations />} />
          <Route path="/ai-insights" element={<AIInsights />} />
          <Route path="/ai-insights/:id" element={<RecommendationDetail />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </LayoutWrapper>
    </BrowserRouter>
  );
}
