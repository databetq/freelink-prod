import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

export const jobService = {
  listJobs(filters) {
    assertApiConfigured()
    return apiClient.get(endpoints.jobs.list, { params: filters }).then((r) => r.data)
  },

  getJob(id) {
    assertApiConfigured()
    return apiClient.get(endpoints.jobs.detail(id)).then((r) => r.data)
  },

  listClientJobs(clientId) {
    assertApiConfigured()
    return apiClient.get(endpoints.jobs.clientJobs(clientId)).then((r) => r.data)
  },

  createJob(payload, clientId) {
    assertApiConfigured()
    return apiClient.post(endpoints.jobs.list, { ...payload, clientId }).then((r) => r.data)
  },

  updateJob(id, payload) {
    assertApiConfigured()
    return apiClient.patch(endpoints.jobs.detail(id), payload).then((r) => r.data)
  },

  deleteJob(id) {
    assertApiConfigured()
    return apiClient.delete(endpoints.jobs.detail(id)).then((r) => r.data)
  },
}
