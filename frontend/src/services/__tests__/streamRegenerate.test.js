import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamRegenerate } from '../streamChat'

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

afterEach(() => vi.unstubAllGlobals())

describe('streamRegenerate', () => {
  it('posts to the regenerate endpoint and streams the new answer', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        'event: delta\ndata: {"text":"A new answer."}\n\n',
        'event: done\ndata: {"conversation_id":4,"assistant_message":{"id":8,"content":"A new answer."}}\n\n',
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)
    const deltas = []

    const result = await streamRegenerate({ conversation_id: 4 }, { onDelta: (text) => deltas.push(text) })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/chat/regenerate')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ conversation_id: 4 })
    expect(deltas).toEqual(['A new answer.'])
    expect(result.assistant_message.id).toBe(8)
  })

  it('reports a 404 for an unknown conversation with the server message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Conversation not found.' }), { status: 404 })),
    )
    await expect(streamRegenerate({ conversation_id: 99 })).rejects.toMatchObject({ message: 'Conversation not found.', status: 404 })
  })

  it('reports a failure during regeneration and does not claim success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse(['event: error\ndata: {"status":504,"detail":"Gemini did not finish the answer in time."}\n\n']),
      ),
    )
    const onDone = vi.fn()
    await expect(streamRegenerate({ conversation_id: 4 }, { onDone })).rejects.toMatchObject({ status: 504 })
    expect(onDone).not.toHaveBeenCalled()
  })
})
