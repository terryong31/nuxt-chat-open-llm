import { eq } from 'drizzle-orm'
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
    throw createError({ statusCode: 403, statusMessage: 'Unauthorized to delete this chat' })
  }

  const db = useAppDb()
  await db.delete(tables.chats).where(eq(tables.chats.id, id))

  return { success: true }
})
