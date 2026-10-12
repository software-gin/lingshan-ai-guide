/**
 * LiveTalking WebRTC 客户端
 *
 * 与 LiveTalking 3D 数字人引擎建立 WebRTC 连接，
 * 接收视频/音频轨，并获取 sessionid 用于后续 API 调用。
 */
const ICE_SERVERS = {
  iceServers: [{ urls: [import.meta.env.VITE_STUN_SERVER || 'stun:stun.l.google.com:19302'] }]
}

export const RTCState = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  ERROR: 'error'
}

/**
 * 连接 LiveTalking
 *
 * @param {object} callbacks
 * @param {function} callbacks.onStateChange - 状态变化 (state)
 * @param {function} callbacks.onStream - 收到媒体流 (stream)
 * @param {function} callbacks.onSessionId - 收到 sessionid (sessionid)
 * @returns {{ close: function }}
 */
export function connectLiveTalking(avatarId, callbacks = {}) {
  const pc = new RTCPeerConnection(ICE_SERVERS)
  let settled = false
  let sessionId = ''

  function setState(state) {
    if (settled && state !== RTCState.DISCONNECTED) return
    if (state === RTCState.CONNECTED || state === RTCState.ERROR) {
      settled = true
    }
    callbacks.onStateChange?.(state)
  }

  pc.onconnectionstatechange = () => {
    console.log('[RTC] ICE 状态:', pc.connectionState)
    if (pc.connectionState === 'connected') setState(RTCState.CONNECTED)
    else if (pc.connectionState === 'failed') setState(RTCState.ERROR)
  }

  pc.ontrack = (evt) => {
    console.log('[RTC] 收到 track:', evt.track.kind)
    callbacks.onStream?.(evt.streams[0])
  }

  async function negotiate() {
    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    await new Promise((resolve) => {
      if (pc.iceGatheringState === 'complete') resolve()
      else pc.addEventListener('icegatheringstatechange',
        () => { if (pc.iceGatheringState === 'complete') resolve() })
    })

    const resp = await fetch('/offer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type,
        avatar: avatarId || ''
      })
    })
    if (!resp.ok) throw new Error(`LiveTalking 返回 HTTP ${resp.status}`)

    const answer = await resp.json()
    // 捕获 sessionid —— 后续 /human /interrupt_talk 都需要
    sessionId = answer.sessionid || ''
    console.log('[RTC] sessionid:', sessionId)
    callbacks.onSessionId?.(sessionId)

    await pc.setRemoteDescription(answer)
    console.log('[RTC] WebRTC 连接建立成功')
  }

  function close() {
    settled = false
    try { pc.close() } catch (_) { /* ignore */ }
  }

  function getSessionId() {
    return sessionId
  }

  setState(RTCState.CONNECTING)
  negotiate().catch((err) => {
    console.error('[RTC] 协商失败:', err.message)
    setState(RTCState.ERROR)
  })

  return { close, getSessionId }
}
