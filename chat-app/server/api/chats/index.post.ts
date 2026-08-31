import { generateId } from 'ai'
import { useAppDb, tables } from '../../utils/db'
import { getSessionUser } from '../../utils/session'
import { extractTextFromParts, generateTitleFromPrompt } from '../../utils/llm'

export default defineEventHandler(async (event) => {
  const user = await getSessionUser(event)
  const body = await readBody(event)

  const id = body.id || generateId()
  const now = new Date()

  const userText = extractTextFromParts(body.message?.parts)
  const initialTitle = userText ? generateTitleFromPrompt(userText) : 'Untitled'

  const db = useAppDb()

  await db.insert(tables.chats).values({
    id,
    title: initialTitle,
    userId: user.id,
    visibility: 'private',
    createdAt: now
  })

  if (body.message) {
    const messageId = body.message.id || generateId()
    await db.insert(tables.messages).values({
      id: messageId,
      chatId: id,
      role: 'user',
      parts: body.message.parts || [{ type: 'text', text: userText || '' }],
      createdAt: now
    })
  }

  return { id }
})
