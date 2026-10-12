<template>
  <div class="dashboard-wrap">
    <!-- 页面标题 -->
    <div class="page-title">
      <span class="title-icon"></span>
      灵山胜境数字人导游 · 运营数据大屏
      <div class="title-actions">
        <el-button text @click="goConsumption" class="consumption-link-btn">
          <el-icon><Money /></el-icon> 消费分析
        </el-button>
        <span class="update-time">最后更新：{{ lastUpdateTime }}</span>
        <el-tag :type="isLive ? 'success' : 'danger'" size="small" effect="dark" class="live-tag">
          <span class="dot"></span>
          {{ isLive ? '实时' : '已断开' }}
        </el-tag>
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

    <!-- 第一行图表：7日趋势 + 实时消息 -->
    <div class="chart-grid">
      <div class="chart-card chart-card-main">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">📈</span> 近7日游客对话趋势
          </div>
          <div class="chart-filters">
            <custom-select v-model="trendFilter" size="small" placeholder="筛选周期" :options="trendOptions" @change="refreshChart" />
          </div>
        </div>
        <div ref="trendChartRef" class="chart-box" id="trendChart"></div>
      </div>
      <div class="msg-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">🔔</span> 实时游客咨询提醒
          </div>
          <el-badge :value="msgList.length" :hidden="msgList.length === 0" class="msg-badge">
            <span class="badge-text">新消息</span>
          </el-badge>
        </div>
        <div class="msg-list" ref="msgListRef">
          <div class="msg-item" v-for="(item, idx) in msgList" :key="idx">
            <div class="msg-user">
              <div class="msg-avatar" :style="{ background: getAvatarColor(item.name) }">
                {{ item.name.slice(0, 1) }}
              </div>
              <span class="msg-name">{{ item.name }}</span>
              <span class="msg-time">{{ item.time }}</span>
            </div>
            <div class="msg-content" :class="{ self: item.isSelf }">{{ item.content }}</div>
          </div>
          <div v-if="msgList.length === 0" class="msg-empty">
            <el-empty description="暂无实时消息" :image-size="60" />
          </div>
        </div>
      </div>
    </div>

    <!-- 第二行：热门问题 / 情绪分布 -->
    <div class="chart-row-bottom">
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">🔥</span> 热门咨询问题 TOP10
          </div>
        </div>
        <div ref="hotQChartRef" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">😊</span> 游客交互情绪分布
          </div>
        </div>
        <div ref="moodChartRef" class="chart-box"></div>
      </div>
    </div>

    <!-- 第三行：游览偏好 + 语音交互成功率 -->
    <div class="chart-row-bottom" style="margin-top: 16px">
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">🗺️</span> 游客游览偏好分析
          </div>
        </div>
        <div ref="likeChartRef" class="chart-box"></div>
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">🎤</span> 语音交互成功率
          </div>
        </div>
        <div ref="voiceChartRef" class="chart-box"></div>
      </div>
    </div>

    <!-- 第四行：消费结构概览（代表性消费分析图表） -->
    <div class="chart-row-bottom" style="margin-top: 16px">
      <div class="chart-card consumption-card">
        <div class="chart-header">
          <div class="chart-title">
            <span class="chart-icon">💰</span> 游客消费结构概览
          </div>
          <div class="chart-subtitle" v-if="consumptionOverview">
            人均 ¥{{ consumptionOverview.avg_total_cost }} · 总消费 ¥{{ formatMoney(consumptionOverview.total_revenue) }}
          </div>
        </div>
        <div class="consumption-body">
          <div ref="consumptionChartRef" class="consumption-chart-box"></div>
          <div class="consumption-stats">
            <div class="consumption-stat-item" v-for="item in consumptionStats" :key="item.key">
              <div class="consumption-stat-label">{{ item.label }}</div>
              <div class="consumption-stat-value" :style="{ color: item.color }">¥{{ item.value }}</div>
              <div class="consumption-stat-bar">
                <div class="consumption-stat-fill" :style="{ width: item.ratio + '%', background: item.color }"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="consumption-link-bar">
          <el-button type="primary" @click="goConsumption" class="consumption-link-btn" :icon="ArrowRight">
            进入消费分析大屏
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboardStats, getDashboardPref, getChatLogs, getConsumptionOverview } from '@/utils/api'
import { ElMessage } from 'element-plus'

// 路由
const router = useRouter()

// ========== 响应式数据 ==========
const trendFilter = ref('week')
const trendOptions = [
  { label: '近7天', value: 'week' },
  { label: '近30天', value: 'month' },
]
const lastUpdateTime = ref('--')
const isLive = ref(false)
const msgList = ref([])
const msgListRef = ref(null)
const trendChartRef = ref(null)
const hotQChartRef = ref(null)
const moodChartRef = ref(null)
const likeChartRef = ref(null)
const voiceChartRef = ref(null)
const consumptionChartRef = ref(null)

// 消费分析数据
const consumptionOverview = ref(null)
const consumptionStats = ref([])

// 统计卡片数据
const stats = ref([
  { label: '总对话次数', value: '--', desc: '累计游客交互记录', icon: '💬' },
  { label: '总注册游客', value: '--', desc: '平台注册游客总量', icon: '👥' },
  { label: '今日接待人次', value: '--', desc: '当日新增对话交互', icon: '📝' },
  { label: '知识库条目', value: '--', desc: '向量文档块+FAQ总量', icon: '📚' },
  { label: '数字人形象', value: '--', desc: '可切换导游模型数量', icon: '🪷' },
  { label: '游客满意度', value: '--', desc: '历史交互好评占比', icon: '⭐' },
])

let trendChart = null
let hotQChart = null
let moodChart = null
let likeChart = null
let voiceChart = null
let consumptionChart = null
let refreshTimer = null
let msgTimer = null

// 缓存的原始数据
let cachedDailyData = []
let cachedEmotionData = []
let cachedHotQuestions = []

// ========== 头像颜色 ==========
const avatarColors = ['#00e5cc', '#00a8cc', '#66a0ad', '#ff7c7c', '#f3d19e', '#79bbff']
let colorIndex = 0
const colorMap = new Map()

function getAvatarColor(name) {
  if (!colorMap.has(name)) {
    colorMap.set(name, avatarColors[colorIndex % avatarColors.length])
    colorIndex++
  }
  return colorMap.get(name)
}

function goConsumption() {
  router.push('/consumption')
}

// ========== 格式化时间 ==========
function formatTime() {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

function formatMoney(val) {
  if (!val || val === 0) return '0'
  if (val >= 10000) return (val / 10000).toFixed(1) + '万'
  return val.toFixed(0)
}

function formatDate(d) {
  const date = new Date(d)
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return weekdays[date.getDay()]
}

// ========== 消费数据加载 ==========
async function loadConsumptionData() {
  try {
    const res = await getConsumptionOverview()
    if (res.code === 200 && res.data) {
      consumptionOverview.value = res.data
      const structure = res.data.cost_structure || {}
      consumptionStats.value = [
        { key: 'ticket', label: '门票', value: structure.ticket?.amount || 0, ratio: structure.ticket?.ratio || 0, color: '#00e5cc' },
        { key: 'food', label: '餐饮', value: structure.food?.amount || 0, ratio: structure.food?.ratio || 0, color: '#00a8cc' },
        { key: 'shopping', label: '购物', value: structure.shopping?.amount || 0, ratio: structure.shopping?.ratio || 0, color: '#f3d19e' },
        { key: 'transport', label: '交通', value: structure.transport?.amount || 0, ratio: structure.transport?.ratio || 0, color: '#79bbff' },
        { key: 'entertainment', label: '娱乐', value: structure.entertainment?.amount || 0, ratio: structure.entertainment?.ratio || 0, color: '#ff7c7c' },
      ]
      nextTick(() => {
        initConsumptionChart()
      })
    }
  } catch (e) {
    console.warn('加载消费数据失败:', e)
  }
}

// ========== 数据加载 ==========
async function loadDashboardData() {
  try {
    const [statsRes, prefRes] = await Promise.all([
      getDashboardStats(),
      getDashboardPref()
    ])

    if (statsRes.code === 200) {
      const data = statsRes.data
      stats.value = [
        { label: '总对话次数', value: data.total_chats ?? '--', desc: '累计游客交互记录', icon: '💬' },
        { label: '总注册游客', value: data.total_users ?? '--', desc: '平台注册游客总量', icon: '👥' },
        { label: '今日接待人次', value: data.today_chats ?? '--', desc: '当日新增对话交互', icon: '📝' },
        { label: '知识库条目', value: data.total_knowledge ?? '--', desc: '向量文档块+FAQ总量', icon: '📚' },
        { label: '数字人形象', value: data.total_digital_humans ?? '--', desc: '可切换导游模型数量', icon: '🪷' },
        { label: '游客满意度', value: data.satisfaction != null ? `${data.satisfaction}%` : '--', desc: '历史交互好评占比', icon: '⭐' },
      ]

      // 缓存每日对话数据
      if (data.daily_chats && data.daily_chats.length > 0) {
        cachedDailyData = data.daily_chats
      }

      // 缓存热门问题
      if (data.hot_questions && data.hot_questions.length > 0) {
        cachedHotQuestions = data.hot_questions
      }

      // 缓存情绪数据
      if (data.emotion_stats) {
        cachedEmotionData = Object.entries(data.emotion_stats).map(([k, v]) => ({
          name: k,
          value: v
        }))
      }
    }

    if (prefRes.code === 200) {
      const prefData = prefRes.data
      // 偏好数据存储在缓存中供图表使用
      window.__prefData = prefData
    }

    lastUpdateTime.value = formatTime()
    isLive.value = true
  } catch (e) {
    console.warn('数据加载失败:', e)
    isLive.value = false
  }
}

// ========== 加载实时消息 ==========
async function loadRecentMessages() {
  try {
    const res = await getChatLogs({ page: 1, per_page: 5 })
    if (res.code === 200) {
      const logs = res.data?.items || []
      msgList.value = logs.map(log => {
        const time = log.question_time
        const timeStr = time ? time.split(' ')[1]?.slice(0, 5) || time : '--'
        return {
          name: log.username || log.nickname || '游客',
          time: timeStr,
          content: log.question_text || log.content || '--',
          isSelf: log.is_self || false
        }
      })
    }
  } catch (e) {
    // silent
  }
}

// ========== 图表初始化 ==========
function initCharts() {
  initTrendChart()
  initHotQChart()
  initMoodChart()
  initLikeChart()
  initVoiceChart()
}

function initTrendChart() {
  if (!trendChartRef.value) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value)

  let xData = []
  let yData = []

  if (cachedDailyData.length > 0) {
    xData = cachedDailyData.map(d => {
      const date = new Date(d.date)
      return `${date.getMonth() + 1}/${date.getDate()}`
    })
    yData = cachedDailyData.map(d => d.count)
  } else {
    xData = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    yData = [0, 0, 0, 0, 0, 0, 0]
  }

  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff', fontSize: 12 },
      formatter: (params) => {
        const p = params[0]
        return `<div style="font-weight:600;margin-bottom:4px">${p.axisValue}</div><div>对话次数：<span style="color:#00e5cc;font-size:16px;font-weight:700">${p.value}</span> 次</div>`
      }
    },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
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
      splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    series: [{
      name: '当日对话量',
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      showSymbol: true,
      data: yData,
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0, 229, 204, 0.4)' },
          { offset: 0.5, color: 'rgba(0, 229, 204, 0.15)' },
          { offset: 1, color: 'rgba(0, 229, 204, 0)' }
        ])
      },
      lineStyle: { color: '#00e5cc', width: 2.5 },
      itemStyle: {
        color: '#00e5cc',
        borderColor: '#0c1422',
        borderWidth: 2
      },
      markLine: {
        silent: true,
        label: { show: false },
        data: [{
          type: 'average',
          lineStyle: { color: '#66a0ad60', type: 'dashed', width: 1 }
        }]
      }
    }],
    animationDuration: 1000,
    animationEasing: 'cubicOut'
  })
  trendChart.on('click', () => {})
}

function initHotQChart() {
  if (!hotQChartRef.value) return
  if (hotQChart) hotQChart.dispose()
  hotQChart = echarts.init(hotQChartRef.value)

  const labels = []
  const values = []

  if (cachedHotQuestions.length > 0) {
    cachedHotQuestions.forEach(q => {
      labels.push(q.question?.length > 8 ? q.question.slice(0, 8) + '..' : q.question)
      values.push(q.count)
    })
  } else {
    labels.push('暂无数据')
    values.push(0)
  }

  hotQChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        const p = params[0]
        const idx = labels.indexOf(p.name)
        const fullQ = cachedHotQuestions[idx]?.question || p.name
        return `<div>${fullQ}</div><div>咨询次数：<span style="color:#00e5cc;font-weight:700">${p.value}</span> 次</div>`
      }
    },
    grid: { left: 90, right: 30, top: 15, bottom: 30 },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#00889920', type: 'dashed' } },
      axisLabel: { color: '#8cccd6', fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: '#00889960' } },
      axisLabel: { color: '#b8e7ee', fontSize: 12, fontWeight: 500 },
      axisTick: { show: false }
    },
    series: [{
      type: 'bar',
      data: values.map((v, i) => ({
        value: v,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
            { offset: 0, color: '#008899' },
            { offset: 0.5, color: '#00a8cc' },
            { offset: 1, color: '#00e5cc' }
          ]),
          borderRadius: [0, 6, 6, 0]
        }
      })),
      barWidth: 24,
      barGap: 0.4,
      animationDuration: 800,
      animationEasing: 'cubicOut'
    }]
  })
}

function initMoodChart() {
  if (!moodChartRef.value) return
  if (moodChart) moodChart.dispose()
  moodChart = echarts.init(moodChartRef.value)

  const moodData = cachedEmotionData.length > 0
    ? cachedEmotionData
    : [
        { name: '热情满意', value: 0 },
        { name: '普通中性', value: 0 },
        { name: '疑问不满', value: 0 }
      ]

  const moodColors = {
    '热情满意': '#00e5cc',
    '微笑': '#00e5cc',
    '开心': '#79bbff',
    '普通中性': '#66a0ad',
    '平静': '#66a0ad',
    '疑问不满': '#ff7c7c',
    '困惑': '#e6a23c',
    '不满': '#f56c6c'
  }

  moodChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        return `${params.name}<br/>次数：<span style="color:#00e5cc;font-weight:700">${params.value}</span> 次<br/>占比：<span style="color:#00e5cc;font-weight:700">${params.percent}%</span>`
      }
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center',
      textStyle: { color: '#b8e7ee', fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12
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
      labelLine: {
        lineStyle: { color: '#00889960' }
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 229, 204, 0.3)'
        },
        label: { fontSize: 15, fontWeight: 'bold' }
      },
      data: moodData.map(d => ({
        ...d,
        itemStyle: { color: moodColors[d.name] || '#66a0ad' }
      })),
      animationDuration: 1000,
      animationEasing: 'cubicOut'
    }]
  })
}

function initLikeChart() {
  if (!likeChartRef.value) return
  if (likeChart) likeChart.dispose()
  likeChart = echarts.init(likeChartRef.value)

  const prefData = window.__prefData
  let chartData = [
    { name: '亲子家庭', value: 0 },
    { name: '祈福观光', value: 0 },
    { name: '研学采风', value: 0 }
  ]
  const colors = ['#00e5cc', '#00a8cc', '#66a0ad']

  if (prefData?.digital_humans && prefData.digital_humans.length > 0) {
    chartData = prefData.digital_humans.map((d, i) => ({
      name: d.name || `数字人${i + 1}`,
      value: d.count || 0,
      itemStyle: { color: colors[i % colors.length] }
    }))
  }

  likeChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff' },
      formatter: (params) => {
        return `${params.name}<br/>使用次数：<span style="color:#00e5cc;font-weight:700">${params.value}</span> 次<br/>占比：<span style="color:#00e5cc;font-weight:700">${params.percent}%</span>`
      }
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center',
      textStyle: { color: '#b8e7ee', fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12
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
      labelLine: {
        lineStyle: { color: '#00889960' }
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 229, 204, 0.3)'
        },
        label: { fontSize: 15, fontWeight: 'bold' }
      },
      data: chartData.map((d, i) => ({
        ...d,
        itemStyle: d.itemStyle || { color: colors[i % colors.length] }
      })),
      animationDuration: 1000,
      animationEasing: 'cubicOut'
    }]
  })
}

function initVoiceChart() {
  if (!voiceChartRef.value) return
  if (voiceChart) voiceChart.dispose()
  voiceChart = echarts.init(voiceChartRef.value)

  const voiceSuccessRate = 94.2  // 默认值

  voiceChart.setOption({
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge',
      radius: '85%',
      center: ['50%', '55%'],
      startAngle: 220,
      endAngle: -40,
      progress: {
        show: true,
        width: 14,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: '#008899' },
              { offset: 0.5, color: '#00a8cc' },
              { offset: 1, color: '#00e5cc' }
            ]
          }
        }
      },
      axisLine: {
        lineStyle: {
          width: 14,
          color: [[1, 'rgba(0, 136, 153, 0.2)']]
        }
      },
      axisTick: {
        show: false
      },
      splitLine: {
        length: 10,
        lineStyle: {
          width: 2,
          color: '#00e5cc60'
        }
      },
      axisLabel: {
        distance: 20,
        color: '#8cccd6',
        fontSize: 11,
        formatter: (v) => v + '%'
      },
      pointer: {
        width: 4,
        length: '65%',
        itemStyle: { color: '#00e5cc' }
      },
      detail: {
        valueAnimation: true,
        formatter: (v) => `${v.toFixed(1)}%`,
        color: '#00e5cc',
        fontSize: 32,
        fontWeight: 700,
        offsetCenter: [0, '40%']
      },
      title: {
        offsetCenter: [0, '75%'],
        fontSize: 13,
        color: '#8cccd6'
      },
      data: [{ value: voiceSuccessRate, name: '语音交互成功率' }],
      animationDuration: 1500,
      animationEasing: 'cubicOut'
    }]
  })
}

// ========== 消费结构图表初始化 ==========
function initConsumptionChart() {
  if (!consumptionChartRef.value) return
  if (consumptionChart) consumptionChart.dispose()
  consumptionChart = echarts.init(consumptionChartRef.value)

  const stats = consumptionStats.value || []
  if (stats.length === 0) return

  const pieData = stats.map(s => ({
    name: s.label,
    value: s.value || 0,
    itemStyle: { color: s.color }
  }))

  consumptionChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 39, 56, 0.9)',
      borderColor: '#00889960',
      textStyle: { color: '#e6f7ff', fontSize: 12 },
      formatter: (params) => {
        const s = stats.find(x => x.label === params.name)
        return `<div style="font-weight:600;margin-bottom:2px">${params.name}</div>
          金额：¥${formatMoney(params.value)}<br/>
          占比：📊<span style="color:#00e5cc;font-weight:700">${params.percent}%</span>`
      }
    },
    series: [{
      type: 'pie',
      radius: ['52%', '78%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      padAngle: 2,
      itemStyle: {
        borderRadius: 4,
        borderColor: '#0c1422',
        borderWidth: 2
      },
      label: {
        show: true,
        formatter: '{b}\n{d}%',
        color: '#8cccd6',
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 14
      },
      labelLine: {
        length: 8,
        length2: 8,
        lineStyle: { color: '#00889960' }
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 229, 204, 0.3)'
        }
      },
      data: pieData,
      animationDuration: 800,
      animationEasing: 'cubicOut'
    }]
  })
}

// ========== 刷新图表 ==========
function refreshChart() {
  nextTick(() => {
    initCharts()
  })
}

// ========== 自动刷新 ==========
function startAutoRefresh() {
  // 每30秒刷新数据
  refreshTimer = setInterval(async () => {
    await loadDashboardData()
    nextTick(() => {
      initCharts()
    })
  }, 30000)

  // 每10秒刷新消息
  msgTimer = setInterval(() => {
    loadRecentMessages()
  }, 10000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (msgTimer) {
    clearInterval(msgTimer)
    msgTimer = null
  }
}

// ========== 窗口自适应 ==========
function handleResize() {
  trendChart?.resize()
  hotQChart?.resize()
  moodChart?.resize()
  likeChart?.resize()
  voiceChart?.resize()
  consumptionChart?.resize()
}

// ========== 生命周期 ==========
onMounted(async () => {
  // 加载模拟消息
  msgList.value = [
    { name: '游客张先生', time: '14:23', content: '灵山大佛门票多少钱？', isSelf: false },
    { name: '数字人导游', time: '14:23', content: '灵山胜境成人门票210元，线上购票优惠195元', isSelf: true },
    { name: '李女士', time: '14:25', content: '景区内有素食餐厅吗？', isSelf: false },
    { name: '数字人导游', time: '14:25', content: '景区梵宫、灵山精舍均提供素斋餐饮', isSelf: true },
    { name: '王同学', time: '14:28', content: '带老人游览路线推荐一下', isSelf: false },
  ]

  await loadDashboardData()
  loadRecentMessages()
  loadConsumptionData()

  nextTick(() => {
    initCharts()
  })

  startAutoRefresh()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  stopAutoRefresh()
  window.removeEventListener('resize', handleResize)
  ;[trendChart, hotQChart, moodChart, likeChart, voiceChart, consumptionChart].forEach(c => c?.dispose())
})
</script>

<style scoped>
/* ========== 全局容器 ========== */
.dashboard-wrap {
  padding: 20px;
  width: 100%;
  min-height: 100vh;
  background: radial-gradient(ellipse at top, #0f1a2e 0%, #0a101f 50%, #060c16 100%);
  position: relative;
  overflow: hidden;
}

/* 背景装饰 */
.dashboard-wrap::before {
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
  gap: 12px;
}

.update-time {
  font-size: 12px;
  color: #66a0ad;
  font-weight: 400;
}

.live-tag {
  font-size: 11px;
  padding: 0 10px;
  height: 24px;
  line-height: 24px;
}

.dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  margin-right: 4px;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
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
  font-size: 30px;
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

/* ========== 图表区域网格布局 ========== */
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

/* ========== 实时消息栏 ========== */
.msg-card {
  background: linear-gradient(135deg, rgba(16, 34, 56, 0.9) 0%, rgba(13, 26, 43, 0.9) 100%);
  border: 1px solid rgba(0, 136, 153, 0.4);
  border-radius: 12px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(8px);
  animation: fadeInUp 0.6s ease 0.35s both;
}

.msg-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 229, 204, 0.3), transparent);
}

.msg-badge {
  margin-right: 4px;
}

.badge-text {
  font-size: 11px;
  color: #66a0ad;
}

.msg-list {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.msg-list::-webkit-scrollbar {
  width: 3px;
}

.msg-list::-webkit-scrollbar-thumb {
  background: rgba(0, 136, 153, 0.3);
  border-radius: 2px;
}

.msg-item {
  padding: 10px 8px;
  border-bottom: 1px solid rgba(15, 39, 56, 0.8);
  margin-bottom: 8px;
  transition: background 0.2s ease;
  border-radius: 6px;
}

.msg-item:hover {
  background: rgba(0, 136, 153, 0.08);
}

.msg-user {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.msg-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #008899;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0c1422;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.msg-name {
  font-size: 12px;
  color: #b8e7ee;
  font-weight: 500;
}

.msg-time {
  font-size: 11px;
  color: #66a0ad;
  margin-left: auto;
}

.msg-content {
  font-size: 13px;
  color: #99c7d1;
  padding: 8px 10px;
  background: rgba(15, 39, 56, 0.6);
  border-radius: 8px;
  margin-top: 4px;
  line-height: 1.5;
  border-left: 2px solid rgba(0, 136, 153, 0.3);
}

.msg-content.self {
  background: rgba(0, 119, 112, 0.25);
  border-left-color: #00e5cc;
  text-align: right;
}

.msg-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  min-height: 200px;
}

:deep(.el-empty__description p) {
  color: #66a0ad;
}

/* ========== 响应式设计 ========== */
@media (max-width: 1400px) {
  .card-row {
    grid-template-columns: repeat(3, 1fr);
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
}

@media (max-width: 640px) {
  .card-row {
    grid-template-columns: 1fr;
  }
  .dashboard-wrap {
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
  .consumption-chart-box {
    height: 200px !important;
  }
  .consumption-stats {
    display: none;
  }
}

/* ========== 消费结构概览卡片 ========== */
.chart-subtitle {
  font-size: 12px;
  color: #00e5cc;
  font-weight: 500;
}

.consumption-card {
  animation-delay: 0.45s;
}

.consumption-body {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 0;
}

.consumption-chart-box {
  width: 240px;
  height: 240px;
  flex-shrink: 0;
}

.consumption-stats {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 200px;
}

.consumption-stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.consumption-stat-label {
  font-size: 12px;
  color: #8cccd6;
  font-weight: 500;
}

.consumption-stat-value {
  font-size: 16px;
  font-weight: 700;
  text-shadow: 0 0 12px rgba(0, 229, 204, 0.2);
}

.consumption-stat-bar {
  width: 100%;
  height: 4px;
  background: rgba(0, 136, 153, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.consumption-stat-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 1s ease;
  box-shadow: 0 0 8px rgba(0, 229, 204, 0.4);
}

.consumption-link-bar {
  margin-top: 12px;
  text-align: center;
}

.consumption-link-btn {
  background: linear-gradient(135deg, #00e5cc, #00a8cc) !important;
  border: none !important;
  color: #0c1422 !important;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 24px;
  border-radius: 20px;
  transition: all 0.3s ease;
}

.consumption-link-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 229, 204, 0.4) !important;
}

.title-actions .consumption-link-btn {
  color: #00e5cc !important;
  background: transparent !important;
  border: 1px solid rgba(0, 229, 204, 0.3) !important;
  font-weight: 500;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
}

.title-actions .consumption-link-btn:hover {
  color: #ffffff !important;
  background: rgba(0, 229, 204, 0.15) !important;
  border-color: #00e5cc !important;
  transform: none;
  box-shadow: none;
}
</style>