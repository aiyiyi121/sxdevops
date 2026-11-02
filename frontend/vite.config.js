import { defineConfig } from 'vite'
import workbenchTheme from './build/workbench-theme.js'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
    plugins: [vue()],
    css: {
        postcss: {
            plugins: [workbenchTheme()],
        },
    },
    build: {
        chunkSizeWarningLimit: 900,
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (!id.includes('node_modules')) return
                    if (id.includes('echarts')) return 'echarts'
                    if (id.includes('@xterm')) return 'xterm'
                    if (id.includes('vue-router')) return 'vue-router'
                    if (id.includes('pinia')) return 'pinia'
                    if (id.includes('axios')) return 'axios'
                    if (id.includes('/vue/')) return 'vue'
                },
            },
        },
    },
    server: {
        host: '0.0.0.0',
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/ws': {
                target: 'ws://127.0.0.1:8000',
                ws: true,
            },
        },
    },
    resolve: {
        alias: {
            '@': '/src',
        },
    },
})
