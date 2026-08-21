import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { postRecommend } from '../api/client'
import IntentEditor from '../components/IntentEditor'
import OutfitView, { GenderPrompt } from '../components/OutfitView'
import ProductCard from '../components/ProductCard'
import {
  EmptyState,
  ErrorState,
  Notes,
  ResultsSkeleton,
  UnparsedState,
} from '../components/States'
import { CONFIDENCE_COPY, categoryFamily, categoryLabel } from '../lib/labels'

/**
 * Results are driven entirely by the URL, so a search can be reloaded, shared
 * and navigated back to. Corrections from the intent editor are written to the
 * URL, which re-runs the request through the same path.
 */
export default function ResultsPage({ onBusyChange, onModeChange }) {
  const [params, setParams] = useSearchParams()
  const [state, setState] = useState({ status: 'loading', data: null, error: null })

  const request = useMemo(() => paramsToRequest(params), [params])
  const requestKey = JSON.stringify(request)

  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, status: 'loading' }))
    onBusyChange?.(true)

    postRecommend(request)
      .then((data) => {
        if (cancelled) return
        setState({ status: 'ready', data, error: null })
        // Report which mode actually answered, so the header cannot claim
        // smart matching for a result the parser produced.
        onModeChange?.(data.ai_status ?? null)
      })
      .catch((error) => {
        if (!cancelled) setState({ status: 'error', data: null, error })
      })
      .finally(() => {
        if (!cancelled) onBusyChange?.(false)
      })

    return () => {
      cancelled = true
    }
    // requestKey captures every field that changes the response
  }, [requestKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const retry = () => setParams(new URLSearchParams(params), { replace: true })

  // Answering "who is this for?" is just another structured correction.
  const chooseGender = (gender) => {
    const next = new URLSearchParams(params)
    next.set('gender', gender)
    setParams(next)
  }

  const applyCorrections = (draft) => {
    const next = new URLSearchParams(params)
    setOrDelete(next, 'colour', draft.colour)
    setOrDelete(next, 'occasion', draft.occasion)
    setOrDelete(next, 'style', draft.style)
    setOrDelete(next, 'gender', draft.gender)
    setListOrDelete(next, 'include', draft.includeCategories)
    setListOrDelete(next, 'exclude', draft.excludeCategories)
    setParams(next)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const busy = state.status === 'loading'

  return (
    <div className="mx-auto max-w-[1320px] px-5 py-8 lg:px-8 lg:py-12">
      {request.query && (
        <p className="mb-6 text-[13px] text-ink-faint">
          You said:{' '}
          <span className="font-display text-[17px] text-ink">“{request.query}”</span>
        </p>
      )}

      {busy && !state.data && <ResultsSkeleton />}

      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}

      {state.data && (
        <Results
          data={state.data}
          busy={busy}
          query={request.query}
          onApply={applyCorrections}
          onRetry={retry}
          onChooseGender={chooseGender}
        />
      )}
    </div>
  )
}

function Results({ data, busy, query, onApply, onRetry, onChooseGender }) {
  const { intent, recommendations, categories, notes, outfit, needs_gender: needsGender } = data
  const unparsed = notes?.some((note) => note.startsWith('Nothing usable'))

  const primaryCategories = new Set(
    (categories ?? []).filter((c) => c.role === 'primary').map((c) => c.category)
  )
  const primaryCount = recommendations.filter((p) =>
    primaryCategories.has(p.category)
  ).length

  const sections = useMemo(
    () => groupIntoSections(recommendations, categories),
    [recommendations, categories]
  )

  return (
    <div className={busy ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
      <IntentEditor intent={intent} onApply={onApply} busy={busy} />

      {needsGender ? (
        <div className="mt-8">
          <GenderPrompt occasion={intent.occasion} onChoose={onChooseGender} busy={busy} />
        </div>
      ) : outfit?.length ? (
        <>
          <div className="mt-10 border-b border-line pb-5">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="font-display text-[26px] leading-tight text-ink">
                Your outfit
              </h2>
              <p className="text-[13px] text-ink-faint">
                {recommendations.length} items found
              </p>
            </div>
            <p className="mt-3 max-w-3xl text-[13.5px] leading-relaxed text-ink-faint">
              Here are some items that work well together.
            </p>
          </div>
          <div className="mt-10">
            <OutfitView outfit={outfit} />
          </div>
        </>
      ) : unparsed && recommendations.length === 0 ? (
        <div className="mt-8">
          <UnparsedState query={query} notes={notes} />
        </div>
      ) : recommendations.length === 0 ? (
        <div className="mt-8">
          <EmptyState notes={notes} onRetry={onRetry} />
        </div>
      ) : (
        <>
          <div className="mt-10 border-b border-line pb-5">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="font-display text-[26px] leading-tight text-ink">
                {primaryCount > 0
                  ? `${primaryCount} item${primaryCount === 1 ? '' : 's'} found, plus ` +
                    `${recommendations.length - primaryCount} that go with them`
                  : `${recommendations.length} item` +
                    `${recommendations.length === 1 ? '' : 's'} found`}
              </h2>
              <p className="text-[13px] text-ink-faint">
                in {sections.length} categor{sections.length === 1 ? 'y' : 'ies'}
              </p>
            </div>
            <p className="mt-3 max-w-3xl text-[13.5px] leading-relaxed text-ink-faint">
              {primaryCount > 0
                ? 'What you searched for comes first, followed by items that go with it.'
                : 'Items from the catalog that work well with what you described.'}
            </p>
          </div>

          <div className="mt-10 space-y-14">
            {sections.map((section) => (
              <CategorySection key={section.key} section={section} />
            ))}
          </div>
        </>
      )}

      <Notes notes={notes} />

      <ThinCategories categories={categories} />
    </div>
  )
}

function CategorySection({ section }) {
  const confidence = CONFIDENCE_COPY[section.meta?.confidence]

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex items-baseline gap-3">
          <h3 className="font-display text-[22px] text-ink">{section.label}</h3>
          <span className="text-[10px] uppercase tracking-[0.16em] text-ink-faint">
            {section.products.length} items
          </span>
        </div>
        {confidence && section.meta?.confidence !== 'strong' && (
          <span className={`text-[12px] ${confidence.tone}`}>{confidence.label}</span>
        )}
      </div>

      {section.meta?.why_considered && (
        <details className="group/why mb-4">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-ink-faint transition hover:text-ink">
            Why this category
            <span className="transition group-open/why:rotate-90" aria-hidden="true">
              ›
            </span>
          </summary>
          <p className="mt-2 max-w-3xl border-l-2 border-line pl-3 text-[12.5px] leading-relaxed text-ink-faint">
            {section.meta.why_considered}
          </p>
        </details>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        {section.products.map((product, index) => (
          <ProductCard
            key={product.product_id}
            product={product}
            index={index}
            role={section.meta?.role ?? 'complement'}
          />
        ))}
      </div>
    </section>
  )
}

/** Categories the engine considered but could not fill well - stated, not hidden. */
function ThinCategories({ categories }) {
  const weak = (categories ?? []).filter(
    (c) => c.note && (c.confidence === 'thin' || c.confidence === 'none')
  )
  if (!weak.length) return null

  return (
    <details className="mt-12 rounded-[14px] border border-line bg-paper-raised px-5 py-4">
      <summary className="cursor-pointer text-[13px] font-semibold text-ink-soft">
        {weak.length} categor{weak.length === 1 ? 'y' : 'ies'} had little to offer
      </summary>
      <ul className="mt-3 space-y-2.5">
        {weak.map((category) => (
          <li key={category.category} className="text-[13px] leading-relaxed text-ink-faint">
            <span className="font-medium text-ink-soft">
              {categoryLabel(category.category)}
            </span>{' '}
            {category.note}
          </li>
        ))}
      </ul>
    </details>
  )
}

/* -------------------------------------------------------------------------- */

/**
 * Group the flat, already-ranked list into category sections.
 *
 * Insertion order is the backend's own ranking, so a category appears in the
 * position its best product earned. The client only groups - it never re-scores
 * or re-sorts, which would quietly override the engine's diversity re-ranking.
 */
function groupIntoSections(recommendations, categories) {
  const meta = new Map((categories ?? []).map((c) => [c.category, c]))
  const sections = new Map()

  recommendations.forEach((product) => {
    const key = product.category
    if (!sections.has(key)) {
      sections.set(key, {
        key,
        label: categoryLabel(key),
        family: categoryFamily(key),
        meta: meta.get(key),
        products: [],
      })
    }
    sections.get(key).products.push(product)
  })

  return [...sections.values()]
}

function paramsToRequest(params) {
  const productId = params.get('product_id')
  return {
    query: params.get('q') ?? '',
    productId: productId ? Number(productId) : undefined,
    anchorType: params.get('anchor') ?? '',
    colour: params.get('colour') ?? '',
    occasion: params.get('occasion') ?? '',
    style: params.get('style') ?? '',
    gender: params.get('gender') ?? '',
    includeCategories: splitList(params.get('include')),
    excludeCategories: splitList(params.get('exclude')),
    limit: 18,
    maxPerCategory: 4,
  }
}

const splitList = (value) => (value ? value.split(',').filter(Boolean) : [])

function setOrDelete(params, key, value) {
  if (value) params.set(key, value)
  else params.delete(key)
}

function setListOrDelete(params, key, values) {
  if (values?.length) params.set(key, values.join(','))
  else params.delete(key)
}
