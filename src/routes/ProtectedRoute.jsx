import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { PageLoader } from '@/components/common/LoadingSkeleton'
import { dashboardForRole } from '@/services/auth/authService'

export function ProtectedRoute({ role }) {
  const { isAuthenticated, user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <PageLoader />

  if (!isAuthenticated) {
    return (
      <Navigate
        to={role === 'admin' ? '/admin/login' : '/login'}
        state={{ from: location.pathname + location.search + location.hash }}
        replace
      />
    )
  }

  if (role && user.role !== role) {
    return (
      <Navigate
        to={dashboardForRole(user.role)}
        replace
      />
    )
  }

  return <Outlet />
}
