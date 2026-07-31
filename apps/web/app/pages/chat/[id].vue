<script setup lang="ts">
// Deliberately synchronous. The fetch lives in ChatConversation, one Suspense
// boundary down, so a cold load paints the sidebar and the frame below right
// away instead of holding the whole app on the chat query.
const route = useRoute()
</script>

<template>
  <Suspense>
    <ChatConversation :key="route.params.id as string" />

    <template #fallback>
      <UDashboardPanel
        id="chat"
        class="relative min-h-0"
        :ui="{ body: 'p-0 sm:p-0 overscroll-none' }"
      >
        <template #header>
          <Navbar>
            <template #title>
              <USkeleton class="h-5 w-40" />
            </template>
          </Navbar>
        </template>

        <template #body>
          <UContainer class="flex-1 flex flex-col gap-6 pt-(--ui-header-height)">
            <!-- Alternating widths and offsets so the placeholder reads as a
                 conversation rather than a stack of bars. -->
            <div
              v-for="(width, i) in ['55%', '80%', '40%', '70%']"
              :key="i"
              class="flex flex-col gap-2"
              :class="i % 2 === 0 ? 'items-end' : 'items-start'"
            >
              <USkeleton class="h-4" :style="{ width }" />
              <USkeleton v-if="i % 2 === 1" class="h-4 w-1/2" />
            </div>
          </UContainer>
        </template>
      </UDashboardPanel>
    </template>
  </Suspense>
</template>
