<template>
  <div class="history-page">
    <van-nav-bar title="对话历史" left-arrow @click-left="$router.back()">
      <template #right>
        <van-button size="mini" plain type="success" color="#5b8c5a" @click="showClearDialog">
          清除全部
        </van-button>
      </template>
    </van-nav-bar>

    <van-dialog
      v-model:show="showClearConfirm"
      title="确认清除"
      showCancelButton
      confirmButtonText="清除"
      cancelButtonText="取消"
      confirmButtonColor="#5b8c5a"
      @confirm="confirmClear"
    >
      <p style="margin:16px 0;color:#666;font-size:14px;">清除后将无法恢复，确定要删除所有对话记录吗？</p>
    </van-dialog>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        finished-text="没有更多了"
        @load="loadMore"
      >
        <div
          v-for="session in sessions"
          :key="session.session_id"
          ref="sessionRefs"
          class="session-card"
        >
          <div class="session-header" @click="toggleSession(session.session_id)">
            <div class="session-info">
              <div class="session-meta">
                <div class="session-title">{{ truncateText(session.title, 25) }}</div>
                <div class="session-sub">
                  {{ session.time }} · {{ session.message_count }} 轮对话
                </div>
              </div>
            </div>
            <div class="session-actions">
              <span class="expand-label">{{ expandedId === session.session_id ? '收起' : '展开' }}</span>
            </div>
          </div>

          <div class="session-messages" v-if="expandedId === session.session_id">
            <div
              v-for="msg in session.messages"
              :key="msg.id"
              class="msg-item"
            >
              <div class="msg-question">
                <span class="role-tag user-tag">用户</span>
                <div>
                  <span>{{ msg.question_text }}</span>
                  <div v-if="msg.image_urls && msg.image_urls.length > 0" class="msg-images">
                    <img
                      v-for="(url, idx) in msg.image_urls"
                      :key="idx"
                      :src="url"
                      :alt="`图片 ${idx + 1}`"
                      class="msg-image-thumb"
                      @click="previewImage(url)"
                    />
                  </div>
                </div>
              </div>
              <div class="msg-answer">
                <span class="role-tag ai-tag">数字人</span>
                <span>{{ truncateText(msg.answer_text, 200) }}</span>
              </div>
              <div class="msg-footer">
                <span class="msg-time">{{ msg.question_time }}</span>
                <span class="msg-emotion">{{ msg.emotion_label }}</span>
              </div>
            </div>
          </div>
        </div>

        <van-empty v-if="!loading && sessions.length === 0" description="暂无对话记录" />
      </van-list>
    </van-pull-refresh>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { showSuccessToast, showFailToast } from 'vant'
import { getChatHistory, clearChatHistory } from '@/utils/api'

const sessions = ref([])
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const page = ref(1)
const expandedId = ref(null)
const showClearConfirm = ref(false)
const clearing = ref(false)
const sessionRefs = ref([])

function truncateText(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

function previewImage(url) {
  import('vant').then(({ ImagePreview }) => {
    ImagePreview([{ url }])
  })
}

async function toggleSession(sid) {
  expandedId.value = expandedId.value === sid ? null : sid
  // Auto-scroll to the expanded session
  await nextTick()
  if (expandedId.value) {
    const idx = sessions.value.findIndex(s => s.session_id === sid)
    if (idx >= 0 && sessionRefs.value[idx]) {
      sessionRefs.value[idx].scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }
}

async function loadMore() {
  loading.value = true
  try {
    const res = await getChatHistory({ page: page.value, per_page: 10 })
    if (res.code === 200 && res.data?.sessions) {
      sessions.value.push(...res.data.sessions)
      finished.value = res.data.sessions.length < 10
      page.value++
    } else {
      finished.value = true
    }
  } catch (e) {
    finished.value = true
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function onRefresh() {
  page.value = 1
  sessions.value = []
  expandedId.value = null
  finished.value = false
  loadMore()
}

function showClearDialog() {
  if (sessions.value.length === 0) {
    showFailToast('没有可清除的对话记录')
    return
  }
  showClearConfirm.value = true
}

async function confirmClear() {
  showClearConfirm.value = false
  clearing.value = true
  try {
    const res = await clearChatHistory()
    if (res.code === 200) {
      sessions.value = []
      page.value = 1
      expandedId.value = null
      showSuccessToast(res.message || '已清除所有对话记录')
    } else {
      showFailToast(res.message || '清除失败')
    }
  } catch (e) {
    showFailToast('清除失败，请稍后重试')
  } finally {
    clearing.value = false
  }
}
</script>

<style scoped>
.history-page {
  min-height: 100vh;
  background: #f5f7f0;
}
.session-card {
  background: #fff;
  margin: 8px 16px;
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  overflow: hidden;
}
.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px;
  cursor: pointer;
}
.session-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.session-title { font-size: 15px; font-weight: 600; color: #2e3d2e; }
.session-sub { font-size: 12px; color: #9aab9a; margin-top: 2px; }
.session-actions { display: flex; align-items: center; gap: 12px; }
.expand-label {
  font-size: 13px;
  color: #9aab9a;
}
.session-messages {
  border-top: 1px solid #f0f4eb;
  padding: 8px 14px 12px;
  max-height: 360px;
  overflow-y: auto;
}
.msg-item {
  padding: 8px 0;
  border-bottom: 1px solid #f5f7f0;
}
.msg-item:last-child { border-bottom: none; }
.msg-question, .msg-answer {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 13px;
  line-height: 1.6;
  padding: 3px 0;
}
.role-tag {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
}
.user-tag {
  color: #fff;
  background: #5b8c5a;
}
.ai-tag {
  color: #5b8c5a;
  background: #e8efe8;
}
.msg-question { color: #5b8c5a; }
.msg-answer { color: #4b5b4b; }
.msg-footer {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #b0b8b0;
  margin-top: 4px;
}

/* 消息中的图片 */
.msg-images {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}
.msg-image-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
  cursor: pointer;
}
</style>
