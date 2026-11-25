import './Seal.css'

/** 朱印：四象智投的标志性符号，用于“已封存”“已揭晓”等时刻。ghost 为待盖章状态。 */
export default function Seal({ children, size = 64, ghost = false, stamp = false, className = '' }: {
  children: React.ReactNode; size?: number; ghost?: boolean; stamp?: boolean; className?: string
}) {
  return (
    <span className={`seal ${ghost ? 'ghost' : ''} ${stamp ? 'stamp' : ''} ${className}`} style={{ '--size': `${size}px` } as React.CSSProperties}>
      {children}
    </span>
  )
}
