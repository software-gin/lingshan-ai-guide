<template>
  <div class="ai-config-page">
    <h2 class="page-title">⚙️ AI参数配置</h2>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card>
          <template #header>🔑 多模态大模型配置</template>
          <el-form ref="formRef" :model="config" label-width="140px" style="max-width: 600px;">
            <el-form-item label="API密钥" prop="api_key">
              <el-input v-model="config.api_key" type="password" show-password placeholder="输入您的API密钥" />
            </el-form-item>
            <el-form-item label="API接口地址" prop="api_base">
              <el-input v-model="config.api_base" placeholder="https://api.openai.com/v1" />
            </el-form-item>
            <el-form-item label="模型名称" prop="model_name">
              <el-input v-model="config.model_name" placeholder="gpt-3.5-turbo" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleSave" :loading="saving">保存配置</el-button>
              <el-button @click="fetchConfig">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>📖 配置说明</template>
          <div class="config-tips">
            <h4>支持的模型平台：</h4>
            <ul>
              <li>OpenAI（GPT系列）</li>
              <li>通义千问（Qwen系列）</li>
              <li>智谱（GLM系列）</li>
              <li>DeepSeek</li>
              <li>任何兼容OpenAI接口的模型</li>
            </ul>
            <h4 style="margin-top: 16px;">注意事项：</h4>
            <ul>
              <li>API密钥仅保存在运行内存中</li>
              <li>配置后立即全局生效</li>
              <li>未配置时将使用内置模拟回复</li>
              <li>模拟回复仅包含灵山景区内容</li>
            </ul>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getAiConfig, updateAiConfig } from '@/utils/api'

const formRef = ref(null)
const saving = ref(false)
const config = ref({
  api_key: '',
  api_base: 'https://api.openai.com/v1',
  model_name: 'gpt-3.5-turbo'
})

onMounted(() => fetchConfig())

async function fetchConfig() {
  try {
    const res = await getAiConfig()
    if (res.code === 200) {
      config.value = {
        api_key: res.data.api_key || '',
        api_base: res.data.api_base || 'https://api.openai.com/v1',
        model_name: res.data.model_name || 'gpt-3.5-turbo'
      }
    }
  } catch (e) {
    console.warn('获取配置失败:', e)
  }
}

async function handleSave() {
  saving.value = true
  try {
    const res = await updateAiConfig(config.value)
    if (res.code === 200) {
      ElMessage.success('AI配置已更新，全局生效')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.config-tips {
  font-size: var(--font-size-base);
  line-height: 2;
  color: var(--text-body);
}

.config-tips h4 {
  color: var(--text-secondary);
  margin-bottom: 4px;
  font-size: var(--font-size-md);
}

.config-tips ul {
  padding-left: 20px;
}

.config-tips li {
  list-style: disc;
  color: var(--text-body);
}
</style>