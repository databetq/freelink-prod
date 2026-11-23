import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { ToastProvider } from '@/contexts/ToastContext'
import { NotificationProvider } from '@/contexts/NotificationContext'
import { WalletProvider } from '@/contexts/WalletContext'
import { ToastViewport } from '@/components/common/ToastNotification'
import { AppRoutes } from '@/routes/AppRoutes'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <WalletProvider>
            <NotificationProvider>
              <AppRoutes />
            </NotificationProvider>
            <ToastViewport />
          </WalletProvider>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
