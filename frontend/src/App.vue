<template>
  <el-container class="app-container">
    <el-header>
      <h1>Agent for Exam</h1>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
// App 根组件
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
}

#app {
  width: 100%;
  height: 100vh;
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.el-header {
  display: flex;
  align-items: center;
  background-color: #409eff;
  color: white;
  padding: 0 20px;
  height: 60px !important; /* 固定 header 高度 */
  flex-shrink: 0;
}

.el-header h1 {
  font-size: 20px;
  font-weight: 500;
}

.el-main {
  padding: 0;
  height: calc(100vh - 60px); /* 减去 header 高度 */
  overflow: hidden;
  flex: 1; /* 填充剩余空间 */
}
</style>
