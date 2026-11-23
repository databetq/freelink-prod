import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

function path(projectId) {
  assertApiConfigured()
  return `${endpoints.projects.detail(projectId)}/escrow`
}

export const escrowService = {
  get(projectId) {
    return apiClient.get(path(projectId)).then(({ data }) => data)
  },
  getReleaseProgress(projectId) {
    return apiClient.get(`${path(projectId)}/release-progress`).then(({ data }) => data)
  },
  prepare(projectId, payload) {
    return apiClient.post(`${path(projectId)}/prepare`, payload).then(({ data }) => data)
  },
  consent(projectId, payload) {
    return apiClient.post(`${path(projectId)}/consent`, payload).then(({ data }) => data)
  },
  recordTransaction(projectId, agreementId, txHash) {
    return apiClient.post(`${path(projectId)}/transactions`, { agreementId, txHash }).then(({ data }) => data)
  },
}
