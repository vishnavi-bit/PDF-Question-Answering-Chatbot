import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'

/**
 * Renders an answer as Markdown with code highlighting.
 * Raw HTML in the answer is NOT rendered (react-markdown escapes it), and links open in a new tab.
 */
export default function Markdown({ text }) {
  return (
    <div className="md-body" data-testid="markdown">
      <ReactMarkdown
        rehypePlugins={[rehypeHighlight]}
        components={{
          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {text || ''}
      </ReactMarkdown>
    </div>
  )
}
