import SourceReference from '../SourceReference'
import { api } from '../../services/api'

/** Opens the cited PDF at the cited page (the browser PDF viewer supports #page=N). */
export function openStudySource(source) {
  const url = `${api.documentFileUrl(source.document_id)}#page=${source.page_number}`
  window.open(url, '_blank', 'noopener,noreferrer')
}

/** Citation chips for generated study items. Only grounded sources are shown. */
export default function StudyCitations({ sources = [] }) {
  if (!sources.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2" aria-label="Sources">
      {sources.map((source) => (
        <SourceReference
          key={`${source.document_id}-${source.page_number}-${source.source_id}`}
          source={{ ...source, relevant_text: `Open ${source.filename} at page ${source.page_number}` }}
          onOpen={openStudySource}
        />
      ))}
    </div>
  )
}
