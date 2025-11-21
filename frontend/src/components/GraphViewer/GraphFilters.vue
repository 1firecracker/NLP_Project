<template>
  <el-card class="graph-filters-card" shadow="never">
    <template #header>
      <div class="filters-header">
        <span>图谱过滤</span>
        <el-button 
          text 
          type="primary" 
          size="small" 
          @click="handleReset"
          :disabled="!hasFilters"
        >
          重置
        </el-button>
      </div>
    </template>
    
    <div class="filters-content">
      <!-- 搜索框 -->
      <div class="filter-item">
        <label>搜索实体</label>
        <el-input
          v-model="searchText"
          placeholder="输入实体名称..."
          clearable
          @input="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
      
      <!-- 实体类型过滤 -->
      <div class="filter-item">
        <label>实体类型</label>
        <el-checkbox-group v-model="selectedTypes" @change="handleTypeFilter">
          <el-checkbox 
            v-for="type in availableTypes" 
            :key="type.value" 
            :label="type.value"
          >
            {{ type.label }}
          </el-checkbox>
        </el-checkbox-group>
      </div>
      
      <!-- 连接度过滤 -->
      <div class="filter-item">
        <label>最小连接度</label>
        <el-slider
          v-model="minDegree"
          :min="0"
          :max="maxDegree"
          :step="1"
          show-stops
          :show-tooltip="true"
          @change="handleDegreeFilter"
        />
        <div class="slider-info">
          <span>当前: {{ minDegree }}</span>
          <span>最大: {{ maxDegree }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useGraphStore } from '../../stores/graphStore'

const emit = defineEmits(['filter-change'])

const graphStore = useGraphStore()

const searchText = ref('')
const selectedTypes = ref([])
const minDegree = ref(0)
const maxDegree = ref(10) // 初始值，会根据实际数据更新

// 固定的实体类型列表（对应 LightRAG constants.py 中的 DEFAULT_ENTITY_TYPES + unknown）
const availableTypes = [
  { value: 'chapterconcept', label: '章节概念' },
  { value: 'definition', label: '定义' },
  { value: 'method', label: '方法' },
  { value: 'application', label: '应用' },
  { value: 'example', label: '例子' },
  { value: 'unknown', label: '未知' }
]

// 计算是否有过滤条件
const hasFilters = computed(() => {
  return searchText.value.length > 0 || 
         selectedTypes.value.length > 0 || 
         minDegree.value > 0
})

// 监听图谱数据变化，更新最大连接度
watch(() => graphStore.entities, (entities) => {
  if (entities && entities.length > 0) {
    // 计算每个实体的连接度
    const degreeMap = new Map()
    graphStore.relations.forEach(rel => {
      degreeMap.set(rel.source, (degreeMap.get(rel.source) || 0) + 1)
      degreeMap.set(rel.target, (degreeMap.get(rel.target) || 0) + 1)
    })
    
    // 找到最大连接度
    const degrees = Array.from(degreeMap.values())
    if (degrees.length > 0) {
      maxDegree.value = Math.max(...degrees)
    }
  }
}, { immediate: true, deep: true })

// 搜索处理
const handleSearch = () => {
  emitFilterChange()
}

// 类型过滤处理
const handleTypeFilter = () => {
  emitFilterChange()
}

// 连接度过滤处理
const handleDegreeFilter = () => {
  emitFilterChange()
}

// 发送过滤事件
const emitFilterChange = () => {
  // 确保类型值都是小写，与过滤逻辑保持一致
  const normalizedTypes = selectedTypes.value.map(t => t.toLowerCase())
  emit('filter-change', {
    searchText: searchText.value,
    selectedTypes: normalizedTypes,
    minDegree: minDegree.value
  })
}

// 重置过滤条件
const handleReset = () => {
  searchText.value = ''
  selectedTypes.value = []
  minDegree.value = 0
  emitFilterChange()
}
</script>

<style scoped>
.graph-filters-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.graph-filters-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.filters-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.filters-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-item label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.el-checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slider-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>

