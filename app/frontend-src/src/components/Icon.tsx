import type { CSSProperties, ReactNode } from 'react'

export type IconName = 'overview' | 'analysis' | 'ask' | 'document' | 'search' | 'medication' | 'lab' | 'diagnosis' | 'review' | 'chevron' | 'send'

export function Icon({ name, className = '', style }: { name: IconName; className?: string; style?: CSSProperties }) {
  const paths: Record<IconName, ReactNode> = {
    overview: <><rect x="3" y="3" width="18" height="18" rx="4" /><path d="M3 10h18M10 10v11" /></>,
    analysis: <><path d="M3 12h4l3-7 4 14 3-7h4" /></>,
    ask: <><path d="M8 19H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-5l-6 3z" /><path d="M7 9h10M7 13h6" /></>,
    document: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M8 13h8M8 17h5" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
    medication: <><path d="m8 4 12 12a5 5 0 0 1-7 7L1 11a5 5 0 0 1 7-7z" transform="translate(1 -1)" /><path d="m8 16 8-8" /></>,
    lab: <><path d="M9 3h6M10 3v7l-6 9a1.3 1.3 0 0 0 1 2h14a1.3 1.3 0 0 0 1-2l-6-9V3M7 15h10" /></>,
    diagnosis: <><rect x="5" y="4" width="14" height="17" rx="3" /><path d="M9 4V2h6v2M9 11h6M12 8v6M9 17h6" /></>,
    review: <><path d="m8 12 3 3 5-6" /><path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6z" /></>,
    chevron: <path d="m9 5 7 7-7 7" />,
    send: <><path d="m3 3 18 9-18 9 4-9zM7 12h14" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={`ui-icon ${className}`} style={style}>{paths[name]}</svg>
}

export function BrandMark({ className = '' }: { className?: string }) {
  return <svg aria-hidden="true" viewBox="0 0 36 36" fill="none" className={`brand-mark ${className}`}><path d="M8 26 16 9a2.2 2.2 0 0 1 4 0l8 17M12 21h12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /><circle cx="18" cy="27" r="1.8" fill="currentColor" /></svg>
}

export function PatientAvatar({ name, className = '' }: { name: string; className?: string }) {
  const parts = name.trim().split(/\s+/)
  const initials = [parts[0]?.[0], parts.length > 1 ? parts.at(-1)?.[0] : ''].join('') || '?'
  return <span aria-hidden="true" className={`patient-avatar ${className}`}>{initials}</span>
}
