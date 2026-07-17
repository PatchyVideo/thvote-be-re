<script setup lang="ts">
import { ref } from 'vue'
import { probeLogin } from '@/api/client'
import { useAuth } from '@/composables/useAuth'

const { setSecret } = useAuth()
const val = ref('')
const err = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  err.value = ''
  const s = val.value.trim()
  if (!s) {
    err.value = '请输入管理密钥'
    return
  }
  busy.value = true
  try {
    const status = await probeLogin(s)
    if (status === 200) setSecret(s)
    else if (status === 403) err.value = '密钥错误,或你的 IP 不在白名单'
    else err.value = '登录失败 (HTTP ' + status + ')'
  } catch (e) {
    err.value = '连接失败: ' + (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-overlay">
    <div class="login-box">
      <h1>THVote 管理台</h1>
      <label class="lbl">管理密钥 (X-Admin-Secret)</label>
      <input
        class="field"
        style="width: 100%"
        type="password"
        v-model="val"
        @keyup.enter="submit"
      />
      <div class="err">{{ err }}</div>
      <button
        class="btn"
        style="width: 100%; margin-top: 0.4rem"
        :disabled="busy"
        @click="submit"
      >
        {{ busy ? '验证中…' : '登录' }}
      </button>
    </div>
  </div>
</template>
