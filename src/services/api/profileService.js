import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

export const profileService = {
  listFreelancers(filters) {
    assertApiConfigured()
    return apiClient.get(endpoints.profiles.freelancers, { params: filters }).then((r) => r.data)
  },

  getFreelancer(id) {
    assertApiConfigured()
    return apiClient.get(endpoints.profiles.freelancer(id)).then((r) => r.data)
  },

  updateFreelancer(id, payload) {
    assertApiConfigured()
    return apiClient.patch(endpoints.profiles.freelancer(id), payload).then((r) => r.data)
  },

  getClient(id) {
    assertApiConfigured()
    return apiClient.get(endpoints.profiles.client(id)).then((r) => r.data)
  },

  updateClient(id, payload) {
    assertApiConfigured()
    return apiClient.patch(endpoints.profiles.client(id), payload).then((r) => r.data)
  },

  listReviews(freelancerId) {
    assertApiConfigured()
    return apiClient.get(endpoints.profiles.reviews(freelancerId)).then((r) => r.data)
  },

  addReview(payload) {
    assertApiConfigured()
    return apiClient
      .post(endpoints.profiles.reviews(payload.freelancerId), payload)
      .then((r) => r.data)
  },
}
