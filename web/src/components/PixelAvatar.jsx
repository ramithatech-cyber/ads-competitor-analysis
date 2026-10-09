import { memo } from 'react'

const SKIN = ['#F6D3B3', '#E8B48F', '#D29A6E', '#B87A50', '#8F5A3A', '#6B4029']
const HAIR = ['#141413', '#2B1D14', '#4A2E1C', '#7A4B2A', '#9C9A92', '#C8A165']
const SHIRT = ['#D97757', '#C15F3C', '#141413', '#5B7FA6', '#7A9E7E', '#B8A27A', '#8C6BB1', '#E3B23C', '#3D3D3A']

function rng(seed) {
  let s = 0
  for (const ch of String(seed)) s = (s * 31 + ch.charCodeAt(0)) >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

function build(seed, gender) {
  const r = rng(seed)
  const pick = (a) => a[Math.floor(r() * a.length)]
  const skin = pick(SKIN), hair = pick(HAIR), shirt = pick(SHIRT)
  const female = gender === 'female' || (gender == null && r() > 0.5)
  const style = female ? pick(['long', 'long', 'bun', 'short']) : pick(['short', 'short', 'spiky', 'bald'])
  const glasses = r() > 0.72
  const beard = !female && r() > 0.6
  const px = new Map()
  const set = (x, y, c) => px.set(`${x},${y}`, c)

  if (style === 'long') for (let y = 2; y <= 9; y++) { set(2, y, hair); set(9, y, hair) }
  for (let y = 3; y <= 8; y++) for (let x = 3; x <= 8; x++) set(x, y, skin)
  set(2, 5, skin); set(9, 5, skin)
  if (style !== 'bald') {
    for (let x = 3; x <= 8; x++) { set(x, 1, hair); set(x, 2, hair) }
    set(3, 3, hair); set(8, 3, hair)
  } else {
    for (let x = 4; x <= 7; x++) set(x, 2, skin)
    set(3, 3, hair); set(8, 3, hair)
  }
  if (style === 'bun') { set(5, 0, hair); set(6, 0, hair) }
  if (style === 'spiky') { set(3, 0, hair); set(5, 0, hair); set(7, 0, hair) }
  if (glasses) { for (const x of [3, 4, 5, 6, 7, 8]) set(x, 5, '#141413'); set(4, 5, '#DCEBF5'); set(7, 5, '#DCEBF5') }
  else { set(4, 5, '#141413'); set(7, 5, '#141413') }
  set(5, 7, '#8E3B2E'); set(6, 7, '#8E3B2E')
  if (beard) { for (let x = 3; x <= 8; x++) set(x, 8, hair); set(3, 7, hair); set(8, 7, hair) }
  set(5, 9, skin); set(6, 9, skin)
  for (const x of [3, 4, 7, 8]) set(x, 9, shirt)
  for (let y = 10; y <= 11; y++) for (let x = 2; x <= 9; x++) set(x, y, shirt)
  return [...px.entries()].map(([k, c]) => { const [x, y] = k.split(',').map(Number); return { x, y, c } })
}

export default memo(function PixelAvatar({ seed, gender, size = 40 }) {
  const pixels = build(seed, gender)
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" shapeRendering="crispEdges" aria-hidden="true">
      {pixels.map((p) => <rect key={`${p.x}-${p.y}`} x={p.x} y={p.y} width="1.02" height="1.02" fill={p.c} />)}
    </svg>
  )
})
