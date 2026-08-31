import { eq } from 'drizzle-orm'
import { useAppDb, tables } from '../../../utils/db'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) return []

  const db = useAppDb()
  const votesList = await db
    .select()
    .from(tables.votes)
    .where(eq(tables.votes.chatId, id))

  return votesList.map(v => ({
    chatId: v.chatId,
    messageId: v.messageId,
    isUpvoted: Boolean(v.isUpvoted)
  }))
})
