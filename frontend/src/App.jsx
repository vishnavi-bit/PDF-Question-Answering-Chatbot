import { useState } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Chat from './pages/Chat'
import History from './pages/History'
import Study from './pages/Study'
import { useAppState } from './context/ChatContext'

const PAGE_TITLES = [
  { prefix: '/chat', title: 'Chat with your PDFs' },
  { prefix: '/history', title: 'Chat history' },
  { prefix: '/study', title: 'Study Assistant' },
  { prefix: '/', title: 'Home' },
]

function titleFor(pathname) {
  const match = PAGE_TITLES.find((item) => (item.prefix === '/' ? pathname === '/' : pathname.startsWith(item.prefix)))
  return match ? match.title : 'AI PDF Chatbot'
}

/** Page frame: sidebar on the left, top bar, and the routed page. */
function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const { error, setError } = useAppState()

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Navbar title={titleFor(location.pathname)} onMenuClick={() => setSidebarOpen(true)} />
        {error && (
          <div role="alert" className="flex items-center justify-between gap-3 border-b border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 sm:px-6">
            <span>{error}</span>
            <button type="button" onClick={() => setError('')} className="rounded px-2 py-0.5 text-xs font-medium hover:bg-rose-100">
              Dismiss
            </button>
          </div>
        )}
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/chat" element={<ChatRoute />} />
        <Route path="/chat/:conversationId" element={<ChatRoute />} />
        <Route path="/history" element={<History />} />
        <Route path="/study" element={<Study />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </Layout>
  )
}

// Chat fills the full height, so it does not scroll as a whole page.
function ChatRoute() {
  return (
    <div className="h-full">
      <Chat />
    </div>
  )
}
