<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useChat } from '@ai-sdk/vue'
import { DefaultChatTransport } from 'ai'
import type { UIMessage } from 'ai'

const route = useRoute()
const toast = useToast()
const config = useRuntimeConfig()
const user = useSupabaseUser()
const token = useAuthToken()
const { model } = useModels()
const { fetchChat } = useSupabaseChats()
const { fetchVotes, toggleVote: toggleSupabaseVote, deleteMessagesFrom, saveMessage } = useSupabaseMessages()

const { data } = await useAsyncData(`chat-${route.params.id}`, async () => {
  const result: any = await fetchChat(route.params.id as string)
  if (!result) return null

  // The gateway verifies the JWT, so it decides ownership and returns it. The
  // client-side comparison is only a fallback: with no Supabase session
  // `user.value` is null, which would read as "not the owner" and hide the
  // composer on a chat you just created.
  const isOwner = result.isOwner ?? (user.value?.id === result.user_id)
  const messages = (result.messages || []).sort((a: any, b: any) =>
    new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  ).map((m: any) => ({
    id: m.id,
    role: m.role,
    parts: m.parts,
    createdAt: m.created_at
  }))

  return {
    ...result,
    isOwner,
    messages
  }
})

const isOwner = computed(() => data.value?.isOwner ?? false)
const visibility = ref<'public' | 'private'>(data.value?.visibility ?? 'private')
const title = ref<string | null>(data.value?.title ?? null)

watch(() => data.value?.title, (next) => {
  title.value = next ?? null
})

const {
  dropzoneRef,
  dragging,
  open,
  files,
  uploading,
  uploadedFiles,
  removeFile,
  clearFiles
} = useFileUploadWithStatus(route.params.id as string)

const { data: votes } = await useAsyncData(`votes-${route.params.id}`, async () => {
  const list: any[] = (await fetchVotes(route.params.id as string)) || []
  return list.map((v: any) => ({
    chatId: v.chat_id,
    messageId: v.message_id,
    isUpvoted: v.is_upvoted
  }))
}, {
  immediate: isOwner.value
})

const input = ref('')
const backendUrl = config.public.backendUrl || 'http://localhost:8000'

const { messages, status, error, sendMessage, regenerate, stop } = useChat({
  id: data.value?.id,
  messages: data.value?.messages,
  // `messages.id` is a uuid column and `votes.message_id` references it. The
  // SDK's default generator emits nanoid strings, which Postgres rejects, so
  // every turn after the first was silently dropped from history.
  generateId: () => crypto.randomUUID(),
  transport: new DefaultChatTransport({
    api: `${backendUrl}/v1/chats/${route.params.id}/stream`,
    headers: token.value ? { Authorization: `Bearer ${token.value}` } : undefined,
    body: {
      model: model.value,
      chatId: data.value?.id
    }
  }),
  onData: async (dataPart) => {
    if (dataPart.type === 'data-chat-title') {
      // The gateway sends the title it just persisted, so take it directly
      // rather than refetching and hoping the write landed first.
      const next = (dataPart.data as { title?: string } | undefined)?.title
      if (next) title.value = next
      await refreshNuxtData('chats')
    }
  },
  onFinish: async ({ message }) => {
    if (data.value?.id && message) {
      await saveMessage(data.value.id, {
        id: message.id,
        role: message.role,
        parts: message.parts
      })
    }
  },
  onError(error) {
    let message = error.message
    if (typeof message === 'string' && message[0] === '{') {
      try {
        message = JSON.parse(message).message || message
      } catch {
        // keep original message on malformed JSON
      }
    }

    toast.add({
      description: message,
      icon: 'i-lucide-alert-circle',
      color: 'error',
      duration: 0
    })
  }
})

async function handleSubmit(e: Event) {
  e.preventDefault()
  if (input.value.trim() && !uploading.value && data.value?.id) {
    const userMsg = {
      text: input.value,
      files: uploadedFiles.value.length > 0 ? uploadedFiles.value : undefined
    }
    sendMessage(userMsg)

    saveMessage(data.value.id, {
      id: crypto.randomUUID(),
      role: 'user',
      parts: [{ type: 'text', text: input.value }, ...(uploadedFiles.value || [])]
    }).catch(e => console.error('Failed saving message:', e))

    input.value = ''
    clearFiles()
  }
}

const editingMessageId = ref<string | null>(null)

function startEdit(message: UIMessage) {
  if (editingMessageId.value) return
  editingMessageId.value = message.id
}

async function saveEdit(message: UIMessage, text: string) {
  try {
    await deleteMessagesFrom(data.value!.id, message.id, 'edit')
  } catch {
    toast.add({ description: 'Failed to save edit.', icon: 'i-lucide-alert-circle', color: 'error' })
    return
  }

  editingMessageId.value = null
  sendMessage({ text, messageId: message.id })
}

async function regenerateMessage(message: UIMessage) {
  try {
    await deleteMessagesFrom(data.value!.id, message.id, 'regenerate')
  } catch {
    toast.add({ description: 'Failed to regenerate.', icon: 'i-lucide-alert-circle', color: 'error' })
    return
  }

  regenerate({ messageId: message.id })
}

function getVote(messageId: string) {
  const vote = votes.value?.find(v => v.messageId === messageId)
  if (!vote) return null
  return !!vote.isUpvoted
}

async function vote(message: UIMessage, isUpvoted: boolean) {
  const snapshot = (votes.value ?? []).map(v => ({ ...v }))
  const toggling = getVote(message.id) === isUpvoted
  const next = toggling ? undefined : isUpvoted

  votes.value = next === undefined
    ? (votes.value ?? []).filter(v => v.messageId !== message.id)
    : [
        ...(votes.value ?? []).filter(v => v.messageId !== message.id),
        { chatId: data.value!.id, messageId: message.id, isUpvoted: next }
      ]

  try {
    await toggleSupabaseVote(data.value!.id, message.id, next)
  } catch {
    votes.value = snapshot
    toast.add({
      description: 'Failed to save vote',
      icon: 'i-lucide-alert-circle',
      color: 'error'
    })
  }
}

onMounted(() => {
  if (isOwner.value && data.value?.messages?.length === 1) {
    regenerate()
  }
})
</script>

<template>
  <UDashboardPanel
    v-if="data?.id"
    id="chat"
    class="relative min-h-0"
    :ui="{ body: 'p-0 sm:p-0 overscroll-none' }"
  >
    <template #header>
      <Navbar>
        <template #title>
          <ChatTitle
            :chat-id="data!.id"
            :title="title"
            :is-owner="isOwner"
            @update:title="title = $event"
          />
        </template>

        <ChatVisibility
          v-if="isOwner"
          :chat-id="data!.id"
          :visibility="visibility"
          @update:visibility="visibility = $event"
        />
      </Navbar>
    </template>

    <template #body>
      <div ref="dropzoneRef" class="flex flex-1">
        <DragDropOverlay v-if="isOwner" :show="dragging" />

        <UContainer class="flex-1 flex flex-col gap-4 sm:gap-6">
          <UChatMessages
            should-auto-scroll
            :messages="messages"
            :status="status"
            :spacing-offset="isOwner ? 200 : 0"
            class="pt-(--ui-header-height) pb-4 sm:pb-6"
          >
            <template #indicator>
              <div class="flex items-center gap-1.5">
                <ChatIndicator />

                <UChatShimmer text="Thinking..." class="text-sm" />
              </div>
            </template>

            <template #files="{ message, parts }">
              <ChatFilePreview
                v-for="(part, index) in parts"
                :key="`${message.id}-${index}`"
                :name="getFileName(part.url)"
                :type="part.mediaType"
                :preview-url="part.url"
                size="3xl"
              />
            </template>

            <template #content="{ message }">
              <ChatMessageContent
                :message="message"
                :editing="isOwner && editingMessageId === message.id"
                @save="saveEdit"
                @cancel-edit="editingMessageId = null"
              />
            </template>

            <template v-if="isOwner" #actions="{ message }">
              <ChatMessageActions
                :message="message"
                :streaming="status === 'streaming' && message.id === messages[messages.length - 1]?.id"
                :editing="editingMessageId === message.id"
                :vote="getVote(message.id)"
                @vote="(_message, isUpvoted) => vote(_message, isUpvoted)"
                @edit="startEdit"
                @regenerate="regenerateMessage"
              />
            </template>
          </UChatMessages>

          <UChatPrompt
            v-if="isOwner"
            v-model="input"
            :error="error"
            :disabled="uploading"
            color="neutral"
            variant="subtle"
            class="sticky bottom-0 [view-transition-name:chat-prompt] rounded-b-none z-10"
            :ui="{ base: 'px-1.5' }"
            @submit="handleSubmit"
          >
            <template v-if="files.length > 0" #header>
              <ChatFiles :files="files" @remove="removeFile" />
            </template>

            <template #footer>
              <div class="flex items-center gap-1">
                <ChatFileUploadButton :open="open" />

                <ModelSelect />
              </div>

              <UChatPromptSubmit
                :status="status"
                :disabled="uploading"
                color="neutral"
                size="sm"
                @stop="stop()"
                @reload="regenerate()"
              />
            </template>
          </UChatPrompt>
        </UContainer>
      </div>
    </template>
  </UDashboardPanel>

  <UContainer v-else class="flex-1 flex flex-col gap-4 sm:gap-6">
    <UError :error="{ statusMessage: 'Chat not found', statusCode: 404 }" class="min-h-full" />
  </UContainer>
</template>
