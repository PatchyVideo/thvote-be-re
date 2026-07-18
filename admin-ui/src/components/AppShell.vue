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
  { to: '/candidates', label: '候选项' },
  { to: '/nominations', label: '提名审核' },
  { to: '/questionnaires', label: '问卷配置' },
  { to: '/sync', label: '数据同步' },
  { to: '/logs', label: '审计日志' },
  { to: '/export', label: '导出' },
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
    <a class="navlink" href="/admin-ui-legacy/" title="旧单文件面板(备用回退)">
      旧版(备用)↗
    </a>
    <span class="navlink" @click="clearSecret">登出</span>
  </div>
  <div class="page">
    <RouterView />
  </div>
</template>
