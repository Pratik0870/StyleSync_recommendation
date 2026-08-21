import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { postRecommend } from '../api/client'
import ProductCard, { ProductCardSkeleton } from '../components/ProductCard'
import SearchBar from '../components/SearchBar'
import HowMatchThinks from '../components/HowMatchThinks'

/** Clickable examples. Each runs a real recommendation. */
const EXAMPLES = [
  { label: 'Black saree for a wedding', query: "I'm wearing a black saree to a wedding. I want an elegant look." },
  { label: 'Green kurta for Diwali', query: 'Green silk kurta for Diwali, traditional style.' },
  { label: 'Pink dress for a party', query: 'I have a pink dress for a party. Suggest makeup and accessories.' },
  { label: 'Blue shirt for dinner', query: 'Blue shirt for dinner.' },
]

/**
 * Editorial strips on the home page. Each is a real /recommend call, so nothing
 * here is mock content to fill space. If the engine returns nothing
 * for one, the strip does not render at all.
 */
const STRIPS = [
  {
    id: 'festive',
    eyebrow: 'Example',
    title: 'Goes with a red saree',
    lede: 'Gold and neutral pieces that work with a red saree.',
    request: {
      anchorType: 'saree', colour: 'red', occasion: 'festive', gender: 'women',
      limit: 4, maxPerCategory: 1,
    },
  },
  {
    id: 'beauty',
    eyebrow: 'Example',
    title: 'Makeup for a black outfit',
    lede: 'Colours that stand out against black rather than blending into it.',
    request: {
      anchorType: 'saree', colour: 'black', occasion: 'wedding', gender: 'women',
      includeCategories: ['beauty_lip', 'beauty_eye', 'beauty_nails', 'beauty_face'],
      limit: 4, maxPerCategory: 1,
    },
  },
]

export default function HomePage({ onSearch, busy }) {
  return (
    <>
      <Hero onSearch={onSearch} busy={busy} />

      {STRIPS.map((strip) => (
        <EditorialStrip key={strip.id} strip={strip} />
      ))}

      <section className="border-b border-line bg-paper-raised">
        <div className="mx-auto max-w-[1320px] px-5 py-16 lg:px-8 lg:py-20">
          <HowMatchThinks />
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[1320px] px-5 py-16 lg:px-8">
          <p className="max-w-2xl border-l-2 border-gold pl-5 text-[14px] leading-relaxed text-ink-soft">
            Every product here is a real item from an open catalog of 43,165 fashion,
            footwear, accessory and beauty products. The catalog has no prices, ratings
            or reviews, so none are shown.
          </p>
        </div>
      </section>
    </>
  )
}

/* -------------------------------------------------------------------------- */

function Hero({ onSearch, busy }) {
  return (
    <section className="relative overflow-hidden border-b border-line">
      <Backdrop />
      <div className="relative mx-auto max-w-[1320px] px-5 pb-16 pt-14 sm:pt-20 lg:px-8 lg:pb-20">
        <div className="max-w-3xl">
          <p className="mb-6 text-[10px] font-semibold uppercase tracking-[0.28em] text-berry">
            Beauty and fashion
          </p>

          <h1 className="font-display text-[clamp(2.5rem,6.4vw,4.5rem)] font-normal leading-[1.02] tracking-[-0.025em] text-ink">
            Find what completes
            <br />
            your look<span className="text-berry">.</span>
          </h1>

          <p className="mt-7 max-w-xl text-[17px] leading-relaxed text-ink-soft">
            Describe what you're wearing or what you're looking for, and StyleSync
            finds real products that go with it.
          </p>

          <div className="mt-9 max-w-2xl">
            <SearchBar
              onSubmit={onSearch}
              busy={busy}
              autoFocus
              cta="Search"
              placeholder="Tell us what you're wearing or the look you want…"
            />
          </div>

          <div className="mt-7">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-faint">
              Start here
            </p>
            <div className="flex flex-wrap gap-2.5">
              {EXAMPLES.map((example) => (
                <button
                  key={example.query}
                  type="button"
                  onClick={() => onSearch(example.query)}
                  className="group flex items-center gap-2 rounded-full border border-line bg-paper-raised px-4 py-2 text-left transition hover:border-ink"
                >
                  {[example.label].map((label) => (
                    <span key={label} className="flex items-center gap-2">
                      <span className="text-[13px] font-medium text-ink">{label}</span>
                    </span>
                  ))}
                  <span
                    aria-hidden="true"
                    className="ml-1 text-berry opacity-0 transition group-hover:opacity-100"
                  >
                    →
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/** A strip of real recommendations. Renders nothing if the engine returns none. */
function EditorialStrip({ strip }) {
  const [state, setState] = useState({ status: 'loading', products: [] })

  useEffect(() => {
    let cancelled = false
    postRecommend(strip.request)
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', products: data.recommendations ?? [] })
      })
      .catch(() => !cancelled && setState({ status: 'error', products: [] }))
    return () => {
      cancelled = true
    }
  }, [strip.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Never render an empty or broken strip - it would be decoration, not content.
  if (state.status === 'error' || (state.status === 'ready' && !state.products.length)) {
    return null
  }

  const params = new URLSearchParams({
    anchor: strip.request.anchorType,
    colour: strip.request.colour,
    occasion: strip.request.occasion,
  })
  if (strip.request.gender) params.set('gender', strip.request.gender)

  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-[1320px] px-5 py-14 lg:px-8">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">
              {strip.eyebrow}
            </p>
            <h2 className="font-display text-[27px] leading-tight text-ink">{strip.title}</h2>
            <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-ink-soft">
              {strip.lede}
            </p>
          </div>
          <Link
            to={`/results?${params}`}
            className="border-b border-ink/25 pb-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink transition hover:border-berry hover:text-berry"
          >
            See the full look
          </Link>
        </div>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {state.status === 'loading'
            ? [0, 1, 2, 3].map((i) => <ProductCardSkeleton key={i} />)
            : state.products.map((product, i) => (
                <ProductCard key={product.product_id} product={product} index={i} compact />
              ))}
        </div>
      </div>
    </section>
  )
}

/** Soft tonal wash behind the hero — decorative only. */
function Backdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -right-32 -top-40 size-[520px] rounded-full bg-berry-wash blur-3xl" />
      <div className="absolute -left-24 top-48 size-[360px] rounded-full bg-gold-wash blur-3xl" />
    </div>
  )
}
