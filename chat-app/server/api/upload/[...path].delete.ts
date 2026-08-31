import { blob } from '@nuxthub/blob'

export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path')
  if (!path) {
    throw createError({ statusCode: 400, statusMessage: 'Path required' })
  }
  return blob.delete(path)
})
