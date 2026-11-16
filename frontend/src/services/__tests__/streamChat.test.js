import { afterEach, describe, expect, it, vi } from 'vitest'
import { parseSseBlock, streamChat } from '../streamChat'

/** Build a streamed Response from text chunks (chunks may split events anywhere). */
function sseResponse(chunks, status = 200) {
  const encoder = new TextEncoder()
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } })
}

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function stubFetch(response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
  return globalThis.fetch
}

const DONE = {
  conversation_id: 3,
  user_message: { id: 1, role: 'user', content: 'How long?', sources: [] },
  assistant_message: { id: 2, role: 'assistant', content: 'Two years.', sources: [{ source_id: 'S1', filename: 'p.pdf', page_number: 1 }] },
  answered_from_documents: true,
  retrieval: { chunks_used: 1 },
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('parseSseBlock', () => {
  it('reads the event name and the JSON data', () => {
    expect(parseSseBlock('event: delta\ndata: {"text":"Hi"}')).toEqual({ event: 'delta', data: { text: 'Hi' } })
  })

  it('returns null for a block without data', () => {
    expect(parseSseBlock('event: meta')).toBeNull()
  })

  it('skips a damaged block instead of crashing', () => {
    expect(parseSseBlock('event: delta\ndata: {not json')).toBeNull()
  })
})

describe('streamChat', () => {
  it('delivers text as it arrives and resolves with the saved messages', async () => {
    stubFetch(
      sseResponse([
        'event: meta\ndata: {"retrieval":{"chunks_used":1}}\n\n',
        'event: delta\ndata: {"text":"Two "}\n\n',
        'event: delta\ndata: {"text":"years."}\n\n',
        `event: done\ndata: ${JSON.stringify(DONE)}\n\n`,
      ]),
    )
    const deltas = []
    const onMeta = vi.fn()
    const onDone = vi.fn()

    const result = await streamChat({ question: 'How long?' }, { onMeta, onDelta: (text) => deltas.push(text), onDone })

    expect(deltas).toEqual(['Two ', 'years.'])
    expect(onMeta).toHaveBeenCalledWith({ chunks_used: 1 })
    expect(onDone).toHaveBeenCalledWith(DONE)
    expect(result.assistant_message.content).toBe('Two years.')
  })

  it('handles events split across network chunks', async () => {
    const full = 'event: delta\ndata: {"text":"Split answer"}\n\nevent: done\ndata: ' + JSON.stringify(DONE) + '\n\n'
    stubFetch(sseResponse([full.slice(0, 9), full.slice(9, 40), full.slice(40)]))
    const deltas = []

    await streamChat({ question: 'Q' }, { onDelta: (text) => deltas.push(text) })

    expect(deltas).toEqual(['Split answer'])
  })

  it('sends the question as JSON to the streaming endpoint', async () => {
    const fetchMock = stubFetch(sseResponse([`event: done\ndata: ${JSON.stringify(DONE)}\n\n`]))

    await streamChat({ question: 'How long?', document_ids: ['d1'] })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/chat/stream')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ question: 'How long?', document_ids: ['d1'] })
  })

  it('reports an error that happens during the answer', async () => {
    stubFetch(
      sseResponse([
        'event: delta\ndata: {"text":"The warranty "}\n\n',
        'event: error\ndata: {"status":502,"detail":"The answer was interrupted."}\n\n',
      ]),
    )
    const onDone = vi.fn()

    await expect(streamChat({ question: 'Q' }, { onDone })).rejects.toMatchObject({
      message: 'The answer was interrupted.',
      status: 502,
    })
    expect(onDone).not.toHaveBeenCalled()
  })

  it('reports an HTTP error that happens before the answer starts, with the server message', async () => {
    stubFetch(jsonResponse({ detail: 'Gemini is temporarily unavailable. Please try again in about 45 seconds.' }, 503))

    await expect(streamChat({ question: 'Q' })).rejects.toMatchObject({
      message: 'Gemini is temporarily unavailable. Please try again in about 45 seconds.',
      status: 503,
    })
  })

  it('uses a friendly default when the HTTP error has no readable message', async () => {
    stubFetch(new Response('<html>gateway</html>', { status: 504 }))

    await expect(streamChat({ question: 'Q' })).rejects.toMatchObject({ status: 504 })
  })

  it('reports an interrupted connection that never sent a done event', async () => {
    stubFetch(sseResponse(['event: delta\ndata: {"text":"Partial"}\n\n']))

    await expect(streamChat({ question: 'Q' })).rejects.toMatchObject({
      message: 'The answer was interrupted before it finished. Please try again.',
      status: 502,
    })
  })

  it('can be cancelled with an AbortSignal', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn().mockImplementation((url, options) => {
      return new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const pending = streamChat({ question: 'Q' }, {}, { signal: controller.signal })
    controller.abort()

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })
})
