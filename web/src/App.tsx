import { lazy, Suspense } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Loading, useIdentity } from './components/common'

// Pages load on demand: the force-graph and chart libraries stay out of the first load.
const ChatPage = lazy(() => import('./pages/ChatPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const KnowledgePage = lazy(() => import('./pages/KnowledgePage'))
const ReviewPage = lazy(() => import('./pages/ReviewPage'))
const StatusPage = lazy(() => import('./pages/StatusPage'))

export default function App() {
  const { id, setId } = useIdentity()
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">Engineering Intelligence Hub</strong>
        <nav>
          <NavLink to="/chat">Chat</NavLink>
          <NavLink to="/knowledge">Knowledge</NavLink>
          <NavLink to="/review">Review</NavLink>
          <NavLink to="/dashboard">Results</NavLink>
          <NavLink to="/status">Status</NavLink>
        </nav>
        <label className="identity" title="Your edits and approvals are recorded as human:<id> (OKF §7)">
          human:
          <input value={id} onChange={(e) => setId(e.target.value)} placeholder="your-id" aria-label="Reviewer id" size={12} />
        </label>
      </header>
      <main>
        <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:proposalId" element={<ReviewPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<div className="state">Page not found.</div>} />
        </Routes>
        </Suspense>
      </main>
    </div>
  )
}
