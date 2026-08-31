<script setup lang="ts">
import type { UIMessage } from 'ai'

const props = defineProps<{
  message: UIMessage
}>()

interface InferenceMetrics {
  total_tokens?: number
  thinking_tokens?: number
  answer_tokens?: number
  generation_tps?: number
  elapsed_time_sec?: number
  prompt_tokens?: number
  prompt_tps?: number
  peak_memory_gb?: number
}

const metrics = computed<InferenceMetrics | null>(() => {
  if (!props.message?.parts) return null
  for (const part of props.message.parts) {
    const p = part as Record<string, unknown>
    if (p.type === 'metrics' && p.data) {
      return p.data as InferenceMetrics
    }
    if (p.type === 'metrics' && typeof p.generation_tps === 'number') {
      return p as InferenceMetrics
    }
    if (p.type === 'data-metrics' && p.data) {
      return p.data as InferenceMetrics
    }
  }
  return null
})

interface MetricItem {
  label: string
  value: string
  detail?: string
}

const metricList = computed<MetricItem[]>(() => {
  if (!metrics.value) return []

  const m = metrics.value
  return [
    {
      label: 'Generation Speed',
      value: `${m.generation_tps ?? 0} tok/s`
    },
    {
      label: 'Prompt Speed',
      value: `${m.prompt_tps ?? 0} tok/s`
    },
    {
      label: 'Output Tokens',
      value: `${m.total_tokens ?? 0} tok`
    },
    {
      label: 'Prompt Tokens',
      value: `${m.prompt_tokens ?? 0} tok`
    },
    {
      label: 'Elapsed Time',
      value: `${m.elapsed_time_sec ?? 0}s`
    },
    {
      label: 'Peak Unified RAM',
      value: `${m.peak_memory_gb ?? 0} GB`
    }
  ]
})
</script>

<template>
  <div v-if="metrics" class="inline-flex items-center">
    <UPopover>
      <template #default>
        <UButton
          color="neutral"
          variant="ghost"
          size="sm"
          icon="i-lucide-info"
          aria-label="Generation Metrics"
        />
      </template>

      <template #content>
        <div class="w-70 p-4 space-y-3 text-xs">
          <div
            v-for="item in metricList"
            :key="item.label"
            class="flex items-center justify-between gap-2"
          >
            <span>{{ item.label }}</span>
            <div class="text-right">
              <span>{{ item.value }}</span>
              <span v-if="item.detail">
                {{ item.detail }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </UPopover>
  </div>
</template>
