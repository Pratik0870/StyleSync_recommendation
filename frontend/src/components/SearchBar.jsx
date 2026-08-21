import { useState } from 'react'

export default function SearchBar({
  initialValue = '',
  onSubmit,
  busy = false,
  size = 'large',
  autoFocus = false,
  cta,
  placeholder = "Describe what you're wearing, or the look you want…",
}) {
  const [value, setValue] = useState(initialValue)
  const large = size === 'large'

  const submit = (event) => {
    event.preventDefault()
    const text = value.trim()
    if (text && !busy) onSubmit(text)
  }

  return (
    <form onSubmit={submit} className="w-full">
      <div
        className={`flex items-center gap-2 rounded-full border border-line bg-paper-raised shadow-[0_1px_2px_rgba(22,19,26,0.04)] transition focus-within:border-ink focus-within:shadow-[0_8px_30px_-16px_rgba(22,19,26,0.4)] ${
          large ? 'p-2 pl-5' : 'p-1.5 pl-4'
        }`}
      >
        <svg
          className="size-[18px] shrink-0 text-ink-faint"
          viewBox="0 0 20 20"
          fill="none"
          aria-hidden="true"
        >
          <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.5" />
          <path d="m13.5 13.5 3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>

        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus={autoFocus}
          maxLength={2000}
          aria-label="Describe your outfit, occasion or the look you want"
          placeholder={placeholder}
          className={`min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint ${
            large ? 'py-2.5 text-[16px]' : 'py-2 text-[15px]'
          }`}
        />

        <button
          type="submit"
          disabled={busy || !value.trim()}
          className={`shrink-0 rounded-full bg-berry font-semibold text-white transition hover:bg-berry-deep disabled:cursor-not-allowed disabled:bg-mist disabled:text-ink-faint ${
            large ? 'px-6 py-3 text-sm' : 'px-4 py-2 text-[13px]'
          }`}
        >
          {busy ? 'Searching…' : cta ?? 'Search'}
        </button>
      </div>
    </form>
  )
}
