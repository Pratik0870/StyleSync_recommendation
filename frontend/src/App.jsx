import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { getHealth } from './api/client'
import Header from './components/Header'
import BrowsePage from './pages/BrowsePage'
import HomePage from './pages/HomePage'
import HowItWorksPage from './pages/HowItWorksPage'
import ProductPage from './pages/ProductPage'
import ResultsPage from './pages/ResultsPage'

export default function App() {
  const navigate = useNavigate()
  const [health, setHealth] = useState(null)
  const [busy, setBusy] = useState(false)
  // Which mode produced the result currently on screen. The health check only
  // says whether a provider is configured; this says what actually answered.
  const [resultMode, setResultMode] = useState(null)

  // One health check on load: it tells the header whether natural-language
  // understanding is active, and surfaces a dead backend before the user types.
  useEffect(() => {
    let cancelled = false
    getHealth()
      .then((data) => !cancelled && setHealth(data))
      .catch((error) => !cancelled && setHealth({ error: error.detail ?? error.message }))
    return () => {
      cancelled = true
    }
  }, [])

  const search = useCallback(
    (query) => navigate(`/results?q=${encodeURIComponent(query)}`),
    [navigate]
  )

  return (
    <div className="flex min-h-dvh flex-col">
      <Header onSearch={search} busy={busy} health={health} mode={resultMode} />

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage onSearch={search} busy={busy} />} />
          <Route
            path="/results"
            element={<ResultsPage onBusyChange={setBusy} onModeChange={setResultMode} />}
          />
          <Route path="/browse/:section" element={<BrowsePage />} />
          <Route path="/how-it-works" element={<HowItWorksPage />} />
          <Route path="/product/:productId" element={<ProductPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <Footer />
    </div>
  )
}

function Footer() {
  return (
    <footer className="border-t border-line bg-paper-raised">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-2 px-5 py-8 text-[12px] leading-relaxed text-ink-faint lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <p>
          <span className="font-display text-[15px] text-ink">StyleSync</span>. Beauty &amp;
          fashion compatibility over an open 43,165-product catalog.
        </p>
        <p>
          Products are real catalog items. The dataset carries no prices, ratings or
          reviews, so none are shown.
        </p>
      </div>
    </footer>
  )
}
