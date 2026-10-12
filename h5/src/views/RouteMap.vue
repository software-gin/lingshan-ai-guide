<template>
  <div class="route-map-page">
    <van-nav-bar title="路线导航" left-arrow @click-left="goBack" />

    <!-- AI 建议 -->
    <div class="route-info-card">
      <div class="info-title">📋 AI 导游建议</div>
      <div class="info-text">{{ routeSummary }}</div>
    </div>

    <!-- 路线概览卡片 -->
    <div class="route-summary-card">
      <div class="viz-title">🗺️ 路线预览</div>
      <div class="route-flow">
        <div class="route-node start">
          <span class="node-dot"></span>
          <span class="node-label">{{ origin }}</span>
        </div>
        <template v-for="(wp, i) in waypoints" :key="i">
          <div class="route-line"></div>
          <div class="route-node waypoint">
            <span class="node-dot small"></span>
            <span class="node-label">{{ wp }}</span>
          </div>
        </template>
        <div class="route-line"></div>
        <div class="route-node end">
          <span class="node-dot"></span>
          <span class="node-label">{{ destination }}</span>
        </div>
      </div>
      <div class="route-meta">
        <span class="meta-tag">{{ mode === 'drive' ? '🚗 驾车' : '🚶 步行' }}</span>
        <span class="meta-tag">{{ waypoints.length }} 个途经点</span>
        <span class="meta-tag">{{ estimateDistance }}km</span>
        <span class="meta-tag">{{ estimateTime }}</span>
        <span class="meta-tag" v-if="userLat">📍 已定位</span>
      </div>
    </div>

    <!-- Canvas 预览 -->
    <!-- <div class="route-viz-card">
      <canvas ref="vizCanvas" class="viz-canvas"></canvas>
    </div> -->

    <!-- Leaflet 交互地图 -->
    <div class="route-map-card">
      <div class="viz-title">📍 交互地图</div>
      <div ref="leafletMap" class="leaflet-map"></div>
      <div class="map-actions">
        <van-button size="small" round plain type="primary" @click="openInMapApp">
          🧭 跳转地图App导航
        </van-button>
        <van-button size="small" round plain @click="locateUser">
          📍 {{ userLat ? '重新定位' : '获取我的位置' }}
        </van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const route = useRoute()
const router = useRouter()
const vizCanvas = ref(null)
const leafletMap = ref(null)
const userLat = ref(null)
const userLng = ref(null)
let mapInstance = null

// ---- 从 history.state 获取完整路线数据（含坐标） ----
const routeState = history.state?.spots ? { spots: history.state.spots } : null

// ---- 景区坐标（硬编码，作为降级方案） ----
const SPOT_COORDS = {
  '南门': [31.4210, 120.1020],
  '南门（入口）': [31.4210, 120.1020],
  '景区入口': [31.4210, 120.1020],
  '佛足坛': [31.4200, 120.1035],
  '九龙灌浴': [31.4190, 120.1050],
  '菩提大道': [31.4185, 120.1040],
  '灵山大佛': [31.4170, 120.1080],
  '祥符禅寺': [31.4180, 120.1065],
  '梵宫': [31.4165, 120.1070],
  '五印坛城': [31.4155, 120.1085],
  '曼飞龙塔': [31.4160, 120.1090],
  '灵山精舍': [31.4150, 120.1075],
  '拈花湾': [31.4100, 120.1150],
  '佛手广场': [31.4195, 120.1045],
  '百子戏弥勒': [31.4188, 120.1055],
  '梵宫广场': [31.4163, 120.1072]
}

const origin = computed(() => route.query.origin || '景区入口')
const destination = computed(() => route.query.destination || '灵山大佛')
const waypoints = computed(() => (route.query.waypoints || '').split(',').filter(Boolean))
const mode = computed(() => route.query.mode || 'walk')

// 估算距离与时间（基于 route-plan 传来的 summary 或默认值）
const estimateDistance = computed(() => {
  // 根据途经点数估算：每个途经点约 0.3-0.5km
  const totalPoints = 2 + waypoints.value.length
  const base = totalPoints * 0.4
  return base.toFixed(1)
})

const estimateTime = computed(() => {
  const totalPoints = 2 + waypoints.value.length
  const minutes = totalPoints * 15 + waypoints.value.length * 10
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (hours > 0) return `${hours}小时${mins}分钟`
  return `${minutes}分钟`
})

const routeSummary = computed(() => {
  // 优先使用 history.state 传递的描述信息
  const summary = history.state?.summary || ''
  const tips = history.state?.tips || ''
  const routeName = history.state?.routeName || ''
  const duration = history.state?.duration || ''

  if (summary) {
    let text = summary
    if (duration) text += `（${duration}）`
    return text
  }

  const base = `从${origin.value}出发，前往${destination.value}`
  if (waypoints.value.length) {
    return `${base}，途经 ${waypoints.value.join(' → ')}。建议按此顺序游览，沿途可欣赏核心景点。`
  }
  return `${base}。路线简洁直接，${mode.value === 'drive' ? '可乘坐景区观光车' : '适合步行游览'}。`
})

// ---- 解析地点坐标（优先使用数据库坐标，降级到硬编码） ----
function getCoords(name) {
  // 1. 优先使用 history.state 传递的数据库坐标
  if (routeState?.spots) {
    const matched = routeState.spots.find(s => s.name === name)
    if (matched && matched.latitude != null && matched.longitude != null) {
      return [matched.latitude, matched.longitude]
    }
  }

  // 2. 降级：精确匹配硬编码坐标
  const exact = SPOT_COORDS[name]
  if (exact) return exact

  // 3. 再次降级：从 routeState 做模糊匹配
  if (routeState?.spots) {
    const fuzzy = routeState.spots.find(s => name.includes(s.name) || s.name.includes(name))
    if (fuzzy && fuzzy.latitude != null && fuzzy.longitude != null) {
      return [fuzzy.latitude, fuzzy.longitude]
    }
  }

  // 4. 模糊匹配硬编码坐标
  const key = Object.keys(SPOT_COORDS).find(k => name.includes(k) || k.includes(name))
  if (key) return SPOT_COORDS[key]

  // 5. 兜底
  console.warn(`[RouteMap] 未找到坐标: ${name}，使用默认值`)
  return [31.417, 120.108]
}

// ---- Canvas 预览 ----
function drawRouteViz() {
  const canvas = vizCanvas.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const w = canvas.parentElement.clientWidth - 32
  const h = 160
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  ctx.fillStyle = '#f0f5ee'
  ctx.beginPath()
  ctx.moveTo(12, 0); ctx.lineTo(w - 12, 0)
  ctx.quadraticCurveTo(w, 0, w, 12)
  ctx.lineTo(w, h - 12); ctx.quadraticCurveTo(w, h, w - 12, h)
  ctx.lineTo(12, h); ctx.quadraticCurveTo(0, h, 0, h - 12)
  ctx.lineTo(0, 12); ctx.quadraticCurveTo(0, 0, 12, 0)
  ctx.fill()

  const pts = waypoints.value.length
  const totalPoints = 2 + pts
  const pad = 44
  const usableW = w - pad * 2
  const y = h / 2
  const step = totalPoints > 1 ? usableW / (totalPoints - 1) : 0

  // 连线
  ctx.beginPath()
  ctx.setLineDash([6, 3])
  ctx.strokeStyle = '#5b8c5a'
  ctx.lineWidth = 2.5
  if (totalPoints > 1) {
    ctx.moveTo(pad, y)
    for (let i = 1; i < totalPoints; i++) ctx.lineTo(pad + i * step, y)
  }
  ctx.stroke()
  ctx.setLineDash([])

  function node(x, yPos, r, color, label) {
    ctx.beginPath(); ctx.arc(x, yPos, r, 0, Math.PI * 2)
    ctx.fillStyle = color; ctx.fill()
    ctx.fillStyle = '#2d3a2d'; ctx.font = '11px sans-serif'
    ctx.textAlign = 'center'; ctx.fillText(label, x, yPos + r + 14)
  }

  node(pad, y, 9, '#5b8c5a', origin.value)
  for (let i = 0; i < pts; i++) {
    node(pad + (i + 1) * step, y, 6, '#e67e22', waypoints.value[i])
  }
  if (totalPoints > 1) {
    node(pad + (totalPoints - 1) * step, y, 9, '#e74c3c', destination.value)
  }
}

// ---- Leaflet 交互地图 ----
function initMap() {
  if (!leafletMap.value || mapInstance) return

  mapInstance = L.map(leafletMap.value, {
    attributionControl: false,
    zoomControl: true
  }).setView([31.419, 120.105], 15)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
  }).addTo(mapInstance)

  drawMapRoute()
  setTimeout(() => mapInstance.invalidateSize(), 200)
}

function drawMapRoute() {
  if (!mapInstance) return

  // 清除旧标记
  mapInstance.eachLayer(l => { if (l instanceof L.Marker || l instanceof L.Polyline) mapInstance.removeLayer(l) })

  const allNames = [origin.value, ...waypoints.value, destination.value]
  const coords = allNames.map(getCoords)

  // 画线
  L.polyline(coords, { color: '#5b8c5a', weight: 4, dashArray: '8 4' }).addTo(mapInstance)

  // 标记
  const icons = {
    start: L.divIcon({ html: '<div style="background:#5b8c5a;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:12px">起</div>', iconSize: [24, 24] }),
    waypoint: L.divIcon({ html: '<div style="background:#e67e22;color:#fff;border-radius:50%;width:18px;height:18px;text-align:center;line-height:18px;font-size:10px">·</div>', iconSize: [18, 18] }),
    end: L.divIcon({ html: '<div style="background:#e74c3c;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:12px">终</div>', iconSize: [24, 24] })
  }

  L.marker(coords[0], { icon: icons.start }).addTo(mapInstance).bindPopup(origin.value)
  for (let i = 1; i < coords.length - 1; i++) {
    L.marker(coords[i], { icon: icons.waypoint }).addTo(mapInstance).bindPopup(allNames[i])
  }
  if (coords.length > 1) {
    L.marker(coords[coords.length - 1], { icon: icons.end }).addTo(mapInstance).bindPopup(destination.value)
  }

  // 适配视野
  mapInstance.fitBounds(coords, { padding: [30, 30] })

  // 用户位置
  if (userLat.value && userLng.value) {
    const userIcon = L.divIcon({ html: '<div style="background:#2196f3;border:2px solid #fff;border-radius:50%;width:16px;height:16px"></div>', iconSize: [16, 16] })
    L.marker([userLat.value, userLng.value], { icon: userIcon }).addTo(mapInstance).bindPopup('我的位置')
  }
}

// ---- 定位 ----
function locateUser() {
  if (!navigator.geolocation) {
    alert('当前浏览器不支持定位')
    return
  }
  navigator.geolocation.getCurrentPosition(
    pos => {
      userLat.value = pos.coords.latitude
      userLng.value = pos.coords.longitude
      drawMapRoute()
    },
    () => alert('获取位置失败，请允许定位权限'),
    { enableHighAccuracy: true, timeout: 10000 }
  )
}

// ---- 跳转地图 App ----
function openInMapApp() {
  const dest = getCoords(destination.value)
  const url = `https://uri.amap.com/navigation?to=${dest[1]},${dest[0]},${encodeURIComponent(destination.value)}&mode=${mode.value === 'drive' ? 'car' : 'walk'}&coordinate=gaode`
  window.open(url, '_blank')
}

function goBack() {
  window.history.length > 1 ? router.back() : router.push('/home')
}

onMounted(async () => {
  await nextTick()
  drawRouteViz()
  // 地图延迟初始化，确保 DOM 就绪
  setTimeout(initMap, 300)
})
</script>

<style scoped>
.route-map-page {
  min-height: 100vh;
  background: #f4f6f4;
  padding-bottom: 20px;
}
.route-summary-card {
  margin: 12px 16px;
  background: #fff;
  border-radius: 14px;
  padding: 20px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.route-flow {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.route-node {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 3px 0;
}
.route-node.start .node-label { font-weight: 700; color: #2d3a2d; font-size: 16px; }
.route-node.end .node-label { font-weight: 700; color: #2d3a2d; font-size: 16px; }
.node-dot {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #5b8c5a;
  flex-shrink: 0;
}
.node-dot.small { width: 10px; height: 10px; background: #e67e22; }
.node-label { font-size: 14px; color: #4b5b4b; }
.route-line {
  width: 2px; height: 18px;
  background: #d4e4d4;
  margin-left: 6px;
}
.route-meta {
  display: flex; gap: 8px; flex-wrap: wrap;
  margin-top: 14px; padding-top: 12px;
  border-top: 1px solid #eee;
}
.meta-tag {
  background: #edf6ea; color: #5b8c5a;
  padding: 3px 10px; border-radius: 999px;
  font-size: 12px;
}
.route-info-card {
  margin: 10px 16px 12px;
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.info-title { font-size: 14px; font-weight: 700; color: #2d3a2d; margin-bottom: 8px; }
.info-text { font-size: 13px; line-height: 1.7; color: #4b5b4b; }
.route-viz-card {
  margin: 0 16px 12px;
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.viz-title { font-size: 14px; font-weight: 700; color: #2d3a2d; margin-bottom: 12px; border-bottom: 1px solid #eaeaea; padding-bottom: 8px; }
.viz-canvas { width: 100%; display: block; }
.route-map-card {
  margin: 0 16px 12px;
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.leaflet-map {
  width: 100%; height: 320px;
  border-radius: 12px;
  margin-bottom: 10px;
  background: #e8f5e9;
  z-index: 1;
}
.map-actions {
  display: flex; gap: 8px;
  justify-content: center;
}
</style>
