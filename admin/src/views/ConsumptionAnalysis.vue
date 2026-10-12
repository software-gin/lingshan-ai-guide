<template>
  <div class="consumption-wrap">
    <!-- 页面标题 -->
    <div class="page-title">
      <span class="title-icon"></span>
      灵山大佛景区 · 游客消费分析大屏
      <div class="title-actions">
        <el-button
          type="primary"
          :icon="Upload"
          size="small"
          @click="handleUpload"
          class="upload-btn"
        >
          上传数据文件
        </el-button>
        <el-button
          type="default"
          size="small"
          @click="loadAllData"
          class="refresh-btn"
        >
          <el-icon><Refresh /></el-icon> 刷新数据
        </el-button>
        <span class="update-time">最后更新：{{ lastUpdateTime }}</span>
      </div>
    </div>

    <!-- 顶部指标卡片行 -->
    <div class="card-row">
      <div class="stat-card" v-for="stat in stats" :key="stat.label">
        <div class="stat-inner">
          <div class="card-label">{{ stat.label }}</div>
          <div class="card-num">{{ stat.value }}</div>
          <div class="card-desc">{{ stat.desc }}</div>
          <div class="stat-icon">{{ stat.icon }}</div>
          <div class="stat-glow"></div>
        </div>
      </div>
    </div>

    <!-- 第一行：消费结构饼图 + 月度趋势 -->
    <div class="chart-grid">
      <div class="chart-card chart-card-main">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">💰</span> 消费结构占比分析
          </div>
          <span class="chart-subtitle" v-if="overviewData">总消费 ¥{{ formatMoney(overviewData.total_revenue) }}</span>
        </div>
        <div ref="structureChartRef" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">📅</span> 月度消费趋势
          </div>
          <div class="chart-filters">
            <el-select v-model="monthlyMetric" size="small" @change="initMonthlyChart" style="width:100px">
              <el-option label="人均消费" value="avg_total_cost" />
              <el-option label="访客数" value="visitors" />
              <el-option label="总营收" value="total_revenue" />
            </el-select>
          </div>
        </div>
        <div ref="monthlyChartRef" class="chart-box"></div>
      </div>
    </div>

    <!-- 第二行：年龄段消费 + 性别消费对比 -->
    <div class="chart-row-bottom">
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">👥</span> 年龄段消费分析
          </div>
          <div class="chart-filters">
            <el-select v-model="ageMetric" size="small" @change="initAgeChart" style="width:100px">
              <el-option label="人均消费" value="avg_total" />
              <el-option label="访客数量" value="count" />
              <el-option label="满意度" value="avg_satisfaction" />
            </el-select>
          </div>
        </div>
        <div ref="ageChartRef" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">⚖️</span> 性别消费对比
          </div>
        </div>
        <div ref="genderChartRef" class="chart-box"></div>
      </div>
    </div>

    <!-- 第三行：消费×满意度交叉 + 停留时长关系 -->
    <div class="chart-row-bottom" style="margin-top: 16px">
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">📊</span> 消费区间 × 满意度交叉
          </div>
          <span class="cross-alert" v-if="satCostData">
            高消费低满意: <span class="alert-num">{{ satCostData.high_cost_low_sat_count }}</span> 人
          </span>
        </div>
        <div ref="crossChartRef" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">⏱️</span> 停留时长与消费关系
          </div>
        </div>
        <div ref="stayChartRef" class="chart-box"></div>
      </div>
    </div>

    <!-- 第四行：运营分析建议 -->
    <div class="insights-row" style="margin-top: 16px">
      <div class="insights-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">💡</span> 数据洞察与运营建议
          </div>
        </div>
        <div class="insights-content">
          <!-- 数据洞察 -->
          <div class="insight-section" v-if="insightsData?.insights">
            <div class="section-title">
              <span class="section-icon">📌</span> 数据洞察
            </div>
            <div class="insight-list">
              <div v-for="(item, idx) in insightsData.insights" :key="idx" class="insight-item">
                <span class="insight-category">{{ item.category }}</span>
                <span class="insight-text">{{ item.text }}</span>
              </div>
            </div>
          </div>

          <!-- 运营建议 -->
          <div class="recommend-section" v-if="insightsData?.recommendations">
            <div class="section-title">
              <span class="section-icon">🎯</span> 运营建议
            </div>
            <div class="recommend-list">
              <div v-for="(item, idx) in insightsData.recommendations" :key="idx" class="recommend-item" :class="item.priority">
                <span class="priority-tag" :class="item.priority.toLowerCase()">{{ item.priority }}</span>
                <div class="recommend-title">{{ item.title }}</div>
                <div class="recommend-detail">{{ item.detail }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传文件对话框 -->
    <el-dialog v-model="uploadDialogVisible" title="上传消费数据文件" width="500px" class="upload-dialog">
      <el-upload
        ref="uploadRef"
        drag
        :before-upload="beforeUpload"
        :on-success="handleUploadSuccess"
        :on-error="handleUploadError"
        :auto-upload="false"
        :limit="1"
        accept=".csv"
        class="upload-area"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">
          将全量景区游客消费数据CSV文件拖到此处，<br/>或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            仅支持 CSV 格式，系统将自动筛选灵山大佛/灵山胜境/拈花湾等景区数据
          </div>
        </template>
      </el-upload>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="uploadDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmUpload">确认上传</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import { Upload, Refresh } from '@element-plus/icons-vue'
import {
  getConsumptionOverview,
  getConsumptionMonthly,
  getConsumptionAge,
  getConsumptionSatCost,
  getConsumptionGender,
  getConsumptionStay,
  getConsumptionInsights,
  uploadConsumptionCSV
} from '@/utils/api'
import { ElMessage, ElLoading } from 'element-plus'

// ========== 响应式数据 ==========
const monthlyMetric = ref('avg_total_cost')
const ageMetric = ref('avg_total')
const lastUpdateTime = ref('--')
const uploadDialogVisible = ref(false)
const uploadRef = ref(null)

// 图表 DOM 引用
const structureChartRef = ref(null)
const monthlyChartRef = ref(null)
const ageChartRef = ref(null)
const genderChartRef = ref(null)
const crossChartRef = ref(null)
const stayChartRef = ref(null)

// 图表实例
let structureChart = null
let monthlyChart = null
let ageChart = null
let genderChart = null
let crossChart = null
let stayChart = null

// 缓存数据
const overviewData = ref(null)
const monthlyData = ref([])
const ageData = ref([])
const genderData = ref([])
const satCostData = ref(null)
const stayData = ref([])
const insightsData = ref(null)

// 统计卡片
const stats = ref([
  { label: '总游客数', value: '--', desc: '消费数据记录数', icon: '👥' },
  { label: '人均消费', value: '--', desc: '平均每人次总消费', icon: '💰' },
  { label: '总消费额', value: '--', desc: '累计消费总金额', icon: '💳' },
  { label: '餐饮占比', value: '--', desc: '餐饮消费占总消费', icon: '🍜' },
  { label: '购物占比', value: '--', desc: '购物消费占总消费', icon: '🛍️' },
  { label: '平均满意度', value: '--', desc: '游客平均满意度评分', icon: '⭐' },
])

// ========== 格式化 ==========
function formatMoney(val) {
  if (!val || val === 0) return '0'
  if (val >= 10000) return (val / 10000).toFixed(1) + '万'
  return val.toFixed(2)
}

function formatPercent(val) {
  return val ? val.toFixed(1) + '%' : '--'
}

function formatTime() {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

// ========== 数据加载 ==========
async function loadOverview() {
  try {
    const res = await getConsumptionOverview()
    if (res.code === 200 && res.data) {
      overviewData.value = res.data
      updateStats(res.data)
    }
  } catch (e) {
    console.warn('加载消费总览失败:', e)
  }
}

async function loadMonthly() {
  try {
    const res = await getConsumptionMonthly()
    if (res.code === 200) monthlyData.value = res.data
  } catch (e) {
    console.warn('加载月度趋势失败:', e)
  }
}

async function loadAge() {
  try {
    const res = await getConsumptionAge()
    if (res.code === 200) ageData.value = res.data
  } catch (e) {
    console.warn('加载年龄分析失败:', e)
  }
}

async function loadGender() {
  try {
    const res = await getConsumptionGender()
    if (res.code === 200) genderData.value = res.data
  } catch (e) {
    console.warn('加载性别分析失败:', e)
  }
}

async function loadSatCost() {
  try {
    const res = await getConsumptionSatCost()
    if (res.code === 200) satCostData.value = res.data
  } catch (e) {
    console.warn('加载满意度分析失败:', e)
  }
}

async function loadStay() {
  try {
    const res = await getConsumptionStay()
    if (res.code === 200) stayData.value = res.data
  } catch (e) {
    console.warn('加载停留分析失败:', e)
  }
}

async function loadInsights() {
  try {
    const res = await getConsumptionInsights()
    if (res.code === 200) insightsData.value = res.data
  } catch (e) {
    console.warn('加载运营建议失败:', e)
  }
}

async function loadAllData() {
  const loading = ElLoading.service({
    lock: true,
    text: '正在加载消费分析数据...',
    background: 'rgba(12, 20, 34, 0.8)'
  })
  try {
    await Promise.all([
      loadOverview(),
      loadMonthly(),
      loadAge(),
      loadGender(),
      loadSatCost(),
      loadStay(),
      loadInsights()
    ])
    lastUpdateTime.value = formatTime()
    nextTick(() => {
      initAllCharts()
    })
  } finally {
    loading.close()
  }
}

function updateStats(data) {
  if (!data) return
  stats.value = [
    { label: '总游客数', value: data.total_visitors ?? '--', desc: '消费数据记录数', icon: '👥' },
    { label: '人均消费', value: `¥${data.avg_total_cost ?? '--'}`, desc: '平均每人次总消费', icon: '💰' },
    { label: '总消费额', value: `¥${formatMoney(data.total_revenue)}`, desc: '累计消费总金额', icon: '💳' },
    { label: '餐饮占比', value: formatPercent(data.cost_structure?.food?.ratio), desc: '餐饮消费占总消费', icon: '🍜' },
    { label: '购物占比', value: formatPercent(data.cost_structure?.shopping?.ratio), desc: '购物消费占总消费', icon: '🛍️' },
    { label: '平均满意度', value: data.avg_satisfaction != null ? `${data.avg_satisfaction}/5` : '--', desc: '游客平均满意度评分', icon: '⭐' },
  ]
}

// ========== 图表初始化 ==========
function initAllCharts() {
  initStructureChart()
  initMonthlyChart()
  initAgeChart()
  initGenderChart()
  initCrossChart()
  initStayChart()
}

function initStructureChart() {
  if (!structureChartRef.value) return
  if (structureChart) structureChart.dispose()
  structureChart = echarts.init(structureChartRef.value)

  const structure = overviewData.value?.cost_structure || {}
  const categories = [
    { name: '门票', key: 'ticket', color: '#00e5cc' },
    { name: '餐饮', key: 'food', color: '#00a8cc' },
    { name: '购物', key: 'shopping', color: '#f3d19e' },
    { name: '交通', key: 'transport', color: '#79bbff' },
    { name: '娱乐', key: 'entertainment', color: '#ff7c7c' },
  ]

  const pieData = categories.map(c => ({
    name: c.name,
    value: structure[c.key]?.amount || 0,
    ratio: structure[c.key]?.ratio || 0,
    itemStyle: { color: c.color }
  }))

  structureChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        return `${params.name}<br/>金额：¥${formatMoney(params.value)}<br/>占比：📊<span style="color:#00e5cc;font-weight:700">${params.percent}%</span>`
      }
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center',
      textStyle: { color: '#b8e7ee', fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12,
      formatter: (name) => {
        const item = pieData.find(d => d.name === name)
        return item ? `${name} ${item.ratio}%` : name
      }
    },
    series: [{
      type: 'pie',
      radius: ['45%', '72%'],
      center: ['40%', '50%'],
      avoidLabelOverlap: true,
      padAngle: 2,
      itemStyle: {
        borderRadius: 4,
        borderColor: '#0c1422',
        borderWidth: 2
      },
      label: {
        show: true,
        position: 'outside',
        formatter: '{d}%',
        color: '#8cccd6',
        fontSize: 13,
        fontWeight: 600
      },
      labelLine: { lineStyle: { color: '#00889960' } },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 229, 204, 0.3)'
        },
        label: { fontSize: 15, fontWeight: 'bold' }
      },
      data: pieData,
      animationDuration: 1000,
      animationEasing: 'cubicOut'
    }]
  })
}

function initMonthlyChart() {
  if (!monthlyChartRef.value) return
  if (monthlyChart) monthlyChart.dispose()
  monthlyChart = echarts.init(monthlyChartRef.value)

  const data = monthlyData.value || []
  if (data.length === 0) {
    monthlyChart.setOption({
      backgroundColor: 'transparent',
      graphic: [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: '暂无数据', fill: '#66a0ad', fontSize: 14 }
      }]
    })
    return
  }

  const metricKey = monthlyMetric.value
  const xData = data.map(d => d.month.replace('2025-', ''))
  const yData = data.map(d => {
    const val = d[metricKey] || 0
    return metricKey === 'total_revenue' ? (val / 10000).toFixed(1) : val
  })

  const axisLabel = metricKey === 'total_revenue' ? '万元' : (metricKey === 'visitors' ? '人次' : '元')

  monthlyChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff', fontSize: 12 },
      formatter: (params) => {
        const p = params[0]
        const month = data[p.dataIndex]?.month || ''
        const fullData = data[p.dataIndex] || {}
        return `<div style="font-weight:600;margin-bottom:4px">${month}月</div>
          <div>人均消费：¥${fullData.avg_total_cost}</div>
          <div>访客数：${fullData.visitors}</div>
          <div>总营收：¥${formatMoney(fullData.total_revenue)}</div>
          <div>满意度：${fullData.avg_satisfaction}/5</div>`
      }
    },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { lineStyle: { color: '#00889960' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: axisLabel,
      nameTextStyle: { color: '#66a0ad', fontSize: 11 },
      splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    series: [{
      name: metricKey,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      showSymbol: true,
      data: yData,
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0, 229, 204, 0.35)' },
          { offset: 1, color: 'rgba(0, 229, 204, 0)' }
        ])
      },
      lineStyle: { color: '#00e5cc', width: 2.5 },
      itemStyle: { color: '#00e5cc', borderColor: '#0c1422', borderWidth: 2 },
      animationDuration: 800,
      animationEasing: 'cubicOut'
    }]
  })
}

function initAgeChart() {
  if (!ageChartRef.value) return
  if (ageChart) ageChart.dispose()
  ageChart = echarts.init(ageChartRef.value)

  const data = ageData.value || []
  if (data.length === 0) {
    ageChart.setOption({
      backgroundColor: 'transparent',
      graphic: [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: '暂无数据', fill: '#66a0ad', fontSize: 14 }
      }]
    })
    return
  }

  const metricKey = ageMetric.value
  const xData = data.map(d => d.age_group)
  const yData = data.map(d => d[metricKey])

  const unitMap = { count: '人次', avg_total: '元', avg_satisfaction: '分' }
  const axisLabel = unitMap[metricKey] || '元'

  ageChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        const p = params[0]
        const idx = xData.indexOf(p.name)
        const d = data[idx]
        return `<div style="font-weight:600;margin-bottom:4px">${p.name}</div>
          <div>访客数：${d.count}</div>
          <div>人均消费：¥${d.avg_total}</div>
          <div>满意度：${d.avg_satisfaction}/5</div>`
      }
    },
    grid: { left: 50, right: 30, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { lineStyle: { color: '#00889960' } },
      axisLabel: { color: '#8cccd6', fontSize: 11, rotate: 15 },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: axisLabel,
      nameTextStyle: { color: '#66a0ad', fontSize: 11 },
      splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    series: [{
      type: 'bar',
      data: yData.map((v, i) => ({
        value: v,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#00e5cc' },
            { offset: 1, color: '#008899' }
          ]),
          borderRadius: [4, 4, 0, 0]
        }
      })),
      barWidth: 32,
      animationDuration: 800,
      animationEasing: 'cubicOut'
    }]
  })
}

function initGenderChart() {
  if (!genderChartRef.value) return
  if (genderChart) genderChart.dispose()
  genderChart = echarts.init(genderChartRef.value)

  const data = genderData.value || []
  if (data.length === 0) {
    genderChart.setOption({
      backgroundColor: 'transparent',
      graphic: [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: '暂无数据', fill: '#66a0ad', fontSize: 14 }
      }]
    })
    return
  }

  const genders = data.map(d => d.gender)
  const costItems = ['avg_ticket', 'avg_food', 'avg_shopping', 'avg_transport', 'avg_entertainment']
  const costNames = ['门票', '餐饮', '购物', '交通', '娱乐']
  const colors = ['#00e5cc', '#00a8cc', '#f3d19e', '#79bbff', '#ff7c7c']

  const seriesData = costItems.map((item, idx) => ({
    name: costNames[idx],
    type: 'bar',
    stack: 'total',
    data: data.map(d => d[item]),
    itemStyle: { color: colors[idx] },
    emphasis: { focus: 'series' }
  }))

  genderChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        const idx = genders.indexOf(params[0].name)
        const d = data[idx]
        let html = `<div style="font-weight:600;margin-bottom:4px">${d.gender}（${d.count}人）</div>`
        params.forEach(p => {
          html += `<div>${p.marker}${p.seriesName}：¥${p.value}</div>`
        })
        html += `<div style="margin-top:4px;font-weight:600">合计：¥${d.avg_total}</div>`
        return html
      }
    },
    legend: {
      bottom: 5,
      textStyle: { color: '#b8e7ee', fontSize: 11 },
      itemWidth: 12,
      itemHeight: 8
    },
    grid: { left: 40, right: 20, top: 20, bottom: 45 },
    xAxis: {
      type: 'category',
      data: genders,
      axisLine: { lineStyle: { color: '#00889960' } },
      axisLabel: { color: '#8cccd6', fontSize: 13 },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: '元',
      nameTextStyle: { color: '#66a0ad', fontSize: 11 },
      splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    series: seriesData,
    animationDuration: 800,
    animationEasing: 'cubicOut'
  })
}

function initCrossChart() {
  if (!crossChartRef.value) return
  if (crossChart) crossChart.dispose()
  crossChart = echarts.init(crossChartRef.value)

  const crossData = satCostData.value?.cross_analysis || []
  if (crossData.length === 0) {
    crossChart.setOption({
      backgroundColor: 'transparent',
      graphic: [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: '暂无数据', fill: '#66a0ad', fontSize: 14 }
      }]
    })
    return
  }

  // 使用堆叠柱状图展示各消费区间的满意度分布
  const brackets = crossData.map(d => d.bracket)
  const satisfactionLevels = [1, 2, 3, 4, 5]
  const satColors = ['#f56c6c', '#e6a23c', '#66a0ad', '#00a8cc', '#00e5cc']

  const seriesData = satisfactionLevels.map((level, idx) => ({
    name: level === 5 ? '非常满意' : level === 4 ? '满意' : level === 3 ? '一般' : level === 2 ? '不满意' : '非常不满意',
    type: 'bar',
    stack: 'total',
    data: crossData.map(d => d.satisfaction_dist?.[level] || 0),
    itemStyle: { color: satColors[idx] },
    emphasis: { focus: 'series' }
  }))

  crossChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        const idx = brackets.indexOf(params[0].name)
        const d = crossData[idx]
        let html = `<div style="font-weight:600;margin-bottom:4px">${d.bracket}</div>`
        params.forEach(p => {
          html += `<div>${p.marker}${p.seriesName}：${p.value}人</div>`
        })
        html += `<div style="margin-top:4px;font-weight:600">合计：${d.total_count}人 | 满意度：${d.avg_satisfaction}/5</div>`
        return html
      }
    },
    legend: {
      bottom: 0,
      textStyle: { color: '#b8e7ee', fontSize: 10 },
      itemWidth: 12,
      itemHeight: 8
    },
    grid: { left: 40, right: 20, top: 20, bottom: 50 },
    xAxis: {
      type: 'category',
      data: brackets,
      axisLine: { lineStyle: { color: '#00889960' } },
      axisLabel: { color: '#8cccd6', fontSize: 10, rotate: 20 },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: '人数',
      nameTextStyle: { color: '#66a0ad', fontSize: 11 },
      splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    series: seriesData,
    animationDuration: 800,
    animationEasing: 'cubicOut'
  })
}

function initStayChart() {
  if (!stayChartRef.value) return
  if (stayChart) stayChart.dispose()
  stayChart = echarts.init(stayChartRef.value)

  const data = stayData.value || []
  if (data.length === 0) {
    stayChart.setOption({
      backgroundColor: 'transparent',
      graphic: [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: '暂无数据', fill: '#66a0ad', fontSize: 14 }
      }]
    })
    return
  }

  const xData = data.map(d => d.stay_group)
  const costData = data.map(d => d.avg_total_cost)
  const satData = data.map(d => d.avg_satisfaction)

  stayChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff', fontSize: 12 },
      formatter: (params) => {
        const idx = xData.indexOf(params[0].axisValue)
        const d = data[idx]
        return `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>
          <div>人数：${d.count}</div>
          <div>人均消费：¥${d.avg_total_cost}</div>
          <div>满意度：${d.avg_satisfaction}/5</div>`
      }
    },
    legend: {
      bottom: 0,
      textStyle: { color: '#b8e7ee', fontSize: 11 },
      itemWidth: 16,
      itemHeight: 8
    },
    grid: { left: 50, right: 60, top: 30, bottom: 45 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { lineStyle: { color: '#00889960' } },
      axisLabel: { color: '#8cccd6', fontSize: 11, rotate: 15 },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        name: '人均消费(元)',
        nameTextStyle: { color: '#00e5cc', fontSize: 11 },
        splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
        axisLabel: { color: '#8cccd6', fontSize: 11 },
        axisLine: { show: false },
        axisTick: { show: false }
      },
      {
        type: 'value',
        name: '满意度(分)',
        nameTextStyle: { color: '#79bbff', fontSize: 11 },
        splitLine: { show: false },
        axisLabel: { color: '#8cccd6', fontSize: 11 },
        axisLine: { show: false },
        axisTick: { show: false },
        max: 5
      }
    ],
    series: [
      {
        name: '人均消费',
        type: 'bar',
        data: costData,
        barWidth: 36,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#00e5cc' },
            { offset: 1, color: '#008899' }
          ]),
          borderRadius: [4, 4, 0, 0]
        },
        animationDuration: 800,
        animationEasing: 'cubicOut'
      },
      {
        name: '满意度',
        type: 'line',
        yAxisIndex: 1,
        data: satData,
        smooth: true,
        symbol: 'circle',
        symbolSize: 10,
        lineStyle: { color: '#79bbff', width: 2.5 },
        itemStyle: { color: '#79bbff', borderColor: '#0c1422', borderWidth: 2 },
        animationDuration: 800,
        animationEasing: 'cubicOut'
      }
    ]
  })
}

// ========== 刷新 ==========
function refreshChart() {
  nextTick(() => {
    initAllCharts()
  })
}

// ========== 窗口自适应 ==========
function handleResize() {
  structureChart?.resize()
  monthlyChart?.resize()
  ageChart?.resize()
  genderChart?.resize()
  crossChart?.resize()
  stayChart?.resize()
}

// ========== 文件上传 ==========
function handleUpload() {
  uploadDialogVisible.value = true
}

function beforeUpload(file) {
  const isCSV = file.name.toLowerCase().endsWith('.csv')
  if (!isCSV) {
    ElMessage.error('仅支持 CSV 格式文件')
    return false
  }
  return true
}

function confirmUpload() {
  const files = uploadRef.value?.getFiles()
  if (!files || files.length === 0) {
    ElMessage.warning('请先选择文件')
    return
  }

  const file = files[0].raw
  const formData = new FormData()
  formData.append('file', file)

  const loading = ElLoading.service({
    lock: true,
    text: '正在解析数据并筛选灵山景区数据...',
    background: 'rgba(12, 20, 34, 0.8)'
  })

  uploadConsumptionCSV(formData).then(res => {
    if (res.code === 200) {
      ElMessage.success(res.message || '数据上传成功，正在刷新...')
      uploadDialogVisible.value = false
      loadAllData()
    } else {
      ElMessage.error(res.message || '上传失败')
    }
  }).catch(err => {
    ElMessage.error('上传失败：' + (err.message || '未知错误'))
  }).finally(() => {
    loading.close()
  })
}

function handleUploadSuccess(response) {
  // 使用手动上传，这里不需要
}

function handleUploadError() {
  ElMessage.error('文件上传失败，请重试')
}

// ========== 生命周期 ==========
onMounted(() => {
  loadAllData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  ;[structureChart, monthlyChart, ageChart, genderChart, crossChart, stayChart].forEach(c => c?.dispose())
})
</script>

<style scoped>
/* ========== 全局容器 ========== */
.consumption-wrap {
  padding: 20px;
  width: 100%;
  min-height: 100vh;
  background: radial-gradient(ellipse at top, #0f1a2e 0%, #0a101f 50%, #060c16 100%);
  position: relative;
  overflow: hidden;
}

.consumption-wrap::before {
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 20% 30%, rgba(0, 229, 204, 0.03) 0%, transparent 50%),
              radial-gradient(circle at 80% 70%, rgba(0, 168, 204, 0.02) 0%, transparent 50%);
  pointer-events: none;
  z-index: 0;
}

/* ========== 页面标题 ========== */
.page-title {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 24px;
  color: #ffffff;
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
  z-index: 1;
  letter-spacing: 1px;
}

.title-icon {
  width: 4px;
  height: 22px;
  background: linear-gradient(180deg, #00e5cc, #008899);
  border-radius: 2px;
  display: inline-block;
}

.title-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.update-time {
  font-size: 12px;
  color: #66a0ad;
  font-weight: 400;
}

.upload-btn {
  background: linear-gradient(135deg, #00e5cc, #00a8cc) !important;
  border: none !important;
  color: #0c1422 !important;
  font-weight: 600;
}

.upload-btn:hover {
  box-shadow: 0 2px 12px rgba(0, 229, 204, 0.4) !important;
}

.refresh-btn {
  color: #8cccd6 !important;
  border: 1px solid rgba(0, 136, 153, 0.4) !important;
}

.refresh-btn:hover {
  color: #00e5cc !important;
  border-color: #00e5cc !important;
}

/* ========== 顶部指标卡片行 ========== */
.card-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 20px;
  position: relative;
  z-index: 1;
}

.stat-card {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  animation: fadeInUp 0.6s ease both;
}

.stat-card:nth-child(1) { animation-delay: 0.05s; }
.stat-card:nth-child(2) { animation-delay: 0.1s; }
.stat-card:nth-child(3) { animation-delay: 0.15s; }
.stat-card:nth-child(4) { animation-delay: 0.2s; }
.stat-card:nth-child(5) { animation-delay: 0.25s; }
.stat-card:nth-child(6) { animation-delay: 0.3s; }

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(0, 229, 204, 0.15);
}

.stat-inner {
  background: linear-gradient(135deg, rgba(16, 34, 56, 0.9) 0%, rgba(13, 26, 43, 0.9) 100%);
  border: 1px solid rgba(0, 136, 153, 0.5);
  border-radius: 12px;
  padding: 20px 16px;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(10px);
}

.stat-inner::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background: linear-gradient(90deg, transparent, #00e5cc, transparent);
}

.stat-glow {
  position: absolute;
  top: -50%;
  right: -50%;
  width: 100%;
  height: 100%;
  background: radial-gradient(circle, rgba(0, 229, 204, 0.05), transparent 70%);
  pointer-events: none;
}

.card-label {
  font-size: 13px;
  color: #8cccd6;
  margin-bottom: 8px;
  position: relative;
  z-index: 1;
}

.card-num {
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  position: relative;
  z-index: 1;
  text-shadow: 0 0 20px rgba(0, 229, 204, 0.2);
}

.card-desc {
  font-size: 11px;
  color: #66a0ad;
  margin-top: 6px;
  position: relative;
  z-index: 1;
}

.stat-icon {
  position: absolute;
  right: 14px;
  bottom: 10px;
  font-size: 42px;
  opacity: 0.12;
  z-index: 1;
}

/* ========== 图表区域 ========== */
.chart-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
  position: relative;
  z-index: 1;
}

.chart-row-bottom {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.chart-card {
  background: linear-gradient(135deg, rgba(16, 34, 56, 0.9) 0%, rgba(13, 26, 43, 0.9) 100%);
  border: 1px solid rgba(0, 136, 153, 0.4);
  border-radius: 12px;
  padding: 18px;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(8px);
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
  animation: fadeInUp 0.6s ease both;
}

.chart-card:nth-child(1) { animation-delay: 0.35s; }
.chart-card:nth-child(2) { animation-delay: 0.4s; }

.chart-card:hover {
  border-color: rgba(0, 229, 204, 0.6);
  box-shadow: 0 4px 24px rgba(0, 229, 204, 0.08);
}

.chart-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 229, 204, 0.3), transparent);
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: #e6f7ff;
  display: flex;
  align-items: center;
  gap: 8px;
}

.chart-icon {
  font-size: 16px;
}

.chart-subtitle {
  font-size: 12px;
  color: #00e5cc;
  font-weight: 500;
}

.chart-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chart-box {
  width: 100%;
  height: 310px;
}

.chart-card-main .chart-box {
  height: 330px;
}

.cross-alert {
  font-size: 12px;
  color: #ff7c7c;
  font-weight: 500;
  background: rgba(255, 124, 124, 0.1);
  padding: 3px 10px;
  border-radius: 10px;
}

.alert-num {
  color: #f56c6c;
  font-weight: 700;
  font-size: 14px;
}

/* ========== 运营建议区域 ========== */
.insights-card {
  background: linear-gradient(135deg, rgba(16, 34, 56, 0.9) 0%, rgba(13, 26, 43, 0.9) 100%);
  border: 1px solid rgba(0, 136, 153, 0.4);
  border-radius: 12px;
  padding: 18px 24px;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(8px);
  animation: fadeInUp 0.6s ease 0.5s both;
}

.insights-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 229, 204, 0.3), transparent);
}

.insights-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  min-height: 250px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #e6f7ff;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 15px;
}

.insight-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.insight-item {
  background: rgba(15, 39, 56, 0.6);
  border-radius: 8px;
  padding: 10px 14px;
  border-left: 3px solid #00e5cc;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.insight-category {
  font-size: 11px;
  color: #00e5cc;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.insight-text {
  font-size: 12px;
  color: #99c7d1;
  line-height: 1.6;
}

.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.recommend-item {
  background: rgba(15, 39, 56, 0.6);
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  border-left: 3px solid #00e5cc;
}

.recommend-item.high {
  border-left-color: #f56c6c;
  background: rgba(245, 108, 108, 0.05);
}

.recommend-item.medium {
  border-left-color: #e6a23c;
  background: rgba(230, 162, 60, 0.05);
}

.recommend-item.low {
  border-left-color: #66a0ad;
}

.priority-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
  align-self: flex-start;
  letter-spacing: 0.5px;
}

.priority-tag.high {
  background: rgba(245, 108, 108, 0.2);
  color: #f56c6c;
}

.priority-tag.medium {
  background: rgba(230, 162, 60, 0.2);
  color: #e6a23c;
}

.priority-tag.low {
  background: rgba(102, 160, 173, 0.2);
  color: #66a0ad;
}

.recommend-title {
  font-size: 13px;
  font-weight: 600;
  color: #e6f7ff;
}

.recommend-detail {
  font-size: 12px;
  color: #99c7d1;
  line-height: 1.6;
}

/* ========== 上传对话框 ========== */
.upload-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
}

.upload-area :deep(.el-upload-dragger) {
  border: 2px dashed rgba(0, 136, 153, 0.4);
  border-radius: 12px;
  background: rgba(15, 39, 56, 0.4);
  padding: 40px 20px;
}

.upload-area :deep(.el-upload-dragger:hover) {
  border-color: #00e5cc;
}

.upload-area :deep(.el-icon--upload) {
  font-size: 48px;
  color: #00e5cc;
  margin-bottom: 16px;
}

.upload-area :deep(.el-upload__text) {
  color: #8cccd6;
  font-size: 14px;
  line-height: 1.8;
}

.upload-area :deep(.el-upload__text em) {
  color: #00e5cc;
  font-style: normal;
  font-weight: 600;
}

.upload-area :deep(.el-upload__tip) {
  color: #66a0ad;
  font-size: 12px;
  margin-top: 12px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* ========== 响应式设计 ========== */
@media (max-width: 1400px) {
  .card-row {
    grid-template-columns: repeat(3, 1fr);
  }
  .insights-content {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}

@media (max-width: 1024px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .chart-row-bottom {
    grid-template-columns: 1fr;
  }
  .card-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .page-title {
    font-size: 18px;
    flex-wrap: wrap;
  }
  .title-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .card-row {
    grid-template-columns: 1fr;
  }
  .consumption-wrap {
    padding: 12px;
  }
  .card-num {
    font-size: 24px;
  }
  .chart-box {
    height: 260px;
  }
  .stat-inner {
    padding: 14px;
  }
  .insights-content {
    grid-template-columns: 1fr;
  }
}
</style>
