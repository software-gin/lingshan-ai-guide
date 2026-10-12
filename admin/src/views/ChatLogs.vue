<template>
  <div class="chat-logs">
    <h2 class="page-title">💬 对话日志管理</h2>

    <!-- 搜索筛选 -->
    <el-card class="search-card">
      <div class="search-form">
        <el-input v-model="keyword" placeholder="搜索问题/回答内容" clearable style="width: 250px;" />
        <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" style="width: 280px;" />
        <el-button type="primary" @click="search">搜索</el-button>
        <el-button @click="reset">重置</el-button>
        <el-button type="success" @click="handleExport">📥 导出Excel</el-button>
      </div>
    </el-card>

    <!-- 日志列表 -->
    <el-card>
      <el-table :data="logs" stripe v-loading="loading" style="width: 100%" max-height="600">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="user_id" label="用户ID" width="70" />
        <el-table-column prop="question_text" label="提问内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="answer_text" label="AI回答" min-width="300" show-overflow-tooltip />
        <el-table-column prop="emotion_label" label="情绪" width="70" />
        <el-table-column prop="digital_human_id" label="数字人ID" width="80" />
        <el-table-column prop="question_time" label="提问时间" width="170" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="viewDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="perPage"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchLogs"
          @size-change="fetchLogs"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="对话详情" width="600px">
      <div class="detail-content">
        <div class="detail-item">
          <label>用户提问：</label>
          <p>{{ detail.question_text }}</p>
          <!-- 用户上传的图片 -->
          <div v-if="detail.image_urls && detail.image_urls.length > 0" class="detail-images">
            <img
              v-for="(url, idx) in detail.image_urls"
              :key="idx"
              :src="url"
              :alt="`图片 ${idx + 1}`"
              class="detail-image"
              @click="previewImage(url)"
            />
          </div>
        </div>
        <div class="detail-item">
          <label>AI回答：</label>
          <p>{{ detail.answer_text }}</p>
        </div>
        <div class="detail-meta">
          <span>情绪：{{ detail.emotion_label }}</span>
          <span>数字人ID：{{ detail.digital_human_id }}</span>
          <span>音色：{{ detail.tts_voice }}</span>
          <span>时间：{{ detail.question_time }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getChatLogs } from '@/utils/api'

const logs = ref([])
const loading = ref(false)
const keyword = ref('')
const dateRange = ref([])
const page = ref(1)
const perPage = ref(20)
const total = ref(0)

const detailVisible = ref(false)
const detail = ref({})

onMounted(() => fetchLogs())

async function fetchLogs() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: perPage.value,
      keyword: keyword.value
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const res = await getChatLogs(params)
    if (res.code === 200) {
      logs.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function search() { page.value = 1; fetchLogs() }
function reset() {
  keyword.value = ''
  dateRange.value = []
  page.value = 1
  fetchLogs()
}

function viewDetail(row) {
  detail.value = row
  detailVisible.value = true
}

function previewImage(url) {
  // 在对话框中查看大图
  const win = window.open('', '_blank', 'width=800,height=600')
  win.document.write(`<img src="${url}" style="max-width:100%;max-height:100vh;"/>`)
}

function handleExport() {
  // 构建带筛选参数的导出URL
  let url = `/api/admin/chat-logs/export?keyword=${keyword.value}`
  if (dateRange.value && dateRange.value.length === 2) {
    url += `&date_from=${dateRange.value[0]}&date_to=${dateRange.value[1]}`
  }
  window.open(url, '_blank')
  ElMessage.success('开始导出Excel文件')
}
</script>

<style scoped>
</style>