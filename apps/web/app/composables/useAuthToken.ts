export function useAuthToken() {
  const session = useSupabaseSession()
  return computed(() => session.value?.access_token || '')
}
