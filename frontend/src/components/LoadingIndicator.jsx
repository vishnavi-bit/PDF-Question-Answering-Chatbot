/** Animated dots shown while the answer is being prepared. */
export default function LoadingIndicator({ label = 'Searching your documents and writing an answer…' }) {
  return (
    <div role="status" aria-live="polite" className="animate-fade-up flex items-center gap-3 text-sm text-slate-500">
      <div className="flex items-center gap-1" aria-hidden="true">
        <span className="dot-bounce h-2 w-2 rounded-full bg-indigo-500" />
        <span className="dot-bounce h-2 w-2 rounded-full bg-violet-500" style={{ animationDelay: '0.15s' }} />
        <span className="dot-bounce h-2 w-2 rounded-full bg-indigo-400" style={{ animationDelay: '0.3s' }} />
      </div>
      <span>{label}</span>
    </div>
  )
}
