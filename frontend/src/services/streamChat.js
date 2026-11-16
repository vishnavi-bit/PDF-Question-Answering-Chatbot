/**
 * Reads streamed answers (Server-Sent Events) from the chat endpoints:
 *   POST /api/chat/stream      a new question
 *   POST /api/chat/regenerate  answer the last question again
 *
 * Events: meta (retrieval info), delta (text), done (saved messages), error (problem mid-answer).
 * Errors before the answer starts arrive as normal HTTP errors and are thrown here.
 */

const DEFAULT_ERROR = 'The answer could not be created. Please try again.'

/** Parse one SSE block ("event: x\ndata: {...}") into { event, data }. Returns null for empty blocks. */
export function parseSseBlock(block) {
  let event = 'message'
  const dataLines = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
  }
  if (dataLines.length === 0) return null
  let data
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    return null // a damaged block is skipped rather than shown
  }
  return { event, data }
}

/**
 * Stream from any of the chat SSE endpoints. Handlers are optional:
 *   onMeta(retrieval), onDelta(text), onDone(result)
 * Resolves with the final result. Rejects with an Error whose `.status` is the HTTP status.
 * Pass an AbortSignal in options.signal to stop reading (the server then saves nothing).
 */
export async function streamSse(path, payload, handlers = {}, options = {}) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal: options.signal,
  })

  if (!response.ok) {
    let detail = DEFAULT_ERROR
    try {
      const body = await response.json()
      if (typeof body.detail === 'string' && body.detail.trim()) detail = body.detail
    } catch {
      // no readable body: keep the default message
    }
    const error = new Error(detail)
    error.status = response.status
    throw error
  }
  if (!response.body) {
    throw new Error('This browser cannot read streamed answers. Please update your browser.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = null

  const dispatch = (parsed) => {
    if (!parsed) return
    const { event, data } = parsed
    if (event === 'meta' && handlers.onMeta) handlers.onMeta(data.retrieval || {})
    if (event === 'delta' && handlers.onDelta) handlers.onDelta(data.text || '')
    if (event === 'done') finished = { ok: true, data }
    if (event === 'error') {
      const error = new Error(data.detail || DEFAULT_ERROR)
      error.status = data.status
      finished = { ok: false, error }
    }
  }

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      dispatch(parseSseBlock(buffer.slice(0, boundary)))
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) dispatch(parseSseBlock(buffer.trim()))

  if (!finished) {
    const error = new Error('The answer was interrupted before it finished. Please try again.')
    error.status = 502
    throw error
  }
  if (!finished.ok) throw finished.error
  if (handlers.onDone) handlers.onDone(finished.data)
  return finished.data
}

/** Stream a new question. */
export function streamChat(payload, handlers = {}, options = {}) {
  return streamSse('/api/chat/stream', payload, handlers, options)
}

/** Stream a new answer to the last question. The old answer is kept if this fails. */
export function streamRegenerate(payload, handlers = {}, options = {}) {
  return streamSse('/api/chat/regenerate', payload, handlers, options)
}
