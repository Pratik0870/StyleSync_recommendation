import { useEffect, useState } from 'react'
import {
  CATEGORY_PICKER,
  COLOUR_OPTIONS,
  COLOUR_SWATCH,
  GENDER_OPTIONS,
  OCCASION_OPTIONS,
  STYLE_OPTIONS,
  categoryLabel,
} from '../lib/labels'

/**
 * Shows what the backend understood, and lets the user correct it.
 *
 * Phase 3 guarantees structured fields override anything parsed from the query,
 * so every control here maps to one of those fields and is sent back verbatim.
 * Unset values render as an em dash rather than a guess.
 */
export default function IntentEditor({ intent, onApply, busy }) {
  const [draft, setDraft] = useState(() => fromIntent(intent))
  const [open, setOpen] = useState(false)

  useEffect(() => setDraft(fromIntent(intent)), [intent])

  const dirty = JSON.stringify(draft) !== JSON.stringify(fromIntent(intent))

  const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }))
  const toggleList = (key, value) =>
    setDraft((d) => ({
      ...d,
      [key]: d[key].includes(value)
        ? d[key].filter((v) => v !== value)
        : [...d[key], value],
    }))

  return (
    <section className="rounded-[14px] border border-line bg-paper-raised">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-berry">
            Showing
          </span>
          <Summary intent={intent} />
        </div>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="rounded-full border border-line px-3.5 py-1.5 text-xs font-semibold text-ink transition hover:border-ink hover:bg-mist"
        >
          {open ? 'Close' : 'Refine'}
        </button>
      </div>

      {intent?.rejected?.length > 0 && (
        <p className="mx-5 mb-4 rounded-lg bg-gold-wash px-3.5 py-2.5 text-[13px] text-ink-soft">
          Ignored, because the catalog has no such value:{' '}
          <span className="font-medium">{intent.rejected.join(', ')}</span>
        </p>
      )}

      {open && (
        <div className="space-y-5 border-t border-line px-5 py-5">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Colour">
              <ChipRow
                options={COLOUR_OPTIONS}
                value={draft.colour}
                onChange={(v) => set('colour', v)}
                renderChip={(option) => (
                  <>
                    <span
                      className="size-3 rounded-full ring-1 ring-line"
                      style={
                        COLOUR_SWATCH[option].startsWith('conic')
                          ? { background: COLOUR_SWATCH[option] }
                          : { backgroundColor: COLOUR_SWATCH[option] }
                      }
                    />
                    {option}
                  </>
                )}
              />
            </Field>

            <Field label="Occasion">
              <ChipRow
                options={OCCASION_OPTIONS}
                value={draft.occasion}
                onChange={(v) => set('occasion', v)}
              />
            </Field>

            <Field label="Style">
              <ChipRow
                options={STYLE_OPTIONS}
                value={draft.style}
                onChange={(v) => set('style', v)}
              />
            </Field>

            <Field label="Shopping for">
              <ChipRow
                options={GENDER_OPTIONS}
                value={draft.gender}
                onChange={(v) => set('gender', v)}
              />
            </Field>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Field label="Only show these" hint="Leave empty to let the engine decide">
              <CategoryPicker
                selected={draft.includeCategories}
                onToggle={(key) => toggleList('includeCategories', key)}
                tone="berry"
              />
            </Field>
            <Field label="Leave these out">
              <CategoryPicker
                selected={draft.excludeCategories}
                onToggle={(key) => toggleList('excludeCategories', key)}
                tone="ink"
              />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <button
              type="button"
              disabled={!dirty || busy}
              onClick={() => onApply(draft)}
              className="rounded-full bg-berry px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-berry-deep disabled:cursor-not-allowed disabled:bg-mist disabled:text-ink-faint"
            >
              {busy ? 'Finding products…' : 'Update recommendations'}
            </button>
            {dirty && (
              <button
                type="button"
                onClick={() => setDraft(fromIntent(intent))}
                className="text-sm font-medium text-ink-faint underline underline-offset-4 hover:text-ink"
              >
                Reset
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function Summary({ intent }) {
  const summary = describeIntent(intent)

  if (!summary) {
    return (
      <span className="text-sm text-ink-faint">
        Nothing specific found, showing a general selection
      </span>
    )
  }
  return <span className="font-display text-[17px] text-ink">{summary}</span>
}

/** Turn the parsed intent into a short phrase, e.g. "Women's red saree for a wedding". */
const OCCASION_WEAR = {
  office: 'office wear',
  formal: 'formal wear',
  casual: 'casual wear',
  sports: 'sportswear',
  wedding: 'wedding outfit',
  party: 'party outfit',
  festive: 'festive wear',
}

function describeIntent(intent) {
  if (!intent) return ''
  const { anchor_type: garment, colour, occasion, gender } = intent
  const owner = gender === 'women' ? "Women's" : gender === 'men' ? "Men's" : ''

  if (garment) {
    const item = [colour, garment].filter(Boolean).join(' ')
    const when = occasion ? ` for a ${occasion}` : ''
    const phrase = `${item}${when}`
    return owner ? `${owner} ${phrase}` : phrase.charAt(0).toUpperCase() + phrase.slice(1)
  }

  const base = OCCASION_WEAR[occasion] || (occasion ? `${occasion} wear` : '')
  if (!base) return colour ? `${colour} items` : ''
  const forWhom = gender ? ` for ${gender}` : ''
  return base.charAt(0).toUpperCase() + base.slice(1) + forWhom
}

function Field({ label, hint, children }) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.09em] text-ink-faint">
        {label}
      </p>
      {children}
      {hint && <p className="mt-2 text-[11px] text-ink-faint">{hint}</p>}
    </div>
  )
}

/** Single-select chips where clicking the active chip clears it back to unset. */
function ChipRow({ options, value, onChange, renderChip }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const active = value === option
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(active ? '' : option)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs capitalize transition ${
              active
                ? 'border-berry bg-berry text-white'
                : 'border-line bg-paper text-ink-soft hover:border-ink'
            }`}
          >
            {renderChip ? renderChip(option) : option}
          </button>
        )
      })}
    </div>
  )
}

function CategoryPicker({ selected, onToggle, tone }) {
  return (
    <div className="space-y-2.5">
      {CATEGORY_PICKER.map((group) => (
        <div key={group.family}>
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.09em] text-ink-faint">
            {group.family}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {group.keys.map((key) => {
              const active = selected.includes(key)
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => onToggle(key)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition ${
                    active
                      ? tone === 'berry'
                        ? 'border-berry bg-berry text-white'
                        : 'border-ink bg-ink text-white line-through'
                      : 'border-line bg-paper text-ink-soft hover:border-ink'
                  }`}
                >
                  {categoryLabel(key)}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function fromIntent(intent) {
  return {
    colour: intent?.colour ?? '',
    occasion: intent?.occasion ?? '',
    style: intent?.style ?? '',
    gender: intent?.gender ?? '',
    includeCategories: intent?.include_categories ?? [],
    excludeCategories: intent?.exclude_categories ?? [],
  }
}
