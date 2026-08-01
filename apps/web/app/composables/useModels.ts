import type { ModelOption } from '#shared/utils/models'
import { FALLBACK_MODEL, toModelOption } from '#shared/utils/models'

export function useModels() {
  const config = useRuntimeConfig()
  const token = useAuthToken()
  const models = useState<ModelOption[]>('models', () => [FALLBACK_MODEL])
  const requested = useState<boolean>('models-requested', () => false)
  // Empty means "whatever the engine has loaded" — `_cached_llm(model or
  // settings.model_id)` in the gateway already resolves it that way, so this
  // stays correct even if the fetch below never lands.
  const model = useCookie<string>('model', { default: () => '' })

  async function load() {
    if (requested.value) return // useModels runs in two components
    requested.value = true

    try {
      const backendUrl = config.public.backendUrl || 'http://127.0.0.1:8000'
      const res = await $fetch<{ data: { id: string }[] }>(`${backendUrl}/v1/models`, {
        headers: token.value ? { Authorization: `Bearer ${token.value}` } : {}
      })

      const list = (res?.data || []).map(m => toModelOption(m.id))
      if (!list.length) return
      models.value = list

      // A cookie set by an earlier build can name a model this deployment does
      // not serve — every existing browser still holds a hosted model id from
      // the template's registry, and would keep sending that dead string.
      if (!list.some(m => m.value === model.value)) {
        model.value = list[0]!.value
      }
    } catch (e) {
      console.error('Error fetching models:', e)
    }
  }

  if (import.meta.client) load()

  return { models, model }
}
