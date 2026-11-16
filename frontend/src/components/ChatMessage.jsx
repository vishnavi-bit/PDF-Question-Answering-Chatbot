import { useState } from 'react'
import { Bot, Check, Copy, RotateCcw, ThumbsDown, ThumbsUp, User } from 'lucide-react'
import Markdown from './chat/Markdown'
import CitationCard from './chat/CitationCard'

/**
 * One message. Assistant answers are Markdown, show citation cards once the answer is complete,
 * and offer Copy, Regenerate (on the latest answer only) and helpful / not helpful feedback.
 */
export default function ChatMessage({ message, onFeedback, onOpenSource, onRegenerate, isLatestAnswer = false, disabled = false }) {
  const [copyState, setCopyState] = useState('idle') // idle | copied | failed
  const isUser = message.role === 'user'
  const isPending = Boolean(message.pending)
  const isSaved = typeof message.id === 'number'

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopyState('copied')
    } catch {
      // the browser may block clipboard access (for example on an http address)
      setCopyState('failed')
    }
    setTimeout(() => setCopyState('idle'), 1800)
  }

  if (isUser) {
    return (
      <div className="animate-fade-up flex justify-end gap-3" data-testid="user-message">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-3 text-[15px] leading-6 text-white shadow-sm sm:max-w-[70%]">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        <div className="mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-600 sm:flex">
          <User size={16} aria-hidden="true" />
        </div>
      </div>
    )
  }

  const sources = message.sources || []
  const showTyping = isPending && !message.content
  const showActions = isSaved && !isPending

  return (
    <div className="animate-fade-up flex gap-3" data-testid="assistant-message">
      <div className="brand-gradient mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-white sm:flex">
        <Bot size={16} aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-5 py-4 shadow-sm">
        {showTyping && (
          <div role="status" aria-live="polite" className="flex items-center gap-1 py-1 text-sm text-slate-500">
            <span className="typing-dot" />
            <span className="typing-dot" style={{ animationDelay: '0.15s' }} />
            <span className="typing-dot" style={{ animationDelay: '0.3s' }} />
            <span className="ml-2">{message.regenerating ? 'Writing a new answer…' : 'Searching your PDFs…'}</span>
          </div>
        )}

        {message.content && (
          <div className={isPending ? 'streaming-text' : ''} aria-live={isPending ? 'polite' : undefined}>
            <Markdown text={message.content} />
          </div>
        )}

        {message.verification && message.verification.verdict === 'partial' && (
          <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800" role="status">
            <span>
              Some statements in this answer could not be matched to the cited PDF text ({message.verification.unsupported} of {message.verification.checked}). Check the sources before relying on them.
            </span>
          </p>
        )}

        {message.stopped && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800" role="status">
            You stopped this answer. It was not saved, so it will not appear after you reload.
          </p>
        )}

        {!isPending && sources.length > 0 && (
          <div className="mt-4 border-t border-slate-100 pt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Sources ({sources.length})
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {sources.map((source) => (
                <CitationCard key={`${source.document_id}-${source.page_number}-${source.source_id}`} source={source} onOpenPage={onOpenSource} />
              ))}
            </div>
          </div>
        )}

        {showActions && (
          <div className="mt-4 flex flex-wrap items-center gap-1 border-t border-slate-100 pt-3">
            <button
              type="button"
              onClick={copyAnswer}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
            >
              {copyState === 'copied' ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
              {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Copy answer'}
            </button>
            {isLatestAnswer && onRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                disabled={disabled}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
              >
                <RotateCcw size={14} aria-hidden="true" /> Regenerate
              </button>
            )}
            <span className="ml-auto flex items-center gap-1">
              <button
                type="button"
                aria-label="Helpful answer"
                aria-pressed={message.feedback === 'up'}
                onClick={() => onFeedback && onFeedback(message.id, 'up')}
                className={`rounded-lg p-1.5 transition hover:bg-slate-100 ${message.feedback === 'up' ? 'text-emerald-600' : 'text-slate-500'}`}
              >
                <ThumbsUp size={15} aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-label="Not helpful answer"
                aria-pressed={message.feedback === 'down'}
                onClick={() => onFeedback && onFeedback(message.id, 'down')}
                className={`rounded-lg p-1.5 transition hover:bg-slate-100 ${message.feedback === 'down' ? 'text-rose-600' : 'text-slate-500'}`}
              >
                <ThumbsDown size={15} aria-hidden="true" />
              </button>
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
