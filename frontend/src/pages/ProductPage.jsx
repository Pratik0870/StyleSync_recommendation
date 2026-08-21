import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { getProduct, imageUrl } from '../api/client'
import { ColourDot } from '../components/ProductCard'
import { ErrorState } from '../components/States'
import { categoryLabel } from '../lib/labels'

/**
 * A catalog product.
 *
 * Only the attributes the catalog actually holds are shown. There is no price
 * block, no rating, no stock badge and no reviews section, because none of that
 * exists in the data. When arrived at from a recommendation, the reasoning that
 * put it there is carried through in router state and shown alongside.
 */
export default function ProductPage() {
  const { productId } = useParams()
  const { state } = useLocation()
  const navigate = useNavigate()
  const recommended = state?.product

  const [product, setProduct] = useState(null)
  const [error, setError] = useState(null)
  const [imageFailed, setImageFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setProduct(null)
    setError(null)
    getProduct(productId)
      .then((data) => !cancelled && setProduct(data))
      .catch((err) => !cancelled && setError(err))
    return () => {
      cancelled = true
    }
  }, [productId])

  if (error) {
    return (
      <div className="mx-auto max-w-[820px] px-5 py-14 lg:px-8">
        <ErrorState error={error} onRetry={() => navigate(0)} />
      </div>
    )
  }

  const src = imageUrl(product?.image?.url ?? recommended?.image?.url)
  const reference = product?.image ?? recommended?.image
  const lowRes = reference?.resolution === 'thumb'

  return (
    <div className="mx-auto max-w-[1100px] px-5 py-8 lg:px-8 lg:py-12">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-7 inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-faint transition hover:text-ink"
      >
        <span aria-hidden="true">←</span> Back
      </button>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,460px)_1fr] lg:gap-14">
        {/* ---- image ---- */}
        <div className="overflow-hidden rounded-[14px] border border-line bg-mist">
          <div className="aspect-[3/4] w-full">
            {src && !imageFailed ? (
              <img
                src={src}
                alt={product?.name ?? recommended?.name ?? 'Product image'}
                onError={() => setImageFailed(true)}
                className={
                  // object-cover on a 60x80 would crop and magnify the little
                  // detail there is. Only a real photograph fills the frame.
                  lowRes
                    ? 'h-full w-full object-contain p-10'
                    : 'h-full w-full object-cover'
                }
              />
            ) : product || recommended ? (
              <div className="flex h-full w-full items-center justify-center text-[13px] text-ink-faint">
                Image unavailable
              </div>
            ) : (
              <div className="shimmer h-full w-full" />
            )}
          </div>
        </div>

        {/* ---- details ---- */}
        <div>
          {product ? (
            <>
              <p className="text-[11px] font-semibold uppercase tracking-[0.11em] text-ink-faint">
                {product.brand || 'Unbranded'}
              </p>
              <h1 className="mt-2 font-display text-[clamp(1.65rem,3.2vw,2.4rem)] leading-tight text-ink">
                {product.name}
              </h1>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Pill>{categoryLabel(product.category)}</Pill>
                <Pill>{product.product_type}</Pill>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper-raised px-3 py-1 text-[12px] text-ink-soft">
                  <ColourDot family={product.colour_family} colour={product.colour} />
                  {product.colour}
                </span>
              </div>

              {recommended?.reasons?.length > 0 && (
                <section className="mt-8 rounded-[14px] border border-line bg-berry-wash px-5 py-5">
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.11em] text-berry">
                    Why this was recommended
                  </h2>
                  <ul className="mt-3 space-y-2.5">
                    {recommended.reasons.map((reason, i) => (
                      <li
                        key={i}
                        className="flex gap-2.5 text-[14px] leading-relaxed text-ink-soft"
                      >
                        <span className="mt-2 size-1 shrink-0 rounded-full bg-berry" />
                        {reason}
                      </li>
                    ))}
                  </ul>
                  {typeof recommended.score === 'number' && (
                    <p className="mt-4 border-t border-berry/15 pt-3 text-[12px] text-ink-faint">
                      Match score{' '}
                      <span className="font-semibold tabular-nums text-ink">
                        {Math.round(recommended.score * 100)}%
                      </span>{' '}
                      based on colour, occasion and category
                      and your stated preferences.
                    </p>
                  )}
                </section>
              )}

              <section className="mt-8">
                <h2 className="text-[11px] font-semibold uppercase tracking-[0.11em] text-ink-faint">
                  Catalog details
                </h2>
                <dl className="mt-3 divide-y divide-line border-y border-line">
                  <Row label="Product ID" value={product.product_id} />
                  <Row label="Brand" value={product.brand} />
                  <Row label="Category" value={categoryLabel(product.category)} />
                  <Row label="Product type" value={product.product_type} />
                  <Row label="Colour" value={product.colour} />
                  <Row label="Colour family" value={product.colour_family} />
                  <Row label="Suited to" value={product.gender} />
                  <Row label="Occasion" value={product.occasion} />
                </dl>
                <p className="mt-4 text-[12px] leading-relaxed text-ink-faint">
                  These are all the attributes the catalog holds for this product. It
                  contains no price, rating or review data, so none is shown.
                </p>
              </section>

              <div className="mt-8">
                <Link
                  to="/"
                  className="inline-block rounded-full border border-line px-5 py-2.5 text-sm font-semibold text-ink transition hover:border-ink hover:bg-mist"
                >
                  Start a new look
                </Link>
              </div>
            </>
          ) : (
            <DetailSkeleton />
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-6 py-2.5">
      <dt className="text-[13px] text-ink-faint">{label}</dt>
      <dd className="text-right text-[14px] capitalize text-ink">
        {value === null || value === undefined || value === '' ? (
          <span className="text-ink-faint">Not recorded</span>
        ) : (
          String(value)
        )}
      </dd>
    </div>
  )
}

function Pill({ children }) {
  return (
    <span className="rounded-full border border-line bg-paper-raised px-3 py-1 text-[12px] text-ink-soft">
      {children}
    </span>
  )
}

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <div className="shimmer h-3 w-24 rounded" />
      <div className="shimmer h-9 w-4/5 rounded" />
      <div className="flex gap-2">
        <div className="shimmer h-7 w-24 rounded-full" />
        <div className="shimmer h-7 w-20 rounded-full" />
      </div>
      <div className="shimmer h-36 w-full rounded-[14px]" />
      <div className="shimmer h-52 w-full rounded" />
    </div>
  )
}
