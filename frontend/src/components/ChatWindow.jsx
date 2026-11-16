import { useEffect, useRef } from 'react'
import { AlertCircle, RotateCcw } from 'lucide-react'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import LoadingIndicator from './LoadingIndicator'
import WelcomeScreen from './chat/WelcomeScreen'
import FollowUps, { followUpSuggestions } from './chat/FollowUps'

const NEAR_BOTTOM_PX = 140

/** Message list, welcome screen, streamed answers, follow-ups, errors and the composer. */
export default function ChatWindow({
  messages,
  streaming = false,
  loadingHistory = false,
  error = '',
  onSend,
  onStop,
  onRetry,
  onRegenerate,
  canRegenerate = false,
  onFeedback,
  onOpenSource,
  documents = [],
  hasDocuments,
  scopeLabel = '',
  onAttach,
  uploading = false,
}) {
  const scrollRef = useRef(null)
  const stickToBottom = useRef(true)

  // Follow the newest text while the reader is at the bottom; leave the view alone if they scrolled up.
  useEffect(() => {
    const element = scrollRef.current
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight
  }, [messages, streaming])

  const handleScroll = () => {
    const element = scrollRef.current
    if (!element) return
    stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM_PX
  }

  const latestSavedIndex = (() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === 'assistant' && typeof messages[index].id === 'number') return index
    }
    return -1
  })()
  const latestAnswer = latestSavedIndex >= 0 ? messages[latestSavedIndex] : null
  const showFollowUps = Boolean(latestAnswer) && !streaming && !loadingHistory
  const followUps = showFollowUps ? followUpSuggestions(
    (messages.slice(0, latestSavedIndex).reverse().find((message) => message.role === 'user') || {}).content || '',
    latestAnswer.sources || [],
  ) : []

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6"
        data-testid="message-list"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.length === 0 && !loadingHistory && (
            <WelcomeScreen
              documents={documents}
              onExample={(question) => onSend(question)}
              onUpload={onAttach}
              uploading={uploading}
              disabled={streaming}
            />
          )}

          {loadingHistory && <LoadingIndicator label="Loading conversation…" />}

          {messages.map((message, index) => (
            <ChatMessage
              key={message.id}
              message={message}
              onFeedback={onFeedback}
              onOpenSource={onOpenSource}
              onRegenerate={index === latestSavedIndex && canRegenerate ? onRegenerate : undefined}
              isLatestAnswer={index === latestSavedIndex}
              disabled={streaming}
            />
          ))}

          {showFollowUps && followUps.length > 0 && (
            <FollowUps suggestions={followUps} onSelect={(text) => onSend(text)} disabled={streaming} />
          )}

          {error && (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <AlertCircle size={18} className="shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">{error}</span>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  disabled={streaming}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 disabled:opacity-50"
                >
                  <RotateCcw size={13} aria-hidden="true" /> Try again
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-slate-200 bg-white/90 px-4 py-4 backdrop-blur sm:px-6">
        <ChatInput
          onSend={onSend}
          onStop={onStop}
          streaming={streaming}
          disabled={loadingHistory || !hasDocuments}
          placeholder={hasDocuments ? 'Ask a question about your PDFs…' : 'Add a PDF first, then ask a question…'}
          scopeLabel={scopeLabel}
          onAttach={onAttach}
          uploading={uploading}
        />
      </div>
    </div>
  )
}
