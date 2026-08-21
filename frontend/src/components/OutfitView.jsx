import ProductCard from './ProductCard'
import { CONFIDENCE_COPY } from '../lib/labels'

/**
 * A whole look, in the order it is assembled: the main garment, then what goes
 * with it, then shoes, then the finishing pieces.
 *
 * Sections come from the API. Only sections with products are returned, so
 * nothing here renders an empty shelf, and a section the catalog can barely
 * fill says so instead of pretending.
 */
export default function OutfitView({ outfit, anchor, occasion, gender }) {
  if (!outfit?.length) return null

  return (
    <div className="space-y-14">
      {outfit.map((section, index) => (
        <section key={section.key} aria-labelledby={`section-${section.key}`}>
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line pb-3">
            <div className="flex items-baseline gap-3">
              <span className="font-display text-[15px] text-gold">
                {String(index + 1).padStart(2, '0')}
              </span>
              <h3
                id={`section-${section.key}`}
                className="font-display text-[22px] leading-tight text-ink"
              >
                {section.title}
              </h3>
              {section.essential && (
                <span className="text-[9.5px] uppercase tracking-[0.16em] text-ink-faint">
                  Essential
                </span>
              )}
            </div>
            {section.confidence !== 'strong' && CONFIDENCE_COPY[section.confidence] && (
              <span className={`text-[12px] ${CONFIDENCE_COPY[section.confidence].tone}`}>
                {CONFIDENCE_COPY[section.confidence].label}
              </span>
            )}
          </div>

          {section.note && (
            <p className="mb-4 max-w-3xl text-[12.5px] leading-relaxed text-ink-faint">
              {section.note}
            </p>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {section.products.map((product, i) => (
              <ProductCard
                key={product.product_id}
                product={product}
                index={i}
                role={section.key === 'main' ? 'primary' : 'complement'}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

/**
 * Asks who the look is for. Shown instead of a look when an outfit was
 * requested without a gender. Mixing men's and women's clothing into one
 * outfit is never the right answer, so the product asks rather than guesses.
 */
export function GenderPrompt({ occasion, onChoose, busy }) {
  return (
    <div className="rise rounded-[3px] border border-line bg-paper-raised px-6 py-12 text-center sm:px-12">
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">
        One thing first
      </p>
      <h2 className="mt-3 font-display text-[clamp(1.6rem,3.2vw,2.1rem)] leading-tight text-ink">
        Who is this {occasion ? `${occasion} ` : ''}look for?
      </h2>
      <p className="mx-auto mt-3 max-w-lg text-[15px] leading-relaxed text-ink-soft">
        An outfit is built from clothing, so it has to be one or the other.
      </p>

      <div className="mt-7 flex flex-wrap justify-center gap-3">
        {[
          { value: 'women', label: "Women's" },
          { value: 'men', label: "Men's" },
        ].map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={busy}
            onClick={() => onChoose(option.value)}
            className="rounded-full bg-berry px-8 py-3 text-sm font-semibold text-white transition hover:bg-berry-deep disabled:bg-mist disabled:text-ink-faint"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}
