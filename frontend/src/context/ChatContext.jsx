import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getErrorMessage } from '../services/api'

export const ChatContext = createContext(null)

/**
 * Shared app state: uploaded documents, which documents are selected for
 * questions, upload progress and the conversation list shown in the sidebar.
 */
export function ChatProvider({ children }) {
  const [documents, setDocuments] = useState([])
  const [documentsLoading, setDocumentsLoading] = useState(false)
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])
  const [conversations, setConversations] = useState([])
  const [uploading, setUploading] = useState({ active: false, done: 0, total: 0, currentName: '' })
  const [error, setError] = useState('')

  const refreshDocuments = useCallback(async () => {
    setDocumentsLoading(true)
    try {
      const data = await api.listDocuments()
      setDocuments(data.documents)
      // Forget selections of documents that no longer exist or are not ready.
      const readyIds = new Set(data.documents.filter((d) => d.processing_status === 'ready').map((d) => d.id))
      setSelectedDocumentIds((current) => current.filter((id) => readyIds.has(id)))
    } catch (err) {
      setError(getErrorMessage(err, 'Could not load your documents.'))
    } finally {
      setDocumentsLoading(false)
    }
  }, [])

  const refreshConversations = useCallback(async () => {
    try {
      const data = await api.listConversations()
      setConversations(data.conversations)
    } catch (err) {
      setError(getErrorMessage(err, 'Could not load your conversations.'))
    }
  }, [])

  useEffect(() => {
    refreshDocuments()
    refreshConversations()
  }, [refreshDocuments, refreshConversations])

  const toggleDocument = useCallback((documentId) => {
    setSelectedDocumentIds((current) =>
      current.includes(documentId) ? current.filter((id) => id !== documentId) : [...current, documentId],
    )
  }, [])

  const selectOnly = useCallback((documentId) => {
    setSelectedDocumentIds([documentId])
  }, [])

  /** Upload files one by one. Returns the server responses that succeeded. */
  const uploadFiles = useCallback(
    async (fileList) => {
      const files = Array.from(fileList || [])
      if (files.length === 0) return []

      setError('')
      setUploading({ active: true, done: 0, total: files.length, currentName: files[0].name })
      const results = []
      const failures = []

      for (let index = 0; index < files.length; index += 1) {
        const file = files[index]
        setUploading((current) => ({ ...current, currentName: file.name }))
        try {
          results.push(await api.uploadDocument(file))
        } catch (err) {
          failures.push(`${file.name}: ${getErrorMessage(err, 'upload failed')}`)
        }
        setUploading((current) => ({ ...current, done: index + 1 }))
      }

      setUploading({ active: false, done: 0, total: 0, currentName: '' })
      await refreshDocuments()
      if (failures.length > 0) setError(failures.join(' '))
      return results
    },
    [refreshDocuments],
  )

  const removeDocument = useCallback(
    async (documentId) => {
      setError('')
      try {
        await api.deleteDocument(documentId)
        setSelectedDocumentIds((current) => current.filter((id) => id !== documentId))
        await refreshDocuments()
        return true
      } catch (err) {
        setError(getErrorMessage(err, 'The document could not be deleted.'))
        return false
      }
    },
    [refreshDocuments],
  )

  const value = useMemo(
    () => ({
      documents,
      documentsLoading,
      refreshDocuments,
      selectedDocumentIds,
      setSelectedDocumentIds,
      toggleDocument,
      selectOnly,
      uploadFiles,
      uploading,
      removeDocument,
      conversations,
      refreshConversations,
      error,
      setError,
    }),
    [
      documents,
      documentsLoading,
      refreshDocuments,
      selectedDocumentIds,
      toggleDocument,
      selectOnly,
      uploadFiles,
      uploading,
      removeDocument,
      conversations,
      refreshConversations,
      error,
    ],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useAppState() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useAppState must be used inside ChatProvider')
  }
  return context
}
