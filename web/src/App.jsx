import { motion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { FeedControls, GridLegend, PersonaGrid, PhoneFeed, StatBar, usePlayback } from './components/Lab.jsx'
import Results from './components/Results.jsx'

const STAGES = {
  queued: 'Starting…', understanding: 'Reading your ad…', scraping: 'Scanning Facebook Ads Library…',
  analysing: 'Analysing competitors…', simulating: 'Showing ads to 30 buyers…', reviewing: 'Reviewing your hook & edge…', done: 'Done', error: 'Error',
}

function ClaudeMark({ size = 22 }) {
  const rays = Array.from({ length: 12 }, (_, i) => i * 30)
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {rays.map((a, i) => <rect key={a} x="11" y={i % 2 ? 2.5 : 1} width="2" height={i % 2 ? 8.5 : 10} rx="1" fill="#D97757" transform={`rotate(${a} 12 12)`} />)}
    </svg>
  )
}

function InputPanel({ onSubmit, busy }) {
  const [kind, setKind] = useState('text')
  const [text, setText] = useState('')
  const [brand, setBrand] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [country, setCountry] = useState('IN')
  useEffect(() => {
    if (!file) return setPreview(null)
    const u = URL.createObjectURL(file); setPreview(u); return () => URL.revokeObjectURL(u)
  }, [file])
  const [url, setUrl] = useState('')
  const ok = kind === 'text' ? text.trim() : kind === 'link' ? /^https?:\/\/\S+\.\S+/i.test(url.trim()) : file
  return (
    <form className="input-panel" onSubmit={(e) => { e.preventDefault(); ok && onSubmit({ kind, text: kind === 'link' ? url.trim() : text, brand, file: kind === 'link' ? null : file, country }) }}>
      <div className="seg">
        {['text', 'image', 'video', 'link'].map((k) => (
          <button type="button" key={k} className={kind === k ? 'on' : ''} onClick={() => { setKind(k); setFile(null) }}>{k}</button>
        ))}
      </div>
      {kind === 'link' && (
        <div className="link-box">
          <input type="url" placeholder="https://… your ad, product or landing page link" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus />
          <small>Instagram / Facebook / YouTube reel or post, product page, or a direct image / video link. Videos get the full video analysis (frames, voiceover, timeline); image posts and pages get the full image analysis.</small>
        </div>
      )}
      {(kind === 'image' || kind === 'video') && (
        <label className="drop">
          <input type="file" accept={kind === 'image' ? 'image/*' : 'video/*'} onChange={(e) => setFile(e.target.files?.[0] || null)} />
          {preview ? (kind === 'image' ? <img src={preview} alt="" /> : <video src={preview} muted autoPlay loop />)
            : <span>Drop or choose your {kind} ad</span>}
        </label>
      )}
      {kind !== 'link' && <textarea placeholder={kind === 'text' ? 'Paste your ad copy exactly as it runs (first line = your hook)…' : `Optional: your ad's caption, the text shown above the ${kind} in the feed`}
        value={text} onChange={(e) => setText(e.target.value)} rows={kind === 'text' ? 5 : 2} />}
      <div className="row">
        <input placeholder="Your brand / page names, comma separated (optional)" value={brand} onChange={(e) => setBrand(e.target.value)} />
        <input className="cc" value={country} maxLength={2} onChange={(e) => setCountry(e.target.value.toUpperCase())} title="Ads Library country" />
      </div>
      <button className="btn primary" disabled={!ok || busy}>{busy ? 'Running…' : 'Test it on 30 buyers →'}</button>
    </form>
  )
}

export default function App() {
  const [job, setJob] = useState(null)
  const [err, setErr] = useState(null)
  const poll = useRef(null)

  const submit = async ({ kind, text, brand, file, country }) => {
    setErr(null); setJob({ stage: 'queued', logs: [] })
    const fd = new FormData()
    fd.append('kind', kind); fd.append('text', text); fd.append('brand', brand); fd.append('country', country || 'IN')
    if (file) fd.append('file', file)
    try {
      const r = await fetch('/api/analyze', { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json()).detail || 'Request failed')
      const { job_id } = await r.json()
      clearInterval(poll.current)
      poll.current = setInterval(async () => {
        try {
          const j = await (await fetch(`/api/jobs/${job_id}`)).json()
          setJob(j)
          if (j.stage === 'done' || j.stage === 'error') clearInterval(poll.current)
        } catch { /* transient network hiccup: retry on next tick */ }
      }, 1200)
    } catch (e) { setErr(e.message); setJob(null) }
  }
  useEffect(() => () => clearInterval(poll.current), [])

  const busy = job && !['done', 'error'].includes(job.stage)
  const pb = usePlayback(job?.feed, job?.reactions, !!job?.feed)

  // live counters for the ad currently on screen
  const live = useMemo(() => {
    const rs = pb.result?.reactions || []
    const shown = (job?.personas || []).map((p, pos) => ({ p, r: rs.find((x) => x.id === p.id), on: pb.revealedRank(pos) })).filter((x) => x.r && x.on)
    const stopped = shown.filter((x) => x.r.stopped)
    return {
      stopped: stopped.length,
      avgWatch: shown.length ? shown.reduce((s, x) => s + x.r.watch_seconds, 0) / shown.length : 0,
      ctr: shown.length ? (100 * shown.filter((x) => x.r.clicked).length) / 30 : 0,
    }
  }, [pb.result, pb.elapsed, job?.personas])

  // per-persona tally of ads they stopped on (up to the current ad)
  const totals = useMemo(() => {
    const t = {}
    ;(job?.feed || []).slice(0, pb.idx).forEach((ad) => {
      const r = job.reactions?.find((x) => x.ad_id === ad.id)
      r?.reactions?.forEach((x) => { if (x.stopped) t[x.id] = (t[x.id] || 0) + 1 })
    })
    ;(job?.personas || []).forEach((p, pos) => {
      const x = pb.result?.reactions?.find((y) => y.id === p.id)
      if (x?.stopped && pb.revealedRank(pos)) t[p.id] = (t[p.id] || 0) + 1
    })
    return t
  }, [job?.feed, job?.reactions, job?.personas, pb.idx, pb.result, pb.elapsed])

  const adsFound = job?.ads_found ?? 0
  const lastLogs = (job?.logs || []).slice(-4)

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><ClaudeMark /> <span>Persona Ad Lab</span></div>
        <span className="muted">Claude-style · Facebook Ads Library · 30 simulated buyers</span>
      </header>

      <section className="hero">
        <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          Will your ad <span className="clay">survive the scroll?</span>
        </motion.h1>
        <p className="sub">Drop in your ad. We pull your real competitors from the Facebook Ads Library, put everyone in one feed and let 30 AI buyers decide who wins the thumb.</p>
      </section>

      <StatBar adIdx={pb.idx} feedLen={job?.feed?.length} buyers={job?.personas?.length} stopped={live.stopped}
        avgWatch={live.avgWatch} ctr={live.ctr} adsFound={adsFound} />

      <section className="lab">
        <div className="lab-left">
          <PhoneFeed ad={pb.current} job={job} result={pb.result} stoppedNow={live.stopped} />
          {job?.feed && <FeedControls feed={job.feed} pb={pb} />}
        </div>
        <div className="lab-right">
          {!job && <InputPanel onSubmit={submit} busy={busy} />}
          {job && (
            <div className="grid-head">
              <div className="eyebrow">The Scroll Test · live</div>
              <h2>30 strangers. 3 seconds. <em>Will your ad stop their thumb?</em></h2>
              <p>Every card is an AI buyer scrolling the feed on the left. Orange means that ad just stopped them.</p>
            </div>
          )}
          {job && <PersonaGrid personas={job.personas} playback={pb} totals={totals} busy={busy && !pb.result} />}
          {job && <GridLegend />}
          {job && (
            <div className="ticker">
              <span className={`dot ${busy ? 'live' : ''}`} /> <b>{STAGES[job.stage]}</b>
              {lastLogs.map((l, i) => <div key={i} className="log"><span>{l.t}s</span> {l.msg}</div>)}
              {job.stage === 'error' && <div className="error">{job.error}</div>}
              {!busy && <button className="btn ghost small" onClick={() => setJob(null)}>← Test another ad</button>}
            </div>
          )}
          {err && <div className="error">{err}</div>}
        </div>
      </section>

      {job?.stage === 'done' && <Results job={job} />}
      <footer>Simulated reactions are AI estimates, not real audience data. Ads data: public Facebook Ads Library.</footer>
    </div>
  )
}
