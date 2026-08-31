import { sqliteTable, text, integer, primaryKey, index, uniqueIndex } from 'drizzle-orm/sqlite-core'

export const users = sqliteTable('users', {
  id: text('id').primaryKey(),
  email: text('email').notNull(),
  name: text('name').notNull(),
  avatar: text('avatar').notNull(),
  username: text('username').notNull(),
  provider: text('provider').notNull(),
  providerId: text('provider_id').notNull(),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull()
}, table => [
  uniqueIndex('users_provider_id_idx').on(table.provider, table.providerId)
])

export const chats = sqliteTable('chats', {
  id: text('id').primaryKey(),
  title: text('title'),
  userId: text('user_id').notNull(),
  visibility: text('visibility', { enum: ['public', 'private'] }).default('private').notNull(),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull()
}, table => [
  index('chats_user_id_idx').on(table.userId)
])

export const messages = sqliteTable('messages', {
  id: text('id').primaryKey(),
  chatId: text('chat_id').notNull().references(() => chats.id, { onDelete: 'cascade' }),
  role: text('role', { enum: ['system', 'user', 'assistant'] }).notNull(),
  parts: text('parts', { mode: 'json' }).$type<Array<Record<string, unknown>>>(),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull()
}, table => [
  index('messages_chat_id_idx').on(table.chatId)
])

export const votes = sqliteTable('votes', {
  chatId: text('chat_id').notNull().references(() => chats.id, { onDelete: 'cascade' }),
  messageId: text('message_id').notNull().references(() => messages.id, { onDelete: 'cascade' }),
  isUpvoted: integer('is_upvoted', { mode: 'boolean' }).notNull()
}, table => [
  primaryKey({ columns: [table.chatId, table.messageId] })
])
