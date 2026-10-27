export interface Product {
  id: string;
  name: string;
  category: string;
  sku: string;
  currentStock: number;
  reorderLevel: number;
  dailyDemand: number;
  supplier: string;
  status: 'Healthy' | 'Low Stock' | 'Critical' | 'Dead Stock';
  price: number;
}

export interface InventoryStats {
  totalProducts: number;
  lowStockCount: number;
  deadStockCount: number;
  inventoryHealth: number; // percentage
  predictedDemandChange: number; // percentage change
  openRecommendationsCount: number;
}

export interface ChartDataPoint {
  date: string;
  stockLevel: number;
  demand: number;
  predictedDemand?: number;
}

export interface ProductForecast {
  productId: string;
  productName: string;
  category: string;
  currentDemand: number;
  predictedDemand: number;
  trend: 'Increasing' | 'Stable' | 'Decreasing';
  confidence: number; // percentage
}

export interface RecommendedPurchase {
  id: string;
  productId: string;
  productName: string;
  currentStock: number;
  predictedDemand: number;
  recommendedQuantity: number;
  suggestedSupplier: string;
  estimatedCost: number;
  confidence: number;
  status: 'Pending' | 'Approved' | 'Ignored';
  whyInventory: string;
  whyForecasting: string;
  whyProcurement: string;
}

export interface Supplier {
  id: string;
  name: string;
  priceRating: string; // e.g. "Competitive", "Average", "Premium"
  leadTime: number; // in days
  reliability: number; // percentage
  score: number; // out of 100
}

export interface Agent {
  id: string;
  name: string;
  status: 'Active' | 'Completed' | 'Waiting';
  lastAnalysis: string;
  latestInsight: string;
  description: string;
  iconName: string;
}

export interface Insight {
  id: string;
  agentId: string;
  agentName: string;
  title: string;
  message: string;
  severity: 'Info' | 'Warning' | 'Critical';
  timestamp: string;
  relatedRecommendationId?: string;
}

export interface ActivityLog {
  id: string;
  agentName: string;
  message: string;
  timestamp: string;
}

export interface OperationalAlert {
  id: string;
  message: string;
  severity: 'Info' | 'Warning' | 'Critical';
  timestamp: string;
}

// ----------------------------------------
// SEED MOCK DATA
// ----------------------------------------

export const MOCK_PRODUCTS: Product[] = [
  { id: '1', name: 'Lenovo ThinkPad E16', category: 'Laptops', sku: 'LAP-THINK-E16', currentStock: 24, reorderLevel: 8, dailyDemand: 5, supplier: 'Lenovo Wholesale Corp', status: 'Healthy', price: 68000 },
  { id: '2', name: 'Logitech M102 Wireless Mouse', category: 'Mice', sku: 'ACC-LOGI-M102', currentStock: 8, reorderLevel: 25, dailyDemand: 6, supplier: 'TechWorld Distributors', status: 'Low Stock', price: 650 },
  { id: '3', name: 'Samsung 980 SSD 1TB', category: 'Storage', sku: 'STO-SAMS-980', currentStock: 3, reorderLevel: 15, dailyDemand: 2, supplier: 'Silicon Supply Co', status: 'Critical', price: 7800 },
  { id: '4', name: 'Apple iPhone 15 Pro', category: 'Mobiles', sku: 'MOB-APPL-I15P', currentStock: 45, reorderLevel: 10, dailyDemand: 8, supplier: 'Apex Electronics', status: 'Healthy', price: 125000 },
  { id: '5', name: 'Dell Inspiron 15', category: 'Laptops', sku: 'LAP-DELL-I15', currentStock: 8, reorderLevel: 10, dailyDemand: 3, supplier: 'TechWorld Distributors', status: 'Low Stock', price: 48000 },
  { id: '6', name: 'HP 65W Laptop Adapter', category: 'Power Adapters', sku: 'PWR-HP-65W', currentStock: 12, reorderLevel: 10, dailyDemand: 2, supplier: 'ElectroBulk Corp', status: 'Healthy', price: 1800 },
  { id: '7', name: 'Kingston 16GB DDR5 RAM', category: 'RAM', sku: 'RAM-KING-16G', currentStock: 2, reorderLevel: 20, dailyDemand: 4, supplier: 'Silicon Supply Co', status: 'Critical', price: 4200 },
  { id: '8', name: 'Keychron K2 Mechanical Keyboard', category: 'Keyboards', sku: 'ACC-KEYC-K2', currentStock: 0, reorderLevel: 10, dailyDemand: 3, supplier: 'Apex Electronics', status: 'Critical', price: 8500 },
  { id: '9', name: 'Dell UltraSharp 27" Monitor', category: 'Monitors', sku: 'MON-DELL-U27', currentStock: 15, reorderLevel: 5, dailyDemand: 1, supplier: 'ElectroBulk Corp', status: 'Healthy', price: 29900 },
  { id: '10', name: 'TP-Link AX3000 Wi-Fi 6 Router', category: 'Networking', sku: 'NET-TPLI-AX30', currentStock: 35, reorderLevel: 10, dailyDemand: 4, supplier: 'Global Trade Link', status: 'Healthy', price: 5400 },
  { id: '11', name: 'Samsung Galaxy S24', category: 'Mobiles', sku: 'MOB-SAMS-S24', currentStock: 18, reorderLevel: 5, dailyDemand: 2, supplier: 'Apex Electronics', status: 'Healthy', price: 79900 },
  { id: '12', name: 'SanDisk Extreme 128GB MicroSD', category: 'Storage', sku: 'STO-SAND-128', currentStock: 50, reorderLevel: 20, dailyDemand: 10, supplier: 'Silicon Supply Co', status: 'Healthy', price: 950 },
  { id: '13', name: 'Crucial 8GB DDR4 RAM', category: 'RAM', sku: 'RAM-CRUC-8G', currentStock: 0, reorderLevel: 15, dailyDemand: 5, supplier: 'Silicon Supply Co', status: 'Critical', price: 2100 },
  { id: '14', name: 'Asus ROG Gaming Mouse', category: 'Mice', sku: 'ACC-ASUS-ROG', currentStock: 4, reorderLevel: 5, dailyDemand: 1, supplier: 'Global Trade Link', status: 'Dead Stock', price: 3400 },
  { id: '15', name: 'Seagate 2TB Backup Plus', category: 'Storage', sku: 'STO-SEAG-2TB', currentStock: 6, reorderLevel: 8, dailyDemand: 1, supplier: 'ElectroBulk Corp', status: 'Low Stock', price: 6200 }
];

export const MOCK_STATS: InventoryStats = {
  totalProducts: 245,
  lowStockCount: 12,
  deadStockCount: 8,
  inventoryHealth: 87,
  predictedDemandChange: 14,
  openRecommendationsCount: 5
};

export const MOCK_CHART_DATA: ChartDataPoint[] = [
  { date: 'Mon', stockLevel: 420, demand: 280, predictedDemand: 290 },
  { date: 'Tue', stockLevel: 390, demand: 310, predictedDemand: 320 },
  { date: 'Wed', stockLevel: 360, demand: 340, predictedDemand: 330 },
  { date: 'Thu', stockLevel: 320, demand: 390, predictedDemand: 380 },
  { date: 'Fri', stockLevel: 380, demand: 410, predictedDemand: 420 },
  { date: 'Sat', stockLevel: 440, demand: 210, predictedDemand: 250 },
  { date: 'Sun', stockLevel: 430, demand: 180, predictedDemand: 210 },
];

export const MOCK_FORECASTS: ProductForecast[] = [
  { productId: '2', productName: 'Logitech M102 Wireless Mouse', category: 'Mice', currentDemand: 6, predictedDemand: 14, trend: 'Increasing', confidence: 94 },
  { productId: '5', productName: 'Dell Inspiron 15', category: 'Laptops', currentDemand: 3, predictedDemand: 8, trend: 'Increasing', confidence: 89 },
  { productId: '1', productName: 'Lenovo ThinkPad E16', category: 'Laptops', currentDemand: 5, predictedDemand: 5, trend: 'Stable', confidence: 95 },
  { productId: '3', productName: 'Samsung 980 SSD 1TB', category: 'Storage', currentDemand: 2, predictedDemand: 4, trend: 'Increasing', confidence: 91 },
  { productId: '7', productName: 'Kingston 16GB DDR5 RAM', category: 'RAM', currentDemand: 4, predictedDemand: 9, trend: 'Increasing', confidence: 88 },
  { productId: '10', productName: 'TP-Link AX3000 Wi-Fi 6 Router', category: 'Networking', currentDemand: 4, predictedDemand: 4, trend: 'Stable', confidence: 92 },
  { productId: '14', productName: 'Asus ROG Gaming Mouse', category: 'Mice', currentDemand: 1, predictedDemand: 0, trend: 'Decreasing', confidence: 78 }
];

export const MOCK_SUPPLIERS: Supplier[] = [
  { id: 's1', name: 'TechWorld Distributors', priceRating: 'Competitive', leadTime: 3, reliability: 96, score: 95 },
  { id: 's2', name: 'ElectroBulk Corp', priceRating: 'Average', leadTime: 5, reliability: 92, score: 88 },
  { id: 's3', name: 'Silicon Supply Co', priceRating: 'Average', leadTime: 4, reliability: 94, score: 91 },
  { id: 's4', name: 'Apex Electronics', priceRating: 'Premium', leadTime: 2, reliability: 98, score: 93 },
  { id: 's5', name: 'Global Trade Link', priceRating: 'Competitive', leadTime: 7, reliability: 88, score: 84 },
  { id: 's6', name: 'Lenovo Wholesale Corp', priceRating: 'Premium', leadTime: 3, reliability: 95, score: 92 }
];

export const MOCK_RECOMMENDATIONS: RecommendedPurchase[] = [
  {
    id: 'rec-1',
    productId: '2',
    productName: 'Logitech M102 Wireless Mouse',
    currentStock: 8,
    predictedDemand: 42,
    recommendedQuantity: 50,
    suggestedSupplier: 'TechWorld Distributors',
    estimatedCost: 32500,
    confidence: 92,
    status: 'Pending',
    whyInventory: 'Current stock is critically below safety margin (8 units vs 25 reorder level). Out-of-stock risk within 36 hours.',
    whyForecasting: 'Weekly demand is expected to spike from 6/day to 14/day due to regional college academic year startups.',
    whyProcurement: 'TechWorld Distributors provides the best unit pricing (₹650) and fastest lead time (3 days) with 96% reliability.',
  },
  {
    id: 'rec-2',
    productId: '5',
    productName: 'Dell Inspiron 15',
    currentStock: 8,
    predictedDemand: 22,
    recommendedQuantity: 20,
    suggestedSupplier: 'TechWorld Distributors',
    estimatedCost: 960000,
    confidence: 89,
    status: 'Pending',
    whyInventory: 'Stock count has dropped to 8 units. Safety threshold is 10 units.',
    whyForecasting: 'Laptop sales have a positive upward trend going into the next fortnight.',
    whyProcurement: 'TechWorld Distributors currently offers the lowest wholesale bulk package for Dell items.',
  },
  {
    id: 'rec-3',
    productId: '3',
    productName: 'Samsung 980 SSD 1TB',
    currentStock: 3,
    predictedDemand: 15,
    recommendedQuantity: 25,
    suggestedSupplier: 'Silicon Supply Co',
    estimatedCost: 195000,
    confidence: 91,
    status: 'Pending',
    whyInventory: 'Only 3 units left in A2 storage rack. High turnover speed on solid-state drives.',
    whyForecasting: 'Consistent high demand for storage electronics expected to hold steady.',
    whyProcurement: 'Silicon Supply Co is the direct manufacturer affiliate with direct component stock availability.',
  },
  {
    id: 'rec-4',
    productId: '7',
    productName: 'Kingston 16GB DDR5 RAM',
    currentStock: 2,
    predictedDemand: 24,
    recommendedQuantity: 30,
    suggestedSupplier: 'Silicon Supply Co',
    estimatedCost: 126000,
    confidence: 87,
    status: 'Pending',
    whyInventory: 'Critical stock alert. Almost fully depleted (2 units remaining).',
    whyForecasting: 'DDR5 upgrade trends are growing due to local corporate office workstation orders.',
    whyProcurement: 'Silicon Supply Co has verified lead time of 4 days, minimizing stockout duration.',
  },
  {
    id: 'rec-5',
    productId: '8',
    productName: 'Keychron K2 Mechanical Keyboard',
    currentStock: 0,
    predictedDemand: 12,
    recommendedQuantity: 15,
    suggestedSupplier: 'Apex Electronics',
    estimatedCost: 127500,
    confidence: 94,
    status: 'Pending',
    whyInventory: 'Product is currently out of stock (0 units remaining).',
    whyForecasting: 'High demand backlog; 4 customer pre-orders waiting on keyboard stock.',
    whyProcurement: 'Apex Electronics offers overnight dispatch (2 days lead time) to fulfill waitlist immediately.',
  }
];

export const MOCK_AGENTS: Agent[] = [
  {
    id: 'inventory-agent',
    name: 'Inventory Agent',
    status: 'Completed',
    lastAnalysis: '10 minutes ago',
    latestInsight: '12 products are approaching their reorder threshold.',
    description: 'Monitors real-time stock levels, detects safety buffer violations, flags dead/slow stock, and keeps inventory records balanced.',
    iconName: 'Package'
  },
  {
    id: 'forecasting-agent',
    name: 'Forecasting Agent',
    status: 'Completed',
    lastAnalysis: '15 minutes ago',
    latestInsight: 'Laptop demand is expected to increase next week.',
    description: 'Applies time-series analytics and trend projections to historical demand data to forecast future warehouse workloads.',
    iconName: 'TrendingUp'
  },
  {
    id: 'procurement-agent',
    name: 'Procurement Agent',
    status: 'Completed',
    lastAnalysis: '18 minutes ago',
    latestInsight: '2 suppliers currently offer better pricing for high-demand products.',
    description: 'Tracks supplier scores, evaluates price lists, estimates bulk shipping costs, and generates smart purchasing lists.',
    iconName: 'ShoppingCart'
  },
  {
    id: 'operations-agent',
    name: 'Operations Agent',
    status: 'Completed',
    lastAnalysis: '5 minutes ago',
    latestInsight: 'Receiving workload increased by 18% today.',
    description: 'Reviews workflow efficiency for core warehouse stages: Receiving, Picking, Packing, and Dispatch.',
    iconName: 'Cpu'
  },
  {
    id: 'supervisor-agent',
    name: 'Supervisor Agent',
    status: 'Waiting',
    lastAnalysis: '1 minute ago',
    latestInsight: '5 procurement recommendations require manager review.',
    description: 'Coordinates insights between specialized agents, resolves conflicting advice, and synthesizes final action proposals.',
    iconName: 'ShieldAlert'
  }
];

export const MOCK_INSIGHTS: Insight[] = [
  {
    id: 'ins-1',
    agentId: 'inventory-agent',
    agentName: 'Inventory Agent',
    title: 'Low Stock Alert',
    message: '12 products may reach low-stock levels within the next 7 days.',
    severity: 'Warning',
    timestamp: '10 mins ago',
    relatedRecommendationId: 'rec-2'
  },
  {
    id: 'ins-2',
    agentId: 'forecasting-agent',
    agentName: 'Forecasting Agent',
    title: 'Demand Spike Predicted',
    message: 'Laptop demand is expected to increase next week by 14%.',
    severity: 'Info',
    timestamp: '15 mins ago',
    relatedRecommendationId: 'rec-2'
  },
  {
    id: 'ins-3',
    agentId: 'procurement-agent',
    agentName: 'Procurement Agent',
    title: 'Supplier Discount Available',
    message: '2 suppliers currently offer better pricing for high-demand products.',
    severity: 'Info',
    timestamp: '18 mins ago',
    relatedRecommendationId: 'rec-1'
  },
  {
    id: 'ins-4',
    agentId: 'operations-agent',
    agentName: 'Operations Agent',
    title: 'Receiving Queue Spike',
    message: 'Receiving workload increased by 18% in Zone B cargo bay.',
    severity: 'Warning',
    timestamp: '5 mins ago'
  },
  {
    id: 'ins-5',
    agentId: 'inventory-agent',
    agentName: 'Inventory Agent',
    title: 'Critical Stock Depletion',
    message: 'Logitech M102 Wireless Mouse is at 8 units. Reorder immediate.',
    severity: 'Critical',
    timestamp: 'Just now',
    relatedRecommendationId: 'rec-1'
  }
];

export const MOCK_ACTIVITY: ActivityLog[] = [
  { id: 'act-1', agentName: 'Inventory Agent', message: 'Completed safety stock analysis on 245 active SKUs.', timestamp: '10m ago' },
  { id: 'act-2', agentName: 'Forecasting Agent', message: 'Updated 30-day demand predictions using updated Q3 sales data.', timestamp: '15m ago' },
  { id: 'act-3', agentName: 'Procurement Agent', message: 'Generated 5 purchasing recommendations based on supplier price sheets.', timestamp: '18m ago' },
  { id: 'act-4', agentName: 'Operations Agent', message: 'Dispatched status alerts: picking queue congestion resolved.', timestamp: '22m ago' },
  { id: 'act-5', agentName: 'Supervisor Agent', message: 'Consolidated logs and generated today\'s executive brief.', timestamp: '25m ago' }
];

export const MOCK_OPERATIONAL_ALERTS: OperationalAlert[] = [
  { id: 'op-1', message: 'Picking queue is higher than average (14 picks delayed).', severity: 'Warning', timestamp: '10m ago' },
  { id: 'op-2', message: 'Dispatch activity is normal across all load bays.', severity: 'Info', timestamp: '15m ago' },
  { id: 'op-3', message: 'Receiving workload increased by 18% over the daily baseline.', severity: 'Info', timestamp: '20m ago' },
  { id: 'op-4', message: 'Packing materials (medium cartons) low in sector C.', severity: 'Warning', timestamp: '45m ago' }
];
