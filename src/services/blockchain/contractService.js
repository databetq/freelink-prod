import { AbiCoder, BrowserProvider, Contract, getAddress, id, isAddress, keccak256, toUtf8Bytes } from 'ethers'
import { contractConfig, getMissingContractConfig, isContractConfigured } from '@/config/contractConfig'
import { ContractNotConfiguredError, normalizeWalletError, WalletError } from './errors'
import { getEthereumProvider, getWalletChainId } from './walletService'

/**
 * FreelinkEscrow v2 (native ETH). Every function either talks to the real
 * contract or throws — nothing here pretends a transaction succeeded.
 *
 * Money rules (see smart-contact/docs/BACKEND_START_ver_0_2.md):
 *  - `amount` is the freelancer's pay in wei; the contract adds its own fee and
 *    `msg.value` must equal `quote(amount).total` exactly.
 *  - after the deposit every function takes `escrowId`, not `projectId`.
 */

/** On-chain `Status` enum, index = Solidity value. */
export const CHAIN_STATUS = [
  'unfunded',
  'funded',
  'active',
  'submitted',
  'disputed',
  'released',
  'refunded',
  'resolved',
]

function requireConfigured() {
  if (!isContractConfigured()) {
    throw new ContractNotConfiguredError(getMissingContractConfig())
  }
}

function requireMethod(name) {
  const method = contractConfig.methods[name]
  if (!method) {
    throw new ContractNotConfiguredError(
      [`Function name: ${name}`],
      `ยังไม่ทราบชื่อฟังก์ชัน ${name} ของ Smart Contract`,
    )
  }
  return method
}

async function getProvider() {
  const ethereum = getEthereumProvider()
  if (!ethereum) throw new WalletError('ไม่พบ Wallet ในเบราว์เซอร์นี้', 'NO_PROVIDER')
  return new BrowserProvider(ethereum)
}

/**
 * A payable call to an address with no code SUCCEEDS and sends the ETH away, so
 * the chain must be checked before every write (also checks the address has code).
 */
async function requireRightChain(provider) {
  const current = await getWalletChainId()
  if (current !== contractConfig.chainId) {
    throw new WalletError(
      `Wallet อยู่คนละ Network — กรุณาสลับไป ${contractConfig.chainName} (Chain ${contractConfig.chainId})`,
      'WRONG_NETWORK',
    )
  }
  const code = await provider.getCode(contractConfig.contractAddress)
  if (!code || code === '0x') {
    throw new WalletError(
      `ไม่พบ Smart Contract ที่ ${contractConfig.contractAddress} บน ${contractConfig.chainName} — ตรวจ VITE_CONTRACT_ADDRESS`,
      'WRONG_NETWORK',
    )
  }
}

async function getReadContract() {
  requireConfigured()
  const provider = await getProvider()
  return new Contract(contractConfig.contractAddress, contractConfig.abi, provider)
}

async function getSignerContract(address) {
  requireConfigured()
  const provider = await getProvider()
  await requireRightChain(provider)
  const signer = await provider.getSigner(address)
  return new Contract(contractConfig.contractAddress, contractConfig.abi, signer)
}

// ---------- Pure helpers (no wallet needed) ----------

export function hashTerms(termsJson) {
  return keccak256(toUtf8Bytes(termsJson))
}

/** projectId (bytes32) = keccak256(utf8(project.id)) */
export function toProjectKey(projectId) {
  return id(String(projectId))
}

/** Same formula as the contract's computeEscrowId: keccak256(abi.encode(client, projectId)). */
export function getEscrowId({ clientAddress, projectId }) {
  if (!isAddress(clientAddress)) {
    throw new WalletError('ไม่ทราบ address ของลูกค้าที่ฝากเงิน', 'INVALID_ADDRESS')
  }
  const encoded = AbiCoder.defaultAbiCoder().encode(
    ['address', 'bytes32'],
    [getAddress(clientAddress), toProjectKey(projectId)],
  )
  return keccak256(encoded)
}

// ---------- Reads ----------

/** Fee and total (wei) for a freelancer pay of `amountWei`, computed by the contract. */
export async function quote(amountWei) {
  const contract = await getReadContract()
  const [fee, total] = await contract[requireMethod('quote')](amountWei)
  return { fee, total }
}

/** Immutable policy values of the deployed contract. Never hard-code these in the UI. */
export async function readPolicy() {
  const contract = await getReadContract()
  const [feeBps, reviewPeriod, arbiterTimeout, revisionPeriod, maxRevisions] = await Promise.all([
    contract.feeBps(),
    contract.reviewPeriod(),
    contract.arbiterTimeout(),
    contract.revisionPeriod(),
    contract.maxRevisions(),
  ])
  return {
    feeBps: Number(feeBps),
    reviewPeriod: Number(reviewPeriod),
    arbiterTimeout: Number(arbiterTimeout),
    revisionPeriod: Number(revisionPeriod),
    maxRevisions: Number(maxRevisions),
  }
}

/**
 * Reads an escrow and converts ethers' bigint fields: enums/uint8 -> Number,
 * unix seconds -> Number, money stays bigint. Returns null if nothing was deposited.
 */
export async function readEscrow({ escrowId }) {
  try {
    const contract = await getReadContract()
    const raw = await contract[requireMethod('getEscrow')](escrowId)
    const status = Number(raw.status)
    if (status === 0) return null
    return {
      escrowId,
      client: raw.client,
      freelancer: raw.freelancer,
      arbiter: raw.arbiter,
      amount: raw.amount,
      fee: raw.fee,
      termsHash: raw.termsHash,
      deadline: Number(raw.deadline),
      reviewEndsAt: Number(raw.reviewEndsAt),
      disputedAt: Number(raw.disputedAt),
      payoutBps: Number(raw.payoutBps),
      revisionCount: Number(raw.revisionCount),
      status,
      statusName: CHAIN_STATUS[status] || `unknown(${status})`,
    }
  } catch (error) {
    if (error instanceof ContractNotConfiguredError || error instanceof WalletError) throw error
    const normalized = normalizeWalletError(error)
    throw new WalletError(normalized.message, normalized.code)
  }
}

// ---------- Writes (each returns the ethers tx; wrap with executeTransaction) ----------

export async function depositEscrow({ projectKey, clientAddress, freelancerAddress, deadline, termsHash, amountWei, expectedTotal }) {
  const method = requireMethod('depositEscrow')
  if (!isAddress(freelancerAddress)) {
    throw new WalletError('address ของ freelancer ไม่ถูกต้อง', 'INVALID_ADDRESS')
  }
  const contract = await getSignerContract(clientAddress)
  const [, total] = await contract[requireMethod('quote')](amountWei)
  if (total !== expectedTotal) {
    throw new WalletError('ค่าธรรมเนียมเปลี่ยน กรุณาโหลดราคาล่าสุดก่อนเซ็น', 'QUOTE_CHANGED')
  }
  return contract[method](projectKey, getAddress(freelancerAddress), deadline, termsHash, amountWei, {
    value: total,
  })
}

/**
 * freelancer: must pass the same termsHash the client bound at deposit, plus the
 * wage (wei) and deadline (unix seconds) from the agreed terms. Take these from the
 * terms in the DB, not from `getEscrow`, otherwise the contract check is pointless.
 */
export async function acceptEscrow({ escrowId, freelancerAddress, termsHash, expectedAmountWei, expectedDeadline }) {
  const contract = await getSignerContract(freelancerAddress)
  return contract[requireMethod('acceptEscrow')](escrowId, termsHash, expectedAmountWei, expectedDeadline)
}

/** freelancer: workHash = keccak256 of the off-chain link/file. */
export async function submitWork({ escrowId, workHash }) {
  const contract = await getSignerContract()
  return contract[requireMethod('submitWork')](escrowId, workHash)
}

/** client approves and pays the freelancer. */
export async function releasePayment({ escrowId, clientAddress }) {
  const contract = await getSignerContract(clientAddress)
  return contract[requireMethod('releasePayment')](escrowId)
}

/** client asks for changes (reason is stored on-chain permanently — no personal data). */
export async function requestRevision({ escrowId, reason }) {
  const contract = await getSignerContract()
  return contract[requireMethod('requestRevision')](escrowId, reason)
}

/** freelancer collects payment after the review period ended without client action. */
export async function claimAfterReview({ escrowId }) {
  const contract = await getSignerContract()
  return contract[requireMethod('claimAfterReview')](escrowId)
}

export async function refundClient({ escrowId }) {
  const contract = await getSignerContract()
  return contract[requireMethod('refundClient')](escrowId)
}

/** reason is stored on-chain permanently — no personal data. */
export async function openDispute({ escrowId, reason }) {
  const contract = await getSignerContract()
  return contract[requireMethod('openDispute')](escrowId, reason)
}

export async function settleExpiredDispute({ escrowId }) {
  const contract = await getSignerContract()
  return contract[requireMethod('settleExpiredDispute')](escrowId)
}

/** pull-payment fallback for payouts that could not be sent at settlement. */
export async function withdraw(address) {
  const contract = await getSignerContract(address)
  return contract[requireMethod('withdraw')]()
}

export async function readPendingWithdrawal(address) {
  requireConfigured()
  const provider = await getProvider()
  await requireRightChain(provider)
  const contract = new Contract(contractConfig.contractAddress, contractConfig.abi, provider)
  return contract.pendingWithdrawals(address)
}

export { isContractConfigured, getMissingContractConfig }
