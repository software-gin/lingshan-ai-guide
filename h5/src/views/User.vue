<template>
  <div class="user-page">
    <van-nav-bar title="个人中心" left-arrow @click-left="$router.back()" />

    <!-- 用户信息区域 -->
    <div class="user-profile">
      <div class="avatar">👤</div>
      <div class="user-info">
        <div class="username">{{ userStore.userInfo?.username || '游客' }}</div>
        <div class="user-meta">
          <span v-if="userStore.userInfo?.phone">{{ userStore.userInfo.phone }}</span>
          <span v-if="userStore.userInfo?.email"> · {{ userStore.userInfo.email }}</span>
        </div>
      </div>
    </div>

    <!-- 功能列表 -->
    <van-cell-group inset class="menu-group">
      <van-cell title="切换数字人导游" is-link @click="$router.push('/digital-human')" />
      <van-cell title="对话历史记录" is-link @click="$router.push('/history')" />
      <van-cell title="游览路线规划" is-link @click="$router.push('/route-plan')" />
    </van-cell-group>

    <!-- 我的记忆（memoryAgent，合规：可查看/可清除） -->
    <van-cell-group inset class="menu-group">
      <van-collapse v-model="memoryOpen">
        <van-collapse-item name="memory" @change="onMemoryToggle">
          <template #title>
            <span>我的记忆</span>
            <span class="memory-subtitle">AI 记住你的偏好，让服务更懂你</span>
          </template>
          <div v-if="memories.length === 0 && !memoriesLoading" class="memory-empty">
            暂无记忆。多和 AI 导游聊聊，它会记住你的出游偏好。
          </div>
          <van-loading v-if="memoriesLoading" class="memory-loading" size="18" vertical>加载中...</van-loading>
          <div v-else class="memory-list">
            <div v-for="m in memories" :key="m.id" class="memory-item">
              <van-tag :type="memoryTagType(m.memory_type)" plain class="memory-tag">
                {{ memoryLabel(m.memory_type) }}
              </van-tag>
              <div class="memory-content">{{ m.content }}</div>
              <div class="memory-time">{{ m.created_at }}</div>
            </div>
          </div>
          <van-button
            v-if="memories.length > 0"
            size="small"
            round
            plain
            type="danger"
            class="memory-clear-btn"
            :loading="clearing"
            @click="handleClearMemories"
          >
            清除全部记忆
          </van-button>
        </van-collapse-item>
      </van-collapse>
    </van-cell-group>

    <!-- 当前数字人信息 -->
    <div class="dh-section">
      <div class="section-title">当前AI导游</div>
      <div class="dh-card">
        <div class="dh-icon">🪷</div>
        <div class="dh-name">{{ dhStore.currentName }}</div>
        <van-tag type="success" plain>在线</van-tag>
      </div>
    </div>

    <!-- 退出登录 -->
    <van-button
      round
      block
      plain
      class="logout-btn"
      @click="handleLogout"
    >
      退出登录
    </van-button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast, showFailToast, Dialog } from 'vant'
import { useUserStore, useDigitalHumanStore } from '@/store'
import { userLogout, getUserMemories, clearUserMemories } from '@/utils/api'

const router = useRouter()
const userStore = useUserStore()
const dhStore = useDigitalHumanStore()

// ---- 我的记忆（memoryAgent 合规面板） ----
const memoryOpen = ref([])
const memories = ref([])
const memoriesLoading = ref(false)
const memoriesLoaded = ref(false)
const clearing = ref(false)

const MEMORY_LABELS = { summary: '会话摘要', profile: '偏好画像', fact: '关键事实' }
function memoryLabel(t) { return MEMORY_LABELS[t] || '记忆' }
function memoryTagType(t) {
  return t === 'profile' ? 'success' : (t === 'summary' ? 'primary' : 'warning')
}

function onMemoryToggle(names) {
  // 首次展开时加载记忆列表
  if (Array.isArray(names) && names.includes('memory') && !memoriesLoaded.value) {
    loadMemories()
  }
}

async function loadMemories() {
  memoriesLoading.value = true
  try {
    const res = await getUserMemories()
    if (res.code === 200) {
      memories.value = res.data || []
      memoriesLoaded.value = true
    } else {
      showFailToast(res.message || '记忆加载失败')
    }
  } catch (e) {
    console.warn('记忆加载失败:', e)
  } finally {
    memoriesLoading.value = false
  }
}

function handleClearMemories() {
  Dialog.confirm({
    title: '清除全部记忆',
    message: '将删除 AI 保存的全部会话摘要与偏好信息，删除后无法恢复。确定清除吗？',
    confirmButtonText: '清除',
    cancelButtonText: '取消',
    confirmButtonColor: '#ee0a24'
  }).then(async () => {
    clearing.value = true
    try {
      const res = await clearUserMemories()
      if (res.code === 200) {
        memories.value = []
        showSuccessToast(res.message || '记忆已清除')
      } else {
        showFailToast(res.message || '清除失败')
      }
    } catch (e) {
      console.warn('记忆清除失败:', e)
    } finally {
      clearing.value = false
    }
  }).catch(() => {})
}

async function handleLogout() {
  try {
    await userLogout()
  } catch (e) {
    console.warn('退出登录接口调用失败，继续清除本地状态', e)
  }

  userStore.logout()
  showSuccessToast('已退出登录')
  router.push('/login')
}
</script>

<style scoped>
.user-page {
  min-height: 100vh;
  background: #f5f7f0;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 32px 20px;
  background: linear-gradient(135deg, #5b8c5a, #7cb342);
  color: #fff;
}

.avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
}

.username {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 4px;
}

.user-meta {
  font-size: 13px;
  opacity: 0.8;
}

.menu-group {
  margin: 16px;
}

/* ===== 我的记忆 ===== */
.memory-subtitle {
  display: block;
  font-size: 11px;
  color: #9aab9a;
  margin-top: 2px;
}

.memory-loading {
  padding: 20px 0;
}

.memory-empty {
  padding: 12px 4px;
  font-size: 13px;
  color: #9aab9a;
  line-height: 1.8;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

.memory-item {
  padding: 10px 12px;
  background: #f7faf5;
  border-radius: 10px;
}

.memory-tag {
  margin-bottom: 6px;
}

.memory-content {
  font-size: 13px;
  color: #2e3d2e;
  line-height: 1.7;
  word-break: break-word;
}

.memory-time {
  margin-top: 6px;
  font-size: 11px;
  color: #b0bcb0;
}

.memory-clear-btn {
  margin-top: 14px;
}

.dh-section {
  margin: 16px;
}

.section-title {
  font-size: 14px;
  color: #6b7c6b;
  margin-bottom: 10px;
  padding-left: 4px;
}

.dh-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.dh-icon {
  font-size: 32px;
}

.dh-name {
  flex: 1;
  font-size: 15px;
  font-weight: 500;
  color: #2e3d2e;
}

.logout-btn {
  margin: 32px 16px;
  color: #e74c3c;
  border-color: #e74c3c;
  width: auto;
}
</style>