import { apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

function withHash(transaction) {
  return { ...transaction, hash: transaction.txHash ?? transaction.hash }
}

export const transactionService = {
  list(userId) {
    assertApiConfigured()
    return apiClient.get(endpoints.transactions.list, { params: { userId } }).then(({ data }) => data.map(withHash))
  },

  getById(id) {
    assertApiConfigured()
    return apiClient.get(endpoints.transactions.detail(id)).then(({ data }) => withHash(data))
  },

}
