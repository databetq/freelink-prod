import { apiClient, assertApiConfigured } from './apiClient'

export const adminService = {
  getOverview() {
    assertApiConfigured()
    return apiClient.get('/admin/overview').then((r) => r.data)
  },

  updateUserStatus(id, status, reason) {
    assertApiConfigured()
    return apiClient.patch(`/admin/users/${id}`, { status, reason }).then((r) => r.data)
  },

  getModerationHistory(id) {
    assertApiConfigured()
    return apiClient.get(`/admin/users/${id}/moderation`).then((r) => r.data)
  },

  addNotice(id, kind, reason) {
    assertApiConfigured()
    return apiClient.post(`/admin/users/${id}/notices`, { kind, reason }).then((r) => r.data)
  },

  resolveReport(id, status) {
    assertApiConfigured()
    return apiClient.patch(`/admin/reports/${id}`, { status }).then((r) => r.data)
  },

  getReportProject(id) {
    assertApiConfigured()
    return apiClient.get(`/admin/reports/${id}/project`).then((response) => response.data)
  },
}
