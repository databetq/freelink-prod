import { apiClient, assertApiConfigured } from './apiClient'

export const walletApi = {
  getLink() {
    assertApiConfigured()
    return apiClient.get('/wallet/link').then(({ data }) => data)
  },

  createChallenge(address, chainId) {
    assertApiConfigured()
    return apiClient.post('/wallet/challenges', { address, chainId }).then(({ data }) => data)
  },

  verify(challengeId, signature) {
    assertApiConfigured()
    return apiClient.post('/wallet/verifications', { challengeId, signature }).then(({ data }) => data)
  },
}
