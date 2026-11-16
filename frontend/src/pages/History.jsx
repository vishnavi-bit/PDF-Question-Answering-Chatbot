import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, History as HistoryIcon, MessageSquare, Pencil, Trash2, X } from 'lucide-react'
import { useAppState } from '../context/ChatContext'
import { api, getErrorMessage } from '../services/api'
import EmptyState from '../components/EmptyState'

function formatDate(value) {
  if (!value) return ''
  // The server stores UTC times without a time-zone marker, so add "Z" before parsing.
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString()
}

/** Every saved conversation, with rename and delete. */
export default function History() {
  const { conversations, refreshConversations, setError } = useAppState()
  const [editingId, setEditingId] = useState(null)
  const [draftTitle, setDraftTitle] = useState('')
  const [busyId, setBusyId] = useState(null)

  const startRename = (conversation) => {
    setEditingId(conversation.id)
    setDraftTitle(conversation.title)
  }

  const saveRename = async (conversationId) => {
    const title = draftTitle.trim()
    if (!title) {
      setError('A conversation needs a title.')
      return
    }
    setBusyId(conversationId)
    try {
      await api.renameConversation(conversationId, title)
      setEditingId(null)
      await refreshConversations()
    } catch (err) {
      setError(getErrorMessage(err, 'The conversation could not be renamed.'))
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (conversation) => {
    if (!window.confirm(`Delete "${conversation.title}" and all its messages?`)) return
    setBusyId(conversation.id)
    try {
      await api.deleteConversation(conversation.id)
      await refreshConversations()
    } catch (err) {
      setError(getErrorMessage(err, 'The conversation could not be deleted.'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <h2 className="flex items-center gap-2 text-2xl font-bold text-slate-900">
          <HistoryIcon size={22} aria-hidden="true" className="text-indigo-600" /> Chat history
        </h2>
        <p className="mt-1 text-sm text-slate-500">Open, rename or delete your earlier conversations.</p>
      </div>

      {conversations.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No conversations yet"
          description="Start a chat after uploading a PDF and your conversations will be saved here."
        >
          <Link to="/chat" className="brand-gradient inline-flex rounded-xl px-4 py-2 text-sm font-semibold text-white">
            Start a new chat
          </Link>
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {conversations.map((conversation) => {
            const isEditing = editingId === conversation.id
            const isBusy = busyId === conversation.id
            return (
              <li key={conversation.id} className="animate-fade-up rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="conversation-item">
                {isEditing ? (
                  <form
                    className="flex flex-wrap items-center gap-2"
                    onSubmit={(event) => {
                      event.preventDefault()
                      saveRename(conversation.id)
                    }}
                  >
                    <label className="sr-only" htmlFor={`rename-${conversation.id}`}>
                      New title
                    </label>
                    <input
                      id={`rename-${conversation.id}`}
                      value={draftTitle}
                      maxLength={120}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-4 focus:ring-indigo-100"
                    />
                    <button type="submit" disabled={isBusy} className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                      <Check size={14} aria-hidden="true" /> Save
                    </button>
                    <button type="button" onClick={() => setEditingId(null)} className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100">
                      <X size={14} aria-hidden="true" /> Cancel
                    </button>
                  </form>
                ) : (
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <Link to={`/chat/${conversation.id}`} className="block truncate font-semibold text-slate-900 hover:text-indigo-700">
                        {conversation.title}
                      </Link>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {conversation.message_count} message{conversation.message_count === 1 ? '' : 's'}
                        {conversation.updated_at ? ` · updated ${formatDate(conversation.updated_at)}` : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => startRename(conversation)}
                        disabled={isBusy}
                        aria-label={`Rename ${conversation.title}`}
                        className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                      >
                        <Pencil size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(conversation)}
                        disabled={isBusy}
                        aria-label={`Delete ${conversation.title}`}
                        className="rounded-lg p-2 text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
