<template>
  <div class="login-page">
    <div class="login-header">
      <div class="logo-icon">🪷</div>
      <h1 class="title">灵山胜境</h1>
      <p class="subtitle">AI数字人导游系统</p>
    </div>

    <div class="login-form">
      <van-form @submit="doLogin">
        <van-cell-group inset>
          <van-field
            v-model="username"
            name="username"
            label="用户名"
            placeholder="请输入用户名"
            :rules="[{ required: true, message: '请输入用户名' }]"
            clearable
          />
          <van-field
            v-model="password"
            type="password"
            name="password"
            label="密码"
            placeholder="请输入密码"
            :rules="[{ required: true, message: '请输入密码' }]"
            clearable
          />
        </van-cell-group>

        <div class="login-actions">
          <van-button round block type="primary" native-type="submit" class="green-btn">
            登 录
          </van-button>
        </div>
      </van-form>

      <div class="register-link">
        还没有账号？
        <router-link to="/register" style="color: #5b8c5a;">立即注册</router-link>
      </div>
    </div>

    <!-- 管理员入口：跳转到独立的管理后台登录页面（不同端口） -->
    <div class="admin-entry" @click="goAdminLogin">
      <span style="color: #9aab9a; font-size: 12px; cursor: pointer;">
        管理员登录 →
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showSuccessToast, showFailToast } from 'vant'
import { userLogin } from '@/utils/api'
import { useUserStore } from '@/store'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const username = ref('')
const password = ref('')
const loading = ref(false)

/** 跳转到独立的管理后台登录页面 */
function goAdminLogin() {
  // 计算管理后台地址：取当前host，端口替换为3001
  const loc = window.location
  const adminUrl = `${loc.protocol}//${loc.hostname}:3001/#/login`
  window.open(adminUrl, '_blank')
}

async function doLogin() {
  loading.value = true
  try {
    const res = await userLogin({
      username: username.value,
      password: password.value
    })

    if (res.code === 200) {
      userStore.setUserInfo(res.data)
      showSuccessToast('登录成功')
      // 跳转到首页或目标页面
      const redirect = route.query.redirect || '/home'
      router.push(redirect)
    } else {
      showFailToast(res.message || '登录失败')
    }
  } catch (error) {
    showFailToast(error?.message || '网络错误，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f5e9 0%, #f1f8e9 40%, #fff8e1 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 24px 0;
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.logo-icon {
  font-size: 64px;
  margin-bottom: 16px;
  filter: drop-shadow(0 4px 8px rgba(91, 140, 90, 0.2));
}

.title {
  font-size: 28px;
  font-weight: 700;
  color: #2e3d2e;
  margin-bottom: 8px;
  letter-spacing: 4px;
}

.subtitle {
  font-size: 14px;
  color: #9aab9a;
  letter-spacing: 2px;
}

.login-form {
  width: 100%;
  max-width: 360px;
}

.login-actions {
  margin-top: 24px;
  padding: 0 16px;
}

.register-link {
  text-align: center;
  margin-top: 20px;
  font-size: 14px;
  color: #6b7c6b;
}

.admin-entry {
  margin-top: 40px;
}
</style>