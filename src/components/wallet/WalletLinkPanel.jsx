import { useState } from 'react'
import { Button } from '@/components/common/Button'
import { InfoBanner } from '@/components/common/InfoBanner'
import { useWallet } from '@/contexts/WalletContext'
import { useAsync } from '@/hooks/useAsync'
import { walletApi } from '@/services/api/walletService'
import { signWalletLinkMessage } from '@/services/blockchain/walletService'
import { formatDate } from '@/utils/format'

export function WalletLinkPanel({ userId }) {
  const wallet = useWallet()
  const { data: link, loading, error, refresh, setData } = useAsync(walletApi.getLink, [userId])
  const [busy, setBusy] = useState(false)
  const [verificationError, setVerificationError] = useState(null)
  const isLinkedWallet = Boolean(
    link && wallet.address?.toLowerCase() === link.address.toLowerCase()
    && wallet.chainId === link.chainId,
  )

  async function verify() {
    if (!wallet.address || !wallet.chainId || busy) return
    const { address, chainId } = wallet
    setBusy(true)
    setVerificationError(null)
    try {
      const { challengeId, message } = await walletApi.createChallenge(address, chainId)
      const signature = await signWalletLinkMessage({ address, chainId, message })
      setData(await walletApi.verify(challengeId, signature))
    } catch (failure) {
      setVerificationError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card p-5">
      <h2 className="text-sm font-bold">Wallet ที่ผูกกับบัญชี Freelink</h2>
      {loading && <p className="mt-2 text-xs text-ink-500">กำลังตรวจสอบ Wallet ที่ยืนยันไว้…</p>}
      {error && (
        <InfoBanner tone="warning" className="mt-3">
          {error.message}
          <Button onClick={refresh} variant="subtle" size="sm" className="mt-2">ลองอีกครั้ง</Button>
        </InfoBanner>
      )}
      {!loading && !error && (
        <>
          {link ? (
            <div className="mt-2 text-xs">
              <p className="break-all font-mono text-ink">{link.address}</p>
              <p className="mt-1 text-ink-500">ยืนยันแล้ว {formatDate(link.verifiedAt)}</p>
            </div>
          ) : <p className="mt-2 text-xs text-ink-500">ยังไม่ได้ผูก Wallet กับบัญชี</p>}
          {!wallet.isConnected && (
            <p className="mt-2 text-xs text-ink-500">เชื่อม MetaMask เพื่อยืนยัน Wallet</p>
          )}
          {wallet.isConnected && wallet.isWrongNetwork && (
            <Button onClick={wallet.switchNetwork} variant="secondary" size="sm" className="mt-3">
              สลับเครือข่าย
            </Button>
          )}
          {wallet.isConnected && !wallet.isWrongNetwork && !isLinkedWallet && (
            <>
              <p className="mt-2 text-xs text-ink-500">
                {link ? 'ยืนยันแล้วจะเปลี่ยน Wallet ที่ผูกกับบัญชี' : 'เซ็นข้อความใน MetaMask เพื่อพิสูจน์ความเป็นเจ้าของ'}
                {' '}การเซ็นนี้ไม่โอน ETH
              </p>
              <Button onClick={verify} variant="brand" size="sm" className="mt-3"
                loading={busy} disabled={!wallet.chainId}>
                {link ? 'ยืนยัน Wallet ใหม่' : 'ยืนยันและผูก Wallet'}
              </Button>
            </>
          )}
          {verificationError && <InfoBanner tone="warning" className="mt-3">{verificationError}</InfoBanner>}
        </>
      )}
    </section>
  )
}
