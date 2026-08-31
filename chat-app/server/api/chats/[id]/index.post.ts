import { createUIMessageStream, createUIMessageStreamResponse, generateId } from 'ai'
import { eq, asc } from 'drizzle-orm'
import { useAppDb, tables } from '../../../utils/db'
import { getSessionUser } from '../../../utils/session'
import {
  extractTextFromParts,
  generateTitleFromPrompt,
  fetchLocalLLMStream,
  type LLMMessage
} from '../../../utils/llm'

export default defineEventHandler(async (event) => {
  const user = await getSessionUser(event)
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Chat ID required' })
  }

  const body = await readBody(event).catch(() => ({}))
  const db = useAppDb()

  // 1. Ensure chat exists
  const chatList = await db.select().from(tables.chats).where(eq(tables.chats.id, id)).limit(1)
  let chat = chatList[0]

  // 1. Collect all incoming messages from body (supports both body.messages array and body.message object)
  const incomingMessages: Array<{ id?: string, role?: string, parts?: Record<string, unknown>[] | null, content?: string }> = []
  if (body.message && typeof body.message === 'object') {
    incomingMessages.push(body.message)
  }
  if (Array.isArray(body.messages)) {
    for (const msg of body.messages) {
      if (msg && typeof msg === 'object') {
        incomingMessages.push(msg)
      }
    }
  }

  if (!chat) {
    const firstUser = incomingMessages.find(m => m.role === 'user')
    const userText = firstUser ? (extractTextFromParts(firstUser.parts) || firstUser.content || '') : ''
    const title = userText ? generateTitleFromPrompt(userText) : 'Untitled'
    await db.insert(tables.chats).values({
      id,
      title,
      userId: user.id,
      visibility: 'private',
      createdAt: new Date()
    })
    chat = { id, title, userId: user.id, visibility: 'private', createdAt: new Date() }
  }

  // 2. Insert any incoming user messages that are not yet stored in DB
  for (const msg of incomingMessages) {
    if (msg.id && msg.role === 'user') {
      const existing = await db
        .select()
        .from(tables.messages)
        .where(eq(tables.messages.id, msg.id))
        .limit(1)

      if (existing.length === 0) {
        const parts = Array.isArray(msg.parts) ? msg.parts : [{ type: 'text', text: msg.content || '' }]
        await db.insert(tables.messages).values({
          id: msg.id,
          chatId: id,
          role: 'user',
          parts,
          createdAt: new Date()
        })
      }
    }
  }

  // 3. Load full message history from database
  const dbMessages = await db
    .select()
    .from(tables.messages)
    .where(eq(tables.messages.chatId, id))
    .orderBy(asc(tables.messages.createdAt))

  let llmMessages: LLMMessage[] = dbMessages
    .map((m) => {
      const parts = typeof m.parts === 'string' ? JSON.parse(m.parts) : m.parts
      const content = extractTextFromParts(parts as Record<string, unknown>[])
      return {
        role: m.role as 'user' | 'assistant' | 'system',
        content
      }
    })
    .filter(m => m.content.length > 0)

  // Fallback if dbMessages is empty
  if (llmMessages.length === 0 && incomingMessages.length > 0) {
    llmMessages = incomingMessages
      .map((m) => {
        const content = extractTextFromParts(m.parts) || m.content || ''
        return {
          role: (m.role || 'user') as 'user' | 'assistant' | 'system',
          content
        }
      })
      .filter(m => m.content.length > 0)
  }

  function parseNum(val: unknown): number | undefined {
    if (val === undefined || val === null || val === '') return undefined
    const n = Number(val)
    return Number.isNaN(n) ? undefined : n
  }

  const selectedModel = typeof body.model === 'string' && body.model ? body.model : getCookie(event, 'model')

  const llmOptions = {
    model: selectedModel,
    thinking_budget: parseNum(body.thinking_budget),
    temperature: parseNum(body.temperature),
    top_p: parseNum(body.top_p),
    max_tokens: parseNum(body.max_tokens)
  }

  // 4. Create UI Message Stream and Bridge with Python MLX Backend
  const stream = createUIMessageStream({
    async execute({ writer }) {
      let accumulatedThinking = ''
      let accumulatedAnswer = ''
      let responseMetrics: Record<string, unknown> | null = null
      const assistantParts: Array<Record<string, unknown>> = []
      const reasoningPartId = generateId()
      const textPartId = generateId()
      let reasoningStarted = false
      let reasoningEnded = false
      let textStarted = false
      let textEnded = false

      function closeReasoning() {
        if (reasoningStarted && !reasoningEnded) {
          writer.write({ type: 'reasoning-end', id: reasoningPartId })
          reasoningEnded = true
        }
      }

      function closeText() {
        if (textStarted && !textEnded) {
          writer.write({ type: 'text-end', id: textPartId })
          textEnded = true
        }
      }

      try {
        const streamBody = await fetchLocalLLMStream(llmMessages, llmOptions)
        const reader = streamBody.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed || !trimmed.startsWith('data: ')) continue

            const dataStr = trimmed.slice(6).trim()
            if (dataStr === '[DONE]') break

            try {
              const data = JSON.parse(dataStr)
              if (data.type === 'thinking' && data.token) {
                if (!reasoningStarted) {
                  writer.write({ type: 'reasoning-start', id: reasoningPartId })
                  reasoningStarted = true
                }
                accumulatedThinking += data.token
                writer.write({ type: 'reasoning-delta', id: reasoningPartId, delta: data.token })
              } else if (data.type === 'tool_call') {
                closeReasoning()
                writer.write({
                  type: 'tool-input-available' as const,
                  toolCallId: data.tool_call_id,
                  toolName: data.tool_name,
                  input: data.args
                } as unknown as Parameters<typeof writer.write>[0])
              } else if (data.type === 'tool_result') {
                writer.write({
                  type: 'tool-output-available' as const,
                  toolCallId: data.tool_call_id,
                  output: data.result
                } as unknown as Parameters<typeof writer.write>[0])
                assistantParts.push({
                  type: `tool-${data.tool_name}`,
                  toolCallId: data.tool_call_id,
                  state: 'complete',
                  input: data.args || {},
                  output: data.result
                })
              } else if (data.type === 'answer' && data.token) {
                // Defensive sanitization: never stream raw tool tags to text
                if (data.token.includes('<tool_call>') || data.token.includes('</tool_call>') || data.token.includes('<function=')) {
                  continue
                }
                closeReasoning()
                if (!textStarted) {
                  writer.write({ type: 'text-start', id: textPartId })
                  textStarted = true
                }
                accumulatedAnswer += data.token
                writer.write({ type: 'text-delta', id: textPartId, delta: data.token })
              } else if (data.type === 'metrics' && data.metrics) {
                responseMetrics = data.metrics
                writer.write({
                  type: 'data-metrics' as const,
                  data: data.metrics
                } as unknown as Parameters<typeof writer.write>[0])
              }
            } catch {
              // Ignore non-JSON lines
            }
          }
        }

        closeReasoning()
        closeText()
      } catch (err: unknown) {
        console.error('Error during Local LLM generation:', err)
        const errorMessage = err instanceof Error ? err.message : String(err)
        const errPartId = generateId()
        writer.write({ type: 'text-start', id: errPartId })
        writer.write({
          type: 'text-delta',
          id: errPartId,
          delta: `\n\n⚠️ **Error connecting to local LLM backend:** ${errorMessage}`
        })
        writer.write({ type: 'text-end', id: errPartId })
        accumulatedAnswer += `\n\n⚠️ Error: ${errorMessage}`
      }

      // Save assistant message to database
      const cleanAnswer = accumulatedAnswer
        .replace(/<tool_call>[\s\S]*?<\/tool_call>/gi, '')
        .replace(/<\/?(tool_call|function|parameter)[^>]*>/gi, '')
        .trim()

      const finalParts: Array<Record<string, unknown>> = []
      if (accumulatedThinking) {
        finalParts.push({ type: 'reasoning', text: accumulatedThinking })
      }
      finalParts.push(...assistantParts)
      if (cleanAnswer) {
        finalParts.push({ type: 'text', text: cleanAnswer })
      }
      if (responseMetrics) {
        finalParts.push({ type: 'metrics', data: responseMetrics })
      }

      if (finalParts.length > 0) {
        await db.insert(tables.messages).values({
          id: generateId(),
          chatId: id,
          role: 'assistant',
          parts: finalParts,
          createdAt: new Date()
        })
      }

      // Auto-generate title if this was the first turn or untitled
      if (!chat.title || chat.title === 'Untitled' || chat.title === 'New Chat') {
        const firstUserMsg = dbMessages.find(m => m.role === 'user')
        if (firstUserMsg) {
          const parts = typeof firstUserMsg.parts === 'string' ? JSON.parse(firstUserMsg.parts) : firstUserMsg.parts
          const promptText = extractTextFromParts(parts)
          if (promptText) {
            const newTitle = generateTitleFromPrompt(promptText)
            await db.update(tables.chats).set({ title: newTitle }).where(eq(tables.chats.id, id))
            writer.write({ type: 'data-chat-title' as const, data: newTitle } as unknown as Parameters<typeof writer.write>[0])
          }
        }
      }
    }
  })

  return createUIMessageStreamResponse({ stream })
})
