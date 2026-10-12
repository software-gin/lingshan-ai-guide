<template>
  <div class="knowledge-manage">
    <h2 class="page-title">知识库管理</h2>

    <!-- 统计概览 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.vector_doc_count }}</div>
          <div class="stat-label">向量文档块</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.knowledge_count }}</div>
          <div class="stat-label">知识条目</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-label">知识库状态</div>
          <el-tag :type="stats.vector_doc_count > 0 ? 'success' : 'warning'" size="small">
            {{ stats.vector_doc_count > 0 ? '已就绪' : '未构建' }}
          </el-tag>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-label">分类数量</div>
          <el-tag type="info" size="small">{{ stats.category_count }} 类</el-tag>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作栏 -->
    <el-row :gutter="16" class="action-row">
      <el-col :span="3">
        <el-button type="success" @click="showUploadDialog" style="width:100%">
          上传知识文件
        </el-button>
      </el-col>
      <el-col :span="3">
        <el-button type="primary" @click="showDialog(null)" style="width:100%">
          添加知识条目
        </el-button>
      </el-col>
      <el-col :span="3">
        <el-button type="warning" @click="handleSync" :loading="syncing" style="width:100%">
          同步向量库
        </el-button>
      </el-col>
      <el-col :span="3">
        <el-button type="info" @click="showBatchImport" style="width:100%">
          批量导入
        </el-button>
      </el-col>
      <el-col :span="3">
        <el-button type="info" @click="handleExport" style="width:100%">
          批量导出
        </el-button>
      </el-col>
      <el-col :span="3">
        <el-button type="danger" @click="handleBatchDelete" :disabled="selectedIds.length === 0" style="width:100%">
          批量删除 ({{ selectedIds.length }})
        </el-button>
      </el-col>
      <el-col :span="3">
        <el-button type="info" @click="showCategoryManage" style="width:100%">
          分类管理
        </el-button>
      </el-col>
      <el-col :span="2">
        <el-button type="info" @click="showGraphDialog" style="width:100%">
          知识图谱
        </el-button>
      </el-col>
    </el-row>

    <!-- 搜索筛选栏 -->
    <el-card class="filter-bar">
      <el-row :gutter="16">
        <el-col :span="4">
          <custom-select v-model="filterCategory" placeholder="分类筛选" clearable :options="categoryFilterOptions" @change="fetchKnowledge" />
        </el-col>
        <el-col :span="4">
          <el-input
            v-model="filterKeyword"
            placeholder="关键词搜索..."
            clearable
            @keyup.enter="search"
            @clear="fetchKnowledge"
          >
            <template #append>
              <el-button @click="search">搜索</el-button>
            </template>
          </el-input>
        </el-col>
        <el-col :span="4">
          <el-input v-model="filterTags" placeholder="标签筛选" clearable @change="fetchKnowledge" />
        </el-col>
        <el-col :span="3">
          <custom-select v-model="filterStatus" placeholder="状态" clearable :options="statusOptions" @change="fetchKnowledge" />
        </el-col>
        <el-col :span="3">
          <custom-select v-model="sortBy" placeholder="排序" :options="sortByOptions" @change="fetchKnowledge" />
        </el-col>
        <el-col :span="3">
          <custom-select v-model="sortOrder" placeholder="排序方向" :options="sortOrderOptions" @change="fetchKnowledge" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 知识库列表 -->
    <el-card>
      <el-table :data="knowledgeList" stripe v-loading="loading" style="width:100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="45" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="分类" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="getCategoryColor(row.category?.code)">
              {{ row.category?.name || '未分类' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column label="标签" width="140">
          <template #default="{ row }">
            <div class="tags-cell">
              <el-tag v-for="(tag, i) in (row.tags || '').split(',').slice(0, 3)" :key="i" size="small" effect="dark">
                {{ tag }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.source_file || '手动录入' }}
          </template>
        </el-table-column>
        <el-table-column label="向量同步" width="90">
          <template #default="{ row }">
            <el-tag :type="row.vector_sync ? 'success' : 'warning'" size="small">
              {{ row.vector_sync ? '已同步' : '待同步' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="60">
          <template #default="{ row }">
            v{{ row.version }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="155" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="showDialog(row)">编辑</el-button>
            <el-button type="info" size="small" link @click="showVersions(row)">历史</el-button>
            <el-popconfirm title="确定删除？" @confirm="handleDelete(row.id)">
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
          @current-change="fetchKnowledge"
          @size-change="fetchKnowledge"
        />
      </div>
    </el-card>

    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑知识条目' : '添加知识条目'"
      width="720px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item label="分类" prop="category_id" :rules="[{ required: true, message: '请选择分类' }]">
          <custom-select v-model="form.category_id" placeholder="选择知识分类" :options="categoryOptions" />
        </el-form-item>
        <el-form-item label="标题" prop="title" :rules="[{ required: true, message: '请输入标题' }]">
          <el-input v-model="form.title" placeholder="请输入标题" />
        </el-form-item>
        <el-form-item label="内容" prop="content" :rules="[{ required: true, message: '请输入内容' }]">
          <el-input v-model="form.content" type="textarea" :rows="6" placeholder="请输入知识内容" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="多个标签用逗号分隔，如：灵山,大佛" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="form.keywords" placeholder="多个关键词用逗号分隔，如：灵山大佛,景点,介绍" />
        </el-form-item>
        <el-form-item label="来源文件">
          <el-input v-model="form.source_file" placeholder="自动填入（文件上传时）" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史对话框 -->
    <el-dialog
      v-model="versionsVisible"
      title="版本历史"
      width="700px"
    >
      <el-timeline v-loading="versionsLoading">
        <el-timeline-item
          v-for="v in versions"
          :key="v.id"
          :timestamp="v.created_at"
          placement="top"
        >
          <el-card>
            <el-tag type="info" size="small" style="margin-bottom:8px">v{{ v.version }}</el-tag>
            <div style="font-size:13px;color:#99c7d1">
              <strong>标题：</strong> {{ v.title }}<br/>
              <strong>内容：</strong> {{ v.content?.substring(0, 100) }}{{ v.content?.length > 100 ? '...' : '' }}
              <el-button type="primary" size="small" link @click="restoreVersion(v.id)">恢复此版本</el-button>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
      <template #footer>
        <el-button @click="versionsVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 文件上传对话框 -->
    <el-dialog
      v-model="uploadVisible"
      title="上传知识文件"
      width="520px"
    >
      <div class="upload-tip">
        <p>支持的文件格式：docx、xlsx、txt、pdf</p>
        <p>上传后系统将自动提取内容、检测类型并加入向量知识库</p>
      </div>
      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        :auto-upload="false"
        :on-change="handleFileSelect"
        :before-upload="beforeUpload"
        :file-list="fileList"
        :limit="1"
        accept=".docx,.xlsx,.txt,.pdf"
      >
        <div class="upload-content">
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <p>点击或将文件拖拽到此区域</p>
          <p class="upload-hint">支持 docx / xlsx / txt / pdf 文件</p>
        </div>
      </el-upload>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">
          确认上传
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 -->
    <el-dialog
      v-model="batchImportVisible"
      title="批量导入知识"
      width="600px"
    >
      <el-form label-width="80px">
        <el-form-item label="目标分类">
          <custom-select v-model="batchCategoryId" placeholder="选择分类" :options="categoryOptions" />
        </el-form-item>
        <el-form-item label="JSON数据">
          <el-input
            v-model="batchImportJson"
            type="textarea"
            :rows="10"
            placeholder='[{"title":"标题1","content":"内容1"},{"title":"标题2","content":"内容2"}]'
          />
        </el-form-item>
        <el-form-item label="示例格式">
          <div style="background:rgba(0,136,153,0.08);padding:10px;border-radius:4px;font-size:12px;font-family:monospace;color:#99c7d1">
[{"title":"标题","content":"内容","tags":"标签1,标签2","keywords":"关键词1,关键词2"}]
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchImportVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchImporting" @click="handleBatchImport">导入</el-button>
      </template>
    </el-dialog>

    <!-- 分类管理对话框 -->
    <el-dialog
      v-model="categoryManageVisible"
      title="知识分类管理"
      width="600px"
    >
      <el-table :data="categories" stripe>
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="code" label="编码" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button type="danger" size="small" link @click="deleteCategory(row.id)" :disabled="!row.is_active">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="categoryManageVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 知识图谱对话框 -->
    <el-dialog
      v-model="graphVisible"
      title="知识库图谱"
      width="80%"
      :close-on-click-modal="false"
    >
      <div class="graph-container" v-loading="graphLoading">
        <div ref="graphCanvasRef" class="graph-canvas"></div>
      </div>
      <template #footer>
        <el-button @click="graphVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import {
  getKnowledgeList,
  createKnowledge,
  updateKnowledge,
  deleteKnowledge,
  syncKnowledge,
  uploadKnowledgeFile,
  getKnowledgeGraph,
  getKnowledgeStats,
  // 新版API
  getKnowledgeCategories,
  getKnowledgeListV2,
  createKnowledgeV2,
  updateKnowledgeV2,
  deleteKnowledgeV2,
  deleteKnowledgeCategory,
  getKnowledgeVersions,
  restoreKnowledgeVersion,
  batchImportKnowledge,
  batchExportKnowledge,
  batchDeleteKnowledge,
} from '@/utils/api'

// ====== 基础数据 ======
const knowledgeList = ref([])
const categories = ref([])
const categoryFilterOptions = computed(() => [
  { label: '全部', value: '' },
  ...categories.value.map(cat => ({ label: cat.name, value: cat.code })),
])
const categoryOptions = computed(() => categories.value.map(cat => ({ label: cat.name, value: cat.id })))
const statusOptions = [
  { label: '全部', value: '' },
  { label: '启用', value: 'true' },
  { label: '停用', value: 'false' },
]
const sortByOptions = [
  { label: '创建时间', value: 'created_at' },
  { label: '更新时间', value: 'updated_at' },
  { label: '标题', value: 'title' },
]
const sortOrderOptions = [
  { label: '降序', value: 'desc' },
  { label: '升序', value: 'asc' },
]
const loading = ref(false)
const saving = ref(false)
const syncing = ref(false)
const selectedIds = ref([])

// ====== 筛选条件 ======
const filterCategory = ref('')
const filterKeyword = ref('')
const filterTags = ref('')
const filterStatus = ref('')
const sortBy = ref('created_at')
const sortOrder = ref('desc')

// ====== 分页 ======
const page = ref(1)
const perPage = ref(20)
const total = ref(0)

// ====== 编辑对话框 ======
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = ref({
  category_id: null,
  title: '',
  content: '',
  tags: '',
  keywords: '',
  source_file: '',
  is_active: true
})

// ====== 统计信息 ======
const stats = ref({
  vector_doc_count: 0,
  knowledge_count: 0,
  faq_count: 0,
  category_count: 0
})

// ====== 版本历史 ======
const versionsVisible = ref(false)
const versionsLoading = ref(false)
const versions = ref([])
const currentVersionId = ref(null)

// ====== 文件上传 ======
const uploadVisible = ref(false)
const uploading = ref(false)
const uploadRef = ref(null)
const fileList = ref([])
const selectedFile = ref(null)

// ====== 批量导入 ======
const batchImportVisible = ref(false)
const batchImporting = ref(false)
const batchCategoryId = ref(null)
const batchImportJson = ref('')

// ====== 分类管理 ======
const categoryManageVisible = ref(false)

// ====== 知识图谱 ======
const graphVisible = ref(false)
const graphLoading = ref(false)
const graphCanvasRef = ref(null)
let graphChart = null

onMounted(() => {
  fetchKnowledge()
  fetchStats()
  fetchCategories()
})

onBeforeUnmount(() => {
  if (graphChart) {
    graphChart.dispose()
    graphChart = null
  }
})

// ====== 分类颜色映射 ======
function getCategoryColor(code) {
  const map = {
    faq: '',
    scene_intro: 'success',
    history: 'warning',
    basic_info: 'info',
    route: 'danger'
  }
  return map[code] || ''
}

// ====== 数据获取 ======
async function fetchKnowledge() {
  loading.value = true
  try {
    const res = await getKnowledgeListV2({
      page: page.value,
      per_page: perPage.value,
      category: filterCategory.value,
      keyword: filterKeyword.value,
      tags: filterTags.value,
      is_active: filterStatus.value,
      sort_by: sortBy.value,
      sort_order: sortOrder.value
    })
    if (res.code === 200) {
      knowledgeList.value = res.data.items || []
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
    const res = await getKnowledgeStats()
    if (res.code === 200) {
      stats.value = res.data
    }
  } catch (e) {
    console.error(e)
  }
}

async function fetchCategories() {
  try {
    const res = await getKnowledgeCategories()
    if (res.code === 200) {
      categories.value = res.data || []
    }
  } catch (e) {
    console.error(e)
  }
}

function search() {
  page.value = 1
  fetchKnowledge()
}

// ====== 编辑/创建 ======
function showDialog(row) {
  isEdit.value = !!row
  editId.value = row?.id || null
  form.value = row
    ? {
        category_id: row.category_id,
        title: row.title,
        content: row.content,
        tags: row.tags || '',
        keywords: row.keywords || '',
        source_file: row.source_file || '',
        is_active: row.is_active
      }
    : {
        category_id: null,
        title: '',
        content: '',
        tags: '',
        keywords: '',
        source_file: '',
        is_active: true
      }
  dialogVisible.value = true
}

async function handleSave() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    let res
    if (isEdit.value) {
      res = await updateKnowledgeV2(editId.value, form.value)
    } else {
      res = await createKnowledgeV2(form.value)
    }
    if (res.code === 200) {
      ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
      dialogVisible.value = false
      fetchKnowledge()
      fetchStats()
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
    const res = await deleteKnowledgeV2(id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchKnowledge()
      fetchStats()
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// ====== 批量操作 ======
function handleSelectionChange(rows) {
  selectedIds.value = rows.map(r => r.id)
}

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条知识？`, '确认', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    const res = await batchDeleteKnowledge({ ids: selectedIds.value })
    if (res.code === 200) {
      ElMessage.success(res.message)
      selectedIds.value = []
      fetchKnowledge()
      fetchStats()
    }
  } catch (e) {
    ElMessage.error('批量删除失败')
  }
}

async function handleSync() {
  syncing.value = true
  try {
    const res = await syncKnowledge()
    if (res.code === 200) {
      ElMessage.success(res.message || '同步完成')
      fetchKnowledge()
      fetchStats()
    }
  } catch (e) {
    ElMessage.error('同步失败')
  } finally {
    syncing.value = false
  }
}

// ====== 批量导入 ======
function showBatchImport() {
  batchImportVisible.value = true
  batchImportJson.value = ''
  batchCategoryId.value = null
}

async function handleBatchImport() {
  if (!batchCategoryId.value) {
    ElMessage.warning('请选择目标分类')
    return
  }
  if (!batchImportJson.value.trim()) {
    ElMessage.warning('请输入JSON数据')
    return
  }

  let items
  try {
    items = JSON.parse(batchImportJson.value)
    if (!Array.isArray(items)) {
      ElMessage.error('JSON数据必须是数组格式')
      return
    }
  } catch {
    ElMessage.error('JSON格式错误，请检查')
    return
  }

  batchImporting.value = true
  try {
    const res = await batchImportKnowledge({ items, category_id: batchCategoryId.value })
    if (res.code === 200) {
      ElMessage.success(res.message)
      batchImportVisible.value = false
      fetchKnowledge()
      fetchStats()
    }
  } catch (e) {
    ElMessage.error('批量导入失败')
  } finally {
    batchImporting.value = false
  }
}

// ====== 批量导出 ======
async function handleExport() {
  const params = {}
  if (filterCategory.value) params.category = filterCategory.value
  if (filterKeyword.value) params.keyword = filterKeyword.value

  try {
    const res = await batchExportKnowledge(params)
    if (res.code === 200) {
      const json = JSON.stringify(res.data.items, null, 2)
      const blob = new Blob([json], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `knowledge_export_${Date.now()}.json`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('导出成功')
    }
  } catch (e) {
    ElMessage.error('导出失败')
  }
}

// ====== 文件上传 ======
function showUploadDialog() {
  uploadVisible.value = true
  fileList.value = []
  selectedFile.value = null
}

function handleFileSelect(file) {
  selectedFile.value = file.raw
}

function beforeUpload() {
  return false
}

async function handleUpload() {
  if (!selectedFile.value) {
    ElMessage.warning('请选择文件')
    return
  }

  uploading.value = true
  const formData = new FormData()
  formData.append('file', selectedFile.value)

  try {
    const res = await uploadKnowledgeFile(formData)
    if (res.code === 200) {
      ElMessage.success(res.message || '上传成功')
      uploadVisible.value = false
      fetchKnowledge()
      fetchStats()
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
  }
}

// ====== 版本历史 ======
async function showVersions(row) {
  currentVersionId.value = row.id
  versionsVisible.value = true
  versionsLoading.value = true
  try {
    const res = await getKnowledgeVersions(row.id)
    if (res.code === 200) {
      versions.value = res.data.versions || []
    }
  } catch (e) {
    ElMessage.error('获取版本历史失败')
  } finally {
    versionsLoading.value = false
  }
}

async function restoreVersion(versionId) {
  if (!currentVersionId.value) return
  try {
    await ElMessageBox.confirm('确定恢复到该版本？当前版本将保存为历史记录。', '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await restoreKnowledgeVersion(currentVersionId.value, versionId)
    if (res.code === 200) {
      ElMessage.success(res.message)
      versionsVisible.value = false
      fetchKnowledge()
    }
  } catch (e) {
    ElMessage.error('恢复失败')
  }
}

// ====== 分类管理 ======
function showCategoryManage() {
  categoryManageVisible.value = true
}

async function deleteCategory(catId) {
  try {
    const res = await deleteKnowledgeCategory(catId)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchCategories()
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// ====== 知识图谱 ======
function showGraphDialog() {
  graphVisible.value = true
  graphLoading.value = true
  fetchGraphData()
}

async function fetchGraphData() {
  try {
    const res = await getKnowledgeGraph()
    if (res.code === 200) {
      renderGraph(res.data)
    }
  } catch (e) {
    console.error(e)
  } finally {
    graphLoading.value = false
  }
}

function renderGraph(data) {
  if (!graphCanvasRef.value || !data.nodes || data.nodes.length === 0) {
    graphLoading.value = false
    return
  }

  // 动态提取所有分类，并为每个分类分配颜色
  const categorySet = new Set()
  data.nodes.forEach(n => {
    if (n.category) categorySet.add(n.category)
  })
  // 边分类也加入（含"关联"）
  data.edges.forEach(e => {
    if (e.category) categorySet.add(e.category)
  })
  const categories = Array.from(categorySet)
  const colorPalette = [
    '#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399',
    '#b37feb', '#5cdbd3', '#ff85c0', '#ffc069', '#95de64',
    '#69c0ff', '#d3adf7', '#ffd666', '#87e8de', '#ff9c6e'
  ]
  const categoryColors = {}
  categories.forEach((cat, i) => {
    categoryColors[cat] = colorPalette[i % colorPalette.length]
  })

  // 去重构建节点
  const nodeMap = {}
  data.nodes.forEach(n => {
    if (!nodeMap[n.label]) {
      nodeMap[n.label] = {
        id: n.label,
        name: n.label,
        category: n.category || '知识'
      }
    }
  })
  const chartNodes = Object.values(nodeMap)

  // 构建边，只保留源和目标都在节点列表中的边
  const chartEdges = []
  data.edges.forEach(e => {
    const sourceNode = chartNodes.find(n => n.id === e.source)
    const targetNode = chartNodes.find(n => n.id === e.target)
    if (sourceNode && targetNode) {
      chartEdges.push({
        source: e.source,
        target: e.target,
        lineStyle: { color: categoryColors[e.category] || '#c0c4cc' }
      })
    }
  })

  // 构建ECharts categories
  const echartsCategories = categories.map(cat => ({
    name: cat,
    itemStyle: { color: categoryColors[cat] }
  }))

  // 节点分类索引映射
  const categoryIndexMap = {}
  categories.forEach((cat, i) => {
    categoryIndexMap[cat] = i
  })

  const option = {
    title: {
      text: '知识库知识图谱',
      subtext: `共 ${data.nodes.length} 个节点 · ${data.edges.length} 条关系`,
      left: 'center',
      textStyle: { fontSize: 18 }
    },
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'node') {
          const nodeData = data.nodes.find(n => n.label === params.name)
          if (nodeData) {
            return `<div style="max-width:300px">
              <strong>${params.name}</strong><br/>
              <span style="color:#8cccd6">${params.data.category || ''}</span><br/>
              <div style="margin-top:4px;color:#99c7d1;font-size:12px">${nodeData.text || ''}</div>
            </div>`
          }
        } else if (params.dataType === 'edge') {
          return `<strong>${params.data.source}</strong> → <strong>${params.data.target}</strong><br/><span style="color:#8cccd6">${params.data.category || ''}</span>`
        }
        return params.name
      }
    },
    legend: {
      data: categories,
      bottom: 0,
      left: 'center',
      type: 'scroll'
    },
    series: [{
      type: 'graph',
      layout: 'force',
      data: chartNodes.map(n => ({
        id: n.id,
        name: n.name,
        symbolSize: Math.max(30, Math.min(60, 50 - n.name.length)),
        category: categoryIndexMap[n.category] ?? 0,
        itemStyle: {
          color: categoryColors[n.category] || '#909399'
        },
        label: { show: true, fontSize: 11 }
      })),
      categories: echartsCategories,
      edges: chartEdges,
      force: {
        repulsion: 300,
        edgeLength: [60, 150],
        gravity: 0.05,
        friction: 0.1
      },
      roam: true,
      draggable: true,
      lineStyle: {
        color: 'source',
        width: 1,
        curveness: 0.2,
        opacity: 0.6
      },
      label: { show: true, position: 'right', fontSize: 11 },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 2 }
      }
    }]
  }

  if (graphChart) {
    graphChart.dispose()
  }
  graphChart = echarts.init(graphCanvasRef.value)
  graphChart.setOption(option)

  graphChart.on('click', (params) => {
    if (params.dataType === 'node') {
      const nodeData = data.nodes.find(n => n.label === params.name)
      if (nodeData) {
        ElMessage.info(`知识节点：${params.name} - ${nodeData.text || ''}`)
      }
    }
  })
}
</script>

<style scoped>
.page-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--primary);
  display: inline-block;
  letter-spacing: 0.5px;
}

/* 统计卡片 */
.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 12px;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: var(--primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 操作栏 */
.action-row {
  margin-bottom: 16px;
}

/* 筛选栏 */
.filter-bar {
  margin-bottom: 16px;
}

.filter-bar .el-card__body {
  padding: 16px 18px;
}

/* 标签单元格 */
.tags-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* 分页 */
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* 文件上传 */
.upload-tip {
  padding: 12px 16px;
  background: rgba(0, 136, 153, 0.06);
  border-radius: 6px;
  margin-bottom: 16px;
  border: 1px solid rgba(0, 136, 153, 0.1);
}

.upload-tip p {
  margin: 4px 0;
  font-size: 13px;
  color: var(--text-body);
}

.upload-area {
  display: flex;
  justify-content: center;
}

.upload-content {
  text-align: center;
  padding: 20px;
}

.upload-icon {
  font-size: 48px;
  color: var(--primary-dark);
}

.upload-hint {
  font-size: 12px;
  color: var(--text-muted);
}

/* 知识图谱 */
.graph-container {
  width: 100%;
  height: 500px;
}

.graph-canvas {
  width: 100%;
  height: 100%;
}
</style>