import { MODELS } from '#shared/utils/models'

export function useModels() {
  const model = useCookie<string>('model', { default: () => 'mlx-community/Qwen3.5-9B-MLX-8bit' })

  return {
    models: MODELS,
    model
  }
}
