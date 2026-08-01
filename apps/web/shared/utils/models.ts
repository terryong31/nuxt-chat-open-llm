export interface ModelOption {
  value: string
  label: string
  description?: string
  icon: string
}

/**
 * Display names for checkpoints this project ships.
 *
 * The list itself comes from the gateway, which proxies what the engine has
 * actually loaded — this map only prettifies ids it recognises. An unknown id
 * still renders via `formatModelLabel`, so the picker cannot go back to
 * advertising models that are not being served.
 */
const MODEL_LABELS: Record<string, Omit<ModelOption, 'value'>> = {
  'mlx-community/Mamba-Codestral-7B-v0.1-4bit': {
    label: 'Codestral Mamba 7B · SSM',
    // The label omits the quantization, so it is carried here: 4-bit is why
    // the occasional stray token shows up mid-identifier.
    description: 'state space model, not a transformer · 4-bit',
    icon: 'i-lucide-cpu'
  }
}

/** Shown when the gateway cannot reach the engine. Empty value means
 *  "whatever the server has loaded", which the gateway already treats that way. */
export const FALLBACK_MODEL: ModelOption = {
  value: '',
  label: 'Local model',
  description: 'engine unreachable',
  icon: 'i-lucide-cpu'
}

/** `mlx-community/Mamba-Codestral-7B-v0.1-4bit` → `Mamba Codestral 7B v0.1 4bit` */
export function formatModelLabel(id: string): string {
  return (id.split('/').pop() || id).replace(/-/g, ' ').trim()
}

export function toModelOption(id: string): ModelOption {
  const known = MODEL_LABELS[id]
  return known
    ? { value: id, ...known }
    : { value: id, label: formatModelLabel(id), icon: 'i-lucide-cpu' }
}
