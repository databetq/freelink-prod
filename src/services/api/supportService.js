import { apiClient, assertApiConfigured } from './apiClient'

export const supportService = {
  listReports() {
    assertApiConfigured()
    return apiClient.get('/support/reports').then((response) => response.data)
  },

  getReport(id) {
    assertApiConfigured()
    return apiClient.get(`/support/reports/${id}`).then((response) => response.data)
  },

  submitReport(payload) {
    assertApiConfigured()
    return apiClient.post('/support/reports', payload).then((response) => response.data)
  },

  reply(id, payload) {
    assertApiConfigured()
    return apiClient.post(`/support/reports/${id}/messages`, payload).then((response) => response.data)
  },
}
