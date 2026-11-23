import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

export const projectService = {
  listProjects(params) {
    assertApiConfigured()
    return apiClient.get(endpoints.projects.list, { params }).then((r) => r.data)
  },

  getProject(id) {
    assertApiConfigured()
    return apiClient.get(endpoints.projects.detail(id)).then((r) => r.data)
  },

  updateProject(id, payload) {
    assertApiConfigured()
    return apiClient.patch(endpoints.projects.detail(id), payload).then((r) => r.data)
  },

  submitWork(projectId, payload) {
    assertApiConfigured()
    return apiClient.post(endpoints.projects.submissions(projectId), payload).then((r) => r.data)
  },

  workFileUrl(projectId, fileId) {
    return apiClient.getUri({ url: endpoints.projects.workFile(projectId, fileId) })
  },

  approveSubmission(projectId, submissionId) {
    assertApiConfigured()
    return apiClient.post(endpoints.projects.approve(projectId), { submissionId }).then((r) => r.data)
  },

  requestRevision(projectId, submissionId, feedback) {
    assertApiConfigured()
    return apiClient
      .post(endpoints.projects.requestRevision(projectId), { submissionId, feedback })
      .then((r) => r.data)
  },
}
