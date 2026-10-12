<template>
  <div class="home-page">
    <!-- 顶部导航 -->
    <div class="home-header">
      <div class="header-left">
        <div class="dh-header" @click="goDigitalHuman">
          <div class="dh-header-avatar" v-if="!headerAvatarError">
            <img
              :src="headerAvatarUrl"
              @error="onHeaderAvatarError"
              alt="数字人头像"
              class="dh-header-avatar-img"
            />
            <span v-if="headerAvatarError" class="dh-header-avatar-fallback">🪷</span>
          </div>
          <span class="dh-name">{{ dhStore.currentName }}</span>
        </div>
      </div>
      <div class="header-right">
        <van-icon name="guide-o" size="20" @click="$router.push('/route-plan')" />
        <van-icon name="records-o" size="20" @click="$router.push('/history')" style="margin-left:16px;" />
      </div>
    </div>

    <!-- ===== 内容区（数字人跨模式持久，v-show 切布局） ===== -->
    <div class="content-area" :class="viewMode === 'full' ? 'full-mode' : 'chat-mode'">
      <!-- 数字人：唯一实例，切换 class 而非销毁重建 -->
      <div
        v-if="dhReady"
        :class="['live2d-container', viewMode === 'full' ? 'live2d-full' : 'live2d-compact']"
        @click="onAvatarClick"
      >
        <Live2DViewer
          ref="live2dRef"
          :emotion="chatStore.currentEmotion"
          :is-speaking="chatStore.isSpeaking"
          :dh-id="dhStore.currentId"
        />
        <div class="emotion-badge" v-if="chatStore.currentEmotion !== '平静'">
          {{ chatStore.currentEmotion === '热情' ? '🔥' : '😊' }}
          {{ chatStore.currentEmotion }}
        </div>
        <!-- 通话状态指示（仅模式A） -->
        <div class="call-indicator" v-if="callActive && viewMode === 'full'">
          <span class="call-dot"></span> 通话中
        </div>
      </div>

      <!-- 模式B：对话区 -->
      <div v-show="viewMode === 'chat'" class="chat-bubbles" ref="bubbleRef">
        <div v-if="messages.length === 0" class="chat-empty">
          <div class="empty-icon">💬</div>
          <p class="empty-text">输入你的问题，AI导游为你解答</p>
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="`${msg.id}-${i}`"
          :class="['bubble', msg.role === 'user' ? 'user-bubble' : 'ai-bubble']"
        >
          <div class="bubble-avatar" v-if="msg.role === 'user'">👤</div>
          <div class="bubble-content">
            <!-- 用户消息中的视频预览 -->
            <div v-if="msg.videoUrl" class="bubble-video-wrap">
              <video
                :src="msg.videoUrl"
                class="bubble-video"
                controls
                preload="metadata"
                playsinline
              ></video>
            </div>
            <!-- 用户消息中的图片预览（独立判断，不级联） -->
            <div v-if="msg.imageUrls && msg.imageUrls.length > 0" class="bubble-images">
              <img
                v-for="(url, imgIdx) in msg.imageUrls"
                :key="imgIdx"
                :src="url"
                :alt="`用户图片 ${imgIdx + 1}`"
                class="bubble-image"
                @click="previewImage(url)"
              />
            </div>
            <!-- 文本内容（独立于图片存在与否） -->
            <div class="bubble-text thinking" v-if="msg.role === 'ai' && !msg.text">
              <template v-if="i === messages.length - 1 && chatStore.isProcessing">
                <span class="dot-pulse"></span>
              </template>
              <template v-else>
                <span class="stopped-text">已停止思考</span>
              </template>
            </div>
            <div class="bubble-text" v-if="msg.text">{{ msg.text }}</div>
            <div v-if="msg.role === 'ai' && msg.routeInfo" class="route-action">
              <van-button size="small" round plain type="primary" @click="openRouteMap(msg.routeInfo)">
                查看地图
              </van-button>
            </div>
            <div class="bubble-meta">
              <span class="bubble-time">{{ msg.time }}</span>
              <span class="bubble-emotion" v-if="msg.emotion && msg.emotion !== '平静'">
                {{ msg.emotion === '热情' ? '🔥' : '😊' }} {{ msg.emotion }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模式A：通话操作栏 -->
    <div v-show="viewMode === 'full'" class="action-bar">
      <div class="action-btn mute" :class="{ active: audioMuted }" @click="toggleMute">
        <van-icon :name="audioMuted ? 'volume-o' : 'volume-o'" size="22" />
        <span>{{ audioMuted ? '已静音' : '静音' }}</span>
      </div>
      <div class="action-btn call" :class="{ active: callActive }" @click="toggleCall">
        <van-icon name="phone-o" size="32" />
        <span>{{ callActive ? '挂断' : '通话' }}</span>
      </div>
      <div class="action-btn text" @click="openTextChat">
        <van-icon name="chat-o" size="22" />
        <span>文字</span>
      </div>
    </div>

    <!-- 模式B：底部输入区域（媒体缩略图条 + 输入框） -->
    <div v-show="viewMode === 'chat'" class="input-area">
      <!-- 已选视频（单视频，优先于图片发送） -->
      <div v-if="selectedVideo" class="selected-video-area">
        <div class="selected-video-thumb">
          <video :src="selectedVideo.url" preload="metadata" muted></video>
          <span class="video-badge">🎬 视频</span>
          <div class="thumb-remove" @click="removeVideo">
            <van-icon name="cross" size="12" />
          </div>
        </div>
        <span class="thumb-clear" @click="removeVideo">移除视频</span>
      </div>

      <!-- 已选图片缩略图条（独立区域，与输入框完全分离） -->
      <div v-if="selectedImages.length > 0" class="selected-images-area">
        <div class="selected-images-row">
          <div
            v-for="(img, idx) in selectedImages"
            :key="idx"
            class="selected-thumb"
          >
            <img :src="img.url" :alt="img.name" />
            <div class="thumb-remove" @click="removeImage(idx)">
              <van-icon name="cross" size="12" />
            </div>
          </div>
        </div>
        <div class="selected-images-meta">
          <span class="thumb-count">{{ selectedImages.length }} 张</span>
          <span class="thumb-clear" @click="clearSelectedImages">清空</span>
        </div>
      </div>

      <!-- 输入框（图片条下方） -->
      <div class="input-bar">
        <div class="input-wrapper">
          <van-icon name="photo-o" size="22" color="#5b8c5a" @click="openImagePicker" />

          <template v-if="!voiceMode">
            <input
              v-model="inputText"
              class="text-input"
              :placeholder="selectedVideo ? '描述你想问的视频内容...' : (selectedImages.length > 0 ? '描述图片内容，或输入问题...' : '输入问题...')"
              @keydown.enter="sendText"
            />
            <van-icon
              v-if="chatStore.isProcessing || chatStore.isSpeaking"
              name="stop-circle-o"
              color="#e74c3c"
              size="22"
              @click="stopReply"
            />
            <van-icon
              v-else-if="!inputText.trim() && selectedImages.length === 0 && !selectedVideo"
              name="volume-o"
              color="#5b8c5a"
              size="22"
              @click="enterVoiceMode"
            />
            <van-icon
              v-else-if="!chatStore.isProcessing && !chatStore.isSpeaking"
              name="arrow-up"
              size="20"
              color="#fff"
              class="send-btn"
              @click="sendText"
            />
          </template>

          <template v-else>
            <div
              :class="['hold-to-speak', { recording: isRecording }]"
              @mousedown.prevent="startHoldSpeak"
              @mouseup.prevent="stopHoldSpeak"
              @mouseleave.prevent="stopHoldSpeak"
              @touchstart.prevent="startHoldSpeak"
              @touchend.prevent="stopHoldSpeak"
            >
              {{ isRecording ? '🎙️ 正在聆听...' : '🎙️ 请按住说话' }}
            </div>
            <van-icon
              v-if="chatStore.isProcessing || chatStore.isSpeaking"
              name="stop-circle-o"
              color="#e74c3c"
              size="22"
              @click="stopReply"
            />
            <van-icon
              v-else-if="!isRecording"
              name="chat-o"
              color="#5b8c5a"
              size="22"
              @click="exitVoiceMode"
            />
          </template>
        </div>

        <!-- 清除对话按钮（输入框右侧，独立于输入框外） -->
        <span v-if="messages.length > 0" class="clear-chat-icon" @click="clearChat" aria-label="清除对话">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18"/>
            <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/>
            <path d="M5 6l1 14a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-14"/>
            <path d="M10 10v7"/>
            <path d="M14 10v7"/>
          </svg>
        </span>
      </div>
    </div>

    <!-- 模式A文字输入弹窗 -->
    <van-popup v-model:show="showTextPopup" position="bottom" round :style="{ minHeight: '40%' }">
      <div class="text-popup">
        <div class="popup-header">
          <span>文字提问</span>
          <van-icon name="cross" size="18" @click="showTextPopup = false" />
        </div>
        <div class="popup-body">
          <textarea
            ref="popupTextRef"
            v-model="popupText"
            class="popup-textarea"
            placeholder="输入你的问题..."
            rows="4"
          ></textarea>
          <div class="popup-actions">
            <van-icon name="photo-o" size="22" color="#5b8c5a" @click="showImageUpload = true" />
            <van-button round type="primary" class="green-btn" @click="sendPopupText" :disabled="!popupText.trim()">
              发送
            </van-button>
          </div>
        </div>
      </div>
    </van-popup>

    <!-- 图片/视频选择弹窗（底部弹出） -->
    <van-action-sheet v-model:show="showImageUpload" title="选择图片或视频" close-on-click-action>
      <div class="upload-sheet">
        <div class="upload-choices">
          <div class="upload-choice" @click="triggerFileSelect">
            <van-icon name="photo-o" size="36" color="#5b8c5a" />
            <span>选择图片</span>
          </div>
          <div class="upload-choice" @click="triggerVideoSelect">
            <van-icon name="video-o" size="36" color="#5b8c5a" />
            <span>选择视频</span>
          </div>
        </div>
        <p class="upload-tip">图片最多 9 张（单张 ≤10MB）；视频单个 ≤100MB，支持 MP4/AVI/MOV/MKV/WebM</p>
      </div>
    </van-action-sheet>

    <!-- 隐藏的文件选择 input -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      multiple
      style="display:none"
      @change="handleFileSelect"
    />

    <!-- 隐藏的视频选择 input -->
    <input
      ref="videoInputRef"
      type="file"
      accept="video/mp4,video/avi,video/quicktime,video/x-matroska,video/webm,video/*"
      style="display:none"
      @change="handleVideoSelect"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast, showSuccessToast, showLoadingToast, closeToast, showNotify, Dialog } from 'vant'
import { useChatStore, useDigitalHumanStore, useUserStore } from '@/store'
import { createWsClient, getWsClient, destroyWsClient } from '@/utils/websocket'
import { getWsInfo, getUserInfo, uploadImage, uploadVideo } from '@/utils/api'
import Live2DViewer from '@/components/Live2DViewer.vue'

const router = useRouter()
const chatStore = useChatStore()
const dhStore = useDigitalHumanStore()
const userStore = useUserStore()

// ---- 双模式状态 ----
const viewMode = ref('full')        // 'full' | 'chat'
const callActive = ref(false)       // 持续收音开关
const audioMuted = ref(false)       // 静音数字人播报
const showTextPopup = ref(false)    // 模式A文字弹窗
const popupText = ref('')
const popupTextRef = ref(null)
const userLocation = ref(null)
const dhReady = ref(false)          // 数字人偏好加载完成，再渲染 Live2DViewer

// ---- 图片上传状态 ----
const selectedImages = ref([])      // 当前选中的图片 { url, name }
const uploading = ref(false)        // 上传中

// ---- 视频上传状态（单视频，优先于图片发送） ----
const selectedVideo = ref(null)     // { url, name }
const videoInputRef = ref(null)
const MAX_VIDEO_SIZE = 100 * 1024 * 1024  // 100MB，与后端 VIDEO_MAX_SIZE 一致

// ---- 顶部头像状态 ----
const headerAvatarLoading = ref(false)
const headerAvatarError = ref(false)
const headerAvatarUrl = computed(() => {
  const currentDh = dhStore.getCurrentHuman()
  if (!currentDh || !currentDh.model_path) return ''
  return `/api/user/avatars/${encodeURIComponent(currentDh.model_path)}/preview?t=${Date.now()}`
})

function onHeaderAvatarError() {
  headerAvatarLoading.value = false
  headerAvatarError.value = true
}

// 监听当前数字人变化，重置头像状态
watch(() => dhStore.currentId, () => {
  headerAvatarLoading.value = true
  headerAvatarError.value = false
}, { deep: false })

// ---- 原有状态 ----
const inputText = ref('')
const showImageUpload = ref(false)
const isRecording = ref(false)
const voiceMode = ref(false)
const bubbleRef = ref(null)
const live2dRef = ref(null)
let currentAudioSource = null
let isDiscarded = false
let doneTimeoutId = null
let sessionIdTimer = null

// --- 响应式消息列表 ---
const messages = computed(() => chatStore.messages)
const hasLastAiMsg = computed(() => {
  const msgs = chatStore.messages
  return msgs.length > 0 && msgs[msgs.length - 1].role === 'ai'
})

// 思考气泡：isProcessing 且最后一条 AI 消息还没有文字内容
const showThinkingBubble = computed(() => {
  if (!chatStore.isProcessing) return false
  const msgs = chatStore.messages
  if (msgs.length === 0) return true
  const last = msgs[msgs.length - 1]
  return last.role === 'ai' && !last.text
})

// ===== 生命周期 =====
onMounted(async () => {
  if (!userStore.isLoggedIn) {
    router.push('/login')
    return
  }

  try {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition((position) => {
        userLocation.value = {
          lat: position.coords.latitude,
          lng: position.coords.longitude
        }
      }, () => {
        userLocation.value = null
      }, { timeout: 4000 })
    }
  } catch (e) {
    console.warn('定位失败', e)
  }

  // 第一步：先加载数字人列表和服务端保存的用户偏好
  await fetchDigitalHumans()
  await loadSavedDigitalHuman()

  // 第二步：数字人准备就绪，再渲染 Live2DViewer（确保首次连接就用正确的数字人）
  dhReady.value = true

  // 第三步：建立 WebSocket 连接（使用正确的 dhStore.currentId）
  try {
    const res = await getWsInfo()
    if (res.code === 200) {
      const wsUrl = res.data.ws_url
      createWsClient(wsUrl, {
        user_id: userStore.userInfo?.id || 0,
        digital_human_id: dhStore.currentId
      })
      setupWsHandlers()
    }
  } catch (e) {
    console.warn('WebSocket连接失败，降级为模拟模式:', e)
  }

  sessionIdTimer = setInterval(() => {
    const sid = live2dRef.value?.getSessionId?.()
    if (sid) {
      const ws = getWsClient()
      if (ws) ws.setLtSessionId(sid)
    }
  }, 500)
})

onUnmounted(() => {
  if (sessionIdTimer) clearInterval(sessionIdTimer)
  destroyWsClient()
})

watch(
  () => chatStore.messages.length,
  () => nextTick(() => scrollToBottom())
)

// 数字人切换后重新连接 WebSocket（确保新配置生效）
watch(
  () => dhStore.currentId,
  async (newId, oldId) => {
    if (newId === oldId) return
    console.log(`[Home] 检测到数字人切换：${oldId} -> ${newId}，重新连接 WebSocket`)
    try {
      const res = await getWsInfo()
      if (res.code === 200) {
        destroyWsClient()
        createWsClient(res.data.ws_url, {
          user_id: userStore.userInfo?.id || 0,
          digital_human_id: newId
        })
        setupWsHandlers()
      }
    } catch (e) {
      console.warn('[Home] 数字人切换后重连 WebSocket 失败:', e)
    }
  }
)

// ===== WebSocket处理器 =====
const audioQueue = ref([])
let isPlayingAudio = false
let audioContext = null

function getAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
  }
  return audioContext
}

function playNextAudio() {
  if (isPlayingAudio || audioQueue.value.length === 0) return
  isPlayingAudio = true

  const audioB64 = audioQueue.value.shift()
  try {
    const audioBytes = Uint8Array.from(atob(audioB64), c => c.charCodeAt(0))
    const ctx = getAudioContext()
    ctx.decodeAudioData(audioBytes.buffer, (buffer) => {
      const source = ctx.createBufferSource()
      currentAudioSource = source
      source.buffer = buffer
      // 如果静音，不连接扬声器，但仍走完播放流程
      if (!audioMuted.value) {
        source.connect(ctx.destination)
      }
      source.onended = () => {
        if (currentAudioSource === source) currentAudioSource = null
        isPlayingAudio = false
        if (audioQueue.value.length > 0) playNextAudio()
        else chatStore.isSpeaking = false
      }
      chatStore.isSpeaking = true
      source.start(0)
    }, () => {
      isPlayingAudio = false
      playNextAudio()
    })
  } catch (e) {
    console.warn('[Audio] 播放失败:', e)
    isPlayingAudio = false
    playNextAudio()
  }
}

function setupWsHandlers() {
  const ws = getWsClient()
  if (!ws) return

  ws.on('user_text', (text) => {
    if (text) {
      chatStore.addUserMessage(text, 'voice')
      scrollToBottom()
    }
  })

  ws.on('text_start', () => {
    isDiscarded = false
    if (doneTimeoutId) {
      clearTimeout(doneTimeoutId)
      doneTimeoutId = null
    }
    // 如果前端已经预创建了空 AI 消息（sendText 立即展示），不再重复创建
    const msgs = chatStore.messages
    const lastEmpty = msgs.length > 0 && msgs[msgs.length - 1].role === 'ai' && !msgs[msgs.length - 1].text
    if (!lastEmpty) {
      chatStore.setProcessing(true)
      chatStore.setEmotion('平静')
      audioQueue.value = []
      isPlayingAudio = false
      chatStore.addAiMessage('')
    }
  })

  ws.on('text_chunk', ({ text }) => {
    if (isDiscarded) return
    chatStore.appendAiText(text)
    scrollToBottom()
  })

  ws.on('text_end', () => {
    if (isDiscarded) return
    chatStore.setProcessing(false)
  })

  ws.on('audio_chunk', ({ audio, lt_synced }) => {
    if (isDiscarded) return
    if (lt_synced) {
      chatStore.isSpeaking = true
      return
    }
    if (audio) {
      audioQueue.value.push(audio)
      if (!isPlayingAudio) playNextAudio()
    }
  })

  ws.on('emotion', (emotion) => {
    if (isDiscarded) return
    chatStore.setEmotion(emotion)
  })

  // ---- 状态消息（仅显示重要状态） ----
  ws.on('status', (msg) => {
    if (msg && msg.includes('音频服务暂不可用')) {
      showNotify({ type: 'warning', message: '语音服务暂不可用，已切换为文字模式', duration: 3000 })
    }
  })

  ws.on('error', (error) => {
    showFailToast(error)
    chatStore.setProcessing(false)
  })

  ws.on('done', () => {
    if (isDiscarded) return
    chatStore.setProcessing(false)
    // 解除 VAD 冷却锁，允许用户再次说话
    if (callVadCooldownTimer) {
      clearTimeout(callVadCooldownTimer)
      callVadCooldownTimer = null
    }
    callVadCooldown = false
    if (audioQueue.value.length === 0) {
      if (doneTimeoutId) clearTimeout(doneTimeoutId)
      doneTimeoutId = setTimeout(() => {
        chatStore.isSpeaking = false
        doneTimeoutId = null
      }, 1000)
    }
  })

  ws.on('route', (routeInfo) => {
    if (isDiscarded) return
    const lastAi = chatStore.messages[chatStore.messages.length - 1]
    if (lastAi?.role === 'ai') {
      lastAi.routeInfo = routeInfo
      chatStore.persistMessages()
    }
  })
}

// ===== 模式切换 =====
function openTextChat() {
  viewMode.value = 'chat'
  showTextPopup.value = false
  popupText.value = ''
  nextTick(() => scrollToBottom())
}

function closeTextChat() {
  viewMode.value = 'full'
}

// ===== 通话控制按钮 =====
function toggleCall() {
  callActive.value = !callActive.value
  if (callActive.value) {
    startCallRecording()
  } else {
    stopCallRecording()
    closeToast()
  }
}

function toggleMute() {
  audioMuted.value = !audioMuted.value
  if (live2dRef.value) {
    if (audioMuted.value) {
      live2dRef.value.muteVideo?.()
    } else {
      live2dRef.value.unmuteVideo?.()
    }
  }
}

// ===== 通话模式：持续录音 + 简单 VAD 打断 =====
let callStream = null
let callAudioCtx = null
let callSource = null
let callAnalyser = null
let callIntervalId = null
let callMediaRecorder = null
let callAudioChunks = []
let callVadSpeaking = false
let callVadSilenceTimer = null
let callVadCooldown = false      // VAD 冷却锁：AI说话期间不监听
let callVadCooldownTimer = null  // 冷却定时器

function startCallRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    showFailToast('设备不支持麦克风')
    callActive.value = false
    return
  }

  navigator.mediaDevices.getUserMedia({
    audio: {
      sampleRate: 16000,       // 强制 16kHz，匹配 Whisper
      sampleSize: 16,           // 16-bit
      channelCount: 1,          // 单声道
      echoCancellation: true,   // 回声消除
      noiseSuppression: true,   // 降噪
      autoGainControl: true     // 自动增益
    }
  })
    .then(stream => {
      callStream = stream
      // 移除默认静音轨道
      stream.getAudioTracks().forEach(track => {
        console.log('[Call] 音频轨道:', track.label, '采样率:', track.getSettings().sampleRate)
      })
      try {
        callAudioCtx = new (window.AudioContext || window.webkitAudioContext)()
        callSource = callAudioCtx.createMediaStreamSource(stream)
        callAnalyser = callAudioCtx.createAnalyser()
        callAnalyser.fftSize = 512
        callSource.connect(callAnalyser)

        const data = new Uint8Array(callAnalyser.fftSize)
        const startThreshold = 0.015   // 降低触发阈值，避免漏掉轻声
        const stopThreshold = 0.01     // 降低停止阈值

        callIntervalId = setInterval(() => {
          callAnalyser.getByteTimeDomainData(data)
          let sum = 0
          for (let i = 0; i < data.length; i++) {
            const n = (data[i] - 128) / 128
            sum += n * n
          }
          const rms = Math.sqrt(sum / data.length)

          // 冷却期间不触发 VAD（AI说话时/刚发送完音频时）
          if (callVadCooldown || chatStore.isSpeaking) return

          if (!callVadSpeaking && rms > startThreshold) {
            callVadSpeaking = true
            const ws = getWsClient()
            if (ws && ws.isConnected.value) ws.sendInterrupt()
            startCallMediaRecorder(stream)
          }

          if (callVadSpeaking && rms <= stopThreshold) {
            if (!callVadSilenceTimer) {
              callVadSilenceTimer = setTimeout(() => {
                callVadSpeaking = false
                stopCallMediaRecorder()
                clearTimeout(callVadSilenceTimer)
                callVadSilenceTimer = null
              }, 800)   // 800ms 静音才停止，避免句中停顿被截断
            }
          } else if (rms > stopThreshold) {
            if (callVadSilenceTimer) {
              clearTimeout(callVadSilenceTimer)
              callVadSilenceTimer = null
            }
          }
        }, 120)
      } catch (e) {
        console.warn('[Call] VAD 初始化失败:', e)
      }
    })
    .catch(() => {
      showFailToast('麦克风访问被拒绝')
      callActive.value = false
    })
}

function stopCallRecording() {
  if (callIntervalId) {
    clearInterval(callIntervalId)
    callIntervalId = null
  }
  if (callVadSilenceTimer) {
    clearTimeout(callVadSilenceTimer)
    callVadSilenceTimer = null
  }
  if (callVadCooldownTimer) {
    clearTimeout(callVadCooldownTimer)
    callVadCooldownTimer = null
  }
  callVadCooldown = false
  if (callMediaRecorder && callMediaRecorder.state === 'recording') {
    try { callMediaRecorder.stop() } catch (_) {}
  }
  if (callAudioCtx) {
    try { callAudioCtx.close() } catch (_) {}
    callAudioCtx = null
  }
  if (callStream) {
    callStream.getTracks().forEach(t => t.stop())
    callStream = null
  }
  callSource = null
  callAnalyser = null
  callMediaRecorder = null
  callAudioChunks = []
  callVadSpeaking = false
}

function startCallMediaRecorder(stream) {
  if (!stream) return
  try {
    callAudioChunks = []
    const mimeTypes = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
    let selectedMimeType = ''
    for (const mime of mimeTypes) {
      if (MediaRecorder.isTypeSupported(mime)) {
        selectedMimeType = mime
        break
      }
    }
    const recorderOpts = selectedMimeType ? { mimeType: selectedMimeType, audioBitsPerSecond: 32000 } : { audioBitsPerSecond: 32000 }
    callMediaRecorder = new MediaRecorder(stream, recorderOpts)
    callMediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) callAudioChunks.push(e.data)
    }
    callMediaRecorder.onstop = () => {
      const mimeType = callMediaRecorder.mimeType || 'audio/webm'
      const blob = new Blob(callAudioChunks, { type: mimeType })
      const reader = new FileReader()
      reader.onload = () => {
        const base64 = reader.result.split(',')[1]
        const ws = getWsClient()
        if (ws && ws.isConnected.value) ws.sendAudio(base64)
        // 发送后进入冷却期，防止回声触发 VAD
        callVadCooldown = true
        if (callVadCooldownTimer) clearTimeout(callVadCooldownTimer)
        callVadCooldownTimer = setTimeout(() => {
          callVadCooldown = false
          callVadCooldownTimer = null
        }, 5000)  // 最多冷却 5 秒，done 到达时会被提前清除
      }
      reader.readAsDataURL(blob)
    }
    callMediaRecorder.start()
  } catch (e) {
    console.warn('[Call] Start MediaRecorder failed:', e)
  }
}

function stopCallMediaRecorder() {
  if (callMediaRecorder && callMediaRecorder.state === 'recording') {
    try { callMediaRecorder.stop() } catch (_) {}
  }
}

// ===== 发送文本 =====
function sendText() {
  // 如果有已选视频，走视频问答流程
  if (selectedVideo.value) {
    sendWithVideo()
    return
  }

  // 如果有已选图片，走图片问答流程
  if (selectedImages.value.length > 0) {
    sendWithImages()
    return
  }

  const text = inputText.value.trim()
  if (!text) return

  // 防止重复发送
  if (chatStore.isProcessing || chatStore.isSpeaking) return

  if (viewMode.value === 'full') openTextChat()

  inputText.value = ''

  // 立即展示用户消息 + AI思考气泡
  chatStore.addUserMessage(text, 'text')
  chatStore.setProcessing(true)
  chatStore.setEmotion('平静')
  isDiscarded = false
  audioQueue.value = []
  isPlayingAudio = false
  chatStore.addAiMessage('')  // 空消息 → 三点动画
  scrollToBottom()

  const ws = getWsClient()
  if (ws && ws.isConnected.value) {
    ws.sendText(text)
  } else {
    fallbackReply()
  }
}

// 模式A弹窗发送
function sendPopupText() {
  // 如果有已选视频，走视频问答流程
  if (selectedVideo.value) {
    sendWithVideo()
    return
  }

  // 如果有已选图片，走图片问答流程
  if (selectedImages.value.length > 0) {
    sendWithImages()
    return
  }

  const text = popupText.value.trim()
  if (!text) return
  if (chatStore.isProcessing || chatStore.isSpeaking) return

  openTextChat()
  showTextPopup.value = false

  chatStore.addUserMessage(text, 'text')
  chatStore.setProcessing(true)
  chatStore.setEmotion('平静')
  isDiscarded = false
  audioQueue.value = []
  isPlayingAudio = false
  chatStore.addAiMessage('')
  scrollToBottom()

  const ws = getWsClient()
  if (ws && ws.isConnected.value) ws.sendText(text)
  else fallbackReply()
}

function fallbackReply() {
  setTimeout(() => {
    chatStore.addAiMessage('您好！我是灵山胜境AI导游。请问有什么可以帮您的？')
    scrollToBottom()
  }, 1000)
}

function openRouteMap(routeInfo) {
  if (!routeInfo) return
  const payload = routeInfo.route_data || routeInfo
  if (!payload) return
  // 将完整路线信息通过 query + state 传递
  const query = {
    origin: payload.origin || '景区入口',
    destination: payload.destination || '灵山大佛',
    waypoints: (payload.waypoints || []).join(','),
    mode: payload.mode || 'walk',
    summary: payload.summary || ''
  }
  router.push({
    path: '/route-map',
    query,
    state: {
      summary: payload.summary || '',
      tips: payload.tips || '',
      routeName: payload.route_name || '',
      duration: payload.duration || ''
    }
  })
}

// ===== 语音输入 =====
let mediaRecorder = null
let audioChunks = []
let holdStartTime = 0
let silenceDetector = null     // { audioContext, analyser, dataArray, maxVolume, intervalId }

function enterVoiceMode() {
  voiceMode.value = true
  inputText.value = ''  // 清空文字，避免发送按钮遮挡键盘图标
}

function exitVoiceMode() {
  voiceMode.value = false
  if (isRecording.value) stopHoldSpeak()
}

function startHoldSpeak() {
  if (!navigator.mediaDevices?.getUserMedia) {
    showFailToast('当前设备不支持语音输入')
    return
  }

  isRecording.value = true
  audioChunks = []
  holdStartTime = Date.now()

  navigator.mediaDevices.getUserMedia({
    audio: {
      sampleRate: 16000,
      sampleSize: 16,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }
  })
    .then(stream => {
      // ---- 静音检测：AnalyserNode + RMS 标准音量算法 ----
      const detector = { audioCtx: null, intervalId: null, maxRms: 0 }
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
        const source = audioCtx.createMediaStreamSource(stream)
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 512
        source.connect(analyser)
        const timeData = new Uint8Array(analyser.fftSize)

        const intervalId = setInterval(() => {
          analyser.getByteTimeDomainData(timeData)
          // 标准 RMS 计算：归一化到 -1..1，平方平均后开方
          let sumSquares = 0
          for (let i = 0; i < timeData.length; i++) {
            const normalized = (timeData[i] - 128) / 128
            sumSquares += normalized * normalized
          }
          const rms = Math.sqrt(sumSquares / timeData.length)
          if (rms > detector.maxRms) detector.maxRms = rms
        }, 100)

        detector.audioCtx = audioCtx
        detector.intervalId = intervalId
        silenceDetector = detector
      } catch (e) {
        console.warn('[Audio] 静音检测初始化失败:', e)
        silenceDetector = null
      }

      // ---- 录音（优先使用 opus 编码，质量更好） ----
      const mimeTypes = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
      let selectedMimeType = ''
      for (const mime of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mime)) {
          selectedMimeType = mime
          break
        }
      }
      const recorderOpts = selectedMimeType ? { mimeType: selectedMimeType, audioBitsPerSecond: 32000 } : { audioBitsPerSecond: 32000 }
      mediaRecorder = new MediaRecorder(stream, recorderOpts)
      console.log('[Audio] MediaRecorder 使用编码:', selectedMimeType || '默认', '比特率:', recorderOpts.audioBitsPerSecond)
      mediaRecorder.ondataavailable = (event) => audioChunks.push(event.data)

      mediaRecorder.onstop = () => {
        // 清理静音检测
        const det = silenceDetector
        if (det) {
          clearInterval(det.intervalId)
          det.audioCtx.close()
        }

        const duration = (Date.now() - holdStartTime) / 1000
        const mimeType = mediaRecorder.mimeType || 'audio/webm'
        const audioBlob = new Blob(audioChunks, { type: mimeType })

        // 标准静音判断：RMS < 0.015 视为静音（典型语音 RMS 0.02~0.2）
        const hasVolume = det
          ? det.maxRms > 0.015
          : audioBlob.size > 8000

        if (duration < 0.4 || !hasVolume) {
          showFailToast('未检测到声音，请重试')
          isRecording.value = false
          silenceDetector = null
          stream.getTracks().forEach(track => track.stop())
          return
        }

        silenceDetector = null

        const reader = new FileReader()
        reader.onload = () => {
          const base64 = reader.result.split(',')[1]
          const ws = getWsClient()
          if (ws && ws.isConnected.value) ws.sendAudio(base64)
        }
        reader.readAsDataURL(audioBlob)
        stream.getTracks().forEach(track => track.stop())
        isRecording.value = false
        voiceMode.value = false
      }

      mediaRecorder.start()
    })
    .catch(() => {
      showFailToast('麦克风访问被拒绝')
      isRecording.value = false
    })
}

function stopHoldSpeak() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop()
  }
}

// ===== 打断/关闭 =====
function stopReply() {
  const ws = getWsClient()
  if (ws && ws.isConnected.value) ws.sendInterrupt()

  isDiscarded = true
  if (doneTimeoutId) {
    clearTimeout(doneTimeoutId)
    doneTimeoutId = null
  }

  audioQueue.value = []
  isPlayingAudio = false
  chatStore.setProcessing(false)
  chatStore.isSpeaking = false
  // 解除 VAD 冷却锁
  if (callVadCooldownTimer) {
    clearTimeout(callVadCooldownTimer)
    callVadCooldownTimer = null
  }
  callVadCooldown = false

  live2dRef.value?.muteVideo?.()
  setTimeout(() => {
    if (!audioMuted.value) {
      live2dRef.value?.unmuteVideo?.()
    }
  }, 2000)

  if (currentAudioSource) {
    try { currentAudioSource.stop() } catch (_) {}
    currentAudioSource = null
  }

  closeToast()
}

// ===== 点击数字人（模式A打断 / 模式B切回） =====
function onAvatarClick() {
  if (viewMode.value === 'chat') {
    closeTextChat()
  } else if (chatStore.isProcessing || chatStore.isSpeaking) {
    stopReply()
  }
}

// ===== 图片上传与预览 =====
const fileInputRef = ref(null)
const MAX_IMAGE_COUNT = 9
const MAX_IMAGE_SIZE = 10 * 1024 * 1024 // 10MB

function openImagePicker() {
  if (selectedImages.value.length >= MAX_IMAGE_COUNT) {
    showFailToast(`最多选择 ${MAX_IMAGE_COUNT} 张图片`)
    return
  }
  showImageUpload.value = true
}

function triggerFileSelect() {
  showImageUpload.value = false
  if (fileInputRef.value) {
    fileInputRef.value.click()
  }
}

function handleFileSelect(event) {
  const files = event.target.files
  if (!files || files.length === 0) {
    event.target.value = ''
    return
  }

  const filesToUpload = Array.from(files)
    .filter(f => f.size <= MAX_IMAGE_SIZE)
    .slice(0, MAX_IMAGE_COUNT - selectedImages.value.length)

  if (filesToUpload.length !== files.length) {
    showNotify({ type: 'warning', message: '部分文件超过大小限制或已达数量上限', duration: 2000 })
  }

  event.target.value = '' // 重置 input，允许重复选择同一文件
  uploadFiles(filesToUpload)
}

async function uploadFiles(files) {
  if (files.length === 0) return

  uploading.value = true
  try {
    const formData = new FormData()
    for (const file of files) {
      formData.append('file', file)
    }
    const res = await uploadImage(formData)
    if (res.code === 200) {
      res.data.images.forEach(img => {
        selectedImages.value.push({ url: img.url, name: img.original_name || img.filename })
      })
      showSuccessToast(`已选择 ${res.data.count} 张图片`)
    } else {
      showFailToast(res.message || '上传失败')
    }
  } catch (e) {
    console.error('图片上传失败:', e)
    showFailToast('上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

function removeImage(index) {
  selectedImages.value.splice(index, 1)
}

function clearSelectedImages() {
  selectedImages.value = []
}

function previewImage(url) {
  // 使用 Vant 的 ImagePreview 组件
  import('vant').then(({ ImagePreview }) => {
    ImagePreview([{ url }])
  })
}

function sendWithImages() {
  const text = inputText.value.trim() || '请分析这些图片'
  const imageUrls = selectedImages.value.map(img => img.url)

  if (!imageUrls.length && !text) return

  // 防止重复发送
  if (chatStore.isProcessing || chatStore.isSpeaking) return

  if (viewMode.value === 'full') openTextChat()

  // 展示用户消息（带图片）
  chatStore.addUserMessage(text, 'text', imageUrls)
  inputText.value = ''
  popupText.value = ''

  // 展示 AI 思考气泡
  chatStore.setProcessing(true)
  chatStore.setEmotion('平静')
  isDiscarded = false
  audioQueue.value = []
  isPlayingAudio = false
  chatStore.addAiMessage('')
  scrollToBottom()

  const ws = getWsClient()
  if (ws && ws.isConnected.value) {
    ws.sendImage(imageUrls, text)
  } else {
    // 降级：模拟回复
    setTimeout(() => {
      chatStore.addAiMessage('已收到您的提问，请保持网络连接。')
      scrollToBottom()
    }, 1000)
  }

  // 清空已选图片
  selectedImages.value = []
}

// ===== 视频上传与发送 =====
function triggerVideoSelect() {
  showImageUpload.value = false
  if (videoInputRef.value) {
    videoInputRef.value.click()
  }
}

async function handleVideoSelect(event) {
  const file = event.target.files?.[0]
  event.target.value = '' // 重置 input，允许重复选择同一文件
  if (!file) return

  if (file.size > MAX_VIDEO_SIZE) {
    showNotify({ type: 'warning', message: '视频超过 100MB 限制', duration: 2000 })
    return
  }

  uploading.value = true
  const toast = showLoadingToast({ message: '视频上传中...', duration: 0, forbidClick: true })
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await uploadVideo(formData)
    closeToast()
    if (res.code === 200) {
      // 选中视频时清空已选图片（互斥发送）
      selectedImages.value = []
      selectedVideo.value = { url: res.data.url, name: res.data.original_name || res.data.filename }
      showSuccessToast('视频已就绪，输入问题后发送')
    } else {
      showFailToast(res.message || '视频上传失败')
    }
  } catch (e) {
    closeToast()
    console.error('视频上传失败:', e)
    showFailToast('视频上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

function removeVideo() {
  selectedVideo.value = null
}

function sendWithVideo() {
  if (!selectedVideo.value) return
  const text = inputText.value.trim() || popupText.value.trim() || '请分析这段视频的内容'
  const videoUrl = selectedVideo.value.url

  // 防止重复发送
  if (chatStore.isProcessing || chatStore.isSpeaking) return

  if (viewMode.value === 'full') openTextChat()

  // 展示用户消息（带视频预览）
  chatStore.addUserMessage(text, 'video', null, videoUrl)
  inputText.value = ''
  popupText.value = ''

  // 展示 AI 思考气泡
  chatStore.setProcessing(true)
  chatStore.setEmotion('平静')
  isDiscarded = false
  audioQueue.value = []
  isPlayingAudio = false
  chatStore.addAiMessage('')
  scrollToBottom()

  const ws = getWsClient()
  if (ws && ws.isConnected.value) {
    ws.sendVideo(videoUrl, text)
  } else {
    // 降级：模拟回复
    setTimeout(() => {
      chatStore.addAiMessage('已收到您的视频，请保持网络连接。')
      scrollToBottom()
    }, 1000)
  }

  // 清空已选视频
  selectedVideo.value = null
}

// ===== 图片上传（旧版兼容） =====
function onImageRead(file) {
  showImageUpload.value = false
  if (!file?.file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    const base64 = e.target.result.split(',')[1]
    const text = inputText.value.trim() || popupText.value.trim() || '请分析这张图片'

    if (viewMode.value === 'full') openTextChat()

    chatStore.addUserMessage(text, 'image')
    inputText.value = ''
    popupText.value = ''

    const ws = getWsClient()
    if (ws && ws.isConnected.value) {
      ws.sendImage([base64], file.file.name, text)
    } else {
      setTimeout(() => {
        chatStore.addAiMessage('已收到您的图片，正在分析...')
        scrollToBottom()
      }, 1500)
    }
  }
  reader.readAsDataURL(file.file)
}

// ===== 路线推荐 =====
function showRoutes() {
  Dialog.confirm({
    title: '选择游览路线',
    message: '请选择您感兴趣的路线类型：',
    confirmButtonText: '自然风光',
    cancelButtonText: '文化朝圣',
    showCancelButton: true
  }).then(() => {
    if (viewMode.value === 'full') openTextChat()
    chatStore.addAiMessage('🌄 自然风光路线（5小时全景游）：南门→佛足坛→九龙灌浴→菩提大道→灵山大佛→曼飞龙塔→灵山精舍→梵宫广场。漫步菩提大道欣赏太湖风光，登顶大佛俯瞰全景，感受人与自然和谐统一。')
    scrollToBottom()
  }).catch(() => {
    if (viewMode.value === 'full') openTextChat()
    chatStore.addAiMessage('🙏 文化朝圣路线（3小时精华游）：南门→佛足坛→九龙灌浴→祥符禅寺→灵山大佛→梵宫→五印坛城。深度体验佛教文化，欣赏梵宫艺术殿堂。')
    scrollToBottom()
  })

  setTimeout(() => {
    Dialog.confirm({
      title: '还有亲子路线',
      message: '是否查看适合家庭出游的亲子路线？',
      confirmButtonText: '查看',
      cancelButtonText: '不用了'
    }).then(() => {
      chatStore.addAiMessage('👨‍👩‍👧‍👦 亲子家庭路线（4小时轻松游）：南门→九龙灌浴→佛手广场→百子戏弥勒→梵宫→五印坛城。适合带孩子的家庭，互动性强！')
      scrollToBottom()
    }).catch(() => {})
  }, 500)
}

// ===== 热门问题 =====
function showHotQuestions() {
  const questions = [
    '灵山胜境门票多少钱？',
    '灵山大佛有多高？',
    '梵宫有什么看点？',
    '景区怎么去？',
    '有什么特色素斋推荐？'
  ]

  Dialog.alert({
    title: '热门问题',
    message: questions.map((q, i) => `${i + 1}. ${q}`).join('\n'),
    confirmButtonText: '知道了'
  })
}

// ===== 切换数字人 =====
function goDigitalHuman() {
  router.push('/digital-human')
}

// ===== 清除对话内容（仅界面，不影响数据库） =====
function clearChat() {
  chatStore.clearMessages()
  localStorage.removeItem('chat_messages')
  showSuccessToast('对话已清除')
}

// ===== 获取数字人列表 =====
async function fetchDigitalHumans() {
  try {
    const { getDigitalHumans } = await import('@/utils/api')
    const res = await getDigitalHumans()
    if (res.code === 200) dhStore.setHumans(res.data)
  } catch (e) {
    console.warn('获取数字人列表失败:', e)
  }
}

// ===== 从服务端加载用户保存的数字人偏好并自动切换 =====
async function loadSavedDigitalHuman() {
  try {
    const userRes = await getUserInfo()
    if (userRes.code === 200 && userRes.data) {
      const savedDhId = userRes.data.digital_human_id
      if (savedDhId && savedDhId !== dhStore.currentId) {
        const targetDh = dhStore.humans.find(h => h.id === savedDhId)
        if (targetDh) {
          console.log(`[Home] 检测到服务端保存的数字人 ${savedDhId}，自动切换`)
          dhStore.switchDigitalHuman(targetDh)
        }
      }
    }
  } catch (e) {
    console.warn('[Home] 获取用户数字人偏好失败:', e)
  }
}

// ===== 滚动到底部 =====
function scrollToBottom() {
  nextTick(() => {
    if (bubbleRef.value) {
      bubbleRef.value.scrollTop = bubbleRef.value.scrollHeight
    }
  })
  setTimeout(() => {
    if (bubbleRef.value) {
      bubbleRef.value.scrollTop = bubbleRef.value.scrollHeight
    }
  }, 50)
}
</script>

<style scoped>
.home-page {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #e8f5e9 0%, #f5f7f0 100%);
  overflow: hidden;
}

.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  padding-top: 48px;
  background: linear-gradient(135deg, #5b8c5a, #7cb342);
  color: #fff;
}

.dh-name {
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dh-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.dh-header-avatar {
  width: 32px;
  height: 44px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255,255,255,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.dh-header-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 20%;
}

.dh-header-avatar-fallback {
  font-size: 18px;
}

.quick-bar {
  display: flex;
  gap: 8px;
  padding: 6px 16px;
  background: rgba(255,255,255,0.7);
  border-bottom: 1px solid rgba(91,140,90,0.08);
}

.quick-btn {
  height: 26px !important;
  font-size: 11px !important;
  padding: 0 10px !important;
}

/* ===== 内容区 ===== */
.route-action {
  margin-top: 8px;
}

.content-area {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: #f6f6f6;
  /* background: linear-gradient(180deg, #e8f5e9 0%, #dce8dc 40%, #cfdbcf 100%); */
}

/* 模式A：全屏数字人 */
.full-mode {
  position: relative;
}

.live2d-full {
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  background: transparent;
}

/* 模式B：上下分布 */
.chat-mode {
  display: flex;
  flex-direction: column;
}

.live2d-compact {
  flex: 0 0 40%;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  background: transparent;
  border-bottom: 1px solid rgba(91,140,90,0.1);
  overflow: hidden;
}
/* 视频撑满全身，裁切只露上半身 */
.live2d-compact :deep(.digital-human-video) {
  position: absolute;
  top: -20px;
  object-fit: contain;
  object-position: top;
  width: 100%;
  height: 230%;
  min-height: 250%;
}

/* 通话状态指示 */
.call-indicator {
  position: absolute;
  top: 10px;
  left: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(76, 175, 80, 0.15);
  color: #388e3c;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  z-index: 5;
}
.call-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4caf50;
  animation: pulse-dot 1.2s ease-in-out infinite;
}

/* 情绪+状态 */
.emotion-badge {
  position: absolute;
  top: 10px;
  right: 12px;
  background: rgba(0,0,0,0.45);
  color: #fff;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  z-index: 5;
}

.status-tip {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0,0,0,0.45);
  color: #fff;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 11px;
  white-space: nowrap;
  z-index: 5;
}

/* ===== 通话操作栏（模式A） ===== */
.action-bar {
  display: flex;
  justify-content: space-evenly;
  align-items: center;
  padding: 14px 24px;
  padding-bottom: calc(14px + env(safe-area-inset-bottom));
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(91,140,90,0.08);
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
  -webkit-user-select: none;
}
.action-btn:active {
  transform: scale(0.93);
}

/* 左右小按钮 */
.action-btn.mute,
.action-btn.text {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #f0f4eb;
  color: #5b8c5a;
  justify-content: center;
  font-size: 11px;
}
.action-btn.mute.active {
  background: #fff0e6;
  color: #e67e22;
}
.action-btn.mute.active :deep(.van-icon) {
  color: #e67e22;
}

/* 中间通话大按钮 */
.action-btn.call {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, #5b8c5a, #7cb342);
  color: #fff;
  justify-content: center;
  font-size: 12px;
  box-shadow: 0 4px 16px rgba(91,140,90,0.35);
}
.action-btn.call :deep(.van-icon) {
  line-height: 1;
}
.action-btn.call.active {
  background: linear-gradient(135deg, #e74c3c, #c0392b);
  box-shadow: 0 4px 16px rgba(231,76,60,0.35);
  animation: call-pulse 1.8s ease-in-out infinite;
}
@keyframes call-pulse {
  0%, 100% { box-shadow: 0 4px 16px rgba(231,76,60,0.35); }
  50% { box-shadow: 0 4px 28px rgba(231,76,60,0.55); }
}

/* ===== 对话气泡（模式B） ===== */
.chat-bubbles {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px;
  -webkit-overflow-scrolling: touch;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9aab9a;
}

.empty-icon {
  font-size: 40px;
  margin-bottom: 10px;
  opacity: 0.4;
}

.empty-text {
  font-size: 13px;
  line-height: 1.8;
  text-align: center;
}

.bubble {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  width: 100%;
  animation: fadeInUp 0.3s ease;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.user-bubble {
  flex-direction: row-reverse;
  justify-content: flex-start;
}

.ai-bubble {
  flex-direction: row;
  justify-content: flex-start;
}

.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.bubble-content {
  max-width: 80%;
}

.user-bubble .bubble-content {
  background: linear-gradient(135deg, #5b8c5a, #7cb342);
  color: #fff;
  border-radius: 16px 4px 16px 16px;
  padding: 10px 14px;
}

.ai-bubble .bubble-content {
  background: rgba(255,255,255,0.95);
  color: #2e3d2e;
  border-radius: 4px 16px 16px 16px;
  padding: 10px 14px;
  box-shadow: var(--shadow-sm);
}

.bubble-text {
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-text.thinking {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 0;
  min-height: 24px;
}

.stopped-text {
  color: #9aab9a;
  font-size: 13px;
}

/* 循环三点动画 */
.dot-pulse {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #9aab9a;
  animation: dot-typing 1.4s infinite both;
  position: relative;
  margin-left: 12px;
}
.dot-pulse::before,
.dot-pulse::after {
  content: '';
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #9aab9a;
  position: absolute;
  top: 0;
}
.dot-pulse::before {
  left: -16px;
  animation: dot-typing 1.4s 0.2s infinite both;
}
.dot-pulse::after {
  left: 16px;
  animation: dot-typing 1.4s 0.4s infinite both;
}

@keyframes dot-typing {
  0%, 60%, 100% { opacity: 0.2; transform: scale(0.8); }
  30% { opacity: 1; transform: scale(1); }
}

.bubble-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: #9aab9a;
}

.user-bubble .bubble-meta {
  justify-content: flex-end;
}

.user-bubble .bubble-text,
.user-bubble .bubble-time {
  text-align: right;
}

.ai-bubble .bubble-meta {
  justify-content: flex-start;
}

.bubble-emotion {
  font-size: 11px;
}

/* ===== 输入区域容器（图片条 + 输入框） ===== */
.input-area {
  padding: 8px 16px;
  padding-bottom: calc(8px + env(safe-area-inset-bottom));
  background: rgba(255,255,255,0.95);
  border-top: 1px solid rgba(91,140,90,0.1);
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

/* ===== 已选图片缩略图区域（与输入框完全分离） ===== */
.selected-images-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.selected-images-row {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding: 4px 0;
}
.selected-images-row::-webkit-scrollbar {
  display: none;
}

.selected-images-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px;
}

.thumb-count {
  font-size: 12px;
  color: #5b8c5a;
  font-weight: 500;
}

.thumb-clear {
  font-size: 12px;
  color: #999;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
}
.thumb-clear:active {
  color: #e74c3c;
  background: rgba(231,76,60,0.1);
}

.selected-thumb {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  border: 2px solid #5b8c5a;
  background: #e8f5e9;
}
.selected-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #e74c3c;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2;
}
.thumb-remove:active {
  transform: scale(0.85);
}

/* ===== 输入框 ===== */
.input-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #f0f4eb;
  border-radius: 24px;
  padding: 6px 12px;
  flex: 1;
  min-width: 0;
}

.text-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 15px;
  color: #2e3d2e;
  padding: 6px 0;
  min-height: 24px;
}

.text-input::placeholder {
  color: #9aab9a;
}

.hold-to-speak {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #5b8c5a, #7cb342);
  color: #fff;
  border-radius: 20px;
  font-size: 15px;
  font-weight: 500;
  padding: 8px 0;
  user-select: none;
  -webkit-user-select: none;
  cursor: pointer;
  transition: transform 0.1s;
}
.hold-to-speak.recording {
  background: linear-gradient(135deg, #e74c3c, #c0392b);
  transform: scale(0.97);
}

.send-btn {
  background: linear-gradient(135deg, #5b8c5a, #7cb342);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
}
.send-btn:active {
  transform: scale(0.9);
}

/* 清除对话图标（输入框外右侧） */
.clear-chat-icon {
  margin-left: 14px;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform .2s;
}
.clear-chat-icon:active {
  transform: scale(0.88);
}

/* ===== 文字弹窗（模式A） ===== */
.text-popup {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 600;
  color: #2e3d2e;
  border-bottom: 1px solid #eee;
}

.popup-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 20px;
  gap: 16px;
}

.popup-textarea {
  flex: 1;
  border: 1px solid #e0e8dc;
  border-radius: 12px;
  padding: 12px;
  font-size: 15px;
  color: #2e3d2e;
  outline: none;
  resize: none;
  font-family: inherit;
  background: #f8faf5;
}

.popup-textarea::placeholder {
  color: #9aab9a;
}

.popup-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.green-btn {
  background: linear-gradient(135deg, #5b8c5a, #7cb342) !important;
  color: #fff !important;
  border: none !important;
}

/* ===== 图片上传弹窗 ===== */
.upload-sheet {
  padding: 20px;
  text-align: center;
}

.upload-choices {
  display: flex;
  justify-content: center;
  gap: 40px;
  padding: 16px 0;
}

.upload-choice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 12px 24px;
  border-radius: 12px;
  transition: background .2s;
}
.upload-choice:active {
  background: rgba(91,140,90,0.08);
}

.upload-tip {
  color: #9aab9a;
  font-size: 12px;
  margin-top: 12px;
}

/* ===== 已选图片缩略图条 ===== */
.selected-images-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0 4px;
  flex-wrap: nowrap;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.selected-images-bar::-webkit-scrollbar {
  display: none;
}

.selected-thumb {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  border: 2px solid #5b8c5a;
  background: #e8f5e9;
}
.selected-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-remove {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e74c3c;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2;
}
.thumb-remove:active {
  transform: scale(0.9);
}

.thumb-count {
  font-size: 11px;
  color: #5b8c5a;
  margin-left: 4px;
  flex-shrink: 0;
  white-space: nowrap;
}

/* ===== 已选视频（单视频缩略预览） ===== */
.selected-video-area {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}

.selected-video-thumb {
  position: relative;
  width: 96px;
  height: 64px;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid #5b8c5a;
  background: #000;
  flex-shrink: 0;
}
.selected-video-thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.video-badge {
  position: absolute;
  left: 4px;
  bottom: 4px;
  font-size: 10px;
  color: #fff;
  background: rgba(0,0,0,0.55);
  padding: 1px 6px;
  border-radius: 8px;
  pointer-events: none;
}

/* ===== 气泡中视频 ===== */
.bubble-video-wrap {
  margin-bottom: 6px;
}

.bubble-video {
  width: 200px;
  max-width: 100%;
  border-radius: 10px;
  display: block;
  background: #000;
}
.user-bubble .bubble-video {
  border: 2px solid rgba(255,255,255,0.3);
}

/* ===== 气泡中图片 ===== */
.bubble-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
  max-width: 100%;
}

.bubble-image {
  width: 100px;
  height: 100px;
  object-fit: cover;
  border-radius: 8px;
  cursor: pointer;
  max-width: 100%;
  display: block;
}
.user-bubble .bubble-image {
  border: 2px solid rgba(255,255,255,0.3);
}
</style>
