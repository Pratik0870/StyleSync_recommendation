import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getBrowse, imageUrl } from '../api/client'
import { ColourDot, ProductCardSkeleton } from '../components/ProductCard'
import { ErrorState } from '../components/States'
import { BROWSE_SECTIONS, categoryLabel, COLOUR_OPTIONS, COLOUR_SWATCH } from '../lib/labels'

const PAGE_SIZE = 24

/**
 * Browse the real catalog.
 *
 * This is not a recommendation surface: /browse performs no scoring, ranking
 * or colour matching. It exists so a shopper can pick something they own and
 * hand it to the engine as the anchor — which is where the actual
 * recommendation happens.
 */
export default function BrowsePage() {
  const { section } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [state, setState] = useState({ status: 'loading', data: null, error: null })

  const config = BROWSE_SECTIONS[section]
  const colour = params.get('colour') ?? ''
  const gender = params.get('gender') ?? ''

  useEffect(() => {
    if (!config) return
    let cancelled = false
    setState((s) => ({ ...s, status: 'loading' }))
    getBrowse({ ...config.params, colour: colour || undefined, gender: gender || undefined, limit: PAGE_SIZE })
      .then((data) => !cancelled && setState({ status: 'ready', data, error: null }))
      .catch((error) => !cancelled && setState({ status: 'error', data: null, error }))
    return () => {
      cancelled = true
    }
  }, [section, colour, gender]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!config) return <Navigate to="/" replace />

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next)
  }

  const products = state.data?.products ?? []

  return (
    <div className="mx-auto max-w-[1320px] px-5 py-10 lg:px-8 lg:py-14">
      <header className="max-w-2xl">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">
          Browse the catalog
        </p>
        <h1 className="font-display text-[clamp(2rem,4vw,2.8rem)] leading-tight text-ink">
          {config.title}
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">{config.lede}</p>
      </header>

      {/* filters */}
      <div className="mt-9 space-y-4 border-y border-line py-5">
        <Filter label="Colour">
          <div className="flex flex-wrap gap-1.5">
            {COLOUR_OPTIONS.map((option) => {
              const active = colour === option
              return (
                <button
                  key={option}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setFilter('colour', active ? '' : option)}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs capitalize transition ${
                    active ? 'border-berry bg-berry text-white' : 'border-line bg-paper text-ink-soft hover:border-ink'
                  }`}
                >
                  <span
                    className="size-3 rounded-full ring-1 ring-line"
                    style={
                      COLOUR_SWATCH[option].startsWith('conic')
                        ? { background: COLOUR_SWATCH[option] }
                        : { backgroundColor: COLOUR_SWATCH[option] }
                    }
                  />
                  {option}
                </button>
              )
            })}
          </div>
        </Filter>

        <Filter label="Shopping for">
          <div className="flex flex-wrap gap-1.5">
            {['women', 'men', 'unisex'].map((option) => {
              const active = gender === option
              return (
                <button
                  key={option}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setFilter('gender', active ? '' : option)}
                  className={`rounded-full border px-2.5 py-1 text-xs capitalize transition ${
                    active ? 'border-berry bg-berry text-white' : 'border-line bg-paper text-ink-soft hover:border-ink'
                  }`}
                >
                  {option}
                </button>
              )
            })}
          </div>
        </Filter>
      </div>

      {state.status === 'error' ? (
        <div className="mt-10">
          <ErrorState error={state.error} onRetry={() => navigate(0)} />
        </div>
      ) : (
        <>
          {state.data && (
            <p className="mt-6 text-[13px] text-ink-faint">
              Showing {products.length} of {state.data.total.toLocaleString()} products
              {colour ? ` in ${colour}` : ''}
              {gender ? ` for ${gender}` : ''}
            </p>
          )}

          {state.status === 'ready' && !products.length ? (
            <p className="mt-10 rounded-[3px] border border-line bg-paper-raised px-6 py-10 text-center text-[15px] text-ink-soft">
              Nothing in the catalog matches those filters. Try clearing one.
            </p>
          ) : (
            <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {state.status === 'loading'
                ? Array.from({ length: 12 }, (_, i) => <ProductCardSkeleton key={i} />)
                : products.map((product, i) => (
                    <BrowseCard
                      key={product.product_id}
                      product={product}
                      index={i}
                      anchorable={config.anchorable}
                    />
                  ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Filter({ label, children }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-6">
      <p className="w-28 shrink-0 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
        {label}
      </p>
      {children}
    </div>
  )
}

/**
 * A browse tile. Deliberately has no match score — nothing here has been
 * scored against anything, and showing a number would imply otherwise.
 */
function BrowseCard({ product, index, anchorable }) {
  const [failed, setFailed] = useState(false)
  const navigate = useNavigate()
  const src = imageUrl(product.image?.url)

  const buildLook = () => {
    navigate(`/results?product_id=${product.product_id}`)
  }

  return (
    <article
      className="rise group flex h-full flex-col overflow-hidden rounded-[3px] border border-line bg-paper-raised transition hover:border-ink/25"
      style={{ animationDelay: `${Math.min(index, 10) * 30}ms` }}
    >
      <button
        type="button"
        onClick={() => navigate(`/product/${product.product_id}`)}
        className="relative block aspect-[4/5] w-full overflow-hidden bg-white"
        aria-label={`View details for ${product.name}`}
      >
        {src && !failed ? (
          <img
            src={src}
            alt={product.name}
            loading="lazy"
            decoding="async"
            onError={() => setFailed(true)}
            className={
              product.image?.resolution === 'thumb'
                ? 'mx-auto max-h-[45%] w-auto translate-y-1/2 object-contain'
                : 'h-full w-full object-contain p-3 transition-transform duration-500 group-hover:scale-[1.04]'
            }
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center bg-mist px-3 text-center text-[11px] text-ink-faint">
            Image unavailable
          </span>
        )}
      </button>

      <div className="flex flex-1 flex-col gap-1 border-t border-line p-3.5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[9.5px] font-semibold uppercase tracking-[0.13em] text-ink-faint">
            {product.brand || 'Unbranded'}
          </p>
          <ColourDot family={product.colour_family} colour={product.colour} />
        </div>
        <p className="font-display text-[13.5px] leading-snug text-ink">{product.name}</p>
        <p className="text-[11.5px] text-ink-faint">
          {product.product_type || categoryLabel(product.category)}
        </p>

        {anchorable && product.can_be_anchor && (
          <button
            type="button"
            onClick={buildLook}
            className="mt-auto pt-3 text-left text-[10.5px] font-semibold uppercase tracking-[0.12em] text-berry transition hover:text-berry-deep"
          >
            Complete this look →
          </button>
        )}
      </div>
    </article>
  )
}
