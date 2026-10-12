<template>
  <div id="app-root">
    <router-view />
    <!-- 底部导航栏 -->
    <van-tabbar
      v-if="showTabbar"
      v-model="activeTab"
      active-color="#5b8c5a"
      inactive-color="#9aab9a"
      route
      safe-area-inset-bottom
      style="border-top: 1px solid rgba(91,140,90,0.1);"
    >
      <van-tabbar-item to="/home" icon="chat-o">AI导游</van-tabbar-item>
      <van-tabbar-item to="/route-plan" icon="guide-o">路线规划</van-tabbar-item>
      <van-tabbar-item to="/history" icon="records-o">对话历史</van-tabbar-item>
      <van-tabbar-item to="/user" icon="contact-o">我的</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeTab = ref(0)

// 控制底部导航显示（登录/注册页不显示）
const showTabbar = computed(() => {
  return !['login', 'register'].includes(route.name)
})

// 根据当前路由同步tab高亮
watch(() => route.path, (path) => {
  const tabMap = {
    '/home': 0,
    '/route-plan': 1,
    '/history': 2,
    '/user': 3
  }
  if (tabMap[path] !== undefined) {
    activeTab.value = tabMap[path]
  }
}, { immediate: true })
</script>

<style scoped>
#app-root {
  width: 100%;
  min-height: 100vh;
  padding-bottom: 50px; /* 为固定底部Tabbar留出空间，避免被遮挡 */
  background: #f5f7f0;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
</style>