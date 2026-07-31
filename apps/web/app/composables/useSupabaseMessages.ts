/* eslint-disable @typescript-eslint/no-explicit-any */
export interface MessageItem {
  id: string
  chat_id: string
  role: 'user' | 'assistant' | 'system'
  parts: any
  created_at?: string
}

export function useSupabaseMessages() {
  const config = useRuntimeConfig()
  const token = useAuthToken()
  const backendUrl = computed(() => config.public.backendUrl || 'http://127.0.0.1:8000')

  function headers(): Record<string, string> {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  async function saveMessage(chatId: string, message: { id: string, role: string, parts: any }) {
    // Message saving is handled server-side during stream / createChat, but helper left for fallback
    return { chatId, message }
  }

  async function deleteMessagesFrom(chatId: string, messageId: string, type: 'edit' | 'regenerate') {
    return await $fetch(`${backendUrl.value}/v1/chats/${chatId}/messages`, {
      method: 'DELETE',
      headers: headers(),
      body: { messageId, type }
    })
  }

  async function fetchVotes(chatId: string) {
    try {
      const data = await $fetch<any[]>(`${backendUrl.value}/v1/chats/${chatId}/votes`, {
        headers: headers()
      })
      return data || []
    } catch (e) {
      console.error('Error fetching votes:', e)
      return []
    }
  }

  async function toggleVote(chatId: string, messageId: string, isUpvoted?: boolean) {
    return await $fetch(`${backendUrl.value}/v1/chats/${chatId}/votes`, {
      method: 'POST',
      headers: headers(),
      body: { messageId, isUpvoted }
    })
  }

  return {
    saveMessage,
    deleteMessagesFrom,
    fetchVotes,
    toggleVote
  }
}
