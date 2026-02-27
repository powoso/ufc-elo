import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

function FighterPicker({ label, value, onSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const ref = useRef()

  useEffect(() => {
    if (query.length < 2) { setResults([]); return }
    const timer = setTimeout(async () => {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
      setResults(await res.json())
      setOpen(true)
    }, 200)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className="predict-fighter-card">
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
        {label}
      </div>
      {value ? (
        <>
          <div className="predict-fighter-name">{value.name}</div>
          <div className="predict-fighter-elo">{Math.round(value.elo)}</div>
          <div className="predict-fighter-meta">{value.fights} fights</div>
          <button
            style={{ marginTop: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', padding: '6px 14px', fontSize: '0.78rem', cursor: 'pointer', fontFamily: 'inherit' }}
            onClick={() => { onSelect(null); setQuery('') }}
          >
            Change
          </button>
        </>
      ) : (
        <div className="predict-search" ref={ref}>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => results.length && setOpen(true)}
            placeholder="Type fighter name..."
            autoFocus={label === 'Fighter A'}
          />
          {open && results.length > 0 && (
            <div className="search-dropdown">
              {results.map(r => (
                <div
                  key={r.name}
                  className="search-item"
                  onClick={() => { onSelect(r); setQuery(''); setOpen(false) }}
                >
                  <span className="search-item-name">{r.name}</span>
                  <span className="search-item-elo">{r.elo ? Math.round(r.elo) : '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Predict() {
  const [fighterA, setFighterA] = useState(null)
  const [fighterB, setFighterB] = useState(null)
  const [prediction, setPrediction] = useState(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!fighterA || !fighterB) { setPrediction(null); return }
    setLoading(true)
    fetch(`/api/predict?a=${encodeURIComponent(fighterA.name)}&b=${encodeURIComponent(fighterB.name)}`)
      .then(r => r.json())
      .then(d => { setPrediction(d); setLoading(false) })
  }, [fighterA, fighterB])

  const probA = prediction?.fighter_a?.win_prob
  const probB = prediction?.fighter_b?.win_prob

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Fight Predictor</h1>
        <p className="page-subtitle">Select two fighters to compare ELO ratings and predicted win probability</p>
      </div>

      <div className="predict-layout">
        <FighterPicker label="Fighter A" value={fighterA} onSelect={setFighterA} />
        <div className="predict-vs">VS</div>
        <FighterPicker label="Fighter B" value={fighterB} onSelect={setFighterB} />
      </div>

      {loading && <div className="loading">Calculating...</div>}

      {prediction && !prediction.error && (
        <div className="prob-bar-container">
          <div className="prob-bar-outer">
            <div className="prob-bar-a" style={{ width: `${(probA * 100).toFixed(1)}%` }}>
              <span className="prob-label">{(probA * 100).toFixed(1)}%</span>
            </div>
            <div className="prob-bar-b">
              <span className="prob-label">{(probB * 100).toFixed(1)}%</span>
            </div>
          </div>
          <div className="prob-names">
            <span
              className="prob-name-a"
              style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/fighter/${encodeURIComponent(prediction.fighter_a.name)}`)}
            >
              {prediction.fighter_a.name}
            </span>
            <span
              className="prob-name-b"
              style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/fighter/${encodeURIComponent(prediction.fighter_b.name)}`)}
            >
              {prediction.fighter_b.name}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 24 }}>
            <div className="card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                ELO Advantage
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: probA > probB ? 'var(--accent-red)' : 'var(--accent-blue)' }}>
                +{Math.abs(Math.round(prediction.fighter_a.elo - prediction.fighter_b.elo))}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                {probA > probB ? prediction.fighter_a.name : prediction.fighter_b.name}
              </div>
            </div>
            <div className="card" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                Implied Odds
              </div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>
                <span style={{ color: 'var(--accent-red)' }}>
                  {probA >= 0.5 ? `-${Math.round(probA / (1 - probA) * 100)}` : `+${Math.round((1 - probA) / probA * 100)}`}
                </span>
                <span style={{ color: 'var(--text-muted)', margin: '0 10px' }}>/</span>
                <span style={{ color: 'var(--accent-blue)' }}>
                  {probB >= 0.5 ? `-${Math.round(probB / (1 - probB) * 100)}` : `+${Math.round((1 - probB) / probB * 100)}`}
                </span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                American odds (moneyline)
              </div>
            </div>
          </div>
        </div>
      )}

      {prediction?.error && (
        <div className="empty-state" style={{ color: 'var(--danger)' }}>
          {prediction.error}
        </div>
      )}
    </div>
  )
}
