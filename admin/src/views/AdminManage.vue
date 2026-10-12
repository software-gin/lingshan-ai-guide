<template>
  <div class="admin-manage">
    <h2 class="page-title">管理员管理</h2>

    <div class="action-row">
      <button class="btn-primary" @click="showDialog = true">+ 添加管理员</button>
    </div>

    <el-card>
      <el-table :data="admins" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="账号" min-width="150" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
      </el-table>
    </el-card>

    <!-- 自定义暗色对话框 -->
    <AddAdminDialog v-model="showDialog" @save="handleSave" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getAdmins, createAdmin } from '@/utils/api'
import AddAdminDialog from '@/components/AddAdminDialog.vue'

const admins = ref([])
const loading = ref(false)
const saving = ref(false)
const showDialog = ref(false)

onMounted(() => fetchAdmins())

async function fetchAdmins() {
  loading.value = true
  try {
    const res = await getAdmins()
    if (res.code === 200) {
      admins.value = res.data || []
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function handleSave(data) {
  saving.value = true
  try {
    const res = await createAdmin(data)
    if (res.code === 200) {
      ElMessage.success('添加成功')
      showDialog.value = false
      fetchAdmins()
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {
    ElMessage.error('添加失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.action-row {
  margin-bottom: 16px;
}

.btn-primary {
  background: var(--primary-dark);
  border: none;
  color: var(--text-inverse);
  font-size: var(--font-size-md);
  font-weight: 500;
  padding: 8px 20px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  letter-spacing: 0.5px;
}

.btn-primary:hover {
  background: #008c9e;
  box-shadow: 0 0 12px rgba(0, 229, 204, 0.25);
}

.btn-primary:active {
  background: var(--primary-darker);
}
</style>
