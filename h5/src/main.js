/**
 * 【灵山胜境AI数字人导游系统】游客移动端H5入口
 * 技术栈：Vue3 + Vant4 + Pinia
 * UI风格：国风浅青+淡金配色
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Vant 组件库（按需引入）
import { 
  Button, Cell, CellGroup, Field, Form, NavBar, Tabbar, TabbarItem,
  Icon, Dialog, Loading, Uploader, Image, Tag, Popup,
  Swipe, SwipeItem, List, PullRefresh, Empty, Badge, ActionSheet,
  Tabs, Tab, Switch, Rate
} from 'vant'
import 'vant/lib/index.css'

// 创建应用
const app = createApp(App)

// 状态管理
const pinia = createPinia()
app.use(pinia)
app.use(router)

// 注册Vant组件
app.use(Button)
app.use(Cell)
app.use(CellGroup)
app.use(Field)
app.use(Form)
app.use(NavBar)
app.use(Tabbar)
app.use(TabbarItem)
app.use(Icon)
app.use(Dialog)
app.use(Loading)
app.use(Uploader)
app.use(Image)
app.use(Tag)
app.use(Popup)
app.use(Swipe)
app.use(SwipeItem)
app.use(List)
app.use(PullRefresh)
app.use(Empty)
app.use(Badge)
app.use(ActionSheet)
app.use(Tabs)
app.use(Tab)
app.use(Switch)
app.use(Rate)

// 全局懒加载指令（IntersectionObserver 实现，带 200px 预加载）
const LazyLoadDirective = {
  mounted(el, binding) {
    if (!binding.value) return
    const realSrc = el.dataset.src || el.getAttribute('data-src') || ''
    if (!realSrc) return
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            el.src = realSrc
            observer.unobserve(el)
          }
        })
      }, { rootMargin: '200px' })
      observer.observe(el)
    } else {
      el.src = realSrc
    }
  }
}

// 全局懒加载指令
app.directive('lazy-load', LazyLoadDirective)

// 全局样式
const style = document.createElement('style')
style.textContent = `
  :root {
    --primary-color: #5b8c5a;
    --primary-light: #7cb342;
    --gold-color: #c8a45c;
    --gold-light: #e8d5a3;
    --bg-color: #f5f7f0;
    --card-bg: rgba(255, 255, 255, 0.92);
    --text-primary: #2e3d2e;
    --text-secondary: #6b7c6b;
    --text-light: #9aab9a;
    --shadow-sm: 0 2px 8px rgba(91, 140, 90, 0.12);
    --shadow-md: 0 4px 16px rgba(91, 140, 90, 0.15);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 20px;
  }
  .van-nav-bar { background: linear-gradient(135deg, #5b8c5a, #7cb342) !important; }
  .van-nav-bar__title { color: #fff !important; }
  .van-nav-bar .van-icon { color: #fff !important; }
  .page-container { min-height: 100vh; padding-bottom: 60px; background: var(--bg-color); }
  .gold-btn { background: linear-gradient(135deg, #c8a45c, #d4b67a) !important; border: none !important; color: #fff !important; }
  .green-btn { background: linear-gradient(135deg, #5b8c5a, #7cb342) !important; border: none !important; color: #fff !important; }
`
document.head.appendChild(style)

// 挂载
app.mount('#app')