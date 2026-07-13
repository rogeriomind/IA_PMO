import clsx from 'clsx'

type BadgeTone = 'neutral' | 'purple' | 'green' | 'yellow' | 'red' | 'blue'

const tones: Record<BadgeTone, string> = {
  neutral: 'border-[#E4E7EC] bg-white text-[#667085]',
  purple: 'border-[#D8C9FF] bg-[#F2EDFF] text-[#6D3DF5]',
  green: 'border-green-200 bg-green-50 text-[#16A34A]',
  yellow: 'border-amber-200 bg-amber-50 text-[#D97706]',
  red: 'border-red-200 bg-red-50 text-[#DC2626]',
  blue: 'border-blue-200 bg-blue-50 text-[#2563EB]',
}

export function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: BadgeTone }) {
  return (
    <span className={clsx('inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold', tones[tone])}>
      {children}
    </span>
  )
}
