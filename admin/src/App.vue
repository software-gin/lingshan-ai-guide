<template>
  <div id="app-container">
    <!-- 使用单一 router-view，由路由结构自动决定渲染 Login 还是 Layout -->
    <router-view />
  </div>
</template>

<script setup>
// App.vue 不再需要判断登录页逻辑，由路由结构处理：
// /login → Login.vue（无侧边栏）
// 其他 → Layout.vue（含侧边栏+子路由）
</script>