<script setup lang="ts">
import { ref } from 'vue'
import { exportApi } from '@/api/exportVotes'
import { useToast } from '@/composables/useToast'
import { VOTE_CATEGORIES } from '@/api/types'

const year = ref(2026)
const category = ref<string>(VOTE_CATEGORIES[0])
const { toast } = useToast()

async function download(): Promise<void> {
  try {
    await exportApi.votes(year.value, category.value)
    toast('已开始下载', 'success')
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="h1">导出</div>
  <div class="card" style="max-width: 420px">
    <div class="h2">导出投票数据 CSV</div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">年份</label>
      <input class="field" type="number" v-model.number="year" />
    </div>
    <div style="margin-bottom: 0.6rem">
      <label class="lbl">类别</label>
      <select class="field" v-model="category">
        <option v-for="c in VOTE_CATEGORIES" :key="c" :value="c">{{ c }}</option>
      </select>
    </div>
    <button class="btn" @click="download">下载 CSV</button>
    <div class="muted small" style="margin-top: 0.6rem">
      列: vote_id, attempt, created_at, user_ip, payload
    </div>
  </div>
</template>
