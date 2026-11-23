import { FileText } from 'lucide-react'
import { projectService } from '@/services/api/projectService'

export function WorkAttachments({ projectId, files }) {
  if (!files?.length) return null

  return (
    <div className="mt-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">ไฟล์แนบ</p>
      <ul className="mt-2 space-y-1.5">
        {files.map((file) => (
          <li key={file.id || file} className="flex items-center gap-2 rounded-lg border border-ink/[0.07] bg-white px-3 py-2 text-[11.5px] text-ink-600">
            <FileText className="h-3.5 w-3.5 shrink-0 text-brand-600" aria-hidden="true" />
            {file.id ? (
              <a className="min-w-0 break-all font-semibold text-brand-700 underline" href={projectService.workFileUrl(projectId, file.id)}>
                {file.name}
              </a>
            ) : file}
          </li>
        ))}
      </ul>
    </div>
  )
}
