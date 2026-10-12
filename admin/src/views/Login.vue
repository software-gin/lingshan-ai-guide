<template>
  <div class="login-container">
    <div class="login-bg-decoration"></div>
    <div class="login-card">
      <div class="login-header">
        <div class="logo-icon">🪷</div>
        <h1 class="title">灵山胜境</h1>
        <p class="subtitle">AI数字人导游系统 · 管理后台</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="0"
        size="large"
        @submit.prevent="doLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="管理员账号"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="管理员密码"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%;">
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <!-- <div class="login-footer">
        <span>默认账号：admin / admin123</span>
      </div> -->
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adminLogin } from '@/utils/api'
import { useAdminStore } from '@/store'

const router = useRouter()
const adminStore = useAdminStore()

const formRef = ref(null)
const loading = ref(false)
const form = reactive({
  username: '',
  password: ''
})
const rules = {
  username: [{ required: true, message: '请输入管理员账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function doLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const res = await adminLogin({
      username: form.username,
      password: form.password
    })
    if (res.code === 200) {
      adminStore.login(res.data)
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } else {
      ElMessage.error(res.message || '登录失败')
    }
  } catch (e) {
    ElMessage.error('网络错误，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: radial-gradient(ellipse at center, #0f1a2e 0%, #0a101f 50%, #060c16 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-decoration {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 30% 40%, rgba(0, 229, 204, 0.04) 0%, transparent 50%),
              radial-gradient(circle at 70% 60%, rgba(0, 168, 204, 0.03) 0%, transparent 50%);
  pointer-events: none;
}

.login-card {
  width: 420px;
  padding: 44px 40px 36px;
  background: linear-gradient(135deg, rgba(16, 34, 56, 0.95) 0%, rgba(13, 26, 43, 0.95) 100%);
  border: 1px solid rgba(0, 136, 153, 0.4);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4), 0 0 60px rgba(0, 229, 204, 0.05);
  backdrop-filter: blur(20px);
  position: relative;
  z-index: 1;
}

.login-card::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, #00e5cc, transparent);
  border-radius: 16px 16px 0 0;
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.logo-icon {
  font-size: 48px;
  margin-bottom: 12px;
  filter: drop-shadow(0 0 20px rgba(0, 229, 204, 0.3));
}

.title {
  font-size: 26px;
  font-weight: 700;
  color: #e6f7ff;
  margin-bottom: 8px;
  letter-spacing: 2px;
}

.subtitle {
  font-size: 13px;
  color: #66a0ad;
  letter-spacing: 1px;
}

:deep(.el-input__wrapper) {
  background: #ffffff !important;
  border: 1px solid #d9d9d9 !important;
  box-shadow: none !important;
  border-radius: 8px !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

:deep(.el-input__wrapper:hover) {
  border-color: #b3b3b3 !important;
}

:deep(.el-input__wrapper.is-focus) {
  border-color: #00e5cc !important;
  box-shadow: 0 0 0 2px rgba(0, 229, 204, 0.15) !important;
}

:deep(.el-input__inner) {
  color: #333333 !important;
}

:deep(.el-input__inner::placeholder) {
  color: #bfbfbf !important;
}

:deep(.el-input__prefix-inner),
:deep(.el-input__prefix-inner .el-icon),
:deep(.el-input__prefix-inner svg),
:deep(.el-input__prefix-inner path) {
  color: #333333 !important;
  fill: #333333 !important;
}

:deep(.el-input__suffix-inner),
:deep(.el-input__suffix-inner .el-icon),
:deep(.el-input__suffix-inner svg),
:deep(.el-input__suffix-inner path) {
  color: #333333 !important;
  fill: #333333 !important;
}

:deep(.el-input__suffix-inner .el-input__icon) {
  color: #333333 !important;
}

.login-footer {
  text-align: center;
  margin-top: 20px;
  font-size: 12px;
  color: rgba(102, 160, 173, 0.6);
}
</style>