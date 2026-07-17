<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { useAuth } from '@/composables/useAuth'

const { clearSecret } = useAuth()

const nav = [
  { to: '/dashboard', label: '仪表盘' },
  { to: '/monitor/overview', label: '流量概览' },
  { to: '/monitor/clusters', label: 'IP·设备聚类' },
  { to: '/monitor/suspects', label: '可疑名单' },
  { to: '/monitor/votes', label: '投票浏览器' },
  { to: '/users', label: '用户' },
]
</script>

<template>
  <div class="topbar">
    <span class="brand">THVote 管理台</span>
    <RouterLink
      v-for="n in nav"
      :key="n.to"
      :to="n.to"
      class="navlink"
      active-class="active"
    >
      {{ n.label }}
    </RouterLink>
    <span class="spacer" />
    <a class="navlink" href="/admin-ui-legacy/" title="尚未迁移到 Vue 的旧工具">
      更多工具(旧版)↗
    </a>
    <span class="navlink" @click="clearSecret">登出</span>
  </div>
  <div class="page">
    <RouterView />
  </div>
</template>
