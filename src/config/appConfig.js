export const appConfig = {
  name: 'Freelink',
  tagline: 'จ้างคนเก่ง ให้งานจบ',
  description:
    'แพลตฟอร์มจ้างงานฟรีแลนซ์ที่รวมงานดี ๆ คนเก่ง และระบบ Escrow ที่ตรวจสอบได้ไว้ในที่เดียว',
  supportEmail: 'hello@freelink.dev',
  currency: 'THB',
  locale: 'th-TH',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? 'http://localhost:8000' : ''),
  explorerUrl: import.meta.env.VITE_EXPLORER_URL
    || (Number(import.meta.env.VITE_CHAIN_ID) === 11155111 ? 'https://sepolia.etherscan.io' : ''),
}
