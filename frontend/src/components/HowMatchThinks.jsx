/**
 * The five steps a request actually goes through.
 *
 * Written for a shopper, not an evaluator. No weights, no component names, no
 * jargon. The technical detail is available where it belongs: on each product
 * card, behind "Why this match?", showing the real scored signals.
 */
const STEPS = [
  {
    n: '01',
    title: 'Understand your request',
    body: 'Your sentence is turned into garment, colour, occasion and style. Anything unrecognised is reported, never guessed.',
  },
  {
    n: '02',
    title: 'Match your preferences',
    body: 'Corrections you make take priority over anything read from your words.',
  },
  {
    n: '03',
    title: 'Find compatible products',
    body: 'Colours are checked against what you are wearing, so you get an accent on a neutral a grounding tone on something saturated.',
  },
  {
    n: '04',
    title: 'Rank and diversify',
    body: 'The strongest matches rise, then near-duplicates are pushed apart so you see a spread of brands and colours.',
  },
  {
    n: '05',
    title: 'Explain every recommendation',
    body: 'Each product carries the reason it was chosen. Nothing appears without one.',
  },
]

export default function HowMatchThinks({ heading = 'How Match thinks' }) {
  return (
    <div>
      <div className="max-w-2xl">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-gold">
          Explainable by design
        </p>
        <h2 className="font-display text-[clamp(1.7rem,3.4vw,2.2rem)] leading-tight text-ink">
          {heading}
        </h2>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
          Match is not a search box. It starts from something you already have and works
          out what goes <em>with</em> it, across beauty, jewellery, bags and footwear.
        </p>
      </div>

      <ol className="mt-11 grid gap-x-8 gap-y-9 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((step) => (
          <li key={step.n}>
            <p className="font-display text-[24px] leading-none text-gold">{step.n}</p>
            <h3 className="mt-3 text-[14px] font-semibold leading-snug text-ink">
              {step.title}
            </h3>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">{step.body}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
