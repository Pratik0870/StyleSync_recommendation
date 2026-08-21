import { Link } from 'react-router-dom'
import { ProductCardSkeleton } from './ProductCard'

/** Skeletons that mirror the real results layout, so nothing jumps on load. */
export function ResultsSkeleton() {
  return (
    <div className="space-y-12" aria-busy="true" aria-label="Finding products">
      <div className="space-y-3">
        <div className="shimmer h-3 w-24 rounded" />
        <div className="shimmer h-7 w-72 max-w-full rounded" />
      </div>
      {[0, 1].map((section) => (
        <div key={section} className="space-y-4">
          <div className="shimmer h-4 w-40 rounded" />
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((card) => (
              <ProductCardSkeleton key={card} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  const offline = error?.code === 'network_error'
  return (
    <Panel
      tone="berry"
      title={offline ? 'The recommendation service is not running' : error?.message ?? 'Something went wrong'}
      body={error?.detail}
    >
      {offline && (
        <pre className="mt-4 overflow-x-auto rounded-lg bg-ink px-4 py-3 text-left text-[12px] leading-relaxed text-paper">
          python scripts/run_api.py
        </pre>
      )}
      <div className="mt-5 flex flex-wrap justify-center gap-3">
        {onRetry && <PrimaryButton onClick={onRetry}>Try again</PrimaryButton>}
        <GhostLink to="/">Start over</GhostLink>
      </div>
    </Panel>
  )
}

export function EmptyState({ notes, onRetry }) {
  return (
    <Panel
      tone="ink"
      title="No products matched this closely enough"
      body="Nothing is shown rather than filling the page with poor matches. Widening the occasion or clearing an exclusion usually helps."
    >
      <Notes notes={notes} centered />
      <div className="mt-5 flex flex-wrap justify-center gap-3">
        {onRetry && <PrimaryButton onClick={onRetry}>Try again</PrimaryButton>}
        <GhostLink to="/">New search</GhostLink>
      </div>
    </Panel>
  )
}

export function UnparsedState({ query, notes }) {
  return (
    <Panel
      tone="gold"
      title="We could not read that request"
      body={
        <>
          Nothing recognisable was found in{' '}
          <span className="font-medium text-ink">“{query}”</span>. No garment, colour,
          occasion, style or category. Rather than guess, here is the shape that works
          best.
        </>
      }
    >
      <p className="mx-auto mt-4 max-w-md rounded-lg bg-paper px-4 py-3 text-[13px] text-ink-soft">
        “I'm wearing a <b>black saree</b> to a <b>wedding</b>. I want an{' '}
        <b>elegant</b> look.”
      </p>
      <Notes notes={notes} centered />
      <div className="mt-5 flex justify-center">
        <GhostLink to="/">Try another description</GhostLink>
      </div>
    </Panel>
  )
}

export function Notes({ notes, centered = false }) {
  if (!notes?.length) return null
  return (
    <ul
      className={`mt-4 space-y-1.5 text-[13px] leading-relaxed text-ink-faint ${
        centered ? 'mx-auto max-w-xl text-center' : ''
      }`}
    >
      {notes.map((note, i) => (
        <li key={i}>{note}</li>
      ))}
    </ul>
  )
}

function Panel({ tone, title, body, children }) {
  const ring = {
    berry: 'border-berry/25 bg-berry-wash',
    gold: 'border-gold/30 bg-gold-wash',
    ink: 'border-line bg-paper-raised',
  }[tone]

  return (
    <div className={`rise rounded-[14px] border px-6 py-10 text-center sm:px-10 ${ring}`}>
      <h2 className="font-display text-2xl text-ink">{title}</h2>
      {body && (
        <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-ink-soft">
          {body}
        </p>
      )}
      {children}
    </div>
  )
}

export function PrimaryButton({ children, ...props }) {
  return (
    <button
      type="button"
      {...props}
      className="rounded-full bg-berry px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-berry-deep"
    >
      {children}
    </button>
  )
}

function GhostLink({ to, children }) {
  return (
    <Link
      to={to}
      className="rounded-full border border-line px-5 py-2.5 text-sm font-semibold text-ink transition hover:border-ink hover:bg-mist"
    >
      {children}
    </Link>
  )
}
