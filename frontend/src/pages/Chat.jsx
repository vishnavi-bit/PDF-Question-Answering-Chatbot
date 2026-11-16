import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Eraser } from 'lucide-react'
import { useAppState } from '../context/ChatContext'
import { useChat } from '../hooks/useChat'
import { api, getErrorMessage } from '../services/api'
import ChatWindow from '../components/ChatWindow'
import PDFViewer from '../components/PDFViewer'

/** Chat page: the conversation, streamed answers with citations, and the PDF viewer beside it. */
export default function Chat() {
  const navigate = useNavigate()
  const { conversationId: routeId } = useParams()
  const conversationId = routeId ? Number(routeId) : null
  const {
    documents,
    selectedDocumentIds,
    conversations,
    refreshConversations,
    uploadFiles,
    uploading,
    setError: setAppError,
  } = useAppState()
  const [viewer, setViewer] = useState(null) // { documentId, filename, page }
  const [clearing, setClearing] = useState(false)

  const handleConversationCreated = useCallback(
    (newId) => {
      refreshConversations()
      navigate(`/chat/${newId}`, { replace: true })
    },
    [navigate, refreshConversations],
  )

  const chat = useChat({
    conversationId: Number.isFinite(conversationId) ? conversationId : null,
    documentIds: selectedDocumentIds,
    topK: 5,
    onConversationCreated: handleConversationCreated,
  })

  const readyDocuments = documents.filter((doc) => doc.processing_status === 'ready')
  const scopeCount = selectedDocumentIds.length
  const scopeLabel =
    scopeCount > 0
      ? `Searching ${scopeCount} selected PDF${scopeCount > 1 ? 's' : ''}`
      : `Searching all ${readyDocuments.length} ready PDF${readyDocuments.length === 1 ? '' : 's'}`

  const title = useMemo(() => {
    if (!conversationId) return 'New chat'
    const match = conversations.find((conversation) => conversation.id === conversationId)
    return match ? match.title : 'Chat'
  }, [conversationId, conversations])

  const openSource = (source) => {
    setViewer({ documentId: source.document_id, filename: source.filename, page: source.page_number })
  }

  const clearChat = async () => {
    if (!conversationId) return
    if (!window.confirm('Clear this chat? All of its messages will be deleted.')) return
    setClearing(true)
    try {
      await api.deleteConversation(conversationId)
      await refreshConversations()
      setViewer(null)
      navigate('/chat')
    } catch (err) {
      setAppError(getErrorMessage(err, 'The chat could not be cleared.'))
    } finally {
      setClearing(false)
    }
  }

  const viewedDocument = viewer ? documents.find((doc) => doc.id === viewer.documentId) : null

  return (
    <div className="flex h-full min-h-0">
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2.5 sm:px-6">
          <h2 className="min-w-0 truncate text-sm font-semibold text-slate-900" title={title}>
            {title}
          </h2>
          <button
            type="button"
            onClick={clearChat}
            disabled={!conversationId || clearing || chat.streaming}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:text-slate-500 disabled:hover:bg-transparent"
          >
            <Eraser size={14} aria-hidden="true" /> {clearing ? 'Clearing…' : 'Clear chat'}
          </button>
        </header>

        <div className="min-h-0 flex-1">
          <ChatWindow
            messages={chat.messages}
            streaming={chat.streaming}
            loadingHistory={chat.loadingHistory}
            error={chat.error}
            onSend={chat.send}
            onStop={chat.stop}
            onRetry={chat.lastQuestion ? chat.retry : undefined}
            onRegenerate={chat.regenerate}
            canRegenerate={chat.canRegenerate}
            onFeedback={chat.setFeedback}
            onOpenSource={openSource}
            documents={documents}
            hasDocuments={readyDocuments.length > 0}
            scopeLabel={scopeLabel}
            onAttach={uploadFiles}
            uploading={uploading.active}
          />
        </div>
      </section>

      {viewer && (
        <div className="fixed inset-0 z-50 flex flex-col bg-white lg:static lg:z-auto lg:w-[46%] lg:max-w-[720px] lg:min-w-[360px]">
          <PDFViewer
            documentId={viewer.documentId}
            filename={viewer.filename}
            page={viewer.page}
            pageCount={viewedDocument ? viewedDocument.page_count : null}
            onClose={() => setViewer(null)}
          />
        </div>
      )}
    </div>
  )
}
