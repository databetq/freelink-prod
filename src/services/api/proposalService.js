import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

export const proposalService = {
  listByJob(jobId) {
    assertApiConfigured()
    return apiClient.get(endpoints.proposals.byJob(jobId)).then((r) => r.data)
  },

  listByFreelancer(freelancerId) {
    assertApiConfigured()
    return apiClient.get(endpoints.proposals.byFreelancer(freelancerId)).then((r) => r.data)
  },

  getProposal(id) {
    assertApiConfigured()
    return apiClient.get(endpoints.proposals.detail(id)).then((r) => r.data)
  },

  createProposal(payload) {
    assertApiConfigured()
    return apiClient.post(endpoints.proposals.byJob(payload.jobId), payload).then((r) => r.data)
  },

  updateStatus(id, status) {
    assertApiConfigured()
    return apiClient.patch(endpoints.proposals.detail(id), { status }).then((r) => r.data)
  },

  withdraw(id) {
    assertApiConfigured()
    return apiClient.post(`${endpoints.proposals.detail(id)}/withdraw`).then((r) => r.data)
  },

  hire(id) {
    assertApiConfigured()
    return apiClient.post(endpoints.proposals.hire(id)).then((r) => r.data)
  },
}
