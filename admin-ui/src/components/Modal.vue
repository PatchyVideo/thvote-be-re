<script setup lang="ts">
defineProps<{ title?: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <div v-if="title" class="modal-title">{{ title }}</div>
      <slot />
    </div>
  </div>
</template>
