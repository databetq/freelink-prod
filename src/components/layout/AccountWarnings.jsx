import { useAsync } from '@/hooks/useAsync'
import { authApi } from '@/services/api/authService'
import { InfoBanner } from '@/components/common/InfoBanner'
import { formatDate } from '@/utils/format'

export function AccountWarnings({ userId }) {
  const { data: warnings } = useAsync(authApi.listWarnings, [userId])
  if (!warnings?.length) return null

  return (
    <InfoBanner tone="warning" className="mb-5" title="คำเตือนเกี่ยวกับบัญชี">
      <ul className="space-y-2">
        {warnings.map(({ id, reason, createdAt }) => (
          <li key={id}>
            <span className="block whitespace-pre-wrap break-words">{reason}</span>
            <time className="text-xs" dateTime={createdAt}>{formatDate(createdAt)}</time>
          </li>
        ))}
      </ul>
    </InfoBanner>
  )
}
