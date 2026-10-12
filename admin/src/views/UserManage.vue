<template>
  <div class="user-manage">
    <h2 class="page-title">👤 用户管理</h2>

    <!-- 搜索栏 -->
    <div class="search-form">
      <el-input v-model="keyword" placeholder="搜索用户名/手机号/邮箱" clearable style="width: 300px;" @keyup.enter="search" />
      <el-button type="primary" @click="search">搜索</el-button>
      <el-button @click="reset">重置</el-button>
    </div>

    <!-- 用户列表 -->
    <el-card>
      <el-table :data="users" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="phone" label="手机号" width="140" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column prop="registered_at" label="注册时间" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该用户？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button type="danger" size="small" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="perPage"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchUsers"
          @size-change="fetchUsers"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getUsers, deleteUser } from '@/utils/api'

const users = ref([])
const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const perPage = ref(20)
const total = ref(0)

onMounted(() => fetchUsers())

async function fetchUsers() {
  loading.value = true
  try {
    const res = await getUsers({ page: page.value, per_page: perPage.value, keyword: keyword.value })
    if (res.code === 200) {
      users.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (e) {
    console.error('获取用户列表失败:', e)
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  fetchUsers()
}

function reset() {
  keyword.value = ''
  page.value = 1
  fetchUsers()
}

async function handleDelete(id) {
  try {
    const res = await deleteUser(id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchUsers()
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>