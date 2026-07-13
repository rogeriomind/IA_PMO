export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        {eyebrow ? (
          <div className="mb-3 inline-flex items-center rounded-md bg-[#6D3DF5] px-3 py-1.5 text-sm font-bold text-white shadow-sm">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="text-2xl font-bold text-[#171A24] md:text-3xl">{title}</h1>
        {description ? <p className="mt-1 text-sm text-[#667085] md:text-base">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
    </div>
  )
}
