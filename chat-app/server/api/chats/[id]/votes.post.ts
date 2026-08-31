import { and, eq } from 'drizzle-orm'
import { useAppDb, tables } from '../../../utils/db'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Chat ID required' })
  }

  const body = await readBody(event)
  const messageId = body?.messageId
  if (!messageId) {
    throw createError({ statusCode: 400, statusMessage: 'Message ID required' })
  }

  const db = useAppDb()

  if (body.isUpvoted === undefined || body.isUpvoted === null) {
    // Delete vote
    await db
      .delete(tables.votes)
      .where(and(eq(tables.votes.chatId, id), eq(tables.votes.messageId, messageId)))
    return { success: true, removed: true }
  }

  // Insert or replace vote
  await db
    .insert(tables.votes)
    .values({
      chatId: id,
      messageId,
      isUpvoted: Boolean(body.isUpvoted)
    })
    .onConflictDoUpdate({
      target: [tables.votes.chatId, tables.votes.messageId],
      set: { isUpvoted: Boolean(body.isUpvoted) }
    })

  return { success: true, isUpvoted: Boolean(body.isUpvoted) }
})
