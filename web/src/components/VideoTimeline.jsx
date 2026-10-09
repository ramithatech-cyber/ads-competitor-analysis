import { useMemo, useRef, useState } from 'react'

const KIND = {
  strength: { icon: '✓', label: 'Keep', cls: 'k-good', color: '#3BA55C' },
  weakness: { icon: '✗', label: 'Weak', cls: 'k-bad', color: '#E5484D' },
  fix: { icon: '→', label: 'Fix', cls: 'k-fix', color: '#D97757' },
}
const W = 600, PLOT_H = 128, PAD_L = 30, PAD_R = 8, LANE = 19, BOT = 18

// % of buyers still watching at second s (watch_seconds = when they scrolled away)
const retention = (rs, s) => (rs.length ? (100 * rs.filter((r) => r.watch_seconds >= s).length) / rs.length : 0)

/* One panel for video ads: player + drop-off curve + time-coded pins, all on the same time axis. */
export default function VideoTimeline({ job, anns }) {
  const ad = job.feed?.find((a) => a.is_user)
  const frames = job.user_frames || []
  const meta = job.video_meta || {}
  const dur = meta.duration || frames.at(-1)?.t || 1
  const video = useRef(null)
  const [now, setNow] = useState(0)
  const [active, setActive] = useState(null)
  const [hover, setHover] = useState(null)
  const [ratio, setRatio] = useState(1)

  const mine = job.reactions?.find((r) => r.ad_id === 'you')?.reactions || []
  const rivals = (job.reactions || []).filter((r) => r.ad_id !== 'you' && r.reactions?.length)
  const x = (t) => PAD_L + ((W - PAD_L - PAD_R) * Math.min(t, dur)) / dur
  // Pins at (almost) the same moment stack upwards in lanes instead of overlapping.
  const lanes = useMemo(() => {
    const placed = []
    return Object.fromEntries(anns.map((a) => {
      let lane = 0
      while (placed.some((p) => p.lane === lane && Math.abs(x(p.t) - x(a.t)) < 18)) lane++
      placed.push({ t: a.t, lane })
      return [a.n, lane]
    }))
  }, [anns, dur])
  const nLanes = Math.max(1, ...Object.values(lanes).map((l) => l + 1))
  const TOP = nLanes * LANE + 6, H = TOP + PLOT_H
  const cyOf = (a) => TOP - 13 - lanes[a.n] * LANE
  const y = (p) => TOP + ((H - TOP - BOT) * (100 - p)) / 100

  const { you, rival, steps } = useMemo(() => {
    const steps = Array.from({ length: Math.ceil(dur * 4) + 1 }, (_, i) => Math.min(dur, i / 4))
    const you = steps.map((s) => [s, s === 0 ? 100 : retention(mine, s)])
    const rival = rivals.length ? steps.map((s) => [s, s === 0 ? 100 : rivals.reduce((a, r) => a + retention(r.reactions, s), 0) / rivals.length]) : null
    return { you, rival, steps }
  }, [job.reactions, dur])

  const path = (pts) => pts.map(([s, p], i) => `${i ? 'L' : 'M'}${x(s).toFixed(1)},${y(p).toFixed(1)}`).join(' ')
  const area = `${path(you)} L${x(dur)},${y(0)} L${x(0)},${y(0)} Z`

  const seek = (a) => {
    setActive(a.n)
    if (video.current) { video.current.currentTime = a.t; video.current.pause() }
    setNow(a.t)
  }
  const act = anns.find((a) => a.n === active)
  const seg = (meta.segments || []).find((g) => now >= g.start && now < g.end)

  // hover readout: who is still watching at that second and why people left there
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    const t = Math.max(0, Math.min(dur, (((e.clientX - r.left) / r.width) * W - PAD_L) / ((W - PAD_L - PAD_R) / dur)))
    const left = mine.filter((m) => m.watch_seconds >= Math.floor(t) && m.watch_seconds < Math.floor(t) + 1 && m.watch_seconds < dur)
    setHover({ t, pct: retention(mine, t), left })
  }
  const pById = Object.fromEntries((job.personas || []).map((p) => [p.id, p]))
  const finished = mine.filter((m) => m.watch_seconds >= dur - 0.05).length

  return (
    <div className="panel vtl">
      <div className="vtl-head">
        <div className="eyebrow">Video timeline · where buyers leave, and why</div>
        <div className="vtl-legend">
          {Object.values(KIND).map((k) => <span key={k.cls} className={`kchip ${k.cls}`}>{k.icon} {k.label}</span>)}
          <span className="lg-line you" /> You<span className="lg-line rival" /> Rival ads avg
          <span className="src-tag sim">Simulation</span>
        </div>
      </div>
      <div className="vtl-body">
        <div className="vtl-left">
        <div className="vtl-player" style={{ aspectRatio: ratio }}>
          <video ref={video} src={ad?.video} poster={ad?.image || undefined} controls playsInline
            onLoadedMetadata={(e) => e.target.videoWidth && setRatio(e.target.videoWidth / e.target.videoHeight)}
            onTimeUpdate={(e) => setNow(e.target.currentTime)} onPlay={() => setActive(null)} />
          {act?.box && (
            <div className={`vtl-box ${KIND[act.kind]?.cls}`} style={{ left: `${act.box.x * 100}%`, top: `${act.box.y * 100}%`, width: `${act.box.w * 100}%`, height: `${act.box.h * 100}%` }}>
              <span className="pin">{act.n}</span>
            </div>
          )}
        </div>
          <div className="vtl-sub">{seg ? <>🎙 {seg.text}</> : <span className="muted">🎙 voiceover appears here as it plays</span>}</div>
          <div className="vtl-stats">
            <span><b>{Math.round(retention(mine, Math.min(3, dur)))}%</b> still watching at 3s</span>
            <span><b>{finished}/30</b> watched to the end</span>
            {rival && <span><b>{Math.round(rival.find(([s]) => s >= Math.min(3, dur))?.[1] ?? 0)}%</b> rival ads avg at 3s</span>}
          </div>
        </div>

        <div className="vtl-main">
          <div className="vtl-chart" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
            <svg viewBox={`0 0 ${W} ${H}`} width="100%">
              {[0, 50, 100].map((p) => (
                <g key={p}><line x1={PAD_L} x2={W - PAD_R} y1={y(p)} y2={y(p)} stroke="#ECEAE2" />
                  <text x={PAD_L - 4} y={y(p) + 3} fontSize="9" textAnchor="end" fill="#73726C">{p}%</text></g>
              ))}
              <path d={area} fill="#D97757" fillOpacity=".16" />
              <path d={path(you)} fill="none" stroke="#D97757" strokeWidth="2.2" />
              {rival && <path d={path(rival)} fill="none" stroke="#141413" strokeWidth="1.4" strokeDasharray="4 3" />}
              <line x1={x(now)} x2={x(now)} y1={TOP - 6} y2={H - BOT} stroke="#141413" strokeWidth="1" />
              {anns.map((a) => {
                const k = KIND[a.kind] || KIND.fix
                return (
                  <g key={a.n} className="vtl-pin" onClick={() => seek(a)} onMouseEnter={() => setActive(a.n)}>
                    <line x1={x(a.t)} x2={x(a.t)} y1={cyOf(a) + 8} y2={H - BOT} stroke={k.color} strokeDasharray="2 2" opacity={active === a.n ? 1 : 0.45} />
                    <circle cx={x(a.t)} cy={cyOf(a)} r={active === a.n ? 9 : 8} fill={k.color} stroke="#fff" strokeWidth="1.5" />
                    <text x={x(a.t)} y={cyOf(a) + 3.5} fontSize="9.5" fontWeight="800" fill="#fff" textAnchor="middle">{a.n}</text>
                  </g>
                )
              })}
              {steps.filter((s) => Number.isInteger(s) && (dur <= 20 || s % 5 === 0)).map((s) => (
                <text key={s} x={x(s)} y={H - 5} fontSize="9" textAnchor="middle" fill="#73726C">{s}s</text>
              ))}
              {hover && <circle cx={x(hover.t)} cy={y(hover.pct)} r="4" fill="#D97757" stroke="#fff" strokeWidth="1.5" />}
            </svg>
            {hover && (
              <div className="vtl-tip" style={{ left: `${(x(hover.t) / W) * 100}%`, top: `${(TOP / H) * 100}%` }}>
                <b>{hover.t.toFixed(1)}s · {Math.round(hover.pct)}% still watching</b>
                {hover.left.slice(0, 3).map((m) => <div key={m.id}>{pById[m.id]?.role}: “{m.reason}”</div>)}
                {!hover.left.length && <div className="muted">nobody left in this second</div>}
              </div>
            )}
          </div>
          <div className="vtl-frames" style={{ paddingLeft: `${(PAD_L / W) * 100}%`, paddingRight: `${(PAD_R / W) * 100}%` }}>
            {frames.map((f, i) => (
              <button key={i} onClick={() => seek({ n: null, t: f.t })} title={`${f.t}s`}><img src={f.src} alt="" /><small>{f.t}s</small></button>
            ))}
          </div>
        </div>
      </div>
      <div className="vtl-list">
            {anns.map((a) => {
              const k = KIND[a.kind] || KIND.fix
              return (
                <button key={a.n} className={`vtl-item ${k.cls} ${active === a.n ? 'on' : ''}`} onClick={() => seek(a)} onMouseEnter={() => setActive(a.n)}>
                  <span className="pin static">{a.n}</span>
                  <span><b>{a.t}s · {k.icon} {a.label}</b><small>{a.quote ? `“${a.quote}” · ` : ''}{a.note}</small></span>
                </button>
              )
            })}
      </div>
    </div>
  )
}
