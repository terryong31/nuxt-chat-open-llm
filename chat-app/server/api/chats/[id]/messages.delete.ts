import { eq, gte, and } from 'drizzle-orm'
import { useAppDb, tables } from '../../../utils/db'
import { getSessionUser, getChatOrThrow } from '../../../utils/session'

export default defineEventHandler(async (event) => {
  const user = await getSessionUser(event)
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Chat ID required' })
  }

  const chat = await getChatOrThrow(event, id)
  if (chat.userId !== user.id) {
    throw createError({ statusCode: 403, statusMessage: 'Unauthorized to modify this chat' })
  }

  const body = await readBody(event)
  const messageId = body?.messageId
  if (!messageId) {
    throw createError({ statusCode: 400, statusMessage: 'Message ID required' })
  }

  const db = useAppDb()
  const targetMsgList = await db
    .select()
    .from(tables.messages)
    .where(and(eq(tables.messages.chatId, id), eq(tables.messages.id, messageId)))
    .limit(1)

  const targetMsg = targetMsgList[0]
  if (targetMsg) {
    // Delete target message and all subsequent messages in this chat
    await db
      .delete(tables.messages)
      .where(
        and(
          eq(tables.messages.chatId, id),
          gte(tables.messages.createdAt, targetMsg.createdAt)
        )
      )
  }

  return { success: true }
})
