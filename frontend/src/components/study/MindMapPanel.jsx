import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Minus, Plus, RotateCcw } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'
import ExportButton from './ExportButton'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const MIN_ZOOM = 0.5
const MAX_ZOOM = 2
const PAN_STEP = 40

/** Keeps zoom inside the allowed range. */
export function clampZoom(value) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(value.toFixed(2))))
}

/** Mind maps: generate from the selected PDFs, zoom and pan, expand and collapse branches, save, rename, delete and export. */
export default function MindMapPanel({ documentIds }) {
  const [maps, setMaps] = useState([])
  const [current, setCurrent] = useState(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [collapsed, setCollapsed] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const dragRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const data = await api.listMindMaps()
      setMaps(data.mind_maps)
    } catch (err) {
      setError(getErrorMessage(err, 'Mind maps could not be loaded.'))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const resetView = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }

  const showMap = (map) => {
    setCurrent(map)
    setTitleDraft(map.title)
    setCollapsed({})
    resetView()
    setError('')
    setNotice('')
  }

  const generate = async () => {
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const map = await api.createMindMap({ document_ids: documentIds })
      showMap(map)
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The mind map could not be created.'))
    } finally {
      setLoading(false)
    }
  }

  const open = async (id) => {
    setError('')
    try {
      showMap(await api.getMindMap(id))
    } catch (err) {
      setError(getErrorMessage(err, 'This mind map could not be opened.'))
    }
  }

  const rename = async () => {
    setError('')
    try {
      const updated = await api.renameMindMap(current.id, titleDraft)
      setCurrent({ ...current, title: updated.title })
      setNotice('Title saved.')
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The title could not be saved.'))
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete this mind map? This cannot be undone.')) return
    try {
      await api.deleteMindMap(id)
      if (current && current.id === id) setCurrent(null)
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The mind map could not be deleted.'))
    }
  }

  const toggleBranch = (id) => setCollapsed((state) => ({ ...state, [id]: !state[id] }))

  const onPointerDown = (event) => {
    // Presses on buttons must reach them as normal clicks, so no drag starts there.
    if (event.target.closest('button, a, input, textarea, select')) return
    dragRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
  const onPointerMove = (event) => {
    if (!dragRef.current) return
    setPan({
      x: dragRef.current.panX + (event.clientX - dragRef.current.x),
      y: dragRef.current.panY + (event.clientY - dragRef.current.y),
    })
  }
  const onPointerUp = () => {
    dragRef.current = null
  }

  const onKeyDown = (event) => {
    const moves = { ArrowLeft: [-PAN_STEP, 0], ArrowRight: [PAN_STEP, 0], ArrowUp: [0, -PAN_STEP], ArrowDown: [0, PAN_STEP] }
    if (moves[event.key]) {
      event.preventDefault()
      const [dx, dy] = moves[event.key]
      setPan((value) => ({ x: value.x + dx, y: value.y + dy }))
    } else if (event.key === '+' || event.key === '=') {
      setZoom((value) => clampZoom(value + 0.25))
    } else if (event.key === '-') {
      setZoom((value) => clampZoom(value - 0.25))
    }
  }

  const tree = current ? current.tree : null

  return (
    <section aria-labelledby="mindmap-heading" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="mindmap-heading" className="text-lg font-semibold text-slate-900">Mind map</h2>
          <p className="text-sm text-slate-500">Main topics and subtopics from your PDFs. Every topic shows its source page.</p>
        </div>
        <button type="button" onClick={generate} disabled={loading}
          className="brand-gradient rounded-xl px-4 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-200 disabled:opacity-50">
          Create mind map
        </button>
      </div>

      {loading && <StudyLoading label="Building the mind map from your PDFs…" />}
      <StudyError message={error} />
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}

      {maps.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200" aria-label="Saved mind maps">
          {maps.map((map) => (
            <li key={map.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <span className="text-sm text-slate-800">{map.title} <span className="text-slate-500">({map.node_count} nodes)</span></span>
              <span className="flex gap-2">
                <button type="button" onClick={() => open(map.id)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700">Open</button>
                <button type="button" onClick={() => remove(map.id)}
                  className="rounded-lg border border-rose-300 px-3 py-1.5 text-sm text-rose-700">Delete</button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {tree && (
        <article className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex-1 text-sm text-slate-600">
              Title
              <input aria-label="Mind map title" value={titleDraft} maxLength={200} onChange={(e) => setTitleDraft(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
            <button type="button" onClick={rename} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Save title</button>
            <ExportButton kind="mind-map" itemId={current.id} label="Download PDF" />
          </div>

          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Map view controls">
            <button type="button" aria-label="Zoom in" onClick={() => setZoom((v) => clampZoom(v + 0.25))}
              className="rounded-lg border border-slate-300 p-2"><Plus size={16} aria-hidden="true" /></button>
            <button type="button" aria-label="Zoom out" onClick={() => setZoom((v) => clampZoom(v - 0.25))}
              className="rounded-lg border border-slate-300 p-2"><Minus size={16} aria-hidden="true" /></button>
            <button type="button" aria-label="Reset view" onClick={resetView}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"><RotateCcw size={14} aria-hidden="true" /> Reset view</button>
            <span className="text-sm text-slate-500" data-testid="zoom-level">{Math.round(zoom * 100)}%</span>
            <span className="text-xs text-slate-500">Drag to move. Arrow keys move, + and - zoom.</span>
          </div>

          <div
            role="application"
            aria-label="Mind map canvas"
            tabIndex={0}
            onKeyDown={onKeyDown}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            className="relative h-[460px] cursor-grab touch-none select-none overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-200 active:cursor-grabbing"
          >
            <div
              data-testid="map-canvas"
              style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: 'top left' }}
              className="flex items-start gap-8 p-6"
            >
              <div className="flex min-h-full items-center">
                <div className="max-w-[220px] rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-3 text-sm font-semibold text-white shadow-md">
                  {tree.centre}
                </div>
              </div>
              <ul className="flex flex-col gap-4 border-l-2 border-indigo-200 pl-6">
                {tree.branches.map((branch) => {
                  const isOpen = !collapsed[branch.id]
                  return (
                    <li key={branch.id} className="space-y-2">
                      <div className="flex items-start gap-2">
                        <button type="button" aria-expanded={isOpen} aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${branch.label}`}
                          onClick={(event) => { event.stopPropagation(); toggleBranch(branch.id) }}
                          className="mt-1 rounded p-0.5 text-indigo-700">
                          {isOpen ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
                        </button>
                        <div className="max-w-[240px] rounded-xl border border-indigo-200 bg-white px-3 py-2 text-sm font-semibold text-slate-900 shadow-sm">
                          {branch.label}
                          <StudyCitations sources={branch.sources} />
                        </div>
                      </div>
                      {isOpen && branch.children.length > 0 && (
                        <ul className="ml-6 space-y-2 border-l border-slate-300 pl-4">
                          {branch.children.map((child) => (
                            <li key={child.id} className="max-w-[240px] rounded-lg bg-white px-3 py-2 text-sm text-slate-700 shadow-sm">
                              {child.label}
                              <StudyCitations sources={child.sources} />
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </article>
      )}
    </section>
  )
}
