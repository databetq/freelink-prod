import { useMemo } from 'react'
import { Star } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { profileService } from '@/services/api/profileService'
import { PageHeader } from '@/components/common/PageHeader'
import { RatingStars } from '@/components/common/RatingStars'
import { Avatar } from '@/components/common/Avatar'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { PageLoader } from '@/components/common/LoadingSkeleton'
import { formatDate } from '@/utils/format'

export default function Reviews() {
  useDocumentTitle('รีวิวของฉัน')
  const { profileId } = useAuth()
  const { data: profile, loading, error, refresh } = useAsync(
    () => profileService.getFreelancer(profileId),
    [profileId],
  )

  const reviews = profile?.reviews || []

  const summary = useMemo(() => {
    if (reviews.length === 0) return null
    const distribution = [5, 4, 3, 2, 1].map((star) => ({
      star,
      count: reviews.filter((review) => review.rating === star).length,
    }))
    return { distribution }
  }, [reviews])

  if (loading) return <PageLoader />
  if (error || !profile) return <ErrorState error={error} onRetry={refresh} />

  return (
    <div>
      <PageHeader
        eyebrow="Reviews"
        title="รีวิวจากลูกค้า"
        description="คะแนนและความคิดเห็นที่ลูกค้าให้หลังจบโครงการ"
      />

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <aside className="lg:sticky lg:top-[88px] lg:self-start">
          <div className="card p-5">
            <div className="flex items-end gap-3">
              <p className="font-display text-5xl font-extrabold tracking-tight text-ink">
                {profile.rating?.toFixed(1)}
              </p>
              <div className="pb-1">
                <RatingStars rating={profile.rating} size="md" />
                <p className="mt-1 text-[10.5px] text-ink-400">
                  จาก {profile.reviewsCount} รีวิวบนแพลตฟอร์ม
                </p>
              </div>
            </div>

            {summary && (
                <div className="mt-4 space-y-1.5">
                  {summary.distribution.map((row) => {
                    const percentage = Math.round((row.count / reviews.length) * 100)
                    return (
                      <div key={row.star} className="flex items-center gap-2">
                        <span className="inline-flex w-7 items-center gap-0.5 text-[10.5px] text-ink-500">
                          {row.star}
                          <Star className="h-2.5 w-2.5 fill-amber-400 text-amber-400" />
                        </span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/[0.06]">
                          <div
                            className="h-full rounded-full bg-amber-400"
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                        <span className="w-4 text-right text-[10px] text-ink-400">{row.count}</span>
                      </div>
                    )
                  })}
                </div>
            )}
          </div>
        </aside>

        <div>
          {reviews.length === 0 ? (
            <EmptyState
              icon={Star}
              title="ยังไม่มีรีวิว"
              description="เมื่อทำงานเสร็จและลูกค้าให้คะแนน รีวิวจะแสดงที่นี่"
            />
          ) : (
            <div className="space-y-4">
              {reviews.map((review) => (
                <article key={review.id} className="card p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <Avatar
                        name={review.client?.name || 'Client'}
                        color={review.client?.avatarColor}
                        size="md"
                      />
                      <div>
                        <p className="text-xs font-bold text-ink">{review.client?.name}</p>
                        <p className="text-[10.5px] text-ink-400">
                          {formatDate(review.createdAt)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <RatingStars rating={review.rating} size="sm" />
                      <span className="text-xs font-bold text-ink">{review.rating}.0</span>
                    </div>
                  </div>

                  <p className="mt-3 text-[13px] leading-relaxed text-ink-600">{review.comment}</p>

                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
