import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8,
      padding: '10px 14px', fontSize: '0.8rem', lineHeight: 1.6
    }}>
      <div style={{ fontWeight: 700 }}>{d.opponent && `vs ${d.opponent}`}</div>
      <div style={{ color: '#8888aa' }}>{d.event}</div>
      <div style={{ color: '#8888aa' }}>{d.date}</div>
      <div style={{ marginTop: 4 }}>
        <span style={{ fontWeight: 700, color: d.elo > d.prevElo ? '#22c55e' : '#ef4444' }}>
          {Math.round(d.elo)}
        </span>
        <span style={{ color: '#55556a', marginLeft: 6 }}>
          ({d.elo > d.prevElo ? '+' : ''}{(d.elo - d.prevElo).toFixed(1)})
        </span>
      </div>
    </div>
  )
}

export default function Fighter() {
  const { name } = useParams()
  const decodedName = decodeURIComponent(name)
  const [fighter, setFighter] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    fetch(`/api/fighter/${encodeURIComponent(decodedName)}`)
      .then(r => r.json())
      .then(d => { setFighter(d); setLoading(false) })
  }, [decodedName])

  if (loading) return <div className="page"><div className="loading">Loading fighter...</div></div>
  if (!fighter || fighter.error) return <div className="page"><div className="empty-state">{fighter?.error || 'Fighter not found'}</div></div>

  const unified = fighter.ratings.unified
  const chartData = []
  if (fighter.trajectory.length) {
    chartData.push({
      date: fighter.trajectory[0].date,
      elo: fighter.trajectory[0].elo_before,
      prevElo: fighter.trajectory[0].elo_before,
      event: '',
      opponent: '',
    })
    fighter.trajectory.forEach((t, i) => {
      chartData.push({
        date: t.date,
        elo: t.elo_after,
        prevElo: t.elo_before,
        event: t.event,
        opponent: t.opponent,
        outcome: t.outcome,
        method: t.method,
      })
    })
  }

  const divisionRatings = Object.entries(fighter.ratings)
    .filter(([k]) => k !== 'unified')
    .sort((a, b) => b[1].elo - a[1].elo)

  return (
    <div className="page">
      <div className="fighter-header">
        <div style={{ flex: 1 }}>
          <h1 className="fighter-name-big">{fighter.name}</h1>
          <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
            {divisionRatings.map(([div, r]) => (
              <div key={div} className="division-rating-chip">
                <span className="chip-label">{div}</span>
                <span className="chip-value">{Math.round(r.elo)}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="fighter-elo-big">{unified ? Math.round(unified.elo) : '—'}</div>
          <div className="fighter-elo-label">Unified ELO</div>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#22c55e' }}>{fighter.record.wins}</div>
          <div className="stat-label">Wins</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#ef4444' }}>{fighter.record.losses}</div>
          <div className="stat-label">Losses</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#8888aa' }}>{fighter.record.draws}</div>
          <div className="stat-label">Draws</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#d4a843' }}>{fighter.record.finishes}</div>
          <div className="stat-label">Finishes</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#e53e3e' }}>{Math.round(fighter.peak_elo)}</div>
          <div className="stat-label">Peak ELO</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{unified?.fights || 0}</div>
          <div className="stat-label">UFC Fights</div>
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-title">ELO TRAJECTORY</div>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="eloGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#e53e3e" stopOpacity={0.45} />
                <stop offset="95%" stopColor="#e53e3e" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#55556a' }}
              tickLine={false}
              axisLine={{ stroke: '#1e1e2e' }}
              tickFormatter={d => d?.slice(0, 4)}
              minTickGap={60}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#55556a' }}
              tickLine={false}
              axisLine={false}
              domain={['auto', 'auto']}
              width={45}
            />
            <ReferenceLine y={1500} stroke="#2a2a3a" strokeDasharray="4 4" />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="elo"
              stroke="#e53e3e"
              strokeWidth={2}
              fill="url(#eloGrad)"
              dot={false}
              activeDot={{ r: 4, fill: '#e53e3e', stroke: '#16161f', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 14px 8px', borderBottom: '1px solid var(--border-light)' }}>
          <div className="chart-title" style={{ margin: 0 }}>FIGHT LOG</div>
        </div>
        <div className="fight-log">
          {[...fighter.trajectory].reverse().map((t, i) => {
            const change = t.elo_after - t.elo_before
            return (
              <div
                key={i}
                className="fight-row"
                onClick={() => navigate(`/fighter/${encodeURIComponent(t.opponent)}`)}
              >
                <span className={`fight-outcome ${t.outcome}`}>
                  {t.outcome === 'win' ? 'W' : t.outcome === 'loss' ? 'L' : 'D'}
                </span>
                <span className="fight-opponent">
                  {t.opponent}
                  {t.is_title && <span className="title-badge">TITLE</span>}
                </span>
                <span className="fight-method">{t.method}{t.round ? ` R${t.round}` : ''}</span>
                <span className={`fight-elo-change ${change >= 0 ? 'positive' : 'negative'}`}>
                  {change >= 0 ? '+' : ''}{change.toFixed(1)}
                </span>
                <span className="fight-date">{t.date}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
