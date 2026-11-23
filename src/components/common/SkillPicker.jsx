import { useId, useMemo, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/common/Button'
import { cn } from '@/utils/cn'

const MAX_SKILL_LENGTH = 50
const MAX_MATCHES = 8

/**
 * Pick skills from suggestions first; typing filters the catalog and only offers
 * "add as new" when nothing in the catalog matches exactly.
 *
 * `suggestions` are shown before anything is typed. `catalog` powers the search and
 * fixes the casing of known skills ("react" becomes "React").
 */
export function SkillPicker({
  label,
  value,
  onChange,
  suggestions = [],
  catalog = [],
  suggestionsLabel = 'แนะนำ',
  emptyHint,
  error,
  required,
}) {
  const inputId = useId()
  const [text, setText] = useState('')
  const query = text.trim().replace(/\s+/g, ' ')
  const lowerQuery = query.toLowerCase()

  const known = useMemo(() => {
    const byKey = new Map()
    ;[...suggestions, ...catalog].forEach((skill) => {
      if (!byKey.has(skill.toLowerCase())) byKey.set(skill.toLowerCase(), skill)
    })
    return byKey
  }, [suggestions, catalog])
  const selected = useMemo(() => new Set(value.map((skill) => skill.toLowerCase())), [value])

  const add = (raw) => {
    const typed = raw.trim().replace(/\s+/g, ' ').replace(/,$/, '')
    if (!typed) return
    const skill = known.get(typed.toLowerCase()) || typed
    if (!selected.has(skill.toLowerCase())) onChange([...value, skill])
    setText('')
  }

  const remaining = suggestions.filter((skill) => !selected.has(skill.toLowerCase()))
  const matches = query
    ? [...known.values()]
        .filter((skill) => skill.toLowerCase().includes(lowerQuery) && !selected.has(skill.toLowerCase()))
        .slice(0, MAX_MATCHES)
    : []
  const alreadyKnown = known.has(lowerQuery) || selected.has(lowerQuery)

  return (
    <div>
      <label htmlFor={inputId} className="field-label">
        {label} {required && <span className="text-rose-500">*</span>}
      </label>
      <div className="flex gap-2">
        <input
          id={inputId}
          value={text}
          maxLength={MAX_SKILL_LENGTH}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ',') {
              event.preventDefault()
              add(text)
            }
          }}
          placeholder="ค้นหาหรือพิมพ์ทักษะ เช่น React"
          className={cn('field-control', error && 'field-error')}
          aria-invalid={Boolean(error)}
          autoComplete="off"
        />
        <Button type="button" variant="secondary" size="md" icon={Plus} onClick={() => add(text)} disabled={!query}>
          เพิ่ม
        </Button>
      </div>
      {error && <p className="mt-1.5 text-xs font-medium text-rose-600" role="alert">{error}</p>}

      <div className="mt-2.5" aria-live="polite">
        {query ? (
          <>
            {matches.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {matches.map((skill) => (
                  <SuggestionChip key={skill} onClick={() => add(skill)}>
                    {skill}
                  </SuggestionChip>
                ))}
              </div>
            )}
            {!alreadyKnown && (
              <button
                type="button"
                onClick={() => add(query)}
                className="mt-1.5 inline-flex items-center gap-1 text-[11.5px] font-semibold text-brand-700 hover:underline"
              >
                <Plus className="h-3 w-3" aria-hidden="true" />
                {matches.length === 0 ? `ไม่พบในรายการแนะนำ — เพิ่ม “${query}” เป็นทักษะใหม่` : `เพิ่ม “${query}” เป็นทักษะใหม่`}
              </button>
            )}
          </>
        ) : remaining.length > 0 ? (
          <>
            <p className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-wide text-ink-400">
              {suggestionsLabel}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {remaining.map((skill) => (
                <SuggestionChip key={skill} onClick={() => add(skill)}>
                  {skill}
                </SuggestionChip>
              ))}
            </div>
          </>
        ) : (
          emptyHint && <p className="text-[11px] text-ink-400">{emptyHint}</p>
        )}
      </div>

      {value.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-ink/[0.06] pt-3">
          {value.map((skill) => (
            <span
              key={skill}
              className="inline-flex items-center gap-1 rounded-lg border border-brand-100 bg-brand-50 px-2.5 py-1 text-[11px] font-medium text-brand-700"
            >
              {skill}
              <button
                type="button"
                onClick={() => onChange(value.filter((item) => item !== skill))}
                className="rounded p-0.5 transition hover:bg-brand-100"
                aria-label={`ลบทักษะ ${skill}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function SuggestionChip({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-lg border border-ink/10 bg-white px-2.5 py-1 text-[11px] font-medium text-ink-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
    >
      <Plus className="h-3 w-3 text-ink-300" aria-hidden="true" />
      {children}
    </button>
  )
}
