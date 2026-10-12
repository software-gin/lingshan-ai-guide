<template>
  <div class="dh-select-page">
    <van-nav-bar title="切换数字人导游" left-arrow @click-left="$router.back()" />

    <div class="dh-list">
      <div
        v-for="dh in dhStore.humans"
        :key="dh.id"
        :class="['dh-item', { active: dh.id === dhStore.currentId }]"
        @click="switchDh(dh)"
      >
        <div class="dh-model">
          <div class="dh-preview">
            <img
              v-if="!avatarError[dh.model_path]"
              :src="getAvatarUrl(dh.model_path)"
              @error="onAvatarError(dh.model_path)"
              alt="数字人头像"
              class="dh-avatar-img"
            />
            <template v-if="avatarError[dh.model_path]">
              <span class="dh-avatar-fallback">
                {{ dh.id === 1 ? '🪷' : dh.id === 2 ? '🌸' : '📿' }}
              </span>
              <span class="dh-avatar-error-tip">加载失败</span>
            </template>
          </div>
        </div>
        <div class="dh-info">
          <div class="dh-name">{{ dh.name }}</div>
          <div class="dh-personality" v-if="dh.personality">
            {{ dh.personality }}
          </div>
          <div class="dh-params">
            <span>语速: {{ dh.default_speed }}</span>
            <span>语调: {{ dh.default_pitch }}</span>
          </div>
          <div class="dh-voice">音色: {{ voiceNameMap[dh.default_voice] || dh.default_voice }}</div>
        </div>
        <div class="dh-check">
          <van-icon v-if="dh.id === dhStore.currentId" name="success" color="#5b8c5a" size="20" />
        </div>
      </div>
    </div>

    <!-- <div class="dh-tip">
      <p>💡 不同的数字人导游拥有独特的语速、语调和音色</p>
      <p>灵韵 —— 温和亲切，适合日常讲解</p>
      <p>慧心 —— 轻柔舒缓，适合禅意体验</p>
      <p>明远 —— 沉稳大气，适合文化讲解</p>
    </div> -->
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast } from 'vant'
import { useDigitalHumanStore } from '@/store'
import { getDigitalHumans, saveUserDigitalHuman } from '@/utils/api'

const router = useRouter()
const dhStore = useDigitalHumanStore()

const voiceNameMap = {
  'zh-CN-XiaoxiaoNeural': '晓晓（女声·推荐）',
  'zh-CN-YunxiNeural': '云希（男声）',
  'zh-CN-XiaoyiNeural': '晓伊（女声·活泼）',
  'zh-CN-XiaohanNeural': '晓涵（女声·温柔）'
}

// 头像加载状态（keyed by model_path）
const avatarLoading = ref({})
const avatarError = ref({})

// 生成头像URL
function getAvatarUrl(modelPath) {
  if (!modelPath) return ''
  // 缓存破坏：用 dh.id 作为版本戳
  return `/api/user/avatars/${encodeURIComponent(modelPath)}/preview?t=${Date.now()}`
}

// 处理头像加载失败，回退到emoji
function onAvatarError(modelPath) {
  avatarLoading.value[modelPath] = false
  avatarError.value[modelPath] = true
}

// 处理头像加载成功，清除加载状态
function onAvatarLoad(modelPath) {
  avatarLoading.value[modelPath] = false
}

onMounted(async () => {
  try {
    const res = await getDigitalHumans()
    if (res.code === 200 && res.data.length > 0) {
      dhStore.setHumans(res.data)
      // 标记所有头像为加载中
      res.data.forEach(dh => {
        avatarLoading.value[dh.model_path] = true
        avatarError.value[dh.model_path] = false
      })
    } else {
      // 降级：使用默认数据
      dhStore.setHumans([
        { id: 1, name: '灵韵（默认导游）', model_path: '1', personality: '温和亲切', default_speed: 1.0, default_pitch: 1.0, default_voice: 'zh-CN-XiaoxiaoNeural' },
        { id: 2, name: '慧心（禅意导游）', model_path: '2', personality: '轻柔舒缓', default_speed: 0.9, default_pitch: 1.1, default_voice: 'zh-CN-XiaoyiNeural' },
        { id: 3, name: '明远（文化导游）', model_path: '1', personality: '沉稳大气', default_speed: 1.1, default_pitch: 0.9, default_voice: 'zh-CN-YunxiNeural' }
      ])
    }
  } catch (e) {
    console.warn('获取数字人列表失败，使用默认数据', e)
    dhStore.setHumans([
      { id: 1, name: '灵韵（默认导游）', model_path: '1', personality: '温和亲切', default_speed: 1.0, default_pitch: 1.0, default_voice: 'zh-CN-XiaoxiaoNeural' },
      { id: 2, name: '慧心（禅意导游）', model_path: '2', personality: '轻柔舒缓', default_speed: 0.9, default_pitch: 1.1, default_voice: 'zh-CN-XiaoyiNeural' },
      { id: 3, name: '明远（文化导游）', model_path: '1', personality: '沉稳大气', default_speed: 1.1, default_pitch: 0.9, default_voice: 'zh-CN-YunxiNeural' }
    ])
  }
})

function switchDh(dh) {
  if (dh.id !== dhStore.currentId) {
    dhStore.switchDigitalHuman(dh)
    showSuccessToast(`已切换至 ${dh.name}`)
    // 保存到服务端
    saveUserDigitalHuman(dh.id).catch(e => console.warn('保存数字人偏好失败:', e))
    setTimeout(() => router.back(), 500)
  }
}
</script>

<style scoped>
.dh-select-page {
  min-height: 100vh;
  background: #f5f7f0;
}
.dh-list { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.dh-item {
  display: flex; align-items: center; gap: 16px; background: #fff;
  border-radius: 16px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 2px solid transparent; transition: all 0.3s ease; cursor: pointer;
}
.dh-item.active {
  border-color: #5b8c5a; box-shadow: 0 4px 16px rgba(91, 140, 90, 0.15);
}
.dh-preview {
  width: 72px; height: 96px; border-radius: 12px;
  background: linear-gradient(135deg, #e8f5e9, #f1f8e9);
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
.dh-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 20%;
}
.dh-avatar-fallback {
  font-size: 36px;
}
.dh-avatar-error-tip {
  position: absolute;
  bottom: -8px;
  font-size: 9px;
  color: #f56c6c;
  background: rgba(255,255,255,0.9);
  padding: 0 3px;
  border-radius: 8px;
}
.dh-info { flex: 1; min-width: 0; }
.dh-name { font-size: 16px; font-weight: 600; color: #2e3d2e; margin-bottom: 4px; }
.dh-personality {
  font-size: 11px;
  color: #c8a45c;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dh-params { display: flex; gap: 16px; font-size: 12px; color: #9aab9a; margin-bottom: 4px; }
.dh-voice { font-size: 12px; color: #6b7c6b; }
.dh-check { width: 24px; display: flex; justify-content: center; }
.dh-tip { margin: 24px 16px; padding: 16px; background: rgba(255,255,255,0.8); border-radius: 12px; font-size: 13px; color: #6b7c6b; line-height: 2; }
</style>