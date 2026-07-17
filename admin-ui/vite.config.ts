import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 产物输出到 backend 的 src/admin_ui/(被 StaticFiles 服务、COPY src/ 进镜像)。
// base:'./' 让资源用相对路径,适配 /admin-ui 挂载。hash 路由无需 SPA fallback。
export default defineConfig({
  base: './',
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../src/admin_ui',
    emptyOutDir: true,
  },
})
