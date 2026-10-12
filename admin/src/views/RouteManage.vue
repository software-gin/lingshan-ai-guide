<template>
  <div class="route-manage">
    <h2 class="page-title">游览路线管理</h2>

    <!-- 统计概览 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">路线总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.active }}</div>
          <div class="stat-label">已启用</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.inactive }}</div>
          <div class="stat-label">已停用</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.styles }}</div>
          <div class="stat-label">风格分类数</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作栏 -->
    <el-row :gutter="16" class="action-row">
      <el-col :span="4">
        <el-button type="primary" @click="showDialog(null)" style="width:100%">
          新增路线
        </el-button>
      </el-col>
      <el-col :span="4">
        <el-button type="success" @click="handleSyncKnowledge" :loading="syncing" style="width:100%">
          同步到知识库
        </el-button>
      </el-col>
      <el-col :span="4">
        <el-button type="danger" @click="handleBatchDelete" :disabled="selectedIds.length === 0" style="width:100%">
          批量删除 ({{ selectedIds.length }})
        </el-button>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card class="filter-bar">
      <el-row :gutter="16">
        <el-col :span="4">
          <custom-select v-model="filterStyle" placeholder="风格筛选" clearable :options="styleFilterOptions" @change="fetchRoutes" />
        </el-col>
        <el-col :span="6">
          <el-input v-model="filterKeyword" placeholder="搜索路线名称..." clearable @keyup.enter="search" @clear="fetchRoutes">
            <template #append>
              <el-button @click="search">搜索</el-button>
            </template>
          </el-input>
        </el-col>
        <el-col :span="3">
          <custom-select v-model="filterStatus" placeholder="状态" clearable :options="statusOptions" @change="fetchRoutes" />
        </el-col>
        <el-col :span="3">
          <custom-select v-model="sortBy" placeholder="排序" :options="sortByOptions" @change="fetchRoutes" />
        </el-col>
        <el-col :span="2">
          <custom-select v-model="sortOrder" placeholder="方向" :options="sortOrderOptions" @change="fetchRoutes" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 路线列表 -->
    <el-card>
      <el-table :data="routeList" stripe v-loading="loading" style="width:100%" @selection-change="handleSelectionChange" row-key="id">
        <el-table-column type="selection" width="45" />
        <el-table-column label="ID" width="60" prop="id" />
        <el-table-column label="封面图" width="100">
          <template #default="{ row }">
            <div class="route-img-cell">
              <el-image
                v-if="row.bg_image"
                :src="row.bg_image"
                fit="cover"
                style="width:60px;height:40px;border-radius:4px;object-position:center top"
                :preview-src-list="[row.bg_image]"
              />
              <span v-else style="color:#ccc;font-size:12px">无</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="路线名称" min-width="160">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:6px">
              <span :style="{ color: row.color, fontWeight: 600 }">{{ row.title }}</span>
              <el-tag v-if="row.subtitle" size="small" effect="dark">{{ row.subtitle }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="风格" width="80">
          <template #default="{ row }">
            <el-tag :color="row.color" style="color:#fff;border:0" size="small">{{ row.style_label || row.style }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时长" width="100" prop="duration" />
        <el-table-column label="难度" width="60" prop="difficulty" />
        <el-table-column label="距离" width="70">
          <template #default="{ row }">{{ row.distance_km }}km</template>
        </el-table-column>
        <el-table-column label="景点数" width="70">
          <template #default="{ row }">
            <el-tag size="small" effect="dark">{{ row.spots?.length || 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推荐指数" width="90">
          <template #default="{ row }">
            <el-rate v-model="row.rating" disabled size="small" :colors="['#c8a45c','#c8a45c','#c8a45c']" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" width="140">
          <template #default="{ row }">
            <div class="tags-cell">
              <el-tag v-for="(tag, i) in (row.tags || []).slice(0, 3)" :key="i" size="small" effect="dark">
                {{ tag }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="showDialog(row)">编辑</el-button>
            <el-button type="success" size="small" link @click="showImageDialog(row)">图片</el-button>
            <el-button type="success" size="small" link @click="showSpotsDialog(row)">景点</el-button>
            <el-button type="warning" size="small" link @click="viewFeedbacks(row)">评价</el-button>
            <el-popconfirm title="确定删除该路线？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button type="danger" size="small" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="perPage"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchRoutes"
          @size-change="fetchRoutes"
        />
      </div>
    </el-card>

    <!-- 编辑/新增路线对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑路线' : '新增路线'" width="760px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="路线名称" prop="title" :rules="[{ required: true, message: '请输入路线名称' }]">
              <el-input v-model="form.title" placeholder="如：文化朝圣路线" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="副标题">
              <el-input v-model="form.subtitle" placeholder="如：3小时精华游" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="风格编码">
              <custom-select v-model="form.style" placeholder="选择风格" :options="styleOptions" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="风格标签">
              <el-input v-model="form.style_label" placeholder="如：文化" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="主题色">
              <el-color-picker v-model="form.color" show-alpha />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="时长">
              <el-input v-model="form.duration" placeholder="如：约3小时" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="难度">
              <custom-select v-model="form.difficulty" :options="difficultyOptions" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="距离(km)">
              <el-input-number v-model="form.distance_km" :min="0" :max="20" :step="0.1" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="推荐指数">
              <el-rate v-model="form.rating" :colors="['#c8a45c','#c8a45c','#c8a45c']" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="排序权重">
              <el-input-number v-model="form.sort_order" :min="0" :max="999" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="最佳时间">
          <el-input v-model="form.best_time" placeholder="如：上午 8:00-11:00" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="路线描述..." />
        </el-form-item>
        <el-form-item label="小贴士">
          <el-input v-model="form.tips" type="textarea" :rows="2" placeholder="游览小贴士..." />
        </el-form-item>
        <el-form-item label="标签">
          <custom-select v-model="form.tags" multiple filterable allow-create :options="tagOptions" placeholder="输入标签后回车" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 景点管理对话框 -->
    <el-dialog v-model="spotsVisible" :title="'景点管理 - ' + (currentRouteTitle || '')" width="600px" :close-on-click-modal="false">
      <div class="spots-tip">拖拽左侧手柄可调整景点顺序</div>
      <el-table :data="spotsForm" stripe style="width:100%">
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="name" label="景点名称" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-model="row.name" placeholder="景点名称" size="small" />
          </template>
        </el-table-column>
        <el-table-column prop="description" label="景点介绍" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-model="row.description" placeholder="景点介绍" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="坐标" width="180">
          <template #default="{ row }">
            <el-input v-model="row.latitude" placeholder="纬度" size="small" style="width:45%;margin-right:5%" />
            <el-input v-model="row.longitude" placeholder="经度" size="small" style="width:45%" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="removeSpot($index)">×</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-spot-btn">
        <el-button type="primary" size="small" @click="addSpot">+ 添加景点</el-button>
      </div>
      <template #footer>
        <el-button @click="spotsVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSpots">保存景点</el-button>
      </template>
    </el-dialog>

    <!-- 路线封面图片管理对话框 -->
    <el-dialog v-model="imageDialogVisible" :title="'路线封面图 - ' + (imageDialogRouteTitle || '')" width="520px" :close-on-click-modal="false">
      <div class="image-manage">
        <div class="image-preview-section">
          <div class="section-title">当前封面图</div>
          <div class="preview-area">
            <el-image
              v-if="imageForm.bg_image"
              :src="imageForm.bg_image"
              fit="cover"
              style="width:100%;height:200px;border-radius:8px;object-position:center top"
              :preview-src-list="[imageForm.bg_image]"
            />
            <div v-else class="no-image">暂无封面图</div>
          </div>
          <div v-if="imageForm.bg_image" class="image-actions">
            <el-button type="danger" :loading="removingImage" @click="handleRemoveImage">移除当前图片</el-button>
          </div>
        </div>
        <div class="image-upload-section">
          <div class="section-title">上传新封面图</div>
          <div class="upload-hint">建议尺寸：800×500px，支持 jpg/png/webp，最大 10MB</div>
          <el-upload
            class="image-uploader"
            :show-file-list="false"
            :before-upload="handleBeforeUpload"
            :http-request="handleImageUpload"
          >
            <el-button type="primary">选择图片</el-button>
          </el-upload>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getAdminRoutes, getAdminRoute, createAdminRoute, updateAdminRoute,
  deleteAdminRoute, batchDeleteAdminRoutes, syncRoutesToKnowledge, getRouteStylesStats,
  uploadRouteImage, setRouteImage, deleteRouteImage
} from '@/utils/api'

// ====== 数据 ======
const router = useRouter()
const routeList = ref([])
const loading = ref(false)
const saving = ref(false)
const syncing = ref(false)
const selectedIds = ref([])

// ====== 筛选 ======
const filterStyle = ref('')
const filterKeyword = ref('')
const filterStatus = ref('')
const sortBy = ref('sort_order')
const sortOrder = ref('asc')

// ====== 分页 ======
const page = ref(1)
const perPage = ref(20)
const total = ref(0)

// ====== 统计 ======
const stats = reactive({ total: 0, active: 0, inactive: 0, styles: 0 })

// ====== 风格选项 ======
const styleOptions = [
  { label: '文化', value: 'culture' },
  { label: '自然', value: 'nature' },
  { label: '亲子', value: 'family' },
  { label: '禅意', value: 'zen' },
  { label: '摄影', value: 'photo' },
  { label: '美食', value: 'food' },
  { label: '建筑', value: 'architecture' },
  { label: '历史', value: 'history' },
  { label: '休闲', value: 'leisure' },
  { label: '速游', value: 'quick' }
]
const styleFilterOptions = computed(() => [
  { label: '全部', value: '' },
  ...styleOptions,
])
const statusOptions = [
  { label: '全部', value: '' },
  { label: '启用', value: 'true' },
  { label: '停用', value: 'false' },
]
const sortByOptions = [
  { label: '排序权重', value: 'sort_order' },
  { label: '创建时间', value: 'created_at' },
  { label: '推荐指数', value: 'rating' },
  { label: '名称', value: 'title' },
]
const sortOrderOptions = [
  { label: '升序', value: 'asc' },
  { label: '降序', value: 'desc' },
]
const difficultyOptions = [
  { label: '低', value: '低' },
  { label: '中', value: '中' },
  { label: '高', value: '高' },
]
const tagOptions = computed(() => commonTags.map(t => ({ label: t, value: t })))

const commonTags = ['佛教文化', '经典', '精华', '自然风光', '户外', '亲子', '家庭', '轻松', '互动',
  '禅意', '静心', '茶道', '素食', '摄影', '打卡', '拍照', '美食', '素斋',
  '建筑', '艺术', '美学', '历史', '文化', '深度', '典故',
  '休闲', '慢节奏', '放松', '全天', '快速', '时间短', '必去',
  '慢节奏', '快节奏']

// ====== 编辑对话框 ======
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = reactive({
  title: '',
  subtitle: '',
  style: 'culture',
  style_label: '',
  icon: '📍',
  color: '#5b8c5a',
  description: '',
  duration: '',
  difficulty: '低',
  best_time: '',
  tips: '',
  distance_km: 0,
  tags: [],
  is_active: true,
  sort_order: 0,
  rating: 4.5
})

// ====== 景点管理对话框 ======
const spotsVisible = ref(false)
const currentRouteId = ref(null)
const currentRouteTitle = ref('')
const spotsForm = ref([])
const editingSpotsRouteId = ref(null)

// ====== 图片管理对话框 ======
const imageDialogVisible = ref(false)
const imageDialogRouteId = ref(null)
const imageDialogRouteTitle = ref('')
const imageForm = reactive({ bg_image: '' })
const removingImage = ref(false)
const uploadProgress = ref(0)

onMounted(() => {
  fetchRoutes()
  fetchStats()
})

// ====== 数据获取 ======
async function fetchRoutes() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: perPage.value,
      style: filterStyle.value,
      keyword: filterKeyword.value,
      is_active: filterStatus.value,
      sort_by: sortBy.value,
      sort_order: sortOrder.value
    }
    const res = await getAdminRoutes(params)
    if (res.code === 200) {
      routeList.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    const [routesRes, stylesRes] = await Promise.all([
      getAdminRoutes({ page: 1, per_page: 1 }),
      getRouteStylesStats()
    ])
    if (routesRes.code === 200) {
      stats.total = routesRes.data.total || 0
    }
    if (stylesRes.code === 200) {
      stats.styles = (stylesRes.data || []).length
    }
    // Count active/inactive
    const allRes = await getAdminRoutes({ per_page: 9999 })
    if (allRes.code === 200) {
      const items = allRes.data.items || []
      stats.active = items.filter(r => r.is_active).length
      stats.inactive = items.filter(r => !r.is_active).length
    }
  } catch (e) {
    console.error(e)
  }
}

function search() {
  page.value = 1
  fetchRoutes()
}

function viewFeedbacks(row) {
  router.push({ path: `/route-feedbacks/${row.id}`, query: { name: row.title } })
}

// ====== 编辑/创建 ======
function resetForm() {
  form.title = ''
  form.subtitle = ''
  form.style = 'culture'
  form.style_label = ''
  form.icon = '📍'
  form.color = '#5b8c5a'
  form.description = ''
  form.duration = ''
  form.difficulty = '低'
  form.best_time = ''
  form.tips = ''
  form.distance_km = 0
  form.tags = []
  form.is_active = true
  form.sort_order = 0
  form.rating = 4.5
}

function showDialog(row) {
  isEdit.value = !!row
  editId.value = row?.id || null
  if (row) {
    form.title = row.title
    form.subtitle = row.subtitle || ''
    form.style = row.style
    form.style_label = row.style_label || ''
    form.icon = row.icon || '📍'
    form.color = row.color || '#5b8c5a'
    form.description = row.description || ''
    form.duration = row.duration || ''
    form.difficulty = row.difficulty || '低'
    form.best_time = row.best_time || ''
    form.tips = row.tips || ''
    form.distance_km = row.distance_km || 0
    form.tags = row.tags || []
    form.is_active = row.is_active !== false
    form.sort_order = row.sort_order || 0
    form.rating = row.rating || 4.5
  } else {
    resetForm()
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!formRef.value) return
  try { await formRef.value.validate() } catch { return }

  saving.value = true
  try {
    const data = { ...form }
    let res
    if (isEdit.value) {
      res = await updateAdminRoute(editId.value, data)
    } else {
      res = await createAdminRoute(data)
    }
    if (res.code === 200) {
      ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
      dialogVisible.value = false
      fetchRoutes()
      fetchStats()
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || ''))
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  try {
    const res = await deleteAdminRoute(id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchRoutes()
      fetchStats()
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// ====== 景点管理 ======
async function showSpotsDialog(row) {
  editingSpotsRouteId.value = row.id
  currentRouteTitle.value = row.title

  try {
    const res = await getAdminRoute(row.id)
    if (res.code === 200 && res.data) {
      spotsForm.value = (res.data.spots || []).map(s => ({
        name: s.name || '',
        description: s.description || '',
        latitude: s.latitude || null,
        longitude: s.longitude || null,
        _id: s.id
      }))
    }
  } catch (e) {
    spotsForm.value = []
  }

  if (spotsForm.value.length === 0) {
    spotsForm.value = [{ name: '', description: '', latitude: null, longitude: null }]
  }
  spotsVisible.value = true
}

function addSpot() {
  spotsForm.value.push({ name: '', description: '', latitude: null, longitude: null })
}

function removeSpot(index) {
  spotsForm.value.splice(index, 1)
}

async function saveSpots() {
  const validSpots = spotsForm.value.filter(s => s.name.trim())
  if (validSpots.length === 0) {
    ElMessage.warning('请至少添加一个有效的景点')
    return
  }

  saving.value = true
  try {
    const routeRes = await getAdminRoute(editingSpotsRouteId.value)
    if (routeRes.code !== 200) {
      ElMessage.error('获取路线信息失败')
      return
    }
    const routeData = routeRes.data

    const updateData = {
      title: routeData.title,
      subtitle: routeData.subtitle,
      style: routeData.style,
      style_label: routeData.style_label,
      tags: routeData.tags,
      icon: routeData.icon,
      color: routeData.color,
      description: routeData.description,
      duration: routeData.duration,
      difficulty: routeData.difficulty,
      best_time: routeData.best_time,
      tips: routeData.tips,
      distance_km: routeData.distance_km,
      is_active: routeData.is_active,
      sort_order: routeData.sort_order,
      rating: routeData.rating,
      bg_image: routeData.bg_image,
      spots: validSpots.map((s, i) => ({
        name: s.name,
        description: s.description || '',
        sort_order: i,
        latitude: s.latitude || null,
        longitude: s.longitude || null
      }))
    }

    const res = await updateAdminRoute(editingSpotsRouteId.value, updateData)
    if (res.code === 200) {
      ElMessage.success('景点保存成功')
      spotsVisible.value = false
      fetchRoutes()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || ''))
  } finally {
    saving.value = false
  }
}

// ====== 批量操作 ======
function handleSelectionChange(rows) {
  selectedIds.value = rows.map(r => r.id)
}

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) return
  try {
    const res = await batchDeleteAdminRoutes({ ids: selectedIds.value })
    if (res.code === 200) {
      ElMessage.success(res.message)
      selectedIds.value = []
      fetchRoutes()
      fetchStats()
    }
  } catch (e) {
    ElMessage.error('批量删除失败')
  }
}

async function handleSyncKnowledge() {
  syncing.value = true
  try {
    const res = await syncRoutesToKnowledge()
    if (res.code === 200) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {
    ElMessage.error('同步失败')
  } finally {
    syncing.value = false
  }
}

// ====== 图片管理 ======
function showImageDialog(row) {
  imageDialogRouteId.value = row.id
  imageDialogRouteTitle.value = row.title
  imageForm.bg_image = row.bg_image || ''
  imageDialogVisible.value = true
}

function closeImageDialog() {
  imageDialogVisible.value = false
}

function handleBeforeUpload(file) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
  if (!allowed.includes(file.type)) {
    ElMessage.error('仅支持 jpg/png/webp/gif 格式')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片不能超过 10MB')
    return false
  }
  uploadProgress.value = 50
  return true
}

async function handleImageUpload(param) {
  uploadProgress.value = 60
  try {
    const formData = new FormData()
    formData.append('image', param.file)
    const res = await uploadRouteImage(formData)
    uploadProgress.value = 80
    if (res.code === 200) {
      const imagePath = res.data.path
      const assignRes = await setRouteImage(imageDialogRouteId.value, { bg_image: imagePath })
      if (assignRes.code === 200) {
        ElMessage.success('图片上传并设置成功')
        imageForm.bg_image = imagePath
        fetchRoutes()
      } else {
        ElMessage.error(assignRes.message || '设置图片失败')
      }
    } else {
      ElMessage.error(res.message || '上传失败')
    }
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.message || ''))
  } finally {
    uploadProgress.value = 0
  }
}

async function handleRemoveImage() {
  if (!imageDialogRouteId.value) return
  removingImage.value = true
  try {
    const res = await deleteRouteImage(imageDialogRouteId.value)
    if (res.code === 200) {
      ElMessage.success('图片已移除')
      imageForm.bg_image = ''
      fetchRoutes()
    } else {
      ElMessage.error(res.message || '移除失败')
    }
  } catch (e) {
    ElMessage.error('移除失败: ' + (e.message || ''))
  } finally {
    removingImage.value = false
  }
}
</script>

<style scoped>
.route-manage {
  padding: 0;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  padding: 4px 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.action-row {
  margin-bottom: 16px;
}

.filter-bar {
  margin-bottom: 16px;
}

.tags-cell {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.spots-tip {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.add-spot-btn {
  margin-top: 12px;
  text-align: center;
}

.route-img-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}

.route-img-cell .el-image {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

/* ========== 图片管理对话框 ========== */
.image-manage {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.image-preview-section,
.image-upload-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}

.preview-area {
  border: 2px dashed var(--border);
  border-radius: 8px;
  padding: 12px;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.no-image {
  color: var(--text-muted);
  font-size: 14px;
  padding: 40px 0;
}

.image-actions {
  margin-top: 4px;
}

.upload-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.image-uploader {
  margin-top: 4px;
}

.upload-progress {
  color: var(--primary);
  font-size: 13px;
  margin-top: 4px;
}

:deep(.el-rate) {
  display: inline-flex;
  align-items: center;
}
</style>