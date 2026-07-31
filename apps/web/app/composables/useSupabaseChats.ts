/* eslint-disable @typescript-eslint/no-explicit-any */
export interface ChatItem {
  id: string
  title: string | null
  user_id: string
  visibility: 'public' | 'private'
  created_at: string
}

export function useSupabaseChats() {
  const config = useRuntimeConfig()
  const token = useAuthToken()
  const backendUrl = computed(() => config.public.backendUrl || 'http://127.0.0.1:8000')

  function headers(): Record<string, string> {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  async function fetchChats() {
    try {
      const data = await $fetch<ChatItem[]>(`${backendUrl.value}/v1/chats`, {
        headers: headers()
      })
      return data || []
    } catch (e) {
      console.error('Error fetching chats:', e)
      return []
    }
  }

  async function fetchChat(id: string) {
    try {
      return await $fetch<any>(`${backendUrl.value}/v1/chats/${id}`, {
        headers: headers()
      })
    } catch (e) {
      console.error('Error fetching chat:', e)
      return null
    }
  }

  async function createChat(id: string, messagePayload: any) {
    return await $fetch<ChatItem>(`${backendUrl.value}/v1/chats`, {
      method: 'POST',
      headers: headers(),
      body: {
        id,
        message: messagePayload
      }
    })
  }

  async function renameChat(id: string, title: string) {
    return await $fetch<ChatItem>(`${backendUrl.value}/v1/chats/${id}/title`, {
      method: 'PATCH',
      headers: headers(),
      body: { title }
    })
  }

  async function updateVisibility(id: string, visibility: 'public' | 'private') {
    return await $fetch<ChatItem>(`${backendUrl.value}/v1/chats/${id}/visibility`, {
      method: 'PATCH',
      headers: headers(),
      body: { visibility }
    })
  }

  async function deleteChat(id: string) {
    await $fetch(`${backendUrl.value}/v1/chats/${id}`, {
      method: 'DELETE',
      headers: headers()
    })
    return true
  }

  return {
    fetchChats,
    fetchChat,
    createChat,
    renameChat,
    updateVisibility,
    deleteChat
  }
}
