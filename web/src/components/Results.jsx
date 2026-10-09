import { useRef, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import PixelAvatar from './PixelAvatar.jsx'
import YourAd from './YourAd.jsx'

const CLAY = '#D97757', INK = '#141413', MUTED = '#B9B6AA'
const PIE = ['#D97757', '#141413', '#E8A58C', '#73726C', '#C15F3C', '#D9D6CC', '#F2CDBE', '#3D3D3A']
const axis = { fontSize: 11, fill: '#73726C' }
const short = (s, n = 16) => (s && s.length > n ? s.slice(0, n - 1) + '…' : s)

function Chart({ title, children, h = 280, note }) {
  return (
    <div className="panel chart">
      <h4>{title}</h4>
      {note && <p className="note">{note}</p>}
      <ResponsiveContainer width="100%" height={h}>{children}</ResponsiveContainer>
    </div>
  )
}

function ThemeTip({ active, payload }) {
  if (!active || !payload?.length) return null
  const t = payload[0].payload, users = t.used_by || []
  return (
    <div className="theme-tip">
      <div className="theme-tip-head"><b>{t.theme}</b><span>{t.prevalence}%</span></div>
      {t.description && <p>{t.description}</p>}
      {users.length > 0 && (
        <>
          <div className="theme-tip-label">Used by {users.length} competitor{users.length > 1 ? 's' : ''}</div>
          <div className="theme-tip-chips">
            {users.slice(0, 8).map((u) => <span key={u}>{u}</span>)}
            {users.length > 8 && <span className="more">+{users.length - 8} more</span>}
          </div>
        </>
      )}
    </div>
  )
}

function WhoStops({ job }) {
  const { feed = [], reactions = [], personas = [] } = job
  const rows = feed.map((ad) => {
    const r = reactions.find((x) => x.ad_id === ad.id) || {}
    return { name: ad.is_user ? '★ Your ad' : short(ad.advertiser, 18), stop: r.stop_rate || 0, watch: r.avg_watch || 0, user: ad.is_user }
  }).sort((a, b) => b.stop - a.stop)
  const mine = reactions.find((r) => r.ad_id === 'you')
  const pById = Object.fromEntries(personas.map((p) => [p.id, p]))
  const rank = rows.findIndex((r) => r.user) + 1
  return (
    <>
      <div className="callout">
        <span className="callout-num">{mine?.stopped ?? 0}<small>/30</small></span>
        <div>
          <b>buyers stopped on your ad</b> — ranked <b>#{rank}</b> of {rows.length} ads in the feed.
          <div className="muted">{mine?.clicked ?? 0} would click · average watch {mine?.avg_watch ?? 0}s</div>
        </div>
      </div>
      <div className="two">
        <Chart title="Stop rate per ad (%)" h={Math.max(260, rows.length * 34)}>
          <BarChart data={rows} layout="vertical" margin={{ left: 10, right: 30 }}>
            <CartesianGrid horizontal={false} stroke="#EEECE4" />
            <XAxis type="number" tick={axis} domain={[0, 100]} />
            <YAxis type="category" dataKey="name" width={130} tick={axis} />
            <Tooltip />
            <Bar dataKey="stop" radius={[0, 6, 6, 0]} label={{ position: 'right', fontSize: 11, formatter: (v) => `${v}%` }}>
              {rows.map((r) => <Cell key={r.name} fill={r.user ? CLAY : INK} />)}
            </Bar>
          </BarChart>
        </Chart>
        <div className="panel">
          <h4>What buyers said about your ad</h4>
          <div className="quotes">
            {(mine?.reactions || []).slice().sort((a, b) => b.stopped - a.stopped || b.watch_seconds - a.watch_seconds).map((r) => {
              const p = pById[r.id] || {}
              return (
                <div key={r.id} className={`quote ${r.stopped ? 'yes' : ''}`}>
                  <PixelAvatar seed={`${p.id}-${p.name}-${p.role}`} gender={p.gender} size={28} />
                  <div><b>{p.name}</b> <span className="muted">{p.role} · {p.city}</span><div>“{r.reason}”</div></div>
                  <span className="pill">{r.clicked ? 'clicked' : r.stopped ? `stopped ${r.watch_seconds}s` : 'scrolled'}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}

const EDGE = { you: 'You', them: 'Them', tie: 'Tie' }
const slug = (s) => `h2h-${(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`

function FactCell({ v, other, hib }) {
  if (v == null) return <td className="na">–</td>
  const win = other != null && (hib ? v > other : v < other)
  return <td className={win ? 'win' : ''}>{v}</td>
}

// Render "quoted ad copy" inside AI prose as highlighted snippets.
function Quoted({ text }) {
  return (text || '').split(/(“[^”]+”|"[^"]+")/g).map((part, i) =>
    /^[“"]/.test(part) ? <mark key={i} className="dq">{part.replace(/^[“"]|[”"]$/g, '')}</mark> : part)
}

const PRIO = { high: 0, medium: 1, low: 2 }
const KIND = { text: 'Text ad', image: 'Image ad', video: 'Video ad' }
const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`

// One side of "What we compared": video frames, the image, or the copy for text ads.
function CreativeSide({ who, label, format, frames = [], image, copy }) {
  return (
    <div className={`dx-cr ${who}`}>
      <div className="dx-cr-h"><span className="dot" /><b>{label}</b><span className="dx-fmt">{format}</span></div>
      {frames.length > 0 ? (
        <div className="dx-frames">{frames.slice(0, 4).map((f) => <figure key={f.t}><img src={f.src} alt="" /><figcaption>{mmss(f.t)}</figcaption></figure>)}</div>
      ) : image ? <img className="dx-cr-img" src={image} referrerPolicy="no-referrer" alt="" />
        : null}
      {copy && <p className={`dx-cr-copy ${!image && !frames.length ? 'big' : ''}`}>{short(copy, 220)}</p>}
    </div>
  )
}

function H2HDetail({ h, name, detailRef, job }) {
  const me = job.feed?.[0] || {}, them = h.their_ad || {}
  const kind = h.input_kind || job.profile?.input_type || 'text'

  const edgeOf = Object.fromEntries((h.rows || []).map((r) => [r.aspect, r]))
  const go = (aspect) => document.getElementById(slug(aspect))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const actions = (h.actions || []).slice().sort((a, b) => (PRIO[a.priority] ?? 3) - (PRIO[b.priority] ?? 3))
  const label = (e) => (e === 'you' ? 'You win' : e === 'them' ? `${short(name, 14)} wins` : 'Tie')
  return (
    <div className="h2h-detail" ref={detailRef}>
      <div className="dx-intro">
        <div>
          <div className="eyebrow">Deep dive</div>
          <h4>Point-by-point breakdown</h4>
          <p className="muted">What each ad actually says, who does it better, and the exact move to make.</p>
        </div>
        <div className="dx-compared">
          <CreativeSide who="you" label="Your ad" format={KIND[kind] || kind} frames={job.user_frames || []}
            image={kind === 'video' ? null : me.image} copy={me.body || me.hook} />
          <span className="dx-vs-badge">VS</span>
          <CreativeSide who="them" label={name} format={them.format || 'Ad'} frames={them.frames || []}
            image={them.image} copy={them.body || them.headline} />
        </div>
        <div className="dx-nav">
          {(h.details || []).map((d, i) => {
            const e = edgeOf[d.aspect]?.edge || 'tie'
            return <button key={d.aspect} className={`dx-chip ${e}`} onClick={() => go(d.aspect)}><i>{i + 1}</i>{d.aspect}</button>
          })}
        </div>
      </div>

      {(h.details || []).map((d, i) => {
        const row = edgeOf[d.aspect] || {}, e = row.edge || 'tie'
        return (
          <article key={d.aspect} id={slug(d.aspect)} className={`dx-card edge-${e}`} style={{ animationDelay: `${i * 70}ms` }}>
            <header>
              <span className="dx-num">{String(i + 1).padStart(2, '0')}</span>
              <div className="dx-title"><h5>{d.aspect}</h5>{row.why && <span>{row.why}</span>}</div>
              <span className={`edge ${e}`}>{label(e)}</span>
            </header>
            <div className="dx-vs">
              <div className={`dx-side you ${e === 'you' ? 'won' : ''}`}>
                <div className="dx-side-h"><span className="dot" />Your ad{e === 'you' && <em>★ stronger</em>}</div>
                <p><Quoted text={d.you} /></p>
              </div>
              <span className="dx-vs-badge">VS</span>
              <div className={`dx-side them ${e === 'them' ? 'won' : ''}`}>
                <div className="dx-side-h"><span className="dot" />{name}{e === 'them' && <em>★ stronger</em>}</div>
                <p><Quoted text={d.them} /></p>
              </div>
            </div>
            {d.takeaway && (
              <div className="dx-do"><span className="dx-do-ic">→</span><div><b>Do this</b><p>{d.takeaway}</p></div></div>
            )}
          </article>
        )
      })}

      <div className="dx-plays">
        {[['steal', '💡', `Adapt from ${name}`, 'What works for them — borrow the idea, not the words'],
          ['attack', '🎯', 'Attack their weak spots', 'Gaps you can position against']].map(([k, ic, title, sub]) => (
          <div key={k} className={`dx-play ${k}`}>
            <div className="dx-play-h"><span className="dx-ic">{ic}</span><div><h4>{title}</h4><small>{sub}</small></div></div>
            <ol>{(h[k] || []).map((x) => <li key={x}>{x}</li>)}</ol>
          </div>
        ))}
      </div>

      {actions.length > 0 && (
        <div className="dx-plan">
          <div className="dx-plan-h">
            <h4>Action plan to beat {name}</h4>
            <span className="muted">{actions.length} moves · highest impact first</span>
          </div>
          <ol className="dx-steps">
            {actions.map((r, i) => (
              <li key={r.title} className={r.priority}>
                <span className="dx-step-n">{i + 1}</span>
                <div><div className="dx-step-t"><b>{r.title}</b><span className={`prio ${r.priority}`}>{r.priority}</span></div><p>{r.detail}</p></div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

function HeadToHead({ job }) {
  const h = job.head_to_head
  const [open, setOpen] = useState(false)
  const detailRef = useRef(null)
  if (!h) return null
  const c = h.competitor || {}, name = c.page_name, sc = h.score || {}
  const jump = (aspect) => {
    setOpen(true)
    setTimeout(() => {
      const el = (aspect && document.getElementById(slug(aspect))) || detailRef.current
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 60)
  }
  const facts = (h.facts || []).filter((f) => f.you != null || f.them != null)
  return (
    <section className="panel h2h">
      <div className="h2h-head">
        <div>
          <div className="eyebrow">Head-to-head · your #1 competitor</div>
          <h3>Your ad <span className="vs">vs</span> {name}</h3>
          <div className="muted">{c.sells ? `Sells: ${c.sells} · ` : ''}{c.relevance} competitor · threat {c.threat_score ?? '–'}/10</div>
        </div>
        <div className="h2h-score" title="Aspects won in the comparison table">
          <span className="you"><b>{sc.you ?? 0}</b><small>you</small></span>
          <span className="tie"><b>{sc.tie ?? 0}</b><small>tie</small></span>
          <span className="them"><b>{sc.them ?? 0}</b><small>{short(name, 12)}</small></span>
        </div>
      </div>
      <div className={`h2h-verdict ${h.winner}`}>
        <span className="pill">{h.winner === 'you' ? 'You lead' : h.winner === 'them' ? `${short(name, 18)} leads` : 'Even match'}</span>
        <p>{h.verdict}</p>
      </div>

      {facts.length > 0 && (
        <table className="h2h-table facts">
          <thead><tr><th><span className="src-tag fact">Measured</span></th><th>Your ad</th><th>{name}</th></tr></thead>
          <tbody>{facts.map((f) => (
            <tr key={f.label}><td>{f.label}</td><FactCell v={f.you} other={f.them} hib={f.higher_is_better} /><FactCell v={f.them} other={f.you} hib={f.higher_is_better} /></tr>
          ))}</tbody>
        </table>
      )}

      <div className="h2h-scroll">
        <table className="h2h-table">
          <thead><tr><th>Key point</th><th>Your ad</th><th>{name}</th><th>Edge</th><th /></tr></thead>
          <tbody>
            {(h.rows || []).map((r) => (
              <tr key={r.aspect} className={`edge-${r.edge}`} onClick={() => jump(r.aspect)} title="Open the detailed analysis for this point">
                <td className="aspect">{r.aspect}</td>
                <td>{r.you}</td>
                <td>{r.them}</td>
                <td><span className={`edge ${r.edge}`}>{r.edge === 'them' ? short(name, 12) : EDGE[r.edge]}</span><small>{r.why}</small></td>
                <td className="go">↓</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="h2h-pn">
        {[['you', 'Your ad'], ['them', name]].map(([k, label]) => (
          <div key={k} className={`h2h-side ${k}`}>
            <h5>{label}</h5>
            <div className="good"><b>+ Positives</b><ul>{(h[k]?.positives || []).map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div className="bad"><b>− Negatives</b><ul>{(h[k]?.negatives || []).map((x) => <li key={x}>{x}</li>)}</ul></div>
          </div>
        ))}
      </div>

      <div className="h2h-actions">
        <button className="btn primary" onClick={() => (open ? setOpen(false) : jump())}>{open ? 'Hide detailed analysis ↑' : 'See detailed analysis ↓'}</button>
        {h.their_ad?.ad_library_url && <a className="btn ghost" href={h.their_ad.ad_library_url} target="_blank" rel="noreferrer">Their ad in Ads Library ↗</a>}
        {c.page_profile_uri && <a className="btn ghost" href={c.page_profile_uri} target="_blank" rel="noreferrer">Their Facebook page ↗</a>}
      </div>

      {open && <H2HDetail h={h} name={name} detailRef={detailRef} job={job} />}
    </section>
  )
}

function Competitors({ job }) {
  const comps = (job.analysis?.competitors || []).filter((c) => c.relevance !== 'irrelevant')
  return (
    <>
      <HeadToHead job={job} />
      <h4 className="section-h comp-list-h">All competitors ({comps.length})</h4>
      {job.own_pages?.length > 0 && (
        <p className="own-note">
          <b>Not counted as competitors (your own pages):</b>{' '}
          {job.own_pages.map((o) => <span key={o.page_name} className="chip">{o.page_name} <small>· {o.reason} · {o.ads} ads</small></span>)}
        </p>
      )}
      <p className="evidence-note">
        <span className="src-tag fact">From their ads</span> = copied exactly from the Facebook Ads Library ·
        <span className="src-tag ai">AI read</span> = OpenAI's interpretation of that copy
      </p>
      <div className="comp-grid">
        {comps.map((c) => (
          <div key={c.page_name} className="panel comp">
            <div className="comp-head">
              {c.profile_pic ? <img src={c.profile_pic} referrerPolicy="no-referrer" alt="" /> : <span className="pp">{c.page_name[0]}</span>}
              <div><b>{c.page_name}</b><div className="muted">{(c.page_categories || []).join(', ')}</div></div>
              <span className={`rel ${c.relevance}`}>{c.relevance}</span>
            </div>
            {c.sells && (
              <div className="ev-block"><div className="ev-h"><span className="src-tag ai">AI read</span> Sells</div>
                <p>{c.sells}</p>
                {c.evidence && <q className="ev-quote">{c.evidence}</q>}</div>
            )}
            <div className="meter" title="Threat = relevance 40% + ads competing with yours 25% + longest-running ad 20% + page size 15%">
              <span style={{ width: `${(c.threat_score || 0) * 10}%` }} /><em>threat {c.threat_score ?? '–'}/10 ⓘ</em>
            </div>
            <div className="kv"><span>{c.competing_ads ?? c.active_ads}<small>competing ads{c.competing_ads != null && c.competing_ads !== c.active_ads ? ` (of ${c.active_ads})` : ''}</small></span><span>{c.max_days_running ?? '–'}<small>longest ad (d)</small></span>
              <span>{c.page_likes ? Intl.NumberFormat('en', { notation: 'compact' }).format(c.page_likes) : '–'}<small>page likes</small></span></div>

            {c.hooks?.length > 0 && (
              <div className="ev-block"><div className="ev-h"><span className="src-tag fact">From their ads</span> Hooks</div>
                {c.hooks.map((x) => <q key={x} className="ev-quote">{x}</q>)}</div>
            )}
            {c.offers?.length > 0 && (
              <div className="ev-block"><div className="ev-h"><span className="src-tag fact">From their ads</span> Offers</div>
                <div className="chips">{c.offers.map((x) => <span key={x} className="chip offer-chip">{x}</span>)}</div></div>
            )}
            {c.positioning && (
              <div className="ev-block"><div className="ev-h"><span className="src-tag ai">AI read</span> Positioning</div>
                <p>{c.positioning}</p>
                <div className="sw"><div><b>+</b> {(c.strengths || []).join('; ')}</div><div><b>−</b> {(c.weaknesses || []).join('; ')}</div></div></div>
            )}
            {c.ads?.length > 0 && (
              <div className="ev-ads">
                {c.ads.map((a) => (
                  <a key={a.url} href={a.url} target="_blank" rel="noreferrer" className="ev-ad" title={a.hook}>
                    {a.image ? <img src={a.image} referrerPolicy="no-referrer" alt="" /> : <span className="ev-noimg">{a.format}</span>}
                    <small>{a.days}d live ↗</small>
                  </a>
                ))}
              </div>
            )}
            {c.page_profile_uri && <a href={c.page_profile_uri} target="_blank" rel="noreferrer">Facebook page ↗</a>}
          </div>
        ))}
      </div>
    </>
  )
}

function Market({ job }) {
  const a = job.analysis || {}, st = job.stats || {}
  const comps = (a.competitors || []).filter((c) => c.relevance !== 'irrelevant').slice(0, 10)
  const s = a.scores || {}
  const radar = (s.dimensions || []).map((d, i) => ({ d, you: s.user?.[i], avg: s.competitor_avg?.[i], best: s.best_competitor?.values?.[i] }))
  const themes = (a.market_themes || []).slice().sort((x, y) => y.prevalence - x.prevalence)
  return (
    <div className="two">
      <Chart title="Creative scorecard: you vs market" note="AI rating of the ad copy (1-10), for direction only" h={320}>
        <RadarChart data={radar} outerRadius="72%">
          <PolarGrid stroke="#E8E6DC" /><PolarAngleAxis dataKey="d" tick={{ fontSize: 10, fill: '#3D3D3A' }} />
          <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
          <Radar name="Your ad" dataKey="you" stroke={CLAY} fill={CLAY} fillOpacity={0.35} />
          <Radar name="Competitor avg" dataKey="avg" stroke={INK} fill={INK} fillOpacity={0.08} />
          {s.best_competitor?.name && <Radar name={`Best: ${s.best_competitor.name}`} dataKey="best" stroke={MUTED} fill="none" strokeDasharray="4 3" />}
          <Legend wrapperStyle={{ fontSize: 11 }} /><Tooltip />
        </RadarChart>
      </Chart>
      <Chart title="Competing ads per competitor" h={320}>
        <BarChart data={comps.map((c) => ({ name: short(c.page_name, 14), ads: c.competing_ads ?? c.active_ads, direct: c.relevance === 'direct' }))} margin={{ bottom: 40 }}>
          <CartesianGrid vertical={false} stroke="#EEECE4" />
          <XAxis dataKey="name" tick={{ ...axis, fontSize: 10 }} angle={-35} textAnchor="end" interval={0} />
          <YAxis tick={axis} allowDecimals={false} /><Tooltip />
          <Bar dataKey="ads" radius={[6, 6, 0, 0]}>{comps.map((c) => <Cell key={c.page_name} fill={c.relevance === 'direct' ? CLAY : '#D9D6CC'} />)}</Bar>
        </BarChart>
      </Chart>
      <Chart title="Messaging themes in the market" note="% of competitors whose real ad copy uses each theme (counted, not guessed)" h={Math.max(240, themes.length * 34)}>
        <BarChart data={themes} layout="vertical" margin={{ left: 10, right: 30 }}>
          <XAxis type="number" domain={[0, 100]} tick={axis} /><YAxis type="category" dataKey="theme" width={150} tick={axis} />
          <Tooltip content={<ThemeTip />} cursor={{ fill: '#F7F6F1' }} wrapperStyle={{ zIndex: 10 }} allowEscapeViewBox={{ y: true }} />
          <Bar dataKey="prevalence" fill={INK} radius={[0, 6, 6, 0]} label={{ position: 'right', fontSize: 11, fill: '#73726C', formatter: (v) => `${v}%` }} />
        </BarChart>
      </Chart>
      <Chart title="Ad formats" note={`Relevant competitors only (${st.relevant_ads ?? '–'} ads) · DPA = catalogue ads · DCO = dynamic creative`} h={260}>
        <PieChart>
          <Pie data={st.formats || []} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
            {(st.formats || []).map((f, i) => <Cell key={f.name} fill={PIE[i % PIE.length]} />)}
          </Pie>
          <Legend wrapperStyle={{ fontSize: 11 }} /><Tooltip />
        </PieChart>
      </Chart>
      <Chart title="Placements" h={240}>
        <BarChart data={st.platforms || []}><XAxis dataKey="name" tick={{ ...axis, fontSize: 9 }} /><YAxis tick={axis} /><Tooltip />
          <Bar dataKey="value" fill={CLAY} radius={[6, 6, 0, 0]} /></BarChart>
      </Chart>
      <Chart title="Call-to-action buttons" h={240}>
        <BarChart data={st.ctas || []} layout="vertical" margin={{ left: 10 }}><XAxis type="number" tick={axis} />
          <YAxis type="category" dataKey="name" width={100} tick={axis} /><Tooltip />
          <Bar dataKey="value" fill={INK} radius={[0, 6, 6, 0]} /></BarChart>
      </Chart>
    </div>
  )
}

function Playbook({ job }) {
  const a = job.analysis || {}
  const fb = a.user_ad_feedback || {}
  return (
    <>
      <div className="panel"><h4>Executive summary</h4><p className="lead">{a.executive_summary}</p></div>
      <div className="two">
        <div className="panel"><h4>Your ad — strengths</h4><ul>{(fb.strengths || []).map((x) => <li key={x}>{x}</li>)}</ul></div>
        <div className="panel"><h4>Your ad — weaknesses</h4><ul>{(fb.weaknesses || []).map((x) => <li key={x}>{x}</li>)}</ul></div>
      </div>
      <div className="panel"><h4>Gaps you can own</h4><ul>{(a.gaps_opportunities || []).map((x) => <li key={x}>{x}</li>)}</ul></div>
      <div className="panel"><h4>Recommendations</h4>
        {(a.recommendations || []).map((r) => (
          <div key={r.title} className={`rec ${r.priority}`}><b>{r.title}</b><span className="pill">{r.priority}</span><p>{r.detail}</p></div>
        ))}
      </div>
      <h4 className="section-h">Ad copy ideas</h4>
      <div className="ideas">
        {(a.ad_copy_ideas || []).map((i) => (
          <div key={i.hook} className="panel idea"><div className="hook">{i.hook}</div><p>{i.body}</p><button>{i.cta}</button></div>
        ))}
      </div>
    </>
  )
}

const TABS = [['you', 'Your ad', YourAd], ['who', 'Who stops', WhoStops], ['comp', 'Competitors', Competitors], ['market', 'Market visuals', Market], ['play', 'Playbook', Playbook]]

function PdfButton({ id }) {
  const [state, setState] = useState('idle')
  const download = async () => {
    setState('busy')
    try {
      const r = await fetch(`/api/jobs/${id}/report.pdf`)
      if (!r.ok) throw new Error()
      const blob = await r.blob()
      const name = (r.headers.get('content-disposition') || '').match(/filename="?([^"]+)"?/)?.[1] || 'ad_report.pdf'
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name })
      a.click(); URL.revokeObjectURL(a.href); setState('idle')
    } catch { setState('error') }
  }
  return (
    <button className="btn primary pdf-btn" onClick={download} disabled={state === 'busy'}>
      {state === 'busy' ? 'Preparing PDF…' : state === 'error' ? 'PDF failed, retry' : '⬇ Download PDF report'}
    </button>
  )
}

export default function Results({ job }) {
  const [tab, setTab] = useState('you')
  const Comp = TABS.find((t) => t[0] === tab)[2]
  return (
    <section className="results">
      <div className="tabs">
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>)}
        <PdfButton id={job.id} />
      </div>
      <Comp job={job} />
    </section>
  )
}
