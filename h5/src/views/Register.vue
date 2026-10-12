<template>
  <div class="register-page">
    <van-nav-bar
      title="注册账号"
      left-arrow
      @click-left="$router.back()"
    />

    <div class="register-form">
      <van-form @submit="doRegister">
        <van-cell-group inset>
          <van-field
            v-model="username"
            name="username"
            label="用户名"
            placeholder="2-32个字符"
            :rules="[
              { required: true, message: '请输入用户名' },
              { pattern: /^.{2,32}$/, message: '用户名长度为2-32个字符' }
            ]"
            clearable
          />
          <van-field
            v-model="password"
            type="password"
            name="password"
            label="密码"
            placeholder="至少6位密码"
            :rules="[
              { required: true, message: '请输入密码' },
              { pattern: /^.{6,}$/, message: '密码长度不能少于6位' }
            ]"
            clearable
          />
          <van-field
            v-model="phone"
            name="phone"
            label="手机号"
            placeholder="选填"
            clearable
          />
          <van-field
            v-model="email"
            name="email"
            label="邮箱"
            placeholder="选填"
            clearable
          />
        </van-cell-group>

        <div class="register-actions">
          <van-button round block type="primary" native-type="submit" class="green-btn" :loading="loading">
            注 册
          </van-button>
        </div>
      </van-form>

      <div class="login-link">
        已有账号？
        <router-link to="/login" style="color: #5b8c5a;">立即登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast, showFailToast } from 'vant'
import { userRegister } from '@/utils/api'

const router = useRouter()
const username = ref('')
const password = ref('')
const phone = ref('')
const email = ref('')
const loading = ref(false)

async function doRegister() {
  loading.value = true
  try {
    const res = await userRegister({
      username: username.value,
      password: password.value,
      phone: phone.value,
      email: email.value
    })

    if (res.code === 200) {
      showSuccessToast('注册成功')
      router.push('/login')
    } else {
      showFailToast(res.message || '注册失败')
    }
  } catch (error) {
    showFailToast(error?.message || '网络错误，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  background: #f5f7f0;
}

.register-form {
  padding: 24px 16px;
}

.register-actions {
  margin-top: 24px;
  padding: 0 16px;
}

.login-link {
  text-align: center;
  margin-top: 20px;
  font-size: 14px;
  color: #6b7c6b;
}
</style>