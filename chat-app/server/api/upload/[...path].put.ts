import { blob } from '@nuxthub/blob'

export default defineEventHandler(async (event) => {
  return blob.handleUpload(event, {
    multiple: true,
    ensure: {
      maxSize: '8MB',
      types: ['image', 'application/pdf', 'text/csv']
    }
  })
})
