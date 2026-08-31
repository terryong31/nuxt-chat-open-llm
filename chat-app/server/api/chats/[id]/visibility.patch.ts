import { eq } from 'drizzle-orm'
import { useAppDb, tables } from '../../../utils/db'
import { getSessionUser, getChatOrThrow } from '../../../utils/session'

export default defineEventHandler(async (event) => {
  const user = await getSessionUser(event)
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Chat ID required' })
  }

  const body = await readBody(event)
  if (!body?.visibility || !['public', 'private'].includes(body.visibility)) {
    throw createError({ statusCode: 400, statusMessage: 'Valid visibility (public/private) required' })
  }

  const chat = await getChatOrThrow(event, id)
  if (chat.userId !== user.id) {
    throw createError({ statusCode: 403, statusMessage: 'Unauthorized to update this chat' })
  }

  const db = useAppDb()
  await db.update(tables.chats).set({ visibility: body.visibility }).where(eq(tables.chats.id, id))

  return { success: true, visibility: body.visibility }
})
