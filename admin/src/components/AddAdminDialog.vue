<template>
  <Teleport to="body">
    <div class="aam-overlay" v-if="modelValue" @click.self="close">
      <div class="aam-dialog" role="dialog" aria-modal="true">
        <!-- 头部 -->
        <div class="aam-header">
          <div class="aam-title">
            <span class="aam-title-accent"></span>
            <span>添加管理员</span>
          </div>
          <button class="aam-close" @click="close" aria-label="关闭">
            <svg viewBox="0 0 14 14" width="14" height="14">
              <path d="M1 1 L13 13 M13 1 L1 13" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
            </svg>
          </button>
        </div>

        <!-- 表单主体 -->
        <div class="aam-body">
          <!-- 账号字段 -->
          <div class="aam-field">
            <label class="aam-label">
              <span class="aam-required">*</span>
              <span>账号</span>
            </label>
            <div class="aam-input-wrap" :class="{ 'is-error': errors.username }">
              <input
                type="text"
                class="aam-input"
                v-model="form.username"
                placeholder="请输入管理员账号"
                @blur="validateField('username')"
              />
            </div>
            <span class="aam-error" v-if="errors.username">{{ errors.username }}</span>
          </div>

          <!-- 密码字段 -->
          <div class="aam-field">
            <label class="aam-label">
              <span class="aam-required">*</span>
              <span>密码</span>
            </label>
            <div class="aam-input-wrap" :class="{ 'is-error': errors.password }">
              <input
                :type="showPassword ? 'text' : 'password'"
                class="aam-input"
                v-model="form.password"
                placeholder="请输入密码"
                @blur="validateField('password')"
              />
              <button type="button" class="aam-toggle-pw" @click="showPassword = !showPassword" aria-label="切换密码可见">
                <svg v-if="!showPassword" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M3 3l18 18"/>
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
            </div>
            <span class="aam-error" v-if="errors.password">{{ errors.password }}</span>
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="aam-footer">
          <button class="aam-btn aam-btn-cancel" @click="close">取 消</button>
          <button class="aam-btn aam-btn-save" @click="handleSave">保 存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'

const props = defineProps({
  modelValue: Boolean
})
const emit = defineEmits(['update:modelValue', 'save'])

const showPassword = ref(false)
const form = reactive({
  username: '',
  password: ''
})
const errors = reactive({
  username: '',
  password: ''
})

watch(() => props.modelValue, (val) => {
  if (!val) {
    form.username = ''
    form.password = ''
    errors.username = ''
    errors.password = ''
    showPassword.value = false
  }
})

function close() {
  emit('update:modelValue', false)
}

function validateField(field) {
  errors[field] = ''
  if (!form[field].trim()) {
    errors[field] = field === 'username' ? '请输入账号' : '请输入密码'
    return false
  }
  return true
}

function handleSave() {
  const uValid = validateField('username')
  const pValid = validateField('password')
  if (!uValid || !pValid) return

  emit('save', {
    username: form.username.trim(),
    password: form.password
  })
}
</script>

<style scoped>
.aam-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  animation: aamFadeIn 0.2s ease;
}

.aam-dialog {
  width: 440px;
  background: linear-gradient(135deg, #0f1a2e 0%, #0a101f 100%);
  border: 1px solid rgba(0, 136, 153, 0.35);
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.55), 0 0 60px rgba(0, 229, 204, 0.05);
  position: relative;
  overflow: hidden;
  animation: aamSlideIn 0.25s ease;
}

.aam-dialog::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, #00e5cc, transparent);
}

/* ---- Header ---- */
.aam-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22px 28px 0;
  position: relative;
}

.aam-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 17px;
  font-weight: 600;
  color: #e6f7ff;
  letter-spacing: 1px;
}

.aam-title-accent {
  display: inline-block;
  width: 3px;
  height: 18px;
  background: #00e5cc;
  border-radius: 2px;
  box-shadow: 0 0 8px rgba(0, 229, 204, 0.5);
}

.aam-close {
  background: none;
  border: none;
  color: #66a0ad;
  cursor: pointer;
  padding: 4px;
  transition: color 0.2s ease, transform 0.2s ease;
  border-radius: 6px;
  line-height: 0;
}

.aam-close:hover {
  color: #00e5cc;
  transform: scale(1.15);
}

/* ---- Body ---- */
.aam-body {
  padding: 24px 28px 8px;
}

.aam-field {
  margin-bottom: 22px;
}

.aam-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: #8cccd6;
  margin-bottom: 8px;
  letter-spacing: 0.5px;
}

.aam-required {
  color: #f06a6a;
  font-size: 13px;
  margin-right: 2px;
}

.aam-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.aam-input {
  width: 100%;
  height: 44px;
  background: rgba(0, 136, 153, 0.08);
  border: 1px solid rgba(0, 136, 153, 0.22);
  border-radius: 8px;
  color: #e6f7ff;
  font-size: 14px;
  padding: 0 16px;
  box-sizing: border-box;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.aam-input::placeholder {
  color: #66a0ad;
  font-size: 13px;
}

.aam-input:hover {
  border-color: rgba(0, 229, 204, 0.45);
}

.aam-input:focus {
  border-color: #00e5cc;
  box-shadow: 0 0 0 2px rgba(0, 229, 204, 0.15);
  background: rgba(0, 136, 153, 0.12);
}

.aam-input-wrap.is-error .aam-input {
  border-color: #c43a3a;
  background: rgba(196, 58, 58, 0.06);
}

.aam-toggle-pw {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #66a0ad;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  transition: color 0.2s ease;
  line-height: 0;
}

.aam-toggle-pw:hover {
  color: #00e5cc;
}

.aam-error {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  color: #f06a6a;
  line-height: 1.4;
}

/* ---- Footer ---- */
.aam-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 12px 28px 24px;
}

.aam-btn {
  min-width: 80px;
  height: 38px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 2px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.aam-btn-cancel {
  background: rgba(74, 122, 136, 0.15);
  border-color: rgba(74, 122, 136, 0.3);
  color: #8cccd6;
}

.aam-btn-cancel:hover {
  background: rgba(74, 122, 136, 0.3);
  border-color: rgba(74, 122, 136, 0.5);
  color: #b8e7ee;
}

.aam-btn-save {
  background: #007080;
  color: #ffffff;
  border-color: #007080;
}

.aam-btn-save:hover {
  background: #008c9e;
  border-color: #008c9e;
  box-shadow: 0 0 12px rgba(0, 229, 204, 0.3);
}

/* ---- Animations ---- */
@keyframes aamFadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes aamSlideIn {
  from { opacity: 0; transform: translateY(-20px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
