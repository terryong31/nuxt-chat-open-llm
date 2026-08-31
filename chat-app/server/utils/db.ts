import { drizzle } from 'drizzle-orm/libsql'
import { createClient } from '@libsql/client'
import { join } from 'pathe'
import * as schema from '../database/schema'

export * as tables from '../database/schema'

let _db: ReturnType<typeof drizzle<typeof schema>> | null = null

export function useAppDb() {
  if (!_db) {
    const dbPath = join(process.cwd(), '.data/db/sqlite.db')
    const client = createClient({ url: `file:${dbPath}` })
    _db = drizzle(client, { schema })
  }
  return _db
}
