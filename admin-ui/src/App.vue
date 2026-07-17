<script setup lang="ts">
import AppShell from '@/components/AppShell.vue'
import LoginOverlay from '@/components/LoginOverlay.vue'
import ToastHost from '@/components/Toast.vue'
import { useAuth } from '@/composables/useAuth'

const { isAuthed } = useAuth()
</script>

<template>
  <ToastHost />
  <LoginOverlay v-if="!isAuthed" />
  <AppShell v-else />
</template>
