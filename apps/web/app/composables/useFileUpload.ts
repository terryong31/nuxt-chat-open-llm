function createObjectUrl(file: File): string {
  return URL.createObjectURL(file)
}

export function useFileUploadWithStatus(chatId: string) {
  const files = ref<FileWithStatus[]>([])
  const toast = useToast()
  const user = useSupabaseUser()
  const supabase = useSupabaseClient()
  const loggedIn = computed(() => !!user.value)

  async function uploadFiles(newFiles: File[]) {
    if (!loggedIn.value || !user.value) {
      return
    }

    const username = user.value.user_metadata?.preferred_username || user.value.user_metadata?.user_name || user.value.id
    const filesWithStatus: FileWithStatus[] = newFiles.map(file => ({
      file,
      id: crypto.randomUUID(),
      previewUrl: createObjectUrl(file),
      status: 'uploading' as const
    }))

    files.value = [...files.value, ...filesWithStatus]

    const uploadPromises = filesWithStatus.map(async (fileWithStatus) => {
      const index = files.value.findIndex(f => f.id === fileWithStatus.id)
      if (index === -1) return

      try {
        const filePath = `${username}/${chatId}/${fileWithStatus.id}-${fileWithStatus.file.name}`
        const { data, error } = await supabase.storage
          .from('chat-attachments')
          .upload(filePath, fileWithStatus.file, {
            cacheControl: '3600',
            upsert: true
          })

        if (error || !data) {
          throw error || new Error('Upload failed')
        }

        const { data: publicUrlData } = supabase.storage
          .from('chat-attachments')
          .getPublicUrl(filePath)

        files.value[index] = {
          ...files.value[index]!,
          status: 'uploaded',
          uploadedUrl: publicUrlData.publicUrl,
          uploadedPathname: filePath
        }
      } catch (error) {
        const errorMessage = (error as Error).message || 'Upload failed'
        toast.add({
          title: 'Upload failed',
          description: errorMessage,
          icon: 'i-lucide-alert-circle',
          color: 'error'
        })
        files.value[index] = {
          ...files.value[index]!,
          status: 'error',
          error: errorMessage
        }
      }
    })

    await Promise.allSettled(uploadPromises)
  }

  const { dropzoneRef, isDragging, open } = useFileUpload({
    accept: FILE_UPLOAD_CONFIG.acceptPattern,
    multiple: true,
    onUpdate: uploadFiles
  })

  const uploading = computed(() =>
    files.value.some(f => f.status === 'uploading')
  )

  const uploadedFiles = computed(() =>
    files.value
      .filter(f => f.status === 'uploaded' && f.uploadedUrl)
      .map(f => ({
        type: 'file' as const,
        mediaType: f.file.type,
        url: f.uploadedUrl!
      }))
  )

  function removeFile(id: string) {
    const file = files.value.find(f => f.id === id)
    if (!file) return

    URL.revokeObjectURL(file.previewUrl)
    files.value = files.value.filter(f => f.id !== id)

    if (file.status === 'uploaded' && file.uploadedPathname) {
      supabase.storage.from('chat-attachments').remove([file.uploadedPathname]).catch((error) => {
        console.error('Failed to delete file from Supabase storage:', error)
      })
    }
  }

  function clearFiles() {
    if (files.value.length === 0) return
    files.value.forEach(fileWithStatus => URL.revokeObjectURL(fileWithStatus.previewUrl))
    files.value = []
  }

  onUnmounted(() => {
    clearFiles()
  })

  return {
    dropzoneRef,
    dragging: isDragging,
    open,
    files,
    uploading,
    uploadedFiles,
    addFiles: uploadFiles,
    removeFile,
    clearFiles
  }
}
