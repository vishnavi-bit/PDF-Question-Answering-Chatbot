import { useEffect, useState } from 'react'
import { Menu, Moon, Settings2, Sun } from 'lucide-react'
import { api } from '../services/api'
import { useTheme } from '../context/ThemeContext'

/** Top bar: opens the sidebar on small screens and warns when the Gemini key is missing. */
export default function Navbar({ title, onMenuClick }) {
  const [keyMissing, setKeyMissing] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const [backendDown, setBackendDown] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then((data) => {
        if (!cancelled) setKeyMissing(!data.gemini_api_key_configured)
      })
      .catch(() => {
        if (!cancelled) setBackendDown(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <header className="flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur sm:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open sidebar"
        className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
      >
        <Menu size={20} aria-hidden="true" />
      </button>
      <h1 className="min-w-0 flex-1 truncate text-base font-semibold text-slate-900">{title}</h1>

      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
        className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100"
      >
        {theme === 'dark' ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
      </button>

      {backendDown && (
        <span className="rounded-full bg-rose-50 px-3 py-1 text-xs font-medium text-rose-700 ring-1 ring-rose-200">
          Backend offline
        </span>
      )}
      {!backendDown && keyMissing && (
        <span
          title="Add GEMINI_API_KEY to backend/.env and restart the backend"
          className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200"
        >
          <Settings2 size={13} aria-hidden="true" /> Gemini key not set
        </span>
      )}
    </header>
  )
}
