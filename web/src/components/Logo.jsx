// Spyra mark: a spyglass lens with crosshairs in a brutalist block with a hard offset shadow.
export function LogoMark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="5" y="5" width="26" height="26" fill="#111" />
      <rect x="1.5" y="1.5" width="26" height="26" fill="#FF5C39" stroke="#111" strokeWidth="2.5" />
      <path d="M14.5 4.5v5M14.5 19.5v5M4.5 14.5h5M19.5 14.5h5" stroke="#111" strokeWidth="2.5" />
      <circle cx="14.5" cy="14.5" r="6" fill="#fff" stroke="#111" strokeWidth="2.5" />
      <circle cx="14.5" cy="14.5" r="2.4" fill="#111" />
    </svg>
  )
}

export default function Logo({ size = 28 }) {
  return (
    <span className="logo-lockup">
      <LogoMark size={size} />
      <span>Spyra</span>
    </span>
  )
}
