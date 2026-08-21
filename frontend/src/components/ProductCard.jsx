import { useState } from 'react'
import { Link } from 'react-router-dom'
import { imageUrl } from '../api/client'
import { categoryLabel, COLOUR_SWATCH, productLabel } from '../lib/labels'

/**
 * One recommended product.
 *
 * Shows only fields the catalog actually has. There is no price, rating,
 * review count, stock or popularity here because the dataset has none.
 * Inventing them would make this look like a shop but would be dishonest.
 */
export default function ProductCard({ product, index = 0, showScore = true, compact = false, role = 'complement' }) {
  const [imageFailed, setImageFailed] = useState(false)
  const [showWhy, setShowWhy] = useState(false)

  const src = imageUrl(product.image?.url)
  const reasons = product.reasons ?? []
  // A 60x80 thumbnail stretched across a 278x351 card is a 4.4x upscale, which
  // is what "blurry" actually looked like. When 60x80 is genuinely all the
  // catalog has, show it at a size it can support instead of enlarging it.
  const lowRes = product.image?.resolution === 'thumb'
  const soft = product.image?.detail === 'soft'

  return (
    <article
      className="group rise flex h-full flex-col overflow-hidden rounded-[3px] border border-line bg-paper-raised transition duration-300 hover:border-ink/25 hover:shadow-[0_18px_48px_-28px_rgba(22,19,26,0.5)]"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <Link
        to={`/product/${product.product_id}`}
        state={{ product }}
        className="relative block aspect-[4/5] overflow-hidden bg-white"
        aria-label={`View details for ${product.name}`}
      >
        {src && !imageFailed ? (
          lowRes ? (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-3">
              <img
                src={src}
                alt={product.name}
                loading="lazy"
                decoding="async"
                width={product.image?.width ?? 60}
                height={product.image?.height ?? 80}
                onError={() => setImageFailed(true)}
                className="max-h-[45%] w-auto object-contain"
              />
              <span className="text-[9px] uppercase tracking-[0.14em] text-ink-faint">
                Low quality image
              </span>
            </div>
          ) : (
            <img
              src={src}
              alt={product.name}
              loading="lazy"
              decoding="async"
              onError={() => setImageFailed(true)}
              className="h-full w-full object-contain p-3 transition-transform duration-500 group-hover:scale-[1.035]"
            />
          )
        ) : (
          <ImageFallback colour={product.colour} />
        )}

        {soft && (
          <span className="absolute bottom-2 right-2 rounded-full bg-ink/70 px-2 py-0.5 text-[9px] uppercase tracking-[0.12em] text-paper">
            Low quality
          </span>
        )}

        {showScore && typeof product.score === 'number' && (
          <span className="absolute left-0 top-3 bg-ink/90 py-1 pl-3 pr-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-paper backdrop-blur">
            {Math.round(product.score * 100)}% {role === 'primary' ? 'match' : 'goes with'}
          </span>
        )}
      </Link>

      <div className="flex flex-1 flex-col gap-1.5 border-t border-line p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            {product.brand || 'Unbranded'}
          </p>
          <ColourDot family={product.colour_family} colour={product.colour} />
        </div>

        <Link
          to={`/product/${product.product_id}`}
          state={{ product }}
          className="font-display text-[15px] leading-snug text-ink transition hover:text-berry"
        >
          {product.name}
        </Link>

        <p className="text-[12px] text-ink-faint">
          {productLabel(product) || categoryLabel(product.category)}
        </p>

        {!compact && reasons[0] && (
          <p className="mt-2 border-t border-line pt-3 text-[12.5px] leading-relaxed text-ink-soft">
            {reasons[0]}
          </p>
        )}

        {!compact && reasons.length > 1 && (
          <div className="mt-auto pt-2">
            <button
              type="button"
              onClick={() => setShowWhy((v) => !v)}
              aria-expanded={showWhy}
              className="text-[11px] font-semibold uppercase tracking-[0.1em] text-berry transition hover:text-berry-deep"
            >
              {showWhy ? 'Hide details' : 'Why this item?'}
            </button>

            {showWhy && (
              <div className="mt-3 space-y-2.5 border-t border-line pt-3">
                {reasons.map((reason, i) => (
                  <p key={i} className="text-[12px] leading-relaxed text-ink-soft">
                    {reason}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {!compact && (
          <Link
            to={`/product/${product.product_id}`}
            state={{ product }}
            className="mt-3 inline-block self-start border-b border-ink/25 pb-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink transition hover:border-berry hover:text-berry"
          >
            View details
          </Link>
        )}
      </div>
    </article>
  )
}

/** One scored signal, shown as a labelled bar with the engine's own wording. */
/** The product's colour, as a small swatch beside the brand. */
export function ColourDot({ family, colour }) {
  const hex = COLOUR_SWATCH[family]
  if (!hex) return null
  return (
    <span
      title={colour || family}
      aria-label={colour || family}
      className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full border border-ink/15"
      style={{ backgroundColor: hex }}
    />
  )
}


function ImageFallback({ colour }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-mist text-ink-faint">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M3 17.5 8.5 12l3.5 3.5L15.5 12 21 17.5M3 6h18v12H3z"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="px-3 text-center text-[11px]">
        Image unavailable
      </span>
    </div>
  )
}

export function ProductCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-[3px] border border-line bg-paper-raised">
      <div className="shimmer aspect-[4/5] w-full" />
      <div className="space-y-2.5 border-t border-line p-4">
        <div className="shimmer h-2.5 w-20 rounded" />
        <div className="shimmer h-3.5 w-full rounded" />
        <div className="shimmer h-3 w-2/3 rounded" />
        <div className="shimmer mt-3 h-3 w-5/6 rounded" />
      </div>
    </div>
  )
}
