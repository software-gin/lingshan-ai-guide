<template>
  <div class="emotion-report">
    <!-- 头部标题 + 导出按钮 -->
    <div class="report-header">
      <h2 class="page-title">📊 游客感受度报告</h2>
      <el-button
        type="primary"
        :icon="Download"
        :loading="exporting"
        @click="handleExport"
        class="export-btn"
      >
        {{ exporting ? '导出中...' : '导出报告' }}
      </el-button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 错误提示 -->
    <div v-else-if="error" class="error-container">
      <el-alert
        :title="error"
        type="error"
        show-icon
        closable
        @close="loadData"
      />
    </div>

    <!-- 报告内容（导出区域） -->
    <div v-else id="report-content">
      <!-- 统计概览 -->
      <el-row :gutter="16" class="stats-row">
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-label">总对话数</div>
            <div class="stat-value">{{ report.total_chats }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card satisfaction">
            <div class="stat-label">游客满意度</div>
            <div class="stat-value" :style="{ color: satisfactionColor }">{{ report.satisfaction }}%</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-label">正面情感</div>
            <div class="stat-value">{{ positiveEmotionCount }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card">
            <div class="stat-label">负面情感</div>
            <div class="stat-value">{{ negativeEmotionCount }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 游客关注点分析 -->
      <el-row :gutter="16" class="section-row">
        <el-col :span="12">
          <el-card>
            <template #header>
              <div class="section-header">
                <span>🎯 游客关注点分析</span>
              </div>
            </template>
            <p class="analysis-text">{{ report.kw_analysis }}</p>
            <div ref="keywordChartRef" class="chart-container"></div>
          </el-card>
        </el-col>

        <!-- 情感趋势报告 -->
        <el-col :span="12">
          <el-card>
            <template #header>
              <div class="section-header">
                <span>📈 情感趋势报告</span>
              </div>
            </template>
            <p class="analysis-text">{{ report.trend_analysis }}</p>
            <div ref="trendChartRef" class="chart-container"></div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 服务建议 -->
      <el-row :gutter="16" class="section-row">
        <el-col :span="24">
          <el-card>
            <template #header>
              <div class="section-header">
                <span>💡 服务建议</span>
              </div>
            </template>
            <ul class="suggestions-list">
              <li v-for="(sug, i) in report.suggestions" :key="i">
                <el-icon><InfoFilled /></el-icon>
                {{ sug }}
              </li>
            </ul>
          </el-card>
        </el-col>
      </el-row>

      <!-- 情感分布补充说明 -->
      <el-row :gutter="16" class="section-row">
        <el-col :span="24">
          <el-card>
            <template #header>
              <div class="section-header">
                <span>😊 游客情感分布</span>
              </div>
            </template>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-table :data="emotionTableData" stripe>
                  <el-table-column prop="emotion" label="情感类型" width="120" />
                  <el-table-column prop="count" label="次数" />
                  <el-table-column prop="ratio" label="占比" />
                  <el-table-column label="等级">
                    <template #default="scope">
                      <el-tag
                        :type="getEmotionTagType(scope.row.emotion)"
                        size="small"
                      >
                        {{ getEmotionLevel(scope.row.emotion) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </el-col>
              <el-col :span="12">
                <p class="analysis-text">
                  根据情感标签统计，游客在与数字人互动过程中表现出多种情感状态。
                  其中正面情感（微笑、热情、开心）占比最高，说明游客对数字人服务整体满意度较高。
                  负面情感（困惑、不满）主要集中在知识检索不充分或服务响应较慢的场景，
                  建议优化知识库覆盖范围和响应速度。
                </p>
              </el-col>
            </el-row>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { Download, InfoFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getEmotionReport } from '@/utils/api'
import { ElMessage } from 'element-plus'

// 响应式数据
const loading = ref(true)
const error = ref('')
const exporting = ref(false)
const report = ref({
  total_chats: 0,
  satisfaction: 0,
  emotion_stats: {},
  keyword_counts: [],
  emotion_trend: [],
  kw_analysis: '',
  trend_analysis: '',
  suggestions: []
})

// 图表引用
const keywordChartRef = ref(null)
const trendChartRef = ref(null)
let keywordChart = null
let trendChart = null

// 计算属性
const satisfactionColor = computed(() => {
  if (report.value.satisfaction >= 80) return '#67c23a'
  if (report.value.satisfaction >= 60) return '#e6a23c'
  return '#f56c6c'
})

const positiveEmotionCount = computed(() => {
  const pos = report.value.emotion_stats['微笑'] || 0
  const pos2 = report.value.emotion_stats['热情'] || 0
  const pos3 = report.value.emotion_stats['开心'] || 0
  return pos + pos2 + pos3
})

const negativeEmotionCount = computed(() => {
  const neg = report.value.emotion_stats['困惑'] || 0
  const neg2 = report.value.emotion_stats['不满'] || 0
  return neg + neg2
})

const topEmotion = computed(() => {
  if (!report.value.emotion_trend || report.value.emotion_trend.length === 0) return '微笑'
  const latest = report.value.emotion_trend[report.value.emotion_trend.length - 1]
  if (!latest.data) return '微笑'
  return Object.keys(latest.data).reduce((a, b) => latest.data[a] > latest.data[b] ? a : b, '微笑')
})

const emotionTableData = computed(() => {
  const total = Object.values(report.value.emotion_stats).reduce((a, b) => a + b, 0) || 1
  return Object.entries(report.value.emotion_stats).map(([emotion, count]) => ({
    emotion,
    count,
    ratio: `${((count / total) * 100).toFixed(1)}%`
  }))
})

const getEmotionTagType = (emotion) => {
  if (['微笑', '热情', '开心'].includes(emotion)) return 'success'
  if (['平静'].includes(emotion)) return 'info'
  return 'danger'
}

const getEmotionLevel = (emotion) => {
  if (['微笑', '热情', '开心'].includes(emotion)) return '正面'
  if (['平静'].includes(emotion)) return '中性'
  return '负面'
}

// 生命周期
onMounted(async () => {
  await loadData()
  nextTick(() => {
    initCharts()
  })
})

onUnmounted(() => {
  if (keywordChart) keywordChart.dispose()
  if (trendChart) trendChart.dispose()
})

// 数据加载
async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const res = await getEmotionReport()
    if (res.code === 200) {
      report.value = res.data
    } else {
      error.value = res.message || '数据加载失败'
    }
  } catch (e) {
    error.value = '网络请求失败，请稍后重试'
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 初始化图表
function initCharts() {
  // 游客关注点图表（水平柱状图）
  if (keywordChartRef.value) {
    const data = report.value.keyword_counts.slice(0, 10)
    keywordChart = echarts.init(keywordChartRef.value)
    keywordChart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const p = params[0]
          return `${p.name}: ${p.value}次`
        }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'value',
        name: '次数',
        nameLocation: 'middle',
        nameGap: 25
      },
      yAxis: {
        type: 'category',
        data: data.map(d => d.keyword),
        inverse: true
      },
      series: [{
        type: 'bar',
        data: data.map(d => d.count),
        barWidth: '50%',
        itemStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: '#409eff' },
              { offset: 1, color: '#79bbff' }
            ]
          }
        },
        label: {
          show: true,
          position: 'right',
          formatter: '{c}'
        }
      }]
    })
  }

  // 情感趋势图表（折线图）
  if (trendChartRef.value) {
    const dates = report.value.emotion_trend.map(t => t.date)
    const emotions = Object.keys(report.value.emotion_stats)
    const colorMap = {
      '微笑': '#67c23a',
      '热情': '#409eff',
      '开心': '#909399',
      '平静': '#e6a23c',
      '困惑': '#f56c6c',
      '不满': '#909399'
    }

    const seriesData = emotions.map(emotion => ({
      name: emotion,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      data: dates.map(date => {
        const item = report.value.emotion_trend.find(t => t.date === date)
        return item?.data?.[emotion] || 0
      }),
      itemStyle: { color: colorMap[emotion] || '#909399' }
    }))

    trendChart = echarts.init(trendChartRef.value)
    trendChart.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          let tip = `${params[0].axisValue}<br/>`
          params.forEach(p => {
            tip += `${p.marker}${p.seriesName}: ${p.value}次<br/>`
          })
          return tip
        }
      },
      legend: {
        bottom: 0,
        type: 'scroll'
      },
      grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: {
          formatter: (val) => val.slice(5) // 只显示月-日
        }
      },
      yAxis: {
        type: 'value',
        name: '次数'
      },
      series: seriesData
    })
  }
}

// 导出报告
async function handleExport() {
  exporting.value = true
  ElMessage.info('正在生成报告...')

  try {
    // 导入 html2canvas 和 jspdf
    const html2canvas = (await import('html2canvas')).default
    const { jsPDF } = await import('jspdf')

    const element = document.getElementById('report-content')
    if (!element) {
      throw new Error('报告内容未找到')
    }

    // 等待图表渲染完成
    await new Promise(resolve => setTimeout(resolve, 500))

    // 使用 html2canvas 捕获页面
    const canvas = await html2canvas(element, {
      scale: 2,
      useCORS: true,
      backgroundColor: '#ffffff',
      logging: false
    })

    // 创建 PDF
    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF('p', 'mm', 'a4')
    const pageWidth = 210
    const pageHeight = 297
    const imgWidth = pageWidth
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= pageHeight

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
    }

    // 生成文件名
    const date = new Date()
    const dateStr = date.toISOString().split('T')[0]
    const filename = `游客感受度报告_${dateStr}.pdf`

    pdf.save(filename)
    ElMessage.success('报告导出成功！')
  } catch (e) {
    console.error('导出失败:', e)
    ElMessage.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.page-title {
  font-size: 22px;
  margin: 0;
  color: #e6f7ff;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.export-btn {
  font-size: 14px;
}

.loading-container,
.error-container {
  padding: 20px;
}

/* 统计卡片 */
.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  padding: 16px;
}

.stat-label {
  font-size: 13px;
  color: #8cccd6;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #00e5cc;
}

.satisfaction .stat-value {
  font-size: 32px;
}

/* 图表区域 */
.section-row {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
}

.chart-container {
  height: 300px;
  width: 100%;
}

.analysis-text {
  font-size: 14px;
  line-height: 1.8;
  color: #99c7d1;
  margin: 0 0 16px 0;
  text-align: justify;
}

/* 建议列表 */
.suggestions-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.suggestions-list li {
  display: flex;
  align-items: flex-start;
  padding: 10px 16px;
  margin-bottom: 8px;
  background: rgba(0, 136, 153, 0.08);
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.6;
  color: #99c7d1;
  border: 1px solid rgba(0, 136, 153, 0.1);
}

.suggestions-list li .el-icon {
  margin-right: 8px;
  color: #00e5cc;
  flex-shrink: 0;
  margin-top: 2px;
}

/* 响应式设计 */
@media screen and (max-width: 768px) {
  .report-header {
    flex-direction: column;
    gap: 12px;
  }

  .stats-row .el-col {
    margin-bottom: 8px;
  }

  .section-row .el-col {
    margin-bottom: 12px;
  }

  .chart-container {
    height: 250px;
  }
}
</style>