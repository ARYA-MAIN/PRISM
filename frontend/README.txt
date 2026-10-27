PRISM dashboard -> live analytics API patch

Copy these two files into your FRONTEND project root (the folder containing package.json), preserving folders:
  src/pages/Dashboard.tsx
  vite.config.ts

Both files replace existing files. This updates the Dashboard to fetch live data from:
  GET /api/analytics/overview
  GET /api/analytics/alerts

The Vite proxy sends /api requests to FastAPI at http://127.0.0.1:8000 without needing a separate CORS change.

After copying:
1. Keep FastAPI running from your backend folder.
2. In a separate terminal, cd to the frontend folder (the one with package.json).
3. Run: npm run dev
4. Open the Vite URL shown in the terminal (usually http://localhost:5173) and visit /dashboard.
5. If Vite was already running when vite.config.ts changed, stop it with Ctrl+C and rerun npm run dev.

Note: this patch changes the dashboard only. Other pages such as Inventory and Products may still use mock data; we can connect those pages next.
