/** Friendly placeholder shown when there is nothing to display yet. */
export default function EmptyState({ icon: Icon, title, description, children }) {
  return (
    <div className="animate-fade-up flex flex-col items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 px-6 py-10 text-center">
      {Icon && (
        <div className="brand-gradient mb-4 flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg shadow-indigo-200">
          <Icon size={26} aria-hidden="true" />
        </div>
      )}
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      {description && <p className="mt-2 max-w-md text-sm text-slate-500">{description}</p>}
      {children && <div className="mt-6 w-full">{children}</div>}
    </div>
  )
}
