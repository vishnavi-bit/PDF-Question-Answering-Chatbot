import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, FileText, MessageSquare, Sparkles } from 'lucide-react'
import { useAppState } from '../context/ChatContext'
import PDFUploader from '../components/PDFUploader'
import DocumentCard from '../components/DocumentCard'
import EmptyState from '../components/EmptyState'

/** Welcome page: upload PDFs, see their status, and start chatting. */
export default function Home() {
  const navigate = useNavigate()
  const { documents, documentsLoading, uploadFiles, uploading, removeDocument, selectOnly } = useAppState()
  const [uploadMessages, setUploadMessages] = useState([])

  const handleUpload = async (files) => {
    setUploadMessages([])
    const results = await uploadFiles(files)
    setUploadMessages(
      results.map((result) => ({
        id: result.document.id,
        text: `${result.document.original_filename}: ${result.message}`,
        ok: result.document.processing_status === 'ready',
      })),
    )
  }

  const handleDelete = async (document) => {
    if (!window.confirm(`Delete "${document.filename}"? Its stored file and search index entries will be removed.`)) return
    await removeDocument(document.id)
  }

  const handleAsk = (documentId) => {
    selectOnly(documentId)
    navigate('/chat')
  }

  const readyCount = documents.filter((doc) => doc.processing_status === 'ready').length
  const uploadProgress = uploading.active
    ? `Processing ${uploading.currentName} (${uploading.done + 1} of ${uploading.total})…`
    : null

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      <section className="animate-fade-up">
        <p className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
          <Sparkles size={13} aria-hidden="true" /> Retrieval-augmented answers
        </p>
        <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Chat with your <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">PDF documents</span>
        </h2>
        <p className="mt-3 max-w-2xl text-slate-600">
          Upload PDFs, ask questions in plain English, and get answers that point to the exact file and page they came from.
        </p>
      </section>

      <section aria-labelledby="upload-heading" className="space-y-3">
        <h3 id="upload-heading" className="text-sm font-semibold text-slate-900">
          1. Upload your PDFs
        </h3>
        <PDFUploader onFiles={handleUpload} disabled={uploading.active} progress={uploadProgress} />
        {uploadMessages.length > 0 && (
          <ul className="space-y-1 text-sm" aria-label="Upload results">
            {uploadMessages.map((item) => (
              <li key={item.id} className={`flex items-start gap-2 ${item.ok ? 'text-emerald-700' : 'text-amber-700'}`}>
                {item.ok && <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" />}
                <span>{item.text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="docs-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="docs-heading" className="text-sm font-semibold text-slate-900">
            2. Your documents {documents.length > 0 && <span className="font-normal text-slate-500">({readyCount} ready)</span>}
          </h3>
          <button
            type="button"
            onClick={() => navigate('/chat')}
            disabled={readyCount === 0}
            className="brand-gradient inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-200 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <MessageSquare size={16} aria-hidden="true" /> Start chatting
          </button>
        </div>

        {documentsLoading && documents.length === 0 && <p className="text-sm text-slate-500">Loading documents…</p>}

        {!documentsLoading && documents.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No documents yet"
            description="Upload a PDF above. Scanned PDFs without selectable text cannot be read yet, and you will see a note explaining why."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {documents.map((doc) => (
              <DocumentCard key={doc.id} document={doc} onDelete={handleDelete} onAsk={handleAsk} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
