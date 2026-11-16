import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import {
  FileText,
  GraduationCap,
  History,
  MessageSquare,
  MessageSquarePlus,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings2,
  Sun,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useAppState } from '../context/ChatContext'
import { useTheme } from '../context/ThemeContext'
import { api } from '../services/api'
import { PREF_KEYS, readPreference, writePreference } from '../hooks/usePreferences'
import { StatusBadge } from './DocumentCard'

const SEARCH_DELAY_MS = 250

/** Left sidebar: new chat, search, chat history, PDFs with selection, Study Assistant, settings. */
export default function Sidebar({ open, onClose }) {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const {
    documents,
    selectedDocumentIds,
    toggleDocument,
    setSelectedDocumentIds,
    uploadFiles,
    uploading,
    conversations,
    removeDocument,
  } = useAppState()
  const { theme, setTheme } = useTheme()

  const [collapsed, setCollapsed] = useState(() => readPreference(PREF_KEYS.sidebarCollapsed, 'false') === 'true')
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [answerStyle, setAnswerStyle] = useState(() => readPreference(PREF_KEYS.answerStyle, 'detailed', ['short', 'detailed']))

  // Conversation search: matches titles and message text on the server, after a short pause.
  useEffect(() => {
    const text = query.trim()
    if (!text) {
      setSearchResults(null)
      setSearching(false)
      return undefined
    }
    setSearching(true)
    let cancelled = false
    const timer = setTimeout(() => {
      api
        .listConversations(text)
        .then((data) => {
          if (!cancelled) setSearchResults(data.conversations)
        })
        .catch(() => {
          if (!cancelled) setSearchResults([])
        })
        .finally(() => {
          if (!cancelled) setSearching(false)
        })
    }, SEARCH_DELAY_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  const readyDocuments = documents.filter((doc) => doc.processing_status === 'ready')
  const readyIds = readyDocuments.map((doc) => doc.id)
  // An empty selection means "all ready documents" (the list updates as PDFs are added or removed).
  const selectionCount = selectedDocumentIds.length
  const scopeText =
    selectionCount === 0
      ? `All ${readyDocuments.length} ready document${readyDocuments.length === 1 ? '' : 's'}`
      : `${selectionCount} of ${readyDocuments.length} selected`

  const handleRemove = async (doc) => {
    if (!window.confirm(`Remove "${doc.filename}"? Its stored file and search entries will be deleted. Other PDFs are not affected.`)) return
    await removeDocument(doc.id)
  }

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      writePreference(PREF_KEYS.sidebarCollapsed, !value)
      return !value
    })
  }

  const chooseAnswerStyle = (style) => {
    writePreference(PREF_KEYS.answerStyle, style)
    setAnswerStyle(style)
  }

  const handleNewChat = () => {
    setQuery('')
    navigate('/chat')
    if (onClose) onClose()
  }

  const recent = (searchResults !== null ? searchResults : conversations).slice(0, searchResults !== null ? 50 : 12)
  const rail = collapsed && !open

  return (
    <>
      {/* dark overlay on small screens when the sidebar is open */}
      {open && <div className="fixed inset-0 z-30 bg-slate-900/30 lg:hidden" onClick={onClose} aria-hidden="true" />}

      <aside
        aria-label="Sidebar"
        data-collapsed={rail ? 'true' : 'false'}
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-slate-200 bg-white transition-all duration-200 lg:static lg:translate-x-0 ${
          open ? 'w-72 translate-x-0' : '-translate-x-full'
        } ${collapsed ? 'lg:w-16' : 'lg:w-72'}`}
      >
        <div className={`flex items-center px-4 py-5 ${collapsed ? 'lg:justify-center lg:px-2' : 'justify-between'}`}>
          <Link to="/" className="flex min-w-0 items-center gap-2.5" onClick={onClose} title="PDF Chatbot home">
            <span className="brand-gradient flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-md shadow-indigo-200">
              <FileText size={18} aria-hidden="true" />
            </span>
            <span className={`truncate font-bold text-slate-900 ${collapsed ? 'lg:hidden' : ''}`}>PDF Chatbot</span>
          </Link>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              className={`hidden rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 lg:inline-flex ${collapsed ? 'lg:hidden' : ''}`}
            >
              <PanelLeftClose size={18} aria-hidden="true" />
            </button>
            <button type="button" onClick={onClose} aria-label="Close sidebar" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden">
              <X size={18} aria-hidden="true" />
            </button>
          </div>
        </div>

        {collapsed && (
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label="Expand sidebar"
            title="Expand sidebar"
            className="mx-auto mb-2 hidden rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:inline-flex"
          >
            <PanelLeftOpen size={18} aria-hidden="true" />
          </button>
        )}

        <div className={`space-y-2 px-4 ${collapsed ? 'lg:px-2' : ''}`}>
          <button
            type="button"
            onClick={handleNewChat}
            title="New chat"
            className="btn-primary flex w-full items-center justify-center gap-2 px-4 py-2.5 text-sm shadow-md shadow-indigo-200"
          >
            <MessageSquarePlus size={17} aria-hidden="true" />
            <span className={collapsed ? 'lg:hidden' : ''}>New chat</span>
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
            disabled={uploading.active}
            title="Upload PDF"
            className="btn-secondary flex w-full items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-50"
          >
            <Upload size={17} aria-hidden="true" />
            <span className={collapsed ? 'lg:hidden' : ''}>
              {uploading.active ? `Uploading ${uploading.done + 1}/${uploading.total}…` : 'Upload PDF'}
            </span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="hidden"
            aria-label="Upload PDF files"
            onChange={async (event) => {
              const files = event.target.files
              event.target.value = ''
              await uploadFiles(files)
            }}
          />
        </div>

        <div className={`mt-5 min-h-0 flex-1 overflow-y-auto px-4 pb-4 ${collapsed ? 'lg:hidden' : ''}`}>
          <section aria-labelledby="sidebar-recent" className="mb-6">
            <h2 id="sidebar-recent" className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Chats
            </h2>
            <label className="relative mb-2 block">
              <span className="sr-only">Search conversations</span>
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search chats…"
                aria-label="Search conversations"
                className="field w-full py-2 pl-8 pr-3 text-sm"
              />
            </label>
            {searching && <p className="px-1 text-xs text-slate-500">Searching…</p>}
            {!searching && recent.length === 0 && (
              <p className="px-1 text-sm text-slate-500">
                {query.trim() ? 'No chats match your search.' : 'Your conversations appear here.'}
              </p>
            )}
            <ul className="space-y-1">
              {recent.map((conversation) => (
                <li key={conversation.id}>
                  <NavLink
                    to={`/chat/${conversation.id}`}
                    onClick={onClose}
                    className={({ isActive }) =>
                      `block truncate rounded-lg px-3 py-2 text-sm transition ${
                        isActive ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-slate-700 hover:bg-slate-100'
                      }`
                    }
                  >
                    {conversation.title}
                  </NavLink>
                </li>
              ))}
            </ul>
            <NavLink
              to="/history"
              onClick={onClose}
              className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              <History size={16} aria-hidden="true" /> All conversations
            </NavLink>
          </section>

          <section aria-labelledby="sidebar-docs">
            <h2 id="sidebar-docs" className="mb-2 flex items-center justify-between px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              PDFs
              <span className="font-normal normal-case">{documents.length} total</span>
            </h2>

            {readyDocuments.length > 0 && (
              <div className="mb-2 flex items-center gap-1 px-1">
                <button
                  type="button"
                  onClick={() => setSelectedDocumentIds(readyIds)}
                  disabled={selectionCount === readyIds.length}
                  className="rounded-md px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:text-slate-500 disabled:hover:bg-transparent"
                >
                  Select all
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedDocumentIds([])}
                  disabled={selectionCount === 0}
                  className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:text-slate-500 disabled:hover:bg-transparent"
                >
                  Clear
                </button>
              </div>
            )}
            <p className="mb-2 px-1 text-xs text-slate-500" data-testid="scope-summary">
              Searching: {scopeText}
            </p>

            {documents.length === 0 && <p className="px-1 text-sm text-slate-500">No PDFs uploaded yet.</p>}
            <ul className="space-y-1">
              {documents.map((doc) => {
                const ready = doc.processing_status === 'ready'
                return (
                  <li key={doc.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                    {ready ? (
                      <input
                        type="checkbox"
                        aria-label={`Use ${doc.filename} in chat`}
                        checked={selectedDocumentIds.includes(doc.id)}
                        onChange={() => toggleDocument(doc.id)}
                        className="h-4 w-4 shrink-0 accent-indigo-600"
                      />
                    ) : (
                      <span className="h-4 w-4 shrink-0" aria-hidden="true" />
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-700" title={doc.filename}>
                      {doc.filename}
                    </span>
                    {!ready && <StatusBadge status={doc.processing_status} />}
                    <button
                      type="button"
                      onClick={() => handleRemove(doc)}
                      aria-label={`Remove ${doc.filename}`}
                      title="Remove this PDF"
                      className="shrink-0 rounded-md p-1 text-slate-500 hover:bg-rose-50 hover:text-rose-600"
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>

          <nav aria-label="Main sections" className="mt-6 space-y-1">
            <NavLink
              to="/chat"
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
                }`
              }
            >
              <MessageSquare size={16} aria-hidden="true" /> PDF Chatbot
            </NavLink>
            <NavLink
              to="/study"
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
                }`
              }
            >
              <GraduationCap size={16} aria-hidden="true" /> Study Assistant
            </NavLink>
          </nav>
        </div>

        <div className={`relative border-t border-slate-200 px-4 py-3 ${collapsed ? 'lg:px-2' : ''}`}>
          <button
            type="button"
            onClick={() => setShowSettings((value) => !value)}
            aria-expanded={showSettings}
            aria-controls="sidebar-settings"
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
          >
            <Settings2 size={16} aria-hidden="true" />
            <span className={collapsed ? 'lg:hidden' : ''}>Settings</span>
          </button>
          {showSettings && (
            <div id="sidebar-settings" className="animate-fade-up card mt-2 space-y-3 p-3 text-sm" role="group" aria-label="Settings">
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Theme</p>
                <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
                  <button
                    type="button"
                    aria-pressed={theme === 'light'}
                    onClick={() => setTheme('light')}
                    className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium ${theme === 'light' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
                  >
                    <Sun size={13} aria-hidden="true" /> Light
                  </button>
                  <button
                    type="button"
                    aria-pressed={theme === 'dark'}
                    onClick={() => setTheme('dark')}
                    className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium ${theme === 'dark' ? 'bg-slate-700 text-white shadow-sm' : 'text-slate-600'}`}
                  >
                    <Moon size={13} aria-hidden="true" /> Dark
                  </button>
                </div>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Answer length</p>
                <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
                  {[
                    ['short', 'Short'],
                    ['detailed', 'Detailed'],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={answerStyle === value}
                      onClick={() => chooseAnswerStyle(value)}
                      className={`rounded-lg px-2 py-1.5 text-xs font-medium ${answerStyle === value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <p className="text-xs text-slate-500">Saved in this browser.</p>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
