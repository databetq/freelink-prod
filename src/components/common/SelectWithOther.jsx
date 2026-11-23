import { Fragment, useState } from 'react'
import { Input, Select } from '@/components/common/FormField'

// Select value that reveals the free-text field for anything the presets do not cover.
const OTHER = '__other__'

const asOption = (option) => (typeof option === 'string' ? { value: option, label: option } : option)

/**
 * A dropdown of ready-made choices; "อื่น ๆ (ระบุเอง)" reveals a text field for anything else.
 *
 * `value` is always the final string (the chosen preset or the typed text), so callers keep a single
 * field and need no extra state. A value that is not in the presets, such as one saved earlier,
 * opens in the text field automatically.
 *
 * Pass `options` (strings or `{ value, label }`) or `groups` (`[{ label?, options }]`) for `<optgroup>`s.
 * `customInputProps` goes to the text field, e.g. `{ type: 'number', placeholder: '…' }`.
 */
export function SelectWithOther({
  label,
  value,
  onChange,
  options = [],
  groups,
  placeholder = 'เลือก',
  otherLabel = 'อื่น ๆ (ระบุเอง)',
  customInputProps,
  error,
  hint,
  required,
  disabled,
}) {
  const [custom, setCustom] = useState(false)
  const sections = groups || [{ options }]
  const known = new Set(sections.flatMap((section) => section.options.map((option) => asOption(option).value)))
  // `custom` keeps the text field open while typing, even if the text happens to equal a preset.
  const isCustom = custom || (value !== '' && !known.has(value))

  const handleSelect = (event) => {
    const next = event.target.value
    if (next === OTHER) {
      setCustom(true)
      if (known.has(value)) onChange('')
      return
    }
    setCustom(false)
    onChange(next)
  }

  return (
    <div className="space-y-3">
      <Select
        label={label}
        value={isCustom ? OTHER : value}
        onChange={handleSelect}
        error={isCustom ? undefined : error}
        hint={isCustom ? undefined : hint}
        required={required}
        disabled={disabled}
      >
        <option value="">{placeholder}</option>
        {sections.map((section, index) => {
          const items = section.options.map(asOption).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))
          return section.label ? (
            <optgroup key={section.label} label={section.label}>
              {items}
            </optgroup>
          ) : (
            <Fragment key={index}>{items}</Fragment>
          )
        })}
        <option value={OTHER}>{otherLabel}</option>
      </Select>
      {isCustom && (
        <Input
          aria-label={`ระบุ${label}`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          error={error}
          required={required}
          disabled={disabled}
          {...customInputProps}
        />
      )}
    </div>
  )
}
