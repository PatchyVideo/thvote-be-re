<script setup lang="ts">
// 过滤条容器:插槽放字段,右侧放动作按钮。语义化包一层,统一间距。
</script>

<template>
  <div class="card">
    <div class="row">
      <slot />
      <span class="spacer" />
      <slot name="actions" />
    </div>
  </div>
</template>
