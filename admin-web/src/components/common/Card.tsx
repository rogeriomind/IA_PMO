import clsx from 'clsx'

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <section className={clsx('rounded-lg border border-[#E4E7EC] bg-white shadow-sm', className)}>{children}</section>
}
