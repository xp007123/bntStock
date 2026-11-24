import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from './AppLayout'
import HomePage from '../features/home/HomePage'
import StockPage, { DEFAULT_STOCK } from '../features/stocks/StockPage'
import MarketPage from '../features/market/MarketPage'
import RecordsPage from '../features/records/RecordsPage'
import PatternsPage from '../features/patterns/PatternsPage'
import NewPatternPage from '../features/patterns/NewPatternPage'
import JobPage from '../features/patterns/JobPage'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'stocks', element: <Navigate to={`/stocks/${DEFAULT_STOCK}`} replace /> },
      { path: 'stocks/:code', element: <StockPage /> },
      { path: 'patterns', element: <PatternsPage /> },
      { path: 'patterns/new/:index', element: <NewPatternPage /> },
      { path: 'patterns/jobs/:id', element: <JobPage /> },
      { path: 'records', element: <RecordsPage /> },
      { path: 'market', element: <MarketPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
