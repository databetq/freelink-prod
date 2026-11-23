import { ExternalLink } from 'lucide-react'

export function WorkLinks({ submission }) {
  const links = submission.links?.length ? submission.links : submission.link ? [{ url: submission.link }] : []
  if (!links.length) return null

  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {links.map(({ url, label }, index) => (
        <li key={`${index}:${url}`} className="min-w-0 max-w-full">
          <a href={url} target="_blank" rel="noreferrer"
            className="inline-flex max-w-full items-center gap-2 rounded-lg border border-ink/10 px-3 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-50">
            <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate" title={url}>{label || url}</span>
          </a>
        </li>
      ))}
    </ul>
  )
}
