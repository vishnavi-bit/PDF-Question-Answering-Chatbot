import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getErrorMessage } from '../services/api'
import { streamChat, streamRegenerate } from '../services/streamChat'
import { currentAnswerStyle } from './usePreferences'

/** A unique id for one question, so the server can recognise a repeated request. */
export function newRequestId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const isAbort = (error) => Boolean(error) && error.name === 'AbortError'

/** The saved answer, plus the verification summary the server sent with it (not stored in the database). */
function withVerification(data) {
  const verification = data.retrieval && data.retrieval.verification
  return verification ? { ...data.assistant_message, verification } : data.assistant_message
}

/**
 * Chat state for one conversation, with streamed answers.
 * - Loads saved messages when a conversation id is given.
 * - Streams the answer as it is written.
 * - Stop keeps the partial text (marked as not saved). Retry resends the last question.
 * - Regenerate replaces the last answer only when the new one succeeds.
 */
export function useChat({ conversationId = null, documentIds = [], topK = 5, onConversationCreated } = {}) {
  const [messages, setMessages] = useState([])
  const [streaming, setStreaming] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState('')
  const [lastQuestion, setLastQuestion] = useState('')
  const controllerRef = useRef(null)
  const busyRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    setError('')
    setLastQuestion('')
    if (!conversationId) {
      setMessages([])
      return undefined
    }
    setLoadingHistory(true)
    api
      .getConversation(conversationId)
      .then((data) => {
        if (!cancelled) setMessages(data.messages)
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'This conversation could not be loaded.'))
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false)
      })
    return () => {
      cancelled = true
    }
  }, [conversationId])

  // Stop a running answer when the chat is left (the server saves nothing for an unfinished answer).
  useEffect(() => () => controllerRef.current?.abort(), [])

  const patchMessage = useCallback((id, patch) => {
    setMessages((current) => current.map((message) => (message.id === id ? { ...message, ...patch } : message)))
  }, [])

  const send = useCallback(
    async (question) => {
      const text = (question || '').trim()
      if (!text || busyRef.current) return false
      busyRef.current = true
      const stamp = Date.now()
      const userTempId = `temp-user-${stamp}`
      const pendingId = `temp-assistant-${stamp}`
      setMessages((current) => [
        ...current,
        { id: userTempId, role: 'user', content: text, sources: [] },
        { id: pendingId, role: 'assistant', content: '', sources: [], pending: true },
      ])
      setError('')
      setLastQuestion(text)
      setStreaming(true)

      const controller = new AbortController()
      controllerRef.current = controller
      let received = ''
      try {
        const data = await streamChat(
          {
            question: text,
            conversation_id: conversationId,
            document_ids: documentIds,
            top_k: topK,
            answer_style: currentAnswerStyle(),
            client_request_id: newRequestId(),
          },
          {
            onDelta: (chunk) => {
              received += chunk
              patchMessage(pendingId, { content: received })
            },
          },
          { signal: controller.signal },
        )
        setMessages((current) => [
          ...current.filter((message) => message.id !== userTempId && message.id !== pendingId),
          data.user_message,
          withVerification(data),
        ])
        setLastQuestion('')
        if (!conversationId && onConversationCreated) onConversationCreated(data.conversation_id)
        return true
      } catch (err) {
        if (isAbort(err)) {
          patchMessage(pendingId, { pending: false, stopped: true, content: received })
          return false
        }
        setMessages((current) => current.filter((message) => message.id !== userTempId && message.id !== pendingId))
        setError(err && err.message ? err.message : 'The question could not be answered. Please try again.')
        return false
      } finally {
        controllerRef.current = null
        busyRef.current = false
        setStreaming(false)
      }
    },
    [conversationId, documentIds, topK, onConversationCreated, patchMessage],
  )

  const stop = useCallback(() => {
    controllerRef.current?.abort()
  }, [])

  const retry = useCallback(() => (lastQuestion ? send(lastQuestion) : Promise.resolve(false)), [lastQuestion, send])

  const lastSavedAssistant = [...messages].reverse().find((message) => message.role === 'assistant' && typeof message.id === 'number')

  const regenerate = useCallback(async () => {
    if (busyRef.current || !conversationId || !lastSavedAssistant) return false
    const original = lastSavedAssistant
    busyRef.current = true
    setStreaming(true)
    setError('')
    patchMessage(original.id, { content: '', pending: true, regenerating: true })

    const controller = new AbortController()
    controllerRef.current = controller
    let received = ''
    try {
      const data = await streamRegenerate(
        { conversation_id: conversationId, document_ids: documentIds, top_k: topK, answer_style: currentAnswerStyle() },
        {
          onDelta: (chunk) => {
            received += chunk
            patchMessage(original.id, { content: received })
          },
        },
        { signal: controller.signal },
      )
      setMessages((current) => current.map((message) => (message.id === original.id ? withVerification(data) : message)))
      return true
    } catch (err) {
      // The server keeps the old answer when a regenerate fails or is stopped, so show it again.
      setMessages((current) => current.map((message) => (message.id === original.id ? original : message)))
      if (!isAbort(err)) setError(err && err.message ? err.message : 'The answer could not be created again.')
      return false
    } finally {
      controllerRef.current = null
      busyRef.current = false
      setStreaming(false)
    }
  }, [conversationId, documentIds, topK, lastSavedAssistant, patchMessage])

  const setFeedback = useCallback(
    async (messageId, feedback) => {
      const previous = messages.find((message) => message.id === messageId)
      const previousValue = previous ? previous.feedback : null
      const nextValue = previousValue === feedback ? null : feedback // clicking again removes it
      patchMessage(messageId, { feedback: nextValue })
      try {
        await api.setMessageFeedback(messageId, nextValue)
      } catch (err) {
        patchMessage(messageId, { feedback: previousValue })
        setError(getErrorMessage(err, 'Feedback could not be saved.'))
      }
    },
    [messages, patchMessage],
  )

  return {
    messages,
    streaming,
    loading: streaming,
    loadingHistory,
    error,
    setError,
    lastQuestion,
    canRegenerate: Boolean(conversationId && lastSavedAssistant) && !streaming,
    send,
    stop,
    retry,
    regenerate,
    setFeedback,
  }
}
