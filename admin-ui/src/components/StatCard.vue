<script setup lang="ts">
defineProps<{ value: string | number; label: string }>()
</script>

<template>
  <div class="stat-card">
    <div class="val"><slot name="value">{{ value }}</slot></div>
    <div class="lbl">{{ label }}</div>
  </div>
</template>
