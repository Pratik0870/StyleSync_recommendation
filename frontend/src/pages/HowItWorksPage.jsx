import { Link } from 'react-router-dom'
import HowMatchThinks from '../components/HowMatchThinks'

/**
 * A real page, not a marketing placeholder: it explains the actual mechanism
 * and links into the parts of the product that demonstrate it.
 */
export default function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-[1320px] px-5 py-12 lg:px-8 lg:py-16">
      <HowMatchThinks heading="How Match works" />

      <div className="mt-16 grid gap-10 border-t border-line pt-12 lg:grid-cols-3">
        <Panel title="A complement is not a duplicate">
          Search engines answer “what is similar to this?”. StyleSync answers “what goes
          <em> with</em> this?”. Ask for something to wear with black and you get
          metallics and accents, not more black. Tonal matches are scored, but they are
          scored below a genuine pairing on purpose.
        </Panel>

        <Panel title="Fashion and beauty, one colour vocabulary">
          The catalog holds clothing, accessories, footwear and beauty under a single set
          of colour families. That shared vocabulary is what makes matching a lipstick to
          a saree possible at all, rather than a guess across two unrelated datasets.
        </Panel>

        <Panel title="Not every colour means the same thing">
          A foundation shade matches a face, and a perfume bottle matches nothing. Those
          products are still recommended where they fit, but they are never
          colour-matched to your outfit, so the engine tracks which kind of colour each
          product carries.
        </Panel>
      </div>

      <div className="mt-16 rounded-[3px] border border-line bg-paper-raised px-6 py-10 text-center sm:px-12">
        <h2 className="font-display text-[26px] text-ink">See it on a real look</h2>
        <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-ink-soft">
          Open any recommendation and choose “Why this item?” to see the actual scored
          signals (colour, occasion, category and preference) that placed it there.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            to={`/results?${new URLSearchParams({
              q: "I'm wearing a black saree to a wedding. I want an elegant look.",
            })}`}
            className="rounded-full bg-berry px-6 py-3 text-sm font-semibold text-white transition hover:bg-berry-deep"
          >
            Try the black saree look
          </Link>
          <Link
            to="/browse/wardrobe"
            className="rounded-full border border-line px-6 py-3 text-sm font-semibold text-ink transition hover:border-ink hover:bg-mist"
          >
            Start from your wardrobe
          </Link>
        </div>
      </div>

      <section className="mt-16 border-t border-line pt-12">
        <h2 className="font-display text-[22px] text-ink">What this product does not do</h2>
        <ul className="mt-4 max-w-3xl space-y-2.5 text-[14px] leading-relaxed text-ink-soft">
          <li>
            It does not show prices, ratings, reviews or stock, because the open catalog behind
            it has none, and inventing them would make everything else here untrustworthy.
          </li>
          <li>
            It does not generate outfits. You bring the garment; StyleSync completes it.
          </li>
          <li>
            It does not let a language model pick products. The model only reads your
            sentence into structured attributes; every product comes from the catalog
            through a deterministic engine.
          </li>
        </ul>
      </section>
    </div>
  )
}

function Panel({ title, children }) {
  return (
    <div>
      <h3 className="font-display text-[19px] leading-snug text-ink">{title}</h3>
      <p className="mt-3 text-[14px] leading-relaxed text-ink-soft">{children}</p>
    </div>
  )
}
