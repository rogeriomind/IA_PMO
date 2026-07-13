import clsx from 'clsx'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const variants: Record<ButtonVariant, string> = {
  primary: 'border-[#6D3DF5] bg-[#6D3DF5] text-white shadow-sm hover:bg-[#5b2ee0]',
  secondary: 'border-[#D8C9FF] bg-white text-[#6D3DF5] hover:bg-[#F2EDFF]',
  ghost: 'border-transparent bg-transparent text-[#667085] hover:bg-[#F8F9FC] hover:text-[#171A24]',
  danger: 'border-red-200 bg-red-50 text-[#DC2626] hover:bg-red-100',
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
}

export function Button({ className, variant = 'secondary', ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={clsx(
        'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#6D3DF5] disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        className,
      )}
    />
  )
}
