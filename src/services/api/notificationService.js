import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

export const notificationService = {
  list(audience) {
    assertApiConfigured()
    return apiClient.get(endpoints.notifications.list, { params: { audience } }).then((r) => r.data)
  },

  markRead(id) {
    assertApiConfigured()
    return apiClient.patch(endpoints.notifications.read(id)).then((r) => r.data)
  },

  markAllRead(audience) {
    assertApiConfigured()
    return apiClient.patch(endpoints.notifications.readAll, { audience }).then((r) => r.data)
  },
}
