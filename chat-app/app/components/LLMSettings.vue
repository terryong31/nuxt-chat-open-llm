<script setup lang="ts">
import { useLLMSettings } from '~/composables/useLLMSettings'

const {
  thinkingBudget,
  temperature,
  topP,
  maxTokens,
  isCustom,
  reset
} = useLLMSettings()
</script>

<template>
  <UPopover>
    <template #default>
      <UTooltip text="LLM Generation Settings">
        <UButton
          size="sm"
          color="neutral"
          variant="ghost"
          icon="i-lucide-sliders-horizontal"
          aria-label="LLM Settings"
        />
      </UTooltip>
    </template>

    <template #content>
      <div class="w-90 pt-4 pb-7 px-6 space-y-6 text-xs">
        <!-- Header -->
        <div class="flex items-center justify-between">
          <div class="font-medium text-sm text-highlighted">
            <span>LLM Parameters</span>
          </div>

          <UButton
            v-if="isCustom"
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-rotate-ccw"
            label="Reset"
            @click="reset"
          />
        </div>

        <!-- 1. Thinking Budget -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-medium text-highlighted">Thinking Budget</span>
            <span class="font-mono text-muted text-[11px]">{{ thinkingBudget.toString() }}</span>
          </div>

          <!-- Slider -->
          <div class="pt-1">
            <USlider
              v-model="thinkingBudget"
              :min="0"
              :max="4096"
              :step="50"
              size="xs"
              color="primary"
            />
          </div>
        </div>

        <!-- 2. Temperature -->
        <div class="space-y-1.5 pt-1">
          <div class="flex items-center justify-between">
            <span class="font-medium text-highlighted">Temperature</span>
            <span class="font-mono text-muted text-[11px]">{{ temperature.toString() }}</span>
          </div>
          <USlider
            v-model="temperature"
            :min="0"
            :max="2"
            :step="0.05"
            size="xs"
            color="primary"
          />
        </div>

        <!-- 3. Top P -->
        <div class="space-y-1.5 pt-1">
          <div class="flex items-center justify-between">
            <span class="font-medium text-highlighted">Top P</span>
            <span class="font-mono text-muted text-[11px]">{{ topP.toString() }}</span>
          </div>
          <USlider
            v-model="topP"
            :min="0.1"
            :max="1"
            :step="0.05"
            size="xs"
            color="primary"
          />
        </div>

        <!-- 4. Max Tokens -->
        <div class="space-y-1.5 pt-1">
          <div class="flex items-center justify-between">
            <span class="font-medium text-highlighted">Max Output Tokens</span>
            <span class="font-mono text-muted text-[11px]">{{ maxTokens.toString() }}</span>
          </div>
          <USlider
            v-model="maxTokens"
            :min="256"
            :max="8192"
            :step="128"
            size="xs"
            color="primary"
          />
        </div>
      </div>
    </template>
  </UPopover>
</template>
