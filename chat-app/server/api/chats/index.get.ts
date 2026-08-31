import { eq, desc } from 'drizzle-orm'
import { useAppDb, tables } from '../../utils/db'
import { getSessionUser } from '../../utils/session'

export default defineEventHandler(async (event) => {
  const user = await getSessionUser(event)
  const db = useAppDb()

  const chatList = await db
    .select({
      id: tables.chats.id,
      title: tables.chats.title,
      visibility: tables.chats.visibility,
      createdAt: tables.chats.createdAt
    })
    .from(tables.chats)
    .where(eq(tables.chats.userId, user.id))
    .orderBy(desc(tables.chats.createdAt))

  return chatList.map(chat => ({
    id: chat.id,
    title: chat.title,
    visibility: chat.visibility,
    createdAt: chat.createdAt ? new Date(chat.createdAt).toISOString() : new Date().toISOString()
  }))
})
