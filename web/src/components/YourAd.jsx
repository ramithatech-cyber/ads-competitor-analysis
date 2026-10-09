import { useState } from 'react'
import VideoTimeline from './VideoTimeline.jsx'

const KIND = {
  strength: { icon: '✓', label: 'Keep', cls: 'k-good' },
  weakness: { icon: '✗', label: 'Weak', cls: 'k-bad' },
  fix: { icon: '→', label: 'Fix', cls: 'k-fix' },
}
const AREA_ICON = { Hook: '🪝', Offer: '🏷️', Visual: '🖼️', Copy: '✍️', CTA: '👆', 'Social proof': '⭐', Trust: '🛡️', Audience: '🎯', Format: '🎞️' }
const DOTS = { high: 3, medium: 2, low: 1 }

function Gauge({ value, max = 10, label, accent = true, size = 120 }) {
  const pct = Math.max(0, Math.min(1, (value || 0) / max))
  const r = 46, c = Math.PI * r
  return (
    <div className="gauge" style={{ width: size }}>
      <svg viewBox="0 0 110 64" width={size}>
        <path d="M9 58 A46 46 0 0 1 101 58" fill="none" stroke="#EEECE4" strokeWidth="10" strokeLinecap="round" />
        <path d="M9 58 A46 46 0 0 1 101 58" fill="none" stroke={accent ? '#D97757' : '#141413'} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`} style={{ transition: 'stroke-dasharray 1s ease' }} />
        <text x="55" y="54" textAnchor="middle" className="gauge-num">{value ?? '–'}</text>
      </svg>
      <div className="gauge-label">{label}</div>
    </div>
  )
}

function Bar({ label, value, max = 10, me, sub }) {
  return (
    <div className={`hbar ${me ? 'me' : ''}`}>
      <span className="hbar-label" title={sub}>{label}</span>
      <span className="hbar-track"><span style={{ width: `${(100 * (value || 0)) / max}%` }} /></span>
      <span className="hbar-val">{value}</span>
    </div>
  )
}

function Highlighted({ text, anns, active, setActive }) {
  // Wrap each annotation quote found in the text with a numbered highlight.
  const spans = []
  anns.forEach((a) => {
    if (!a.quote) return
    const i = text.toLowerCase().indexOf(a.quote.toLowerCase())
    if (i >= 0 && !spans.some((s) => i < s.end && i + a.quote.length > s.start)) spans.push({ start: i, end: i + a.quote.length, a })
  })
  spans.sort((x, y) => x.start - y.start)
  const out = []; let pos = 0
  spans.forEach((s) => {
    if (s.start > pos) out.push(text.slice(pos, s.start))
    out.push(
      <mark key={s.a.n} className={`${KIND[s.a.kind]?.cls} ${active === s.a.n ? 'on' : ''}`} onMouseEnter={() => setActive(s.a.n)} onMouseLeave={() => setActive(null)}>
        {text.slice(s.start, s.end)}<sup>{s.a.n}</sup>
      </mark>,
    )
    pos = s.end
  })
  out.push(text.slice(pos))
  return <p className="ad-text">{out}</p>
}

function AnnotatedCreative({ ad, anns, hasImage, active, setActive }) {
  if (hasImage && ad?.image) {
    const act = anns.find((a) => a.n === active && a.box)
    const below = act && act.box.y + act.box.h < 0.7
    return (
      <div className="annot">
        <div className={`annot-clip ${act ? 'dim' : ''}`}>
          <img src={ad.image} alt="Your ad" />
          {anns.filter((a) => a.box).map((a) => {
            const b = a.box, k = KIND[a.kind] || KIND.fix
            return (
              <div key={a.n} className={`annot-box ${k.cls} ${active === a.n ? 'on' : ''}`}
                style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}
                onMouseEnter={() => setActive(a.n)} onMouseLeave={() => setActive(null)}>
                <span className="pin">{a.n}</span>
              </div>
            )
          })}
        </div>
        {act && (() => {
          const k = KIND[act.kind] || KIND.fix
          const cx = Math.min(0.78, Math.max(0.22, act.box.x + act.box.w / 2))
          const top = below ? act.box.y + act.box.h / 2 : act.box.y + act.box.h / 2
          return (
            <div className={`pin-card ${k.cls} ${below ? 'below' : 'above'}`} style={{ left: `${cx * 100}%`, top: `${top * 100}%` }}>
              <span className="pc-kind">{k.icon} {k.label}</span>
              <b>{act.label}</b>
              <p>{act.note}</p>
            </div>
          )
        })()}
      </div>
    )
  }
  return (
    <div className="annot text-ad">
      <div className="text-ad-head"><span className="pp">{(ad?.advertiser || 'Y')[0]}</span><b>{ad?.advertiser}</b><small>Sponsored</small></div>
      <Highlighted text={ad?.body || ''} anns={anns} active={active} setActive={setActive} />
    </div>
  )
}

const METRIC_ICON = { 'Scroll-stopping': '🛑', Clarity: '🔍', Specificity: '🎯', Emotion: '❤️', Urgency: '⏱️' }
const grade = (v) => (v >= 8 ? ['Strong', 'g-strong'] : v >= 5 ? ['OK', 'g-ok'] : ['Weak', 'g-weak'])

function HookCheck({ h }) {
  const score = h.score || 0
  const r = 52, c = 2 * Math.PI * r
  const [word, cls] = grade(score)
  return (
    <section className="hook-hero">
      <div className="hh-glow" />
      <div className="hh-left">
        <div className="hh-eyebrow"><span className="hh-dot" />Hook check · first 3 seconds</div>
        <blockquote className="hh-quote"><span className="hh-mark">“</span>{h.text}<span className="hh-mark">”</span></blockquote>
        <div className="hh-tags">
          <span className="hh-type">🪝 {h.type}</span>
          {h.verdict && <span className="hh-verdict">{h.verdict}</span>}
        </div>
        <div className="hh-chips">
          {(h.works || []).map((x) => <span key={x} className="hh-chip good">✓ {x}</span>)}
          {(h.fails || []).map((x) => <span key={x} className="hh-chip bad">✗ {x}</span>)}
        </div>
      </div>
      <div className="hh-right">
        <div className="hh-ring">
          <svg viewBox="0 0 120 120" width="132" height="132">
            <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="10" />
            <circle cx="60" cy="60" r={r} fill="none" stroke="url(#hhg)" strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${(c * score) / 10} ${c}`} transform="rotate(-90 60 60)" className="hh-ring-arc" />
            <defs><linearGradient id="hhg" x1="0" x2="1"><stop offset="0" stopColor="#F4CDBD" /><stop offset="1" stopColor="#D97757" /></linearGradient></defs>
          </svg>
          <div className="hh-ring-num"><b>{score}</b><small>/10</small><span className={`hh-grade ${cls}`}>{word}</span></div>
        </div>
        <div className="hh-metrics">
          {Object.entries(h.metrics || {}).map(([k, v], row) => {
            const [w, gc] = grade(v)
            return (
              <div key={k} className="hh-metric">
                <span className="hh-mi">{METRIC_ICON[k] || '•'}</span>
                <span className="hh-ml">{k}</span>
                <span className="hh-blocks">
                  {Array.from({ length: 10 }, (_, i) => (
                    <i key={i} className={i < v ? `on ${gc}` : ''} style={{ animationDelay: `${row * 0.12 + i * 0.04}s` }} />
                  ))}
                </span>
                <span className={`hh-mv ${gc}`}>{v} · {w}</span>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

const IMPACT_ORDER = { high: 0, medium: 1, low: 2 }
// Spread cards over evenly filled rows (max 5 per row) so no card sits alone: 6 -> 3+3, 7 -> 4+3, 8 -> 4+4.
const balancedCols = (n, max = 5) => Math.ceil(n / Math.ceil(n / max)) || 1

function FixBoard({ items, sc }) {
  const [flipped, setFlipped] = useState(null)
  const [done, setDone] = useState(() => new Set())
  const sorted = items.map((it, i) => ({ ...it, key: i })).sort((a, b) => (IMPACT_ORDER[a.impact] ?? 1) - (IMPACT_ORDER[b.impact] ?? 1))
  const weight = (it) => DOTS[it.impact] || 1
  const total = sorted.reduce((s, it) => s + weight(it), 0) || 1
  const gained = sorted.filter((it) => done.has(it.key)).reduce((s, it) => s + weight(it), 0)
  const before = sc.before ?? 0, after = sc.after_estimate ?? before
  const projected = Math.round(before + ((after - before) * gained) / total)
  const toggleDone = (k) => setDone((d) => { const n = new Set(d); n.has(k) ? n.delete(k) : n.add(k); return n })

  return (
    <div className="panel fixboard">
      <div className="fb-head">
        <div>
          <div className="eyebrow">Fix board · flip a card, tick it off</div>
          <h3 className="fb-title">{sorted.length} moves to a stronger ad</h3>
        </div>
        <div className="fb-score">
          <div className="fb-track"><span style={{ width: `${(gained / total) * 100}%` }} /></div>
          <div className="fb-nums">
            <span><b>{done.size}</b>/{sorted.length} fixed</span>
            <span>Ad score <b>{before}</b> → <b className="clay">{projected}</b><small> / {after} max (est.)</small></span>
          </div>
        </div>
      </div>
      <div className="fb-grid" style={{ '--cols': balancedCols(sorted.length) }}>
        {sorted.map((it, rank) => {
          const isDone = done.has(it.key)
          return (
            <div key={it.key} className={`fcard ${flipped === it.key ? 'flipped' : ''} ${isDone ? 'done' : ''} imp-${it.impact}`}
              onClick={() => setFlipped(flipped === it.key ? null : it.key)}>
              <div className="fcard-inner">
                <div className="fface front">
                  <span className="f-rank">#{rank + 1}</span>
                  <span className="f-icon">{AREA_ICON[it.area] || '•'}</span>
                  <b className="f-title">{it.title || it.fix}</b>
                  <span className="f-area">{it.area}</span>
                  {it.problem && <span className="f-why">{it.problem}</span>}
                  <span className="f-heat">{[1, 2, 3].map((d) => <i key={d} className={d <= weight(it) ? 'on' : ''} />)}<em>{it.impact} impact</em></span>
                  <span className="f-flip">tap to see how ↻</span>
                  {isDone && <span className="f-done">✓</span>}
                </div>
                <div className="fface back">
                  <div className="f-row bad"><small>Now</small>{it.problem}</div>
                  <div className="f-row good"><small>Do</small><b>{it.fix}</b></div>
                  {it.example && <q className="f-ex">{it.example}</q>}
                  {it.inspired_by && <span className="f-insp">Inspired by {it.inspired_by}</span>}
                  <button className={`f-btn ${isDone ? 'on' : ''}`} onClick={(e) => { e.stopPropagation(); toggleDone(it.key) }}>
                    {isDone ? '✓ Done' : 'Mark as done'}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function YourAd({ job }) {
  const rv = job.review
  const [active, setActive] = useState(null)
  if (!rv) return <div className="panel">Ad review is not available for this run.</div>
  const h = rv.hook || {}, st = rv.standout || {}, sc = rv.scorecard || {}
  const anns = rv.annotations || []
  const ad = job.feed?.find((a) => a.is_user)
  const stopRows = (job.feed || []).map((a) => ({ a, r: job.reactions?.find((x) => x.ad_id === a.id) })).filter((x) => x.r)
  const mine = stopRows.find((x) => x.a.is_user)?.r
  const others = stopRows.filter((x) => !x.a.is_user).map((x) => x.r.stopped)
  const best = stopRows.filter((x) => !x.a.is_user).sort((p, q) => q.r.stopped - p.r.stopped)[0]
  const avg = others.length ? Math.round(others.reduce((s, v) => s + v, 0) / others.length) : 0
  const hooks = [{ advertiser: 'You', hook: h.text, score: h.score, me: true }, ...(h.competitor_hooks || [])].sort((a, b) => b.score - a.score)
  const label = (x) => (typeof x === 'string' ? x : x.label || x.point)

  return (
    <div className="yourad">
      {/* ── Scoreboard ── */}
      <div className="scoreboard panel">
        <Gauge value={h.score} label="Hook score /10" />
        <div className="lift-g">
          <Gauge value={sc.before} max={100} label="Ad score now" accent={false} size={104} />
          <span className="arrow">→</span>
          <Gauge value={sc.after_estimate} max={100} label="After fixes (est.)" size={104} />
        </div>
        <div className="stopbars">
          <div className="sb-title">Buyers who stopped (of 30)</div>
          <Bar label="You" value={mine?.stopped ?? 0} max={30} me />
          <Bar label={`Best: ${best?.a.advertiser || '–'}`} value={best?.r.stopped ?? 0} max={30} />
          <Bar label="Competitor avg" value={avg} max={30} />
        </div>
      </div>

      {/* ── Annotated creative (video: one timeline panel with the drop-off curve and time-coded pins) ── */}
      {rv.timeline ? (
        <>
          <VideoTimeline job={job} anns={anns} />
          <HookCheck h={h} />
        </>
      ) : (
      <div className="annot-wrap panel">
        <div>
          <div className="eyebrow">Your ad, marked up</div>
          <AnnotatedCreative ad={ad} anns={anns} hasImage={rv.has_image} active={active} setActive={setActive} />
        </div>
        <div className="annot-list">
          <div className="legend-chips">
            {Object.entries(KIND).map(([k, v]) => <span key={k} className={`kchip ${v.cls}`}>{v.icon} {v.label}</span>)}
          </div>
          {anns.map((a) => {
            const k = KIND[a.kind] || KIND.fix
            return (
              <div key={a.n} className={`annot-item ${k.cls} ${active === a.n ? 'on' : ''}`} onMouseEnter={() => setActive(a.n)} onMouseLeave={() => setActive(null)}>
                <span className="pin static">{a.n}</span>
                <div><b>{k.icon} {a.label}</b><small>{a.note}</small></div>
              </div>
            )
          })}
          <HookCheck h={h} />
        </div>
      </div>
      )}

      {/* ── Hook ladder + rewrites ── */}
      <div className="two">
        <div className="panel">
          <div className="eyebrow">Hook ladder: you vs competitors</div>
          {hooks.map((x) => <Bar key={x.advertiser + x.hook} label={x.me ? '★ You' : x.advertiser} value={x.score} me={x.me} sub={`“${x.hook}” ${x.lesson ? '— ' + x.lesson : ''}`} />)}
          <p className="hint">Hover a name to see that hook.</p>
        </div>
        <div className="panel">
          <div className="eyebrow">Try these hooks instead</div>
          <div className="rewrites">
            {(h.rewrites || []).map((r, i) => (
              <div key={r.hook} className="rw" title={r.why}><span className="num">{i + 1}</span><b>“{r.hook}”</b><small>{r.type}</small></div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Stand-out map ── */}
      <div className="panel">
        <div className="eyebrow">Stand-out map</div>
        <div className="smap">
          {[
            ['only', '🏆 Only you', st.unique],
            ['shared', '👥 Everyone says it', st.shared],
            ['missing', '⚠️ They have, you don\'t', st.missing],
            ['open', '🚀 Nobody owns it', st.unclaimed],
          ].map(([cls, title, items]) => (
            <div key={cls} className={`smap-q ${cls}`}>
              <div className="smap-t">{title}</div>
              <div className="chips">
                {(items || []).length ? items.map((x) => (
                  <span key={label(x)} className="chip" title={[x.point, x.evidence, (x.competitors || x.who || []).join(', ')].filter(Boolean).join(' · ')}>{label(x)}</span>
                )) : <span className="chip ghost">none yet</span>}
              </div>
            </div>
          ))}
        </div>
        {st.positioning_suggested && <div className="pos-line">🎯 <b>{st.positioning_suggested}</b></div>}
      </div>

      <FixBoard items={rv.improvements || []} sc={sc} />
    </div>
  )
}
