import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from './AppLayout'
import RequireAuth from './RequireAuth'
import LoginPage from '../features/auth/LoginPage'
import AdminPage from '../features/admin/AdminPage'
import AnswerPage from '../features/ask/AnswerPage'
import AskComparePage from '../features/ask/AskComparePage'
import JudgmentsPage from '../features/judgments/JudgmentsPage'
import JudgmentPage from '../features/judgments/JudgmentPage'
import HomePage from '../features/home/HomePage'
import StockPage, { DEFAULT_STOCK } from '../features/stocks/StockPage'
import MarketPage from '../features/market/MarketPage'
import RecordsPage from '../features/records/RecordsPage'
import WatchPage from '../features/watch/WatchPage'
import RoomPage from '../features/rooms/RoomPage'
import RoomsPage from '../features/rooms/RoomsPage'
import PersonasPage from '../features/rooms/PersonasPage'
import PersonaAdminPage from '../features/admin/PersonaAdminPage'
import PicksPage from '../features/picks/PicksPage'
import PickRecordPage from '../features/picks/PickRecordPage'
import MePage from '../features/me/MePage'
import PatternsPage from '../features/patterns/PatternsPage'
import NewPatternPage from '../features/patterns/NewPatternPage'
import JobPage from '../features/patterns/JobPage'
import ComparePage from '../features/patterns/ComparePage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth><AppLayout /></RequireAuth>,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'ask/compare', element: <AskComparePage /> },
      { path: 'ask/:kind', element: <AnswerPage /> },
      { path: 'judgments', element: <JudgmentsPage /> },
      { path: 'judgments/:id', element: <JudgmentPage /> },
      { path: 'stocks', element: <Navigate to={`/stocks/${DEFAULT_STOCK}`} replace /> },
      { path: 'stocks/:code', element: <StockPage /> },
      { path: 'picks', element: <PicksPage /> },
      { path: 'picks/record', element: <PickRecordPage /> },
      { path: 'me', element: <MePage /> },
      { path: 'patterns', element: <PatternsPage /> },
      { path: 'patterns/new/:index', element: <NewPatternPage /> },
      { path: 'patterns/jobs/:id', element: <JobPage /> },
      { path: 'patterns/compare', element: <ComparePage /> },
      { path: 'records', element: <RecordsPage /> },
      { path: 'market', element: <MarketPage /> },
      { path: 'watch', element: <WatchPage /> },
      { path: 'rooms', element: <RoomsPage /> },
      { path: 'rooms/:id', element: <RoomPage /> },
      { path: 'personas', element: <PersonasPage /> },
      { path: 'admin', element: <RequireAuth admin><AdminPage /></RequireAuth> },
      { path: 'admin/personas', element: <RequireAuth admin><PersonaAdminPage /></RequireAuth> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
