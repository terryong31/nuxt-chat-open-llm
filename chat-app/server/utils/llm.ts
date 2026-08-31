export interface LLMMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export function extractTextFromParts(parts: Array<Record<string, unknown>> | null | undefined): string {
  if (!parts || !Array.isArray(parts)) return ''
  return parts
    .filter((p): p is Record<string, unknown> & { text: string } => Boolean(p && p.type === 'text' && typeof p.text === 'string'))
    .map(p => p.text)
    .join('\n')
    .trim()
}

export function generateTitleFromPrompt(promptText: string): string {
  const cleaned = promptText
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 45)
  if (!cleaned) return 'New Chat'
  return cleaned.length >= 45 ? `${cleaned.trim()}...` : cleaned
}

export function getLocalLLMUrl(): string {
  return process.env.LOCAL_LLM_URL || 'http://127.0.0.1:8000'
}

export async function fetchLocalLLMStream(
  messages: LLMMessage[],
  options?: {
    model?: string
    thinking_budget?: number
    max_tokens?: number
    temperature?: number
    top_p?: number
  }
) {
  const url = `${getLocalLLMUrl()}/chat`
  const payload = {
    messages,
    model: options?.model,
    thinking_budget: options?.thinking_budget ?? 0,
    max_tokens: options?.max_tokens ?? 2048,
    temperature: options?.temperature ?? 0.7,
    top_p: options?.top_p ?? 0.9,
    stream: true
  }

  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    throw new Error(
      `Cannot connect to Local LLM at ${url}. Please ensure the Python server ('python main.py') is running. Details: ${message}`,
      { cause: err }
    )
  }

  if (!response.ok || !response.body) {
    const errorText = await response.text().catch(() => '')
    throw new Error(
      `Local LLM API error (${response.status}): ${errorText || response.statusText}`
    )
  }

  return response.body
}
