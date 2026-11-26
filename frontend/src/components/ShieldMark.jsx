// Flat PG shield. A future 3D shield can replace this component without layout changes.
export default function ShieldMark({ size = 32, className = '' }) {
  return (
    <svg className={`shield-mark ${className}`} width={size} height={size * 1.12} viewBox="0 0 40 45" aria-hidden="true" focusable="false">
      <path d="M20 1.5 37 7.2v13.3c0 10.6-7 18.7-17 23-10-4.3-17-12.4-17-23V7.2z" fill="#2563eb" />
      <path d="M20 1.5 37 7.2v13.3c0 10.6-7 18.7-17 23z" fill="#1d4fd0" />
      <text x="20" y="27.5" textAnchor="middle" fill="#ffffff" fontFamily="Inter, Segoe UI, system-ui, sans-serif" fontSize="15" fontWeight="800" letterSpacing="-.4">PG</text>
    </svg>
  )
}
