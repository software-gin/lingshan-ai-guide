/**
 * 灵山胜境AI数字人导游系统 - 管理后台入口
 * 技术栈：Vue3 + Element Plus + ECharts
 * UI风格：极简商务浅色风格，主色调沉稳深蓝
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import CustomSelect from './components/CustomSelect.vue'

const app = createApp(App)

// 全局注册Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 全局注册自定义下拉框组件，替换 el-select
app.component('CustomSelect', CustomSelect)

app.mount('#app')