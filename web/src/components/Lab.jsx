import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import PixelAvatar from './PixelAvatar.jsx'

const PLACEHOLDER_ROLES = ['gym owner', 'talent scout', 'startup ops', 'nutrition coach', 'law partner', 'startup cto',
  'first-time founder', 'marketing manager', 'freelance designer', 'IT admin', 'mobile mom', 'skincare nerd',
  'thinking dad', 'photographer', 'D2C marketer', 'yoga teacher', 'busy consultant', 'retired officer',
  'college student', 'sports fan', 'first-time mom', 'old school CA', 'tall woman', 'room of a teen',
  'game-night host', 'coffee regular', 'credit watcher', 'deal-curious', 'stylish mom', 'home cook']

// Each ad stays on screen for AD_DURATION ms: ~1.5s "scanning", buyers react one by one over ~4s, then it holds.
export const AD_DURATION = 16000
const REVEAL_START = 1500, STEP = 130

/* Playback engine: walks through the feed, revealing each persona's reaction. */
export function usePlayback(feed, reactions, enabled) {
  const [idx, setIdx] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [finished, setFinished] = useState(false)
  const [paused, setPaused] = useState(false)
  const start = useRef(performance.now())
  const elapsedRef = useRef(0)
  const order = useRef([])

  const feedKey = (feed || []).map((a) => a.id).join('|')
  useEffect(() => { setIdx(0); setFinished(false); setPaused(false) }, [feedKey])

  const current = feed?.[idx]
  const result = current && reactions?.find((r) => r.ad_id === current.id)

  useEffect(() => { start.current = performance.now(); elapsedRef.current = 0; setElapsed(0) }, [idx, !!result])
  useEffect(() => {
    order.current = Array.from({ length: 30 }, (_, i) => i).sort(() => Math.random() - 0.5)
  }, [idx])

  useEffect(() => {
    if (!enabled || !result || finished || paused) return
    start.current = performance.now() - elapsedRef.current // resume from where we paused
    const t = setInterval(() => {
      const e = performance.now() - start.current
      elapsedRef.current = e
      setElapsed(e)
      if (e > AD_DURATION) {
        if (idx < feed.length - 1) setIdx((i) => i + 1)
        else { setFinished(true); clearInterval(t) }
      }
    }, 60)
    return () => clearInterval(t)
  }, [enabled, result, idx, finished, paused, feed])

  const revealedRank = (pos) => {
    const rank = order.current.indexOf(pos)
    return elapsed > REVEAL_START + rank * STEP
  }
  const go = (i) => {
    const n = feed?.length || 1
    setFinished(false); setElapsed(0); elapsedRef.current = 0; setIdx(((i % n) + n) % n); start.current = performance.now()
  }
  return {
    idx, current, result, elapsed, finished, paused, revealedRank,
    replay: go, next: () => go(idx + 1), prev: () => go(idx - 1),
    togglePause: () => setPaused((p) => !p),
    progress: Math.min(1, elapsed / AD_DURATION),
    remaining: Math.max(0, Math.ceil((AD_DURATION - elapsed) / 1000)),
    scanning: !!result && elapsed < REVEAL_START,
    waiting: !result,
  }
}

export function FeedControls({ feed, pb }) {
  if (!feed?.length) return null
  return (
    <div className="feed-ctrl">
      <div className="fc-bar"><span style={{ width: `${pb.progress * 100}%` }} /></div>
      <div className="fc-row">
        <button className="fc-btn" onClick={pb.prev} aria-label="Previous ad">◀</button>
        <button className="fc-btn main" onClick={pb.finished ? () => pb.replay(0) : pb.togglePause} aria-label="Play or pause">
          {pb.finished ? '↺' : pb.paused ? '▶' : '❚❚'}
        </button>
        <button className="fc-btn" onClick={pb.next} aria-label="Next ad">▶</button>
        <span className="fc-info">
          Ad {pb.idx + 1}/{feed.length}
          <small>{pb.finished ? 'feed finished' : pb.waiting ? 'buyers watching…' : pb.paused ? 'paused' : `next in ${pb.remaining}s`}</small>
        </span>
      </div>
      {pb.current && (
        <div className="fc-source">
          {pb.current.is_user ? <><b>Your ad</b> · exactly as you uploaded it</> : (
            <>
              <b>{pb.current.advertiser}</b>
              {pb.current.relevance && <span className={`rel ${pb.current.relevance}`}>{pb.current.relevance}</span>}
              {pb.current.sells && <span> · sells {pb.current.sells}</span>}
              <small>
                Real ad, live {pb.current.days_running} days ·{' '}
                {pb.current.ad_library_url && <a href={pb.current.ad_library_url} target="_blank" rel="noreferrer">View in Ads Library ↗</a>}
              </small>
            </>
          )}
        </div>
      )}
      <div className="feed-dots">
        {feed.map((a, i) => (
          <button key={a.id} className={`${i === pb.idx ? 'on' : ''} ${a.is_user ? 'you' : ''}`} title={a.advertiser} onClick={() => pb.replay(i)} />
        ))}
      </div>
    </div>
  )
}

export function StatBar({ adIdx, feedLen, buyers, stopped, avgWatch, ctr, adsFound }) {
  const tiles = [
    { label: 'AD IN FEED', value: feedLen ? `${adIdx + 1}/${feedLen}` : '—', dark: true },
    { label: 'BUYERS', value: buyers || 30, dark: true },
    { label: 'STOPPED', value: stopped ?? 0, accent: true },
    { label: 'AVG WATCH (s)', value: (avgWatch ?? 0).toFixed(1) },
    { label: 'CLICK RATE', value: `${(ctr ?? 0).toFixed(1)}%` },
    { label: 'ADS SCANNED', value: adsFound ?? 0 },
  ]
  return (
    <div className="statbar">
      {tiles.map((t) => (
        <div key={t.label} className={`stat ${t.dark ? 'dark' : ''} ${t.accent ? 'accent' : ''}`}>
          <span className="stat-label">{t.label}</span>
          <motion.span key={String(t.value)} className="stat-value" initial={{ y: 6, opacity: 0.3 }} animate={{ y: 0, opacity: 1 }}>
            {t.value}
          </motion.span>
        </div>
      ))}
    </div>
  )
}

export function PersonaGrid({ personas, playback, totals, busy }) {
  const list = personas?.length ? personas : PLACEHOLDER_ROLES.map((role, i) => ({ id: i + 1, role, name: '' }))
  const [hover, setHover] = useState(null)
  return (
    <div className={`grid ${busy ? 'busy' : ''}`}>
      {list.map((p, pos) => {
        const r = playback.result?.reactions?.find((x) => x.id === p.id)
        const shown = r && playback.revealedRank(pos)
        const state = !shown ? (playback.scanning ? 'scan' : 'idle') : r.stopped ? 'stop' : 'pass'
        return (
          <motion.div
            key={p.id}
            className={`card ${state} ${r?.clicked && shown ? 'clicked' : ''}`}
            layout
            style={{ zIndex: hover === p.id ? 20 : undefined }}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: state === 'pass' ? 0.45 : 1, scale: state === 'stop' ? 1.04 : 1 }}
            transition={{ type: 'spring', stiffness: 400, damping: 24, delay: personas?.length ? 0 : pos * 0.015 }}
            onMouseEnter={() => setHover(p.id)}
            onMouseLeave={() => setHover(null)}
          >
            <div className="card-role">{p.role}</div>
            <div className="card-face"><PixelAvatar seed={`${p.id}-${p.name}-${p.role}`} gender={p.gender} size={38} /></div>
            <div className="card-foot">
              <span className="tally">{totals?.[p.id] ?? 0}</span>
              <AnimatePresence>
                {state === 'stop' && (
                  <motion.span className="badge" initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>
                    {r.clicked ? 'CLICK' : `${r.watch_seconds.toFixed(0)}s`}
                  </motion.span>
                )}
              </AnimatePresence>
            </div>
            {hover === p.id && p.name && (
              <div className="tip">
                <b>{p.name}, {p.age}</b> · {p.city}
                <div className="tip-traits">{p.traits}</div>
                {shown && <div className={`tip-reason ${r.stopped ? 'yes' : ''}`}>“{r.reason}”</div>}
              </div>
            )}
          </motion.div>
        )
      })}
    </div>
  )
}

/* The creative exactly as the advertiser published it: video, carousel or single image. */
function PostMedia({ ad }) {
  const [videoFailed, setVideoFailed] = useState(false)
  if (ad.video && !videoFailed) {
    return (
      <div className="post-media">
        <video src={ad.video} poster={ad.image || undefined} autoPlay muted loop playsInline onError={() => setVideoFailed(true)} />
      </div>
    )
  }
  if (ad.images?.length > 1) {
    return (
      <div className="post-media carousel">
        {ad.images.map((src, i) => <img key={i} src={src} referrerPolicy="no-referrer" alt="" />)}
      </div>
    )
  }
  if (ad.image) return <div className="post-media"><img src={ad.image} referrerPolicy="no-referrer" alt="" /></div>
  if (ad.is_user && !ad.body) return <div className="post-media text-only">{ad.hook || ad.advertiser}</div>
  return null
}

export function PhoneFeed({ ad, job, result, stoppedNow }) {
  return (
    <div className="phone">
      <div className="notch" />
      <div className="phone-top"><b>Feed</b><span>⌕ ♡</span></div>
      <div className="phone-body">
        <AnimatePresence mode="popLayout">
          {ad ? (
            <motion.div key={ad.id} className="post" initial={{ y: 420, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
              exit={{ y: -420, opacity: 0 }} transition={{ type: 'spring', stiffness: 120, damping: 20 }}>
              <div className="post-head">
                {ad.profile_pic ? <img src={ad.profile_pic} referrerPolicy="no-referrer" alt="" /> : <span className="pp">{(ad.advertiser || 'Y')[0]}</span>}
                <div><b>{ad.advertiser}</b><small>{ad.is_user ? 'Your ad · Sponsored' : 'Sponsored'}</small></div>
                <span className="post-more">···</span>
              </div>
              {ad.body && <p className={`post-body ${ad.image || ad.video ? '' : 'full'}`}>{ad.body}</p>}
              <PostMedia ad={ad} />
              {(ad.headline || ad.domain || (ad.cta && ad.cta.length <= 24) || !ad.is_user) && (
                <div className="post-cta">
                  <div>
                    {ad.domain && <small>{ad.domain}</small>}
                    <span>{ad.headline || ad.link_description || ad.advertiser}</span>
                  </div>
                  {ad.cta && ad.cta.length <= 24 && <button>{ad.cta}</button>}
                </div>
              )}
              {result && <div className="post-stopped">{stoppedNow} of 30 stopped</div>}
            </motion.div>
          ) : (
            <motion.div key="loading" className="post" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -60 }}>
              <PhoneLoader job={job} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

export function GridLegend() {
  return (
    <div className="legend">
      <div className="legend-title">How to read the grid</div>
      <p>Each card is <b>one simulated buyer</b> scrolling the feed shown in the phone. The label is their role in life,
        and that role decides what they care about, so each one reacts differently to the same ad. Hover a card to see who they are and why they reacted.</p>
      <div className="legend-items">
        <span><i className="sw stop" /> <b>Orange</b> = stopped on this ad (paused 2s+)</span>
        <span><i className="sw pass" /> <b>Faded</b> = scrolled past</span>
        <span><i className="sw badge-sw">4s</i> seconds watched</span>
        <span><i className="sw badge-sw clay">CLICK</i> would tap the ad</span>
        <span><i className="sw num">3</i> ads this buyer has stopped on so far</span>
      </div>
    </div>
  )
}

const STEPS = [
  ['understanding', 'Reading your ad', '👀'],
  ['scraping', 'Hunting competitor ads', '🔍'],
  ['analysing', 'Sizing up rivals', '🧠'],
  ['personas', 'Inviting 30 buyers', '🧑‍🤝‍🧑'],
  ['simulating', 'Starting the feed', '📱'],
]
const BUBBLE = {
  idle: ["Drop an ad and I'll go spy on your competitors 🕵️", 'Image, video or text, I can read them all.'],
  queued: ['Warming up…'],
  understanding: ['Reading every word on your ad…', 'Spotting your hook and offer…'],
  scraping: ['Digging through the Facebook Ads Library…', 'Collecting ads your rivals are running right now…'],
  analysing: ['Comparing their hooks with yours…', 'Checking who runs the longest ads…'],
  simulating: ['30 buyers are grabbing their phones…'],
}
const TIPS = [
  'Ads that run 60+ days are usually the winners.',
  'Most people decide to stop scrolling in under 3 seconds.',
  'A clear offer beats a clever line.',
  'Your hook is the first line people read. Make it count.',
]
const ORDER = ['queued', 'understanding', 'scraping', 'analysing', 'simulating', 'reviewing', 'done']

/* ── Idle explainer: Scout tells the story of what the site does, in 4 looping scenes ── */
const SCENES = [
  { key: 'drop', say: "Hi, I'm Scout! I test ads.", cap: 'You drop your ad', sub: 'Image, video or text' },
  { key: 'spy', say: 'Spying on your rivals… 🕵️', cap: 'I find your real competitors', sub: 'Live ads from the Facebook Ads Library' },
  { key: 'feed', say: 'Who stops scrolling? 👀', cap: '30 AI buyers scroll the feed', sub: 'Orange = your ad stopped them' },
  { key: 'plan', say: "Here's your playbook 🚀", cap: 'You get your score & fixes', sub: 'Plus a PDF report to share' },
]
const SCENE_MS = 3600

function CountUp({ to, ms = 1600, suffix = '' }) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const t0 = performance.now()
    const id = setInterval(() => {
      const p = Math.min(1, (performance.now() - t0) / ms)
      setV(Math.round(to * (1 - Math.pow(1 - p, 3))))
      if (p === 1) clearInterval(id)
    }, 40)
    return () => clearInterval(id)
  }, [to, ms])
  return <>{v}{suffix}</>
}

function SceneDrop() {
  return (
    <div className="sc sc-drop">
      <motion.div className="mini-ad you" initial={{ y: 90, rotate: 8, opacity: 0 }} animate={{ y: 0, rotate: -3, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 140, damping: 14, delay: 0.2 }}>
        <span className="ma-tag">YOUR AD</span><i /><i className="s" /><b>Shop now</b>
      </motion.div>
      {['🖼️', '🎬', '✍️'].map((e, i) => (
        <motion.span key={e} className="sc-float" style={{ left: `${18 + i * 30}%` }}
          initial={{ y: 20, opacity: 0 }} animate={{ y: [-4, -14, -4], opacity: 1 }} transition={{ delay: 0.6 + i * 0.2, duration: 1.8, repeat: Infinity }}>{e}</motion.span>
      ))}
    </div>
  )
}

function SceneSpy() {
  return (
    <div className="sc sc-spy">
      {[0, 1, 2].map((i) => (
        <motion.div key={i} className={`mini-ad rival r${i}`} initial={{ x: 0, rotate: 0, opacity: 0 }}
          animate={{ x: (i - 1) * 62, rotate: (i - 1) * 9, opacity: 1 }} transition={{ delay: 0.15 * i, type: 'spring', stiffness: 120 }}>
          <span className="ma-tag">RIVAL</span><i /><i className="s" />
        </motion.div>
      ))}
      <motion.span className="sc-lens" animate={{ x: [-70, 70, -70], y: [0, -8, 0] }} transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}>🔍</motion.span>
      <div className="sc-counter"><b><CountUp to={127} /></b> ads found <em>example</em></div>
    </div>
  )
}

function SceneFeed() {
  const lit = [1, 4, 7, 9, 14, 16, 20, 23, 27]
  return (
    <div className="sc sc-feed">
      <div className="mini-grid">
        {Array.from({ length: 30 }, (_, i) => {
          const on = lit.indexOf(i)
          return (
            <motion.span key={i} className="mg-cell" initial={{ opacity: 0, scale: 0.6 }}
              animate={on >= 0 ? { opacity: 1, scale: [1, 1.18, 1], backgroundColor: ['#FFFFFF', '#FBEDE6', '#FBEDE6'], borderColor: ['#E8E6DC', '#D97757', '#D97757'] } : { opacity: 0.55, scale: 1 }}
              transition={{ delay: on >= 0 ? 0.6 + on * 0.22 : i * 0.015, duration: 0.45 }}>
              <PixelAvatar seed={`story-${i}`} size={20} />
            </motion.span>
          )
        })}
      </div>
      <div className="sc-counter"><b><CountUp to={9} ms={2400} /></b> of 30 stopped <em>example</em></div>
    </div>
  )
}

function ScenePlan() {
  const r = 30, c = 2 * Math.PI * r
  return (
    <div className="sc sc-plan">
      <div className="sc-ring">
        <svg viewBox="0 0 80 80" width="92" height="92">
          <circle cx="40" cy="40" r={r} fill="none" stroke="#EEECE4" strokeWidth="8" />
          <motion.circle cx="40" cy="40" r={r} fill="none" stroke="#D97757" strokeWidth="8" strokeLinecap="round" transform="rotate(-90 40 40)"
            initial={{ strokeDasharray: `${c * 0.58} ${c}` }} animate={{ strokeDasharray: `${c * 0.86} ${c}` }} transition={{ delay: 0.4, duration: 1.6 }} />
        </svg>
        <span><b><CountUp to={86} ms={2000} /></b><small>example score</small></span>
      </div>
      <ul className="sc-list">
        {['Stronger hook', 'Clear offer', 'Beat 3 rivals'].map((t, i) => (
          <motion.li key={t} initial={{ x: 20, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.5 + i * 0.35 }}>
            <motion.span className="sc-check" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.8 + i * 0.35, type: 'spring' }}>✓</motion.span>{t}
          </motion.li>
        ))}
      </ul>
    </div>
  )
}

const SCENE_VIEW = { drop: SceneDrop, spy: SceneSpy, feed: SceneFeed, plan: ScenePlan }

export function IdleStory() {
  const [i, setI] = useState(0)
  const [cycle, setCycle] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => { setI((x) => (x + 1) % SCENES.length); setCycle((c) => c + 1) }, SCENE_MS)
    return () => clearTimeout(t)
  }, [i, cycle])
  const s = SCENES[i]
  const View = SCENE_VIEW[s.key]
  return (
    <div className="story">
      <div className="st-bar">
        {SCENES.map((x, n) => (
          <button key={x.key} onClick={() => { setI(n); setCycle((c) => c + 1) }} aria-label={x.cap}>
            <span style={n < i ? { width: '100%' } : n === i ? { animation: `fill ${SCENE_MS}ms linear forwards` } : { width: 0 }} key={n === i ? cycle : 'x'} />
          </button>
        ))}
      </div>
      <div className="st-top">
        <motion.div className="st-mascot" animate={{ y: [0, -5, 0], rotate: s.key === 'spy' ? [0, -6, 6, 0] : 0 }} transition={{ duration: 1.6, repeat: Infinity }}>
          <PixelAvatar seed="scout-claude-7" gender="female" size={54} />
          {s.key === 'drop' && <motion.span className="st-wave" animate={{ rotate: [0, 22, -8, 22, 0] }} transition={{ duration: 1.2, repeat: Infinity }}>👋</motion.span>}
        </motion.div>
        <AnimatePresence mode="wait">
          <motion.div key={s.key} className="st-bubble" initial={{ opacity: 0, x: -8, scale: 0.9 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}>
            {s.say}
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="st-scene">
        <AnimatePresence mode="wait">
          <motion.div key={s.key + cycle} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -14 }} transition={{ duration: 0.3 }}>
            <View />
          </motion.div>
        </AnimatePresence>
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={s.key} className="st-cap" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          <span className="st-step">{i + 1}</span>
          <div><b>{s.cap}</b><small>{s.sub}</small></div>
        </motion.div>
      </AnimatePresence>
      <div className="st-cta">👉 Try it: add your ad and tap <b>Test it on 30 buyers</b></div>
    </div>
  )
}

export function PhoneLoader({ job }) {
  return job ? <BusyLoader job={job} /> : <IdleStory />
}

function BusyLoader({ job }) {
  const stage = job?.stage || 'idle'
  const [tick, setTick] = useState(0)
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 2600); return () => clearInterval(t) }, [])
  const msgs = BUBBLE[stage] || BUBBLE.queued
  const adsFound = (job?.logs || []).reduce((n, l) => n + Number((l.msg.match(/-> (\d+) ads fetched/) || [])[1] || 0), 0)
  const at = ORDER.indexOf(stage)
  const stepState = (key) => {
    if (!job) return 'todo'
    if (key === 'personas') return job.personas?.length ? 'done' : at >= 1 ? 'doing' : 'todo'
    const i = ORDER.indexOf(key)
    return at > i ? 'done' : at === i ? 'doing' : 'todo'
  }
  return (
    <div className={`loader ${job ? 'busy' : 'idle'}`}>
      <div className="ld-stage">
        <span className="ld-ring r1" /><span className="ld-ring r2" /><span className="ld-ring r3" />
        <div className="ld-mascot"><PixelAvatar seed="scout-claude-7" gender="female" size={74} /><span className="ld-lens">🔍</span></div>
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={stage + (tick % msgs.length)} className="ld-bubble" initial={{ opacity: 0, y: 6, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
          {msgs[tick % msgs.length]}
        </motion.div>
      </AnimatePresence>
      {job ? (
        <>
          <ul className="ld-steps">
            {STEPS.map(([k, label, icon]) => {
              const st = stepState(k)
              return (
                <li key={k} className={st}>
                  <span className="ld-ic">{st === 'done' ? '✓' : st === 'doing' ? <i className="ld-spin" /> : icon}</span>
                  {label}
                  {k === 'scraping' && adsFound > 0 && <b className="ld-count">{adsFound} ads</b>}
                </li>
              )
            })}
          </ul>
          <div className="ld-parade">
            {Array.from({ length: Math.min(30, job.personas?.length || 0) }, (_, i) => (
              <span key={i} style={{ animationDelay: `${(i % 10) * 0.35}s`, top: `${(i % 3) * 3}px` }}>
                <PixelAvatar seed={`${job.personas[i].id}-${job.personas[i].name}-${job.personas[i].role}`} gender={job.personas[i].gender} size={22} />
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className="ld-tip">💡 {TIPS[tick % TIPS.length]}</div>
      )}
      {job && <div className="ld-tip small">💡 {TIPS[tick % TIPS.length]}</div>}
    </div>
  )
}
