<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

const user = useSupabaseUser()
const supabase = useSupabaseClient()
const loggedIn = computed(() => !!user.value)
const { renameChat, deleteChat } = useChatActions()

async function loginWithGitHub() {
  await supabase.auth.signInWithOAuth({
    provider: 'github',
    options: {
      redirectTo: `${window.location.origin}`
    }
  })
}

const sidebarOpen = ref(false)
const searchOpen = ref(false)

const { fetchChats, fetchChat } = useSupabaseChats()

const { data: chats, status: chatsStatus, refresh: refreshChats } = useAsyncData('chats', async () => {
  const items = await fetchChats()
  return items.map(chat => ({
    id: chat.id,
    label: chat.title || 'Untitled',
    to: `/chat/${chat.id}`,
    icon: 'i-lucide-message-circle',
    createdAt: chat.created_at
  }))
}, {
  lazy: true
})

// Prefetch the most recent conversations so opening one is instant. Driven off
// a watch rather than read once at startup: the list is lazy now and is usually
// still in flight when the app becomes ready. The set keeps a later refresh --
// login, a new chat, a rename -- from refetching what is already cached.
const prefetched = new Set<string>()
watch(chats, (list) => {
  if (!list?.length) return

  onNuxtReady(() => {
    for (const chat of list.slice(0, 10)) {
      if (prefetched.has(chat.id)) continue
      prefetched.add(chat.id)
      // Goes to the gateway. `/api/chats/:id` was a Nitro route and 404s now
      // that the SPA has no server directory.
      fetchChat(chat.id)
    }
  })
}, { immediate: true })

watch(loggedIn, () => {
  refreshChats()

  sidebarOpen.value = false
})

const { groups } = useChats(chats)

const items = computed(() => groups.value?.flatMap((group) => {
  return [{
    label: group.label,
    type: 'label' as const
  }, ...group.items.map(item => ({
    ...item,
    slot: 'chat' as const,
    icon: undefined,
    class: item.label === 'Untitled' ? 'text-muted' : ''
  }))]
}))

function getChatActions(item: { id: string, label: string }): DropdownMenuItem[][] {
  return [[
    {
      label: 'Rename',
      icon: 'i-lucide-pencil',
      onSelect: () => renameChat(item.id, item.label === 'Untitled' ? '' : item.label)
    }
  ], [
    {
      label: 'Delete',
      icon: 'i-lucide-trash',
      color: 'error' as const,
      onSelect: () => deleteChat(item.id)
    }
  ]]
}

defineShortcuts({
  meta_o: () => {
    navigateTo('/')
  }
})
</script>

<template>
  <UDashboardGroup unit="rem">
    <UDashboardSidebar
      id="default"
      v-model:open="sidebarOpen"
      :min-size="12"
      collapsible
      resizable
      :menu="{ inset: true }"
      class="border-r-0 py-4 dark:[--ui-bg-elevated:var(--ui-color-neutral-900)]"
    >
      <template #header="{ collapsed }">
        <NuxtLink v-if="!collapsed" to="/" class="flex items-end gap-0.5">
          <Logo class="h-8 w-auto shrink-0" />
          <span class="text-xl font-bold text-highlighted">Chat</span>
        </NuxtLink>

        <UDashboardSidebarCollapse class="ms-auto" />
      </template>

      <template #default="{ collapsed }">
        <UNavigationMenu
          :items="[{
            label: 'New chat',
            to: '/',
            kbds: ['meta', 'o'],
            icon: 'i-lucide-circle-plus'
          }, {
            label: 'Search',
            icon: 'i-lucide-search',
            kbds: ['meta', 'k'],
            onSelect: () => {
              searchOpen = true
            }
          }]"
          :collapsed="collapsed"
          orientation="vertical"
        >
          <template #item-trailing="{ item }">
            <div v-if="item.kbds?.length" class="flex items-center gap-px opacity-0 group-hover:opacity-100 transition-opacity">
              <UKbd
                v-for="kbd in item.kbds"
                :key="kbd"
                :value="kbd"
                size="sm"
                variant="soft"
                class="bg-accented/50"
              />
            </div>
          </template>
        </UNavigationMenu>

        <!-- Placeholder rows rather than an empty rail: the list arrives a beat
             after first paint now, and a sidebar that pops from blank to full
             reads as a glitch. -->
        <div v-if="!collapsed && chatsStatus === 'pending'" class="flex flex-col gap-2 px-2.5 pt-3">
          <USkeleton
            v-for="i in 6"
            :key="i"
            class="h-4"
            :style="{ width: `${85 - i * 7}%` }"
          />
        </div>

        <UNavigationMenu
          v-else-if="!collapsed"
          :items="items"
          :collapsed="collapsed"
          orientation="vertical"
          :ui="{
            link: 'overflow-hidden pr-7.5',
            linkTrailing: 'translate-x-full group-hover:translate-x-0 group-has-data-[state=open]:translate-x-0 transition-transform ms-0 absolute inset-e-px'
          }"
        >
          <template #chat-trailing="{ item }">
            <UDropdownMenu
              :items="getChatActions(item as { id: string, label: string })"
              :content="{ align: 'end' }"
            >
              <UButton
                as="div"
                icon="i-lucide-ellipsis"
                color="neutral"
                variant="link"
                size="sm"
                class="rounded-[5px] hover:bg-accented/50 focus-visible:bg-accented/50 data-[state=open]:bg-accented/50"
                aria-label="Chat actions"
                tabindex="-1"
                @click.stop.prevent
              />
            </UDropdownMenu>
          </template>
        </UNavigationMenu>
      </template>

      <template #footer="{ collapsed }">
        <UserMenu v-if="loggedIn" :collapsed="collapsed" />
        <UButton
          v-else
          :label="collapsed ? '' : 'Login with GitHub'"
          icon="i-simple-icons-github"
          color="neutral"
          variant="ghost"
          class="w-full"
          @click="loginWithGitHub"
        />
      </template>
    </UDashboardSidebar>

    <UDashboardSearch
      v-model:open="searchOpen"
      placeholder="Search chats..."
      :groups="[{
        id: 'links',
        items: [{
          label: 'New chat',
          to: '/',
          icon: 'i-lucide-circle-plus',
          kbds: ['meta', 'o']
        }]
      }, ...groups]"
    />

    <div class="flex-1 flex m-4 lg:ml-0 rounded-lg ring ring-default bg-default/75 shadow min-w-0 overflow-hidden">
      <slot />
    </div>
  </UDashboardGroup>
</template>
