import { eq, asc } from 'drizzle-orm'
import { useAppDb, tables } from '../../../utils/db'
import { getSessionUser, getChatOrThrow } from '../../../utils/session'

export default defineEventHandler(async (event) => {
  const user = await getSessionUser(event)
  const id = getRouterParam(event, 'id')

  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Chat ID required' })
  }

  const chat = await getChatOrThrow(event, id)

  // Check visibility: if private, must be owner
  const isOwner = chat.userId === user.id
  if (chat.visibility === 'private' && !isOwner) {
    throw createError({ statusCode: 403, statusMessage: 'Unauthorized access to private chat' })
  }

  const db = useAppDb()
  const rawMessages = await db
    .select()
    .from(tables.messages)
    .where(eq(tables.messages.chatId, id))
    .orderBy(asc(tables.messages.createdAt))

  const messages = rawMessages.map(msg => ({
    id: msg.id,
    role: msg.role,
    parts: typeof msg.parts === 'string' ? JSON.parse(msg.parts) : (msg.parts || []),
    createdAt: msg.createdAt ? new Date(msg.createdAt).toISOString() : new Date().toISOString()
  }))

  return {
    id: chat.id,
    title: chat.title,
    visibility: chat.visibility,
    isOwner,
    messages
  }
})
