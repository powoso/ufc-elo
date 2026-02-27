import { useState, useEffect, useRef, useCallback } from 'react'
import { Routes, Route, Link, NavLink, useNavigate } from 'react-router-dom'
import Rankings from './Rankings'
import Fighter from './Fighter'
import Predict from './Predict'
import './App.css'

function Navbar() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const ref = useRef()
  const navigate = useNavigate()

  useEffect(() => {
    if (query.length < 2) { setResults([]); return }
    const timer = setTimeout(async () => {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
      const data = await res.json()
      setResults(data)
      setOpen(true)
    }, 200)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const go = (name) => {
    setQuery('')
    setOpen(false)
    navigate(`/fighter/${encodeURIComponent(name)}`)
  }

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand">
          UFC ELO <span className="logo-badge">RATINGS</span>
        </Link>
        <div className="navbar-links">
          <NavLink to="/" end className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>Rankings</NavLink>
          <NavLink to="/predict" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>Predict</NavLink>
        </div>
        <div className="navbar-search" ref={ref}>
          <span className="search-icon">&#128269;</span>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => results.length && setOpen(true)}
            placeholder="Search fighters..."
          />
          {open && results.length > 0 && (
            <div className="search-dropdown">
              {results.map(r => (
                <div key={r.name} className="search-item" onClick={() => go(r.name)}>
                  <span className="search-item-name">{r.name}</span>
                  <span className="search-item-elo">{r.elo ? Math.round(r.elo) : '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="app">
      <Navbar />
      <Routes>
        <Route path="/" element={<Rankings />} />
        <Route path="/fighter/:name" element={<Fighter />} />
        <Route path="/predict" element={<Predict />} />
      </Routes>
    </div>
  )
}
