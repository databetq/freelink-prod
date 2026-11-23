import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

export const messageService = {
  listThreads(params) {
    assertApiConfigured()
    return apiClient.get(endpoints.messages.threads, { params }).then((r) => r.data)
  },

  getThread(params) {
    assertApiConfigured()
    return apiClient.get(endpoints.messages.thread(params.threadId)).then((r) => r.data)
  },

  send(params) {
    assertApiConfigured()
    return apiClient
      .post(endpoints.messages.send(params.threadId), { text: params.text })
      .then((r) => r.data)
  },

  markRead(params) {
    assertApiConfigured()
    return apiClient.patch(`${endpoints.messages.thread(params.threadId)}/read`).then((r) => r.data)
  },
}
