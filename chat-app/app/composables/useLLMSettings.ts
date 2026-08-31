export interface LLMSettings {
  thinkingBudget: number
  temperature: number
  topP: number
  maxTokens: number
}

export const DEFAULT_LLM_SETTINGS: LLMSettings = {
  thinkingBudget: 0,
  temperature: 0.7,
  topP: 0.9,
  maxTokens: 2048
}

export function useLLMSettings() {
  const thinkingBudget = useCookie<number>('llm_thinking_budget', { default: () => DEFAULT_LLM_SETTINGS.thinkingBudget })
  const temperature = useCookie<number>('llm_temperature', { default: () => DEFAULT_LLM_SETTINGS.temperature })
  const topP = useCookie<number>('llm_top_p', { default: () => DEFAULT_LLM_SETTINGS.topP })
  const maxTokens = useCookie<number>('llm_max_tokens', { default: () => DEFAULT_LLM_SETTINGS.maxTokens })

  const isCustom = computed(() => {
    return (
      thinkingBudget.value !== DEFAULT_LLM_SETTINGS.thinkingBudget
      || temperature.value !== DEFAULT_LLM_SETTINGS.temperature
      || topP.value !== DEFAULT_LLM_SETTINGS.topP
      || maxTokens.value !== DEFAULT_LLM_SETTINGS.maxTokens
    )
  })

  function reset() {
    thinkingBudget.value = DEFAULT_LLM_SETTINGS.thinkingBudget
    temperature.value = DEFAULT_LLM_SETTINGS.temperature
    topP.value = DEFAULT_LLM_SETTINGS.topP
    maxTokens.value = DEFAULT_LLM_SETTINGS.maxTokens
  }

  return {
    thinkingBudget,
    temperature,
    topP,
    maxTokens,
    isCustom,
    reset
  }
}
