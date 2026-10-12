<template>
  <!-- 3D 数字人渲染组件（LiveTalking WebRTC） -->
  <div class="digital-human-viewer" ref="viewerRef">
    <!-- 连接中 -->
    <div class="loading-placeholder" v-if="rtcState === 'connecting'">
      <div class="model-icon">🪷</div>
      <p class="loading-text">3D 导游连接中...</p>
      <van-loading type="spinner" size="20" color="#c8a45c" />
    </div>

    <!-- 连接失败 / 离线降级 -->
    <div class="fallback-placeholder" v-else-if="rtcState === 'error' || rtcState === 'disconnected'">
      <div class="model-icon offline">🪷</div>
      <p class="fallback-text">3D 导游离线</p>
      <p class="fallback-sub">语音模式可用</p>
      <div class="retry-btn" @click="reconnect">
        <van-icon name="replay" size="14" />
        <span>重新连接</span>
      </div>
    </div>

    <!-- 3D 视频画面（隐藏 video，用 canvas 抠像后展示） -->
    <video
      ref="videoRef"
      class="digital-human-video"
      :class="{ 'video-loaded': rtcState === 'connected' }"
      :style="chromeKey ? 'display:none' : ''"
      autoplay
      playsinline
    ></video>
    <canvas
      v-if="chromeKey"
      ref="canvasRef"
      class="digital-human-video"
      :class="{ 'video-loaded': rtcState === 'connected' }"
    />

    <!-- 说话状态指示 -->
    <div class="speaking-indicator" v-if="rtcState === 'connected' && isSpeaking">
      <span class="dot"></span> 讲解中
    </div>

    <!-- 情绪标签 -->
    <div class="emotion-tag" v-if="rtcState === 'connected' && emotion && emotion !== '平静'">
      {{ emotion === '热情' ? '🔥' : '😊' }} {{ emotion }}
    </div>
  </div>
</template>

<script setup>
/**
 * 3D 数字人渲染组件
 *
 * 通过 WebRTC 连接 LiveTalking 引擎，实时展示 3D Avatar 口播画面。
 * LiveTalking 不可用时自动降级为静态占位 + 离线提示，
 * 此时问答功能仍正常（语音通过本地 TTS 播放）。
 */
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { connectLiveTalking, RTCState } from '@/utils/rtc'
import { useDigitalHumanStore } from '@/store'

const props = defineProps({
  emotion: { type: String, default: '平静' },
  isSpeaking: { type: Boolean, default: false },
  dhId: { type: Number, default: 1 },
  chromeKey: { type: Boolean, default: false },     // 是否启用绿幕抠像
  keyColor: { type: String, default: '#5DBE4E' },    // 要抠掉的颜色
  threshold: { type: Number, default: 0.3 }           // 容差 (0-1)
})

const dhStore = useDigitalHumanStore()
const viewerRef = ref(null)
const videoRef = ref(null)
const canvasRef = ref(null)
const rtcState = ref(RTCState.DISCONNECTED)
const sessionId = ref('')
let rtcConnection = null
let chromeKeyAnimId = null

onMounted(() => {
  connect()
})

onUnmounted(() => {
  stopChromeKey()
  disconnect()
})

// 监听数字人切换 → 重新连接
watch(() => props.dhId, () => {
  disconnect()
  setTimeout(() => connect(), 300)
})

/**
 * 建立 WebRTC 连接
 */
function connect() {
  if (rtcConnection) disconnect()

  rtcState.value = RTCState.CONNECTING

  // 从 store 获取当前数字人对应的 LiveTalking avatar 文件夹名
  const avatarId = dhStore.getCurrentAvatarId()
  console.log('[Live2DViewer] 连接 avatar:', avatarId)

  rtcConnection = connectLiveTalking(avatarId, {
    onStateChange(state) {
      rtcState.value = state
    },
    onStream(stream) {
      if (videoRef.value) {
        videoRef.value.srcObject = stream
        // 绿幕抠像模式：启动 canvas 渲染循环
        if (props.chromeKey) {
          videoRef.value.addEventListener('loadedmetadata', startChromeKey)
        }
      }
    },
    onSessionId(id) {
      sessionId.value = id
    }
  })
}

/** 获取当前 LiveTalking sessionid（供父组件调用） */
function getSessionId() {
  return sessionId.value
}

// ==== 绿幕抠像 ====
function parseColor(hex) {
  const c = hex.replace('#', '')
  return {
    r: parseInt(c.substring(0, 2), 16),
    g: parseInt(c.substring(2, 4), 16),
    b: parseInt(c.substring(4, 6), 16)
  }
}

function startChromeKey() {
  if (!props.chromeKey || !videoRef.value || !canvasRef.value) return
  const video = videoRef.value
  const canvas = canvasRef.value
  canvas.width = video.videoWidth || 640
  canvas.height = video.videoHeight || 480
  processChromeKey()
}

function processChromeKey() {
  if (!props.chromeKey || rtcState.value !== RTCState.CONNECTED) {
    stopChromeKey()
    return
  }
  const video = videoRef.value
  const canvas = canvasRef.value
  if (!video || !canvas || video.readyState < 2) {
    chromeKeyAnimId = requestAnimationFrame(processChromeKey)
    return
  }

  const ctx = canvas.getContext('2d')
  // 保持宽高比
  if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
    canvas.width = video.videoWidth || canvas.width
    canvas.height = video.videoHeight || canvas.height
  }

  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  const frame = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const data = frame.data
  const key = parseColor(props.keyColor)
  const t = props.threshold * 255

  for (let i = 0; i < data.length; i += 4) {
    const dr = Math.abs(data[i] - key.r)
    const dg = Math.abs(data[i + 1] - key.g)
    const db = Math.abs(data[i + 2] - key.b)
    if (dr < t && dg < t && db < t) {
      data[i + 3] = 0  // 透明
    }
  }
  ctx.putImageData(frame, 0, 0)
  chromeKeyAnimId = requestAnimationFrame(processChromeKey)
}

function stopChromeKey() {
  if (chromeKeyAnimId) {
    cancelAnimationFrame(chromeKeyAnimId)
    chromeKeyAnimId = null
  }
}

/**
 * 断开 WebRTC 连接
 */
function disconnect() {
  stopChromeKey()
  if (rtcConnection) {
    rtcConnection.close()
    rtcConnection = null
  }
  rtcState.value = RTCState.DISCONNECTED
}

/**
 * 手动重连
 */
function reconnect() {
  disconnect()
  setTimeout(() => connect(), 500)
}

/** 临时静音视频（用于中断时立即生效） */
function muteVideo() {
  if (videoRef.value) {
    videoRef.value.muted = true
  }
}

/** 取消静音 */
function unmuteVideo() {
  if (videoRef.value) {
    videoRef.value.muted = false
  }
}

// 暴露给父组件
defineExpose({ getSessionId, muteVideo, unmuteVideo })
</script>

<style scoped>
.digital-human-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  background: transparent;
  overflow: hidden;
}

/* ---- 3D 视频画面 ---- */
.digital-human-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  transition: opacity 0.6s ease;
}

.digital-human-video.video-loaded {
  opacity: 1;
}

/* ---- 连接中 ---- */
.loading-placeholder {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  z-index: 2;
}

.model-icon {
  font-size: 80px;
  animation: float 2s ease-in-out infinite;
}

.model-icon.offline {
  animation: none;
  opacity: 0.5;
  filter: grayscale(0.5);
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.loading-text {
  font-size: 14px;
  color: #8a9a8a;
}

/* ---- 离线降级 ---- */
.fallback-placeholder {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  z-index: 2;
}

.fallback-text {
  font-size: 16px;
  color: #6b7c6b;
  font-weight: 500;
}

.fallback-sub {
  font-size: 12px;
  color: #9aab9a;
}

.retry-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 6px 16px;
  border: 1px solid #c8a45c;
  border-radius: 20px;
  color: #c8a45c;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: rgba(200, 164, 92, 0.1);
}

/* ---- 说话状态指示 ---- */
.speaking-indicator {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 12px;
  z-index: 3;
}

.speaking-indicator .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4caf50;
  animation: pulse-dot 1s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

/* ---- 情绪标签 ---- */
.emotion-tag {
  position: absolute;
  top: 10px;
  right: 12px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  padding: 3px 10px;
  border-radius: 14px;
  font-size: 12px;
  z-index: 3;
}
</style>
