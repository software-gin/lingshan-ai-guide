<template>
  <div class="dh-manage">
    <h2 class="page-title">🪷 数字人管理</h2>

    <!-- 操作按钮 -->
    <div style="margin-bottom: 16px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
      <el-button type="primary" @click="showDialog(null)">+ 添加数字人</el-button>
      <el-divider direction="vertical" />
      <span style="font-size: 13px; color: #8cccd6;">LiveTalking 工具:</span>
      <el-button type="success" plain size="small"
                 @click="openLiveTalking('/avatar.html')">
        🎬 生成新形象
      </el-button>
      <el-button type="warning" plain size="small"
                 @click="openLiveTalking('/')">
        ⚙️ LiveTalking 主配置
      </el-button>
    </div>

    <!-- 数字人列表 -->
    <el-card>
      <el-table :data="humans" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="数字人名称" min-width="150" />
        <el-table-column prop="model_path" label="Avatar文件夹" min-width="160">
          <template #default="{ row }">
            <el-tag size="small" type="warning">data/avatars/{{ row.model_path }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="默认参数" min-width="200">
          <template #default="{ row }">
            语速: {{ row.default_speed }} | 语调: {{ row.default_pitch }}
          </template>
        </el-table-column>
        <el-table-column prop="default_voice" label="默认音色" min-width="180" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="showDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button type="danger" size="small" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑数字人' : '添加数字人'" width="560" :close-on-click-modal="false">
      <!-- 头像预览区 -->
      <div v-if="form.model_path" class="avatar-preview-section">
        <el-row :gutter="16" align="middle" style="padding: 8px 0 16px; border-bottom: 1px solid rgba(0,136,153,0.15); margin-bottom: 16px;">
          <el-col :span="6">
            <div class="avatar-preview-img" v-loading="avatarLoading">
              <img
                v-if="!avatarError"
                :src="avatarPreviewUrl"
                @error="onAvatarLoadError"
                @load="onAvatarLoadSuccess"
                alt="数字人头像"
              />
              <div v-else class="avatar-preview-error">
                <el-icon size="40" color="#909399"><Picture /></el-icon>
                <span>头像加载失败</span>
              </div>
            </div>
          </el-col>
          <el-col :span="18">
            <span style="font-size: 12px; color: #66a0ad;">
              预览：<el-tag size="small" type="warning" effect="dark">data/avatars/{{ form.model_path }}</el-tag>
            </span>
            <p style="font-size: 12px; color: #909399; margin: 4px 0 0 0;">
              从 LiveTalking 自动读取 full_imgs/ 下的第一张图
            </p>
          </el-col>
        </el-row>
      </div>

      <el-form :model="form" label-width="100px">
        <el-form-item label="数字人名称" required>
          <el-input v-model="form.name" placeholder="例如：女导游" />
        </el-form-item>
        <el-form-item label="Avatar文件夹" required>
          <div style="display:flex;flex-direction:column;gap:4px;width:100%">
            <custom-select v-model="form.model_path" placeholder="选择已生成的 Avatar..." filterable allow-create :options="avatarOptions" />
            <span style="font-size:11px;color:#66a0ad">
              {{ avatarsOnDisk.length === 0 ? '⚠ 未扫描到形象，请检查 LiveTalking 是否启动且 data/avatars/ 下有形象' : '自动扫描自 LiveTalking data/avatars/，也可手动输入' }}
            </span>
          </div>
        </el-form-item>

        <!-- 性格设置 -->
        <el-form-item label="数字人性格">
          <div style="display:flex;flex-direction:column;gap:6px;width:100%">
            <el-radio-group v-model="form.personality" class="personality-presets">
              <el-radio value="温和亲切，语气柔和，适合日常讲解，给游客带来温暖如家的感觉。回答简洁易懂。" size="small">温和亲切</el-radio>
              <el-radio value="轻柔舒缓，语调轻柔，带有禅意和宁静感，适合禅意体验。回答时多用诗意和禅语。" size="small">轻柔禅意</el-radio>
              <el-radio value="沉稳大气，知识渊博，语气稳重，适合文化讲解。回答时体现文化底蕴和历史深度。" size="small">沉稳大气</el-radio>
              <el-radio value="活泼开朗，热情洋溢，充满感染力和活力。回答时多用感叹和生动的比喻。" size="small">活泼开朗</el-radio>
            </el-radio-group>
            <el-input
              v-model="form.personality"
              type="textarea"
              :rows="3"
              placeholder="或自定义性格描述（将传递给大模型，影响回复风格）"
            />
            <span style="font-size:11px;color:#66a0ad;">
              💡 性格描述将作为系统提示词传递给大模型，确保回复风格与数字人性格一致
            </span>
          </div>
        </el-form-item>

        <el-form-item label="默认语速">
          <el-slider v-model="form.default_speed" :min="0.5" :max="2.0" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="默认语调">
          <el-slider v-model="form.default_pitch" :min="0.5" :max="2.0" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="默认音色">
          <custom-select v-model="form.default_voice" :options="voiceOptions" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <!-- 按钮直接放 body 里确保一定显示 -->
        <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:8px;padding-top:12px;border-top:1px solid rgba(0,136,153,0.2)">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button :loading="saving" @click="handleSave">确认保存</el-button>
        </div>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'
import { getAdminDigitalHumans, createDigitalHuman, updateDigitalHuman, deleteDigitalHuman, listAvatarsOnDisk } from '@/utils/api'

const humans = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const avatarsOnDisk = ref([])  // LiveTalking data/avatars/ 中已生成的 avatar 列表
const avatarOptions = computed(() => avatarsOnDisk.value.map(a => ({ label: a.folder, value: a.folder })))
const avatarLoading = ref(false)  // 头像加载状态
const avatarError = ref(false)    // 头像加载失败
const voiceOptions = [
  { label: '晓晓（女声·推荐）', value: 'zh-CN-XiaoxiaoNeural' },
  { label: '云希（男声）', value: 'zh-CN-YunxiNeural' },
  { label: '晓伊（女声·活泼）', value: 'zh-CN-XiaoyiNeural' },
  { label: '晓涵（女声·温柔）', value: 'zh-CN-XiaohanNeural' },
]

// 默认性格预设（按数字人ID对应）
const personalityPresets = {
  '灵韵（默认导游）': '温和亲切，语气柔和，适合日常讲解，给游客带来温暖如家的感觉。回答简洁易懂。',
  '慧心（禅意导游）': '轻柔舒缓，语调轻柔，带有禅意和宁静感，适合禅意体验。回答时多用诗意和禅语。',
  '明远（文化导游）': '沉稳大气，知识渊博，语气稳重，适合文化讲解。回答时体现文化底蕴和历史深度。',
}

const form = ref({
  name: '',
  model_path: '1',
  personality: '',
  default_speed: 1.0,
  default_pitch: 1.0,
  default_voice: 'zh-CN-XiaoxiaoNeural',
  is_active: true
})

// 头像预览 URL（基于 model_path 动态生成）
const avatarPreviewUrl = computed(() => {
  if (!form.value.model_path) return ''
  return `/api/admin/digital-humans/avatars/${encodeURIComponent(form.value.model_path)}/preview?t=${Date.now()}`
})

// 监听 model_path 变化，重置头像加载状态
watch(() => form.value.model_path, () => {
  avatarError.value = false
  avatarLoading.value = true
})

onMounted(() => {
  fetchHumans()
  fetchAvatarsOnDisk()
})

function onAvatarLoadSuccess() {
  avatarLoading.value = false
}

function onAvatarLoadError() {
  avatarLoading.value = false
  avatarError.value = true
}

async function fetchAvatarsOnDisk() {
  try {
    const res = await listAvatarsOnDisk()
    if (res.code === 200) {
      avatarsOnDisk.value = res.data
    }
  } catch (e) {
    console.warn('获取 avatar 目录失败:', e)
  }
}

async function fetchHumans() {
  loading.value = true
  try {
    const res = await getAdminDigitalHumans()
    if (res.code === 200) {
      humans.value = res.data || []
    }
  } catch (e) {
    console.error('获取数字人列表失败:', e)
  } finally {
    loading.value = false
  }
}

function showDialog(row) {
  if (row) {
    isEdit.value = true
    editId.value = row.id
    form.value = { ...row }
    // 确保 personality 不为 undefined
    if (!form.value.personality) {
      form.value.personality = personalityPresets[row.name] || ''
    }
  } else {
    isEdit.value = false
    editId.value = null
    form.value = {
      name: '',
      model_path: '1',
      personality: '',
      default_speed: 1.0,
      default_pitch: 1.0,
      default_voice: 'zh-CN-XiaoxiaoNeural',
      is_active: true
    }
  }
  avatarError.value = false
  avatarLoading.value = true
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    let res
    if (isEdit.value) {
      res = await updateDigitalHuman(editId.value, form.value)
    } else {
      res = await createDigitalHuman(form.value)
    }
    if (res.code === 200) {
      ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
      dialogVisible.value = false
      fetchHumans()
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  try {
    const res = await deleteDigitalHuman(id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchHumans()
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 跳转到 LiveTalking 配置页面（两个项目独立部署，通过链接互访）
function openLiveTalking(path) {
  // LiveTalking 默认运行在 8010 端口，可通过环境变量覆盖
  const ltHost = import.meta.env.VITE_LIVETALKING_HOST || window.location.hostname
  const ltPort = import.meta.env.VITE_LIVETALKING_PORT || '8010'
  window.open(`http://${ltHost}:${ltPort}${path}`, '_blank')
}
</script>

<style scoped>
.avatar-preview-section {
  margin-bottom: 8px;
}

.avatar-preview-img {
  width: 100px;
  height: 100px;
  border-radius: 12px;
  overflow: hidden;
  border: 2px solid rgba(0, 136, 153, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f4f8;
}

.avatar-preview-img img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #f0f4f8;
}

.avatar-preview-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #c0c4cc;
  font-size: 11px;
  width: 100%;
  height: 100%;
}

.personality-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.personality-presets :deep(.el-radio) {
  margin-right: 0;
  margin-bottom: 4px;
}
</style>