import { useEffect, useRef, useState } from 'react'
import { Filter, Paperclip, Send, Square } from 'lucide-react'

const MAX_CHARS = 2000

/**
 * Question box. Enter sends, Shift+Enter adds a new line. While an answer streams, the send
 * button becomes Stop. The text is only cleared when onSend reports success.
 */
export default function ChatInput({
  onSend,
  onStop,
  streaming = false,
  disabled = false,
  placeholder = 'Ask a question about your PDFs…',
  scopeLabel = '',
  onAttach,
  uploading = false,
}) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const trimmed = value.trim()
  const canSend = !disabled && !streaming && trimmed.length > 0 && trimmed.length <= MAX_CHARS

  // grow with the text, up to a limit
  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [value])

  const submit = async (event) => {
    if (event) event.preventDefault()
    // While an answer streams, Enter does nothing. Only the Stop button stops it.
    if (streaming || !canSend) return
    const result = await onSend(trimmed)
    if (result !== false) setValue('')
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent?.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl" aria-label="Ask a question">
      <div className="rounded-3xl border border-slate-300 bg-white p-2 shadow-md transition focus-within:border-indigo-400 focus-within:ring-4 focus-within:ring-indigo-100">
        <label htmlFor="chat-question" className="sr-only">
          Your question
        </label>
        <textarea
          id="chat-question"
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          maxLength={MAX_CHARS + 200}
          disabled={disabled}
          className="block max-h-[200px] min-h-[44px] w-full resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-slate-900 placeholder:text-slate-500 focus:outline-none focus-visible:outline-none disabled:cursor-not-allowed"
        />
        <div className="flex items-center justify-between gap-2 px-1 pb-0.5">
          <div className="flex min-w-0 items-center gap-1">
            {onAttach && (
              <>
                <button
                  type="button"
                  aria-label="Attach PDF"
                  title="Add PDF files"
                  onClick={() => fileInputRef.current && fileInputRef.current.click()}
                  disabled={uploading}
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-indigo-600 disabled:opacity-40"
                >
                  <Paperclip size={18} aria-hidden="true" />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  multiple
                  className="hidden"
                  aria-label="Add PDF files"
                  onChange={(event) => {
                    const files = event.target.files
                    event.target.value = ''
                    onAttach(files)
                  }}
                />
              </>
            )}
            {scopeLabel && (
              <span className="inline-flex min-w-0 items-center gap-1.5 truncate rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700" data-testid="scope-chip">
                <Filter size={12} aria-hidden="true" className="shrink-0" />
                <span className="truncate">{scopeLabel}</span>
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className={`hidden text-xs sm:inline ${trimmed.length > MAX_CHARS ? 'text-rose-500' : 'text-slate-500'}`}>
              {trimmed.length}/{MAX_CHARS}
            </span>
            {streaming ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop answering"
                className="inline-flex h-10 items-center gap-2 rounded-2xl bg-slate-900 px-4 text-sm font-semibold text-white transition hover:opacity-90"
              >
                <Square size={14} aria-hidden="true" /> Stop
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSend}
                aria-label="Send question"
                className="brand-gradient inline-flex h-10 w-10 items-center justify-center rounded-2xl text-white shadow-md shadow-indigo-200 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Send size={18} aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="mt-1.5 px-3 text-xs text-slate-500">
        Enter to send · Shift+Enter for a new line
      </p>
    </form>
  )
}
