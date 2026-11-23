import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { contractConfig } from '@/config/contractConfig'
import { WalletError } from '@/services/blockchain/errors'
import {
  connectWallet as connectWalletService,
  disconnectWallet as disconnectWalletService,
  isWalletAvailable,
  readWalletConnection,
  switchNetwork as switchNetworkService,
  subscribeToWalletEvents,
} from '@/services/blockchain/walletService'
import { useToast } from './ToastContext'

const WalletContext = createContext(null)
const DISCONNECT_KEY = 'freelink.wallet.disconnected'

function rememberDisconnection(disconnected) {
  try {
    if (disconnected) window.localStorage.setItem(DISCONNECT_KEY, 'true')
    else window.localStorage.removeItem(DISCONNECT_KEY)
  } catch {
    // The setting still applies until this page reloads.
  }
}

function wasDisconnected() {
  try {
    return window.localStorage.getItem(DISCONNECT_KEY) === 'true'
  } catch {
    return false
  }
}

export function WalletProvider({ children }) {
  const toast = useToast()
  const [address, setAddress] = useState(null)
  const [chainId, setChainId] = useState(null)
  const [status, setStatus] = useState('disconnected')
  const [error, setError] = useState(null)
  const [isAvailable, setIsAvailable] = useState(isWalletAvailable)
  const restoreDisabled = useRef(wasDisconnected())
  const manualConnect = useRef(false)
  const connectionVersion = useRef(0)

  const connect = useCallback(async () => {
    const version = ++connectionVersion.current
    manualConnect.current = true
    setStatus('connecting')
    setError(null)
    try {
      const result = await connectWalletService()
      if (version !== connectionVersion.current) {
        throw new WalletError('การเชื่อมต่อ Wallet ถูกยกเลิกในแอป', 'WALLET_CONNECTION_CANCELLED')
      }
      restoreDisabled.current = false
      rememberDisconnection(false)
      setIsAvailable(true)
      setAddress(result.address)
      setChainId(result.chainId)
      setStatus('connected')
      toast.success('เชื่อมต่อ Wallet แล้ว', 'สถานะนี้มาจาก Wallet ในเบราว์เซอร์ของคุณ')
      return result
    } catch (err) {
      if (version === connectionVersion.current) {
        setAddress(null)
        setChainId(null)
        setStatus('disconnected')
        setError(err)
        toast.error('เชื่อมต่อ Wallet ไม่สำเร็จ', err.message)
      }
      throw err
    } finally {
      if (version === connectionVersion.current) manualConnect.current = false
    }
  }, [toast])

  const disconnect = useCallback(async () => {
    ++connectionVersion.current
    manualConnect.current = false
    restoreDisabled.current = true
    rememberDisconnection(true)
    await disconnectWalletService()
    setAddress(null)
    setChainId(null)
    setStatus('disconnected')
    setError(null)
    toast.info('ยกเลิกการเชื่อมต่อในแอปแล้ว', 'Wallet ของคุณอาจยังอนุญาตบัญชีนี้อยู่ — จัดการได้ในตัว Wallet')
  }, [toast])

  const switchNetwork = useCallback(async () => {
    try {
      await switchNetworkService()
      toast.success('สลับ Network แล้ว')
    } catch (err) {
      toast.warning('ยังสลับ Network ไม่ได้', err.message)
    }
  }, [toast])

  useEffect(() => {
    let active = true
    let unsubscribe = () => {}

    async function refreshConnection() {
      if (restoreDisabled.current || manualConnect.current) return
      const version = ++connectionVersion.current
      const connection = await readWalletConnection().catch(() => null)
      if (!active || version !== connectionVersion.current) return
      setAddress(connection?.address ?? null)
      setChainId(connection?.chainId ?? null)
      setStatus(connection ? 'connected' : 'disconnected')
      setError(null)
    }

    function initialize() {
      const available = isWalletAvailable()
      setIsAvailable(available)
      if (!available) return
      unsubscribe()
      unsubscribe = subscribeToWalletEvents({
        onAccountsChanged: refreshConnection,
        onChainChanged: refreshConnection,
      })
      refreshConnection()
    }

    initialize()
    window.addEventListener('ethereum#initialized', initialize)
    return () => {
      active = false
      unsubscribe()
      window.removeEventListener('ethereum#initialized', initialize)
    }
  }, [])

  const expectedChainId = contractConfig.chainId
  const isWrongNetwork = Boolean(chainId && expectedChainId && chainId !== expectedChainId)

  const value = useMemo(
    () => ({
      address,
      chainId,
      status,
      error,
      isAvailable,
      isConnected: status === 'connected' && Boolean(address),
      isWrongNetwork,
      expectedChainId,
      connect,
      disconnect,
      switchNetwork,
    }),
    [address, chainId, status, error, isAvailable, isWrongNetwork, expectedChainId, connect, disconnect, switchNetwork],
  )

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>
}

export function useWallet() {
  const context = useContext(WalletContext)
  if (!context) throw new Error('useWallet must be used inside <WalletProvider>')
  return context
}
