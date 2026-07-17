<script setup lang="ts">
import { onMounted, reactive, watch } from 'vue'
import { monitorApi } from '@/api/monitor'
import { useAsync } from '@/composables/useAsync'
import { useToast } from '@/composables/useToast'
import type { AccountDetail } from '@/api/types'

const props = defineProps<{ voteId: string }>()
const { data, loading, run } = useAsync<AccountDetail>()
const { toast } = useToast()
const review = reactive({ status: '', note: '' })

async function load(): Promise<void> {
  const r = await run(() => monitorApi.account(props.voteId))
  if (r) {
    review.status = r.review?.status || ''
    review.note = r.review?.note || ''
  }
}
onMounted(load)
watch(() => props.voteId, load)

async function saveReview(): Promise<void> {
  try {
    const r = await monitorApi.review(props.voteId, {
      status: review.status,
      note: review.note,
    })
    toast('复核已记录: ' + r.detail, 'success')
    load()
  } catch (e) {
    toast((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="h1">账号钻取 · <span class="mono">{{ voteId }}</span></div>
  <div v-if="loading && !data" class="card loading">加载中…</div>
  <template v-else-if="data">
    <div class="card">
      <div class="h2">聚类归属</div>
      <div class="row">
        <span class="muted small">IP:</span>
        <span v-for="ip in data.ip_groups" :key="ip" class="badge gray mono">{{ ip }}</span>
        <span v-if="!data.ip_groups.length" class="muted small">无</span>
      </div>
      <div class="row" style="margin-top: 0.4rem">
        <span class="muted small">设备:</span>
        <span v-for="d in data.device_groups" :key="d" class="badge gray mono">
          {{ String(d).slice(0, 16) }}
        </span>
        <span v-if="!data.device_groups.length" class="muted small">无</span>
      </div>
    </div>

    <div class="card">
      <div class="h2">人工复核</div>
      <div class="row">
        <div>
          <label class="lbl">状态</label>
          <input class="field" v-model="review.status" placeholder="suspicious / cleared / …" />
        </div>
        <div style="flex: 1; min-width: 200px">
          <label class="lbl">备注</label>
          <input class="field" style="width: 100%" v-model="review.note" />
        </div>
        <button class="btn" style="align-self: flex-end" @click="saveReview">保存复核</button>
      </div>
      <div class="muted small" style="margin-top: 0.4rem">
        复核仅记录,不影响排名。
      </div>
    </div>

    <div class="card">
      <div class="h2">各类别投票(取证原始数据)</div>
      <div v-for="(rows, cat) in data.votes" :key="cat" style="margin-bottom: 0.7rem">
        <div class="row"><b>{{ cat }}</b><span class="badge gray">{{ rows.length }}</span></div>
        <pre
          v-if="rows.length"
          class="small mono"
          style="
            background: #fafbfc;
            padding: 0.6rem;
            border-radius: 8px;
            overflow: auto;
            max-height: 220px;
          "
          >{{ JSON.stringify(rows, null, 2) }}</pre
        >
      </div>
    </div>
  </template>
</template>
