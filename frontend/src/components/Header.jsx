import { useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import SearchBar from './SearchBar'

/**
 * Navigation only lists destinations that do something real.
 *
 * Each entry below is a live catalog browse backed by GET /browse. A "New" tab
 * was considered and dropped: the catalog spans 2007-2019 and carries no
 * recency signal, so "New" could only ever be decorative.
 */
const NAV = [
  { to: '/browse/wardrobe', label: 'Wardrobe' },
  { to: '/browse/beauty', label: 'Beauty' },
  { to: '/browse/accessories', label: 'Accessories' },
  { to: '/browse/footwear', label: 'Footwear' },
  { to: '/how-it-works', label: 'How it works' },
]

export default function Header({ onSearch, busy, health, mode }) {
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const showInlineSearch = pathname !== '/'

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur-md">
      {/* brand row */}
      <div className="mx-auto flex max-w-[1320px] items-center gap-4 px-5 py-3.5 lg:px-8">
        <Link to="/" className="flex shrink-0 items-baseline gap-2.5" aria-label="StyleSync, home">
          <span className="font-display text-[23px] leading-none tracking-[-0.01em] text-ink">
            Style<span className="text-berry">Sync</span>
          </span>
          <span className="hidden text-[9.5px] font-semibold uppercase tracking-[0.18em] text-ink-faint sm:inline">
            Find your look. Build your outfit.
          </span>
        </Link>

        {showInlineSearch && onSearch && (
          <div className="mx-auto hidden w-full max-w-lg lg:block">
            <SearchBar size="compact" onSubmit={onSearch} busy={busy} />
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          <EngineStatus health={health} mode={mode} />
          <button
            type="button"
            className="rounded-full border border-line p-2 text-ink md:hidden"
            aria-expanded={menuOpen}
            aria-label="Toggle navigation"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path
                d={menuOpen ? 'M3 3l10 10M13 3L3 13' : 'M2 4h12M2 8h12M2 12h12'}
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* nav row */}
      <nav
        aria-label="Catalog"
        className={`border-t border-line md:border-t-0 ${menuOpen ? 'block' : 'hidden md:block'}`}
      >
        <ul className="mx-auto flex max-w-[1320px] flex-col gap-1 px-5 py-3 md:flex-row md:items-center md:justify-center md:gap-9 md:py-2.5 lg:px-8">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `block py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] transition ${
                    isActive ? 'text-berry' : 'text-ink-soft hover:text-ink'
                  }`
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  )
}

/**
 * A quiet, honest indicator of what the backend can do right now.
 *
 * The deterministic parser is a first-class path, not a degraded one, so it is
 * labelled plainly rather than as an error. The backend never sends the
 * provider's own error text, so there is nothing technical to render here.
 */
function EngineStatus({ health, mode }) {
  if (!health && !mode) return null

  if (health?.error) {
    return (
      <Badge tone="berry" dot="bg-berry" title={health.error}>
        Offline
      </Badge>
    )
  }

  // `mode` describes the result on screen and always wins; `health.llm` is only
  // the boot-time check, used before any search has run.
  const llm = mode ?? health?.llm ?? {}
  const smart = mode ? !mode.using_fallback : Boolean(llm.available)
  return (
    <Badge
      tone={smart ? 'gold' : 'mist'}
      dot={smart ? 'bg-gold' : 'bg-ink-faint'}
      title={smart ? 'AI-assisted matching' : 'Standard matching'}
    >
      <span className="hidden sm:inline">
        {smart ? 'AI-assisted matching' : 'Standard matching'}
      </span>
      <span className="sm:hidden">{smart ? 'AI-assisted' : 'Standard'}</span>
    </Badge>
  )
}

function Badge({ tone, dot, title, children }) {
  const styles = {
    gold: 'border-gold/30 bg-gold-wash text-ink-soft',
    mist: 'border-line bg-mist text-ink-soft',
    berry: 'border-berry/30 bg-berry-wash text-berry',
  }[tone]

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${styles}`}
    >
      <span className={`size-1.5 rounded-full ${dot}`} />
      {children}
    </span>
  )
}
