import { Fragment } from 'react'

/** Render **bold** segments inside one line of text. */
function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={`${keyPrefix}-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <Fragment key={`${keyPrefix}-${index}`}>{part}</Fragment>
  })
}

/**
 * Turn plain answer text into simple formatted blocks.
 * Supports paragraphs, "- " / "* " bullets, "1. " numbered lists and **bold**.
 */
export function formatAnswer(text) {
  const lines = String(text || '').replace(/\r/g, '').split('\n')
  const blocks = []
  let paragraph = []
  let list = null

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'p', lines: paragraph })
      paragraph = []
    }
  }
  const flushList = () => {
    if (list) {
      blocks.push(list)
      list = null
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    const numbered = line.match(/^\d+[.)]\s+(.*)$/)

    if (!line) {
      flushParagraph()
      flushList()
    } else if (bullet) {
      flushParagraph()
      if (!list || list.type !== 'ul') {
        flushList()
        list = { type: 'ul', items: [] }
      }
      list.items.push(bullet[1])
    } else if (numbered) {
      flushParagraph()
      if (!list || list.type !== 'ol') {
        flushList()
        list = { type: 'ol', items: [] }
      }
      list.items.push(numbered[1])
    } else {
      flushList()
      paragraph.push(line)
    }
  }
  flushParagraph()
  flushList()
  return blocks
}

export function AnswerText({ text }) {
  const blocks = formatAnswer(text)
  return (
    <div className="space-y-3 text-[15px] leading-7 text-slate-800">
      {blocks.map((block, blockIndex) => {
        if (block.type === 'p') {
          return (
            <p key={`p-${blockIndex}`}>
              {block.lines.map((line, lineIndex) => (
                <Fragment key={`l-${blockIndex}-${lineIndex}`}>
                  {lineIndex > 0 && <br />}
                  {renderInline(line, `t-${blockIndex}-${lineIndex}`)}
                </Fragment>
              ))}
            </p>
          )
        }
        const ListTag = block.type === 'ol' ? 'ol' : 'ul'
        const listClass = block.type === 'ol' ? 'list-decimal' : 'list-disc'
        return (
          <ListTag key={`list-${blockIndex}`} className={`${listClass} space-y-1 pl-6`}>
            {block.items.map((item, itemIndex) => (
              <li key={`i-${blockIndex}-${itemIndex}`}>{renderInline(item, `li-${blockIndex}-${itemIndex}`)}</li>
            ))}
          </ListTag>
        )
      })}
    </div>
  )
}
