import type { H3Event } from 'h3'
import { eq } from 'drizzle-orm'
import { useAppDb, tables } from './db'

export const LOCAL_USER = {
  id: 'local-user',
  name: 'Local User',
  email: 'local@localhost',
  avatar: 'https://avatars.githubusercontent.com/u/0?v=4',
  username: 'local',
  provider: 'local' as const,
  providerId: 'local-user'
}

export async function getSessionUser(event: H3Event) {
  try {
    const session = await getUserSession(event)
    if (session?.user?.id) {
      return session.user
    }
  } catch {
    // Auth session not active
  }
  return LOCAL_USER
}

export async function getChatOrThrow(event: H3Event, chatId: string) {
  const db = useAppDb()
  const chatList = await db.select().from(tables.chats).where(eq(tables.chats.id, chatId)).limit(1)
  const chat = chatList[0]
  if (!chat) {
    throw createError({
      statusCode: 404,
      statusMessage: 'Chat not found'
    })
  }
  return chat
}
