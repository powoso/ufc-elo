import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function Sparkline({ data, width = 80, height = 24 }) {
  if (!data || data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / range) * (height - 4) - 2
    return `${x},${y}`
  }).join(' ')

  const trending = data[data.length - 1] >= data[0]
  const color = trending ? '#22c55e' : '#ef4444'

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.7"
      />
    </svg>
  )
}

function eloClass(elo) {
  if (elo >= 1800) return 'elo-elite'
  if (elo >= 1650) return 'elo-high'
  if (elo >= 1550) return 'elo-mid'
  return 'elo-low'
}

function rankClass(rank) {
  if (rank === 1) return 'rank-cell top-1'
  if (rank === 2) return 'rank-cell top-2'
  if (rank === 3) return 'rank-cell top-3'
  return 'rank-cell'
}

export default function Rankings() {
  const [data, setData] = useState([])
  const [classes, setClasses] = useState([])
  const [active, setActive] = useState('unified')
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/weight-classes').then(r => r.json()).then(setClasses)
    fetch('/api/stats').then(r => r.json()).then(setStats)
  }, [])

  useEffect(() => {
    setLoading(true)
    fetch(`/api/leaderboard?type=${encodeURIComponent(active)}&limit=50&min_fights=${active === 'unified' ? 5 : 3}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
  }, [active])

  const divisions = [
    { name: 'unified', label: 'All Divisions' },
    ...classes.map(c => ({ name: c.name, label: c.name }))
  ]

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Fighter Rankings</h1>
        <p className="page-subtitle">ELO ratings calculated from {stats?.total_fights?.toLocaleString() || '...'} fights across UFC history</p>
      </div>

      {stats && (
        <div className="stats-bar">
          <div className="stats-bar-item"><strong>{stats.total_fighters.toLocaleString()}</strong>fighters</div>
          <div className="stats-bar-item"><strong>{stats.total_fights.toLocaleString()}</strong>fights</div>
          <div className="stats-bar-item"><strong>{stats.title_fights}</strong>title bouts</div>
          <div className="stats-bar-item"><strong>{stats.date_from?.slice(0,4)}–{stats.date_to?.slice(0,4)}</strong>span</div>
        </div>
      )}

      <div className="division-tabs">
        {divisions.map(d => (
          <button
            key={d.name}
            className={`division-tab ${active === d.name ? 'active' : ''}`}
            onClick={() => setActive(d.name)}
          >
            {d.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading">Loading rankings...</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="rankings-table">
            <thead>
              <tr>
                <th style={{ width: 50 }}>#</th>
                <th>Fighter</th>
                <th className="right">ELO</th>
                <th className="right">Fights</th>
                <th style={{ width: 100 }}>Trend</th>
              </tr>
            </thead>
            <tbody>
              {data.map(r => (
                <tr key={r.name} onClick={() => navigate(`/fighter/${encodeURIComponent(r.name)}`)}>
                  <td className={rankClass(r.rank)}>{r.rank}</td>
                  <td className="fighter-name">{r.name}</td>
                  <td className={`right elo-cell ${eloClass(r.elo)}`}>{Math.round(r.elo)}</td>
                  <td className="right fights-cell">{r.fights}</td>
                  <td className="sparkline-cell">
                    <Sparkline data={r.sparkline} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
