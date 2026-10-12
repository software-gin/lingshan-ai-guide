/**
 * WebSocket 客户端
 * 管理长连接，支持文本/音频/图片的收发
 * 消息类型遵循后端协议定义
 */
import { ref } from 'vue'

// WebSocket消息类型（与后端对应）
export const WS_TYPE = {
  TEXT: 'text',           // 发送文本
  AUDIO: 'audio',         // 发送音频
  IMAGE: 'image',         // 发送图片
  VIDEO: 'video',         // 发送视频
  INTERRUPT: 'interrupt', // 打断
  HEARTBEAT: 'heartbeat', // 心跳

  USER_TEXT: 'user_text',     // 用户语音识别结果
  TEXT_START: 'text_start',   // AI开始生成
  TEXT_CHUNK: 'text_chunk',   // AI文本片段
  TEXT_END: 'text_end',       // AI文本结束
  AUDIO_START: 'audio_start', // 音频开始
  AUDIO_CHUNK: 'audio_chunk', // 音频数据
  AUDIO_END: 'audio_end',     // 音频结束
  EMOTION: 'emotion',         // 情绪标签
  STATUS: 'status',           // 状态消息
  ERROR: 'error',             // 错误消息
  DONE: 'done',               // 完成
  ROUTE: 'route'              // 路线导航信息
}

export class WebSocketClient {
  constructor(url) {
    this.url = url                // WebSocket地址
    this.ws = null                // WebSocket实例
    this.isConnected = ref(false) // 连接状态
    this.isReconnecting = false   // 是否正在重连
    this.reconnectTimer = null    // 重连定时器
    this.heartbeatTimer = null    // 心跳定时器
    this.handlers = {             // 消息处理器
      user_text: [],
      text_start: [],
      text_chunk: [],
      text_end: [],
      audio_chunk: [],
      audio_end: [],
      emotion: [],
      status: [],
      error: [],
      done: [],
      route: []
    }
  }

  /**
   * 建立WebSocket连接
   * @param {Object} initData 初始化数据 {user_id, digital_human_id}
   */
  connect(initData = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return
    }

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this.isConnected.value = true
        this.isReconnecting = false
        console.log('[WebSocket] 连接已建立')

        // 发送初始化消息
        this.send({
          type: 'text',
          data: JSON.stringify({
            user_id: initData.user_id || 0,
            digital_human_id: initData.digital_human_id || 1
          })
        })

        // 启动心跳
        this._startHeartbeat()
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this._handleMessage(message)
        } catch (e) {
          console.warn('[WebSocket] 消息解析失败:', e)
        }
      }

      this.ws.onclose = () => {
        this.isConnected.value = false
        this._stopHeartbeat()
        console.log('[WebSocket] 连接已关闭')
        this._tryReconnect(initData)
      }

      this.ws.onerror = (error) => {
        console.error('[WebSocket] 连接错误:', error)
        this.isConnected.value = false
      }

    } catch (error) {
      console.error('[WebSocket] 创建连接失败:', error)
      this._tryReconnect(initData)
    }
  }

  /**
   * 发送JSON消息
   */
  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('[WebSocket] 连接未就绪，无法发送消息')
    }
  }

  /**
   * 设置 LiveTalking sessionid（用于 /human API 调用）
   */
  setLtSessionId(id) {
    this._ltSessionId = id || ''
  }

  /**
   * 发送文本消息
   */
  sendText(text) {
    this.send({ type: WS_TYPE.TEXT, data: text, lt_sessionid: this._ltSessionId || '' })
  }

  /**
   * 发送音频数据
   */
  sendAudio(audioData) {
    this.send({ type: WS_TYPE.AUDIO, data: audioData })
  }

  /**
   * 发送图片
   * @param {string[]} imageUrls - 图片URL列表（服务器上传后返回的路径，如 /uploads/2026/07/12/xxx.jpg）
   * @param {string} text - 用户文本提问
   * @param {string} filename - 文件名（兼容旧版单图）
   */
  sendImage(imageUrls, text = '', filename = 'image.jpg') {
    if (Array.isArray(imageUrls) && imageUrls.length > 0) {
      // 新格式：多图 URL 列表
      this.send({
        type: WS_TYPE.IMAGE,
        image_urls: imageUrls,
        text,
        lt_sessionid: this._ltSessionId || ''
      })
    } else {
      // 兼容旧格式：单图 base64
      this.send({
        type: WS_TYPE.IMAGE,
        data: imageUrls,
        filename,
        text,
        lt_sessionid: this._ltSessionId || ''
      })
    }
  }

  /**
   * 发送视频
   * @param {string} videoUrl - 视频 URL（服务器上传后返回的路径，如 /uploads/2026/10/11/xxx.mp4）
   * @param {string} text - 用户文本提问
   */
  sendVideo(videoUrl, text = '') {
    this.send({
      type: WS_TYPE.VIDEO,
      video_url: videoUrl,
      text,
      lt_sessionid: this._ltSessionId || ''
    })
  }

  /**
   * 发送打断信号
   */
  sendInterrupt() {
    this.send({ type: WS_TYPE.INTERRUPT, data: '', lt_sessionid: this._ltSessionId || '' })
  }

  /**
   * 注册消息事件处理器
   */
  on(event, handler) {
    if (this.handlers[event]) {
      this.handlers[event].push(handler)
    }
  }

  /**
   * 移除事件处理器
   */
  off(event, handler) {
    if (this.handlers[event]) {
      this.handlers[event] = this.handlers[event].filter(h => h !== handler)
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    this._stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.isConnected.value = false
  }

  // ============ 内部方法 ============

  _handleMessage(message) {
    const { type, data, index, text } = message

    switch (type) {
      case WS_TYPE.USER_TEXT:
        this._emit('user_text', data)
        break
      case WS_TYPE.TEXT_START:
        this._emit('text_start', data)
        break
      case WS_TYPE.TEXT_CHUNK:
        this._emit('text_chunk', { text: data, index })
        break
      case WS_TYPE.TEXT_END:
        this._emit('text_end', data)
        break
      case WS_TYPE.AUDIO_CHUNK:
        this._emit('audio_chunk', {
          audio: data,
          index,
          text,
          lt_synced: message.lt_synced || false
        })
        break
      case WS_TYPE.AUDIO_END:
        this._emit('audio_end', data)
        break
      case WS_TYPE.EMOTION:
        this._emit('emotion', data)
        break
      case WS_TYPE.STATUS:
        this._emit('status', data)
        break
      case WS_TYPE.ERROR:
        this._emit('error', data)
        break
      case WS_TYPE.DONE:
        this._emit('done', data)
        break
      case WS_TYPE.ROUTE:
        this._emit('route', data)
        break
      case WS_TYPE.HEARTBEAT:
        // 心跳响应，不需要处理
        break
      default:
        console.log('[WebSocket] 未知消息类型:', type)
    }
  }

  _emit(event, data) {
    if (this.handlers[event]) {
      this.handlers[event].forEach(handler => handler(data))
    }
  }

  _startHeartbeat() {
    this._stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: WS_TYPE.HEARTBEAT, data: 'ping' })
    }, 25000)
  }

  _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  _tryReconnect(initData) {
    if (this.isReconnecting) return
    this.isReconnecting = true

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }

    this.reconnectTimer = setTimeout(() => {
      console.log('[WebSocket] 正在重连...')
      this.connect(initData)
      this.reconnectTimer = null
    }, 3000)
  }
}

// 单例管理
let _wsClient = null

export function getWsClient() {
  return _wsClient
}

export function createWsClient(url, initData) {
  if (_wsClient) {
    _wsClient.disconnect()
  }
  _wsClient = new WebSocketClient(url)
  _wsClient.connect(initData)
  return _wsClient
}

export function destroyWsClient() {
  if (_wsClient) {
    _wsClient.disconnect()
    _wsClient = null
  }
}