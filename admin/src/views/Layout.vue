<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="sidebar.isCollapsed ? '64px' : '220px'" class="aside">
      <div class="aside-header">
        <img src="/favicon.jpg" class="aside-logo" alt="logo" />
        <span v-if="!sidebar.isCollapsed" class="logo-text">灵山胜境后台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="sidebar.isCollapsed"
        :router="true"
        background-color="#0a1628"
        text-color="#8cccd6"
        active-text-color="#00e5cc"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>数据大屏</template>
        </el-menu-item>
                <el-menu-item index="/emotion-report">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>游客感受度报告</template>
        </el-menu-item>
        <el-menu-item index="/consumption">
          <el-icon><Money /></el-icon>
          <template #title>消费分析</template>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><User /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>
        <el-menu-item index="/digital-humans">
          <el-icon><MagicStick /></el-icon>
          <template #title>数字人管理</template>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Notebook /></el-icon>
          <template #title>知识库管理</template>
        </el-menu-item>
        <el-menu-item index="/routes">
          <el-icon><MapLocation /></el-icon>
          <template #title>游览路线管理</template>
        </el-menu-item>
        <el-menu-item index="/chat-logs">
          <el-icon><ChatDotSquare /></el-icon>
          <template #title>对话日志</template>
        </el-menu-item>
        <!-- <el-menu-item index="/ai-config">
          <el-icon><Setting /></el-icon>
          <template #title>AI参数配置</template>
        </el-menu-item> -->
        <el-menu-item index="/admins">
          <el-icon><UserFilled /></el-icon>
          <template #title>管理员管理</template>
        </el-menu-item>

      </el-menu>
    </el-aside>

    <!-- 主体区域 -->
    <el-container>
      <!-- 顶部导航 -->
      <el-header class="header">
        <div class="header-left">
          <el-button text class="toggle-btn" @click="sidebar.toggle()">
            <el-icon :size="20"><Fold v-if="!sidebar.isCollapsed" /><Expand v-else /></el-icon>
          </el-button>
          <span class="page-name">{{ route.meta.title }}</span>
        </div>
        <div class="header-right">
          <span class="admin-name">
            <el-icon :size="16"><User /></el-icon>
            {{ adminStore.adminInfo?.username || '管理员' }}
          </span>
          <el-button class="logout-btn" text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <!-- 内容区域 -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAdminStore, useSidebarStore } from '@/store'

const route = useRoute()
const router = useRouter()
const adminStore = useAdminStore()
const sidebar = useSidebarStore()

const activeMenu = computed(() => route.path)

function handleLogout() {
  ElMessageBox.confirm('确定要退出登录吗？', '提示').then(() => {
    adminStore.logout()
    router.push('/login')
  }).catch(() => {})
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
  background: #0c1422;
}

.aside {
  background: linear-gradient(180deg, #0a1628 0%, #0d1a2b 100%);
  transition: width 0.3s ease;
  overflow: hidden;
  border-right: 1px solid rgba(0, 136, 153, 0.2);
}

.aside-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #e6f7ff;
  font-size: 15px;
  font-weight: 600;
  border-bottom: 1px solid rgba(0, 136, 153, 0.2);
  letter-spacing: 0.5px;
}

.aside-logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 229, 204, 0.2);
}

.aside-header:deep(.logo-text) {
  display: flex;
  align-items: center;
}

:deep(.el-menu) {
  border-right: none !important;
}

:deep(.el-menu-item) {
  margin: 2px 8px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

:deep(.el-menu-item:hover) {
  background: rgba(0, 229, 204, 0.08) !important;
}

:deep(.el-menu-item.is-active) {
  background: rgba(0, 229, 204, 0.12) !important;
  position: relative;
}

:deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: #00e5cc;
  border-radius: 0 3px 3px 0;
}

.header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(12, 20, 34, 0.95);
  border-bottom: 1px solid rgba(0, 136, 153, 0.15);
  padding: 0 24px;
  backdrop-filter: blur(12px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.toggle-btn {
  color: #8cccd6 !important;
  font-size: 18px;
}

.toggle-btn:hover {
  color: #00e5cc !important;
  background: rgba(0, 229, 204, 0.08) !important;
}

.page-name {
  font-size: 16px;
  font-weight: 600;
  color: #e6f7ff;
  letter-spacing: 0.5px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.admin-name {
  font-size: 13px;
  color: #8cccd6;
  display: flex;
  align-items: center;
  gap: 6px;
}

.logout-btn {
  color: #66a0ad !important;
  font-size: 13px !important;
}

.logout-btn:hover {
  color: #00e5cc !important;
  background: rgba(0, 229, 204, 0.08) !important;
}

.main-content {
  background: radial-gradient(ellipse at top, #0f1a2e 0%, #0a101f 50%, #060c16 100%);
  padding: 20px;
  overflow-y: auto;
}

/* 自定义滚动条 */
.main-content::-webkit-scrollbar {
  width: 6px;
}

.main-content::-webkit-scrollbar-track {
  background: transparent;
}

.main-content::-webkit-scrollbar-thumb {
  background: rgba(0, 136, 153, 0.2);
  border-radius: 3px;
}

.main-content::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 136, 153, 0.4);
}
</style>