<template>
  <div class="graph-canvas-container">
    <div ref="cyContainer" class="cy-container"></div>
    
    <!-- 工具栏 -->
    <div class="graph-toolbar">
      <el-button-group>
        <el-button :icon="ZoomIn" @click="handleZoomIn" size="small" title="放大" />
        <el-button :icon="ZoomOut" @click="handleZoomOut" size="small" title="缩小" />
        <el-button @click="handleResetView" size="small" title="重置视图">重置</el-button>
        <el-button :icon="FullScreen" @click="handleFit" size="small" title="适应画布">适应</el-button>
      </el-button-group>
    </div>
    
    <!-- 节点详情面板 -->
    <el-card 
      v-if="selectedEntity" 
      class="node-details-panel"
      shadow="always"
    >
      <template #header>
        <div class="panel-header">
          <span>实体详情</span>
          <el-button text @click="closeDetails" :icon="Close" />
        </div>
      </template>
      <div v-if="entityDetails" class="details-content">
        <div class="detail-item">
          <label>名称：</label>
          <span>{{ entityDetails.name || entityDetails.entity_id }}</span>
        </div>
        <div class="detail-item">
          <label>类型：</label>
          <el-tag size="small">{{ entityDetails.type || '未知' }}</el-tag>
        </div>
        <div class="detail-item" v-if="entityDetails.description">
          <label>描述：</label>
          <p class="description-text">{{ entityDetails.description }}</p>
        </div>
        <div class="detail-item" v-if="entityDetails.source_documents && entityDetails.source_documents.length > 0">
          <label>来源文档：</label>
          <div class="source-documents">
            <el-tag
              v-for="doc in entityDetails.source_documents"
              :key="doc.file_id"
              size="small"
              type="info"
              class="source-doc-tag"
              @click="handleDocClick(doc)"
            >
              {{ doc.filename }}
            </el-tag>
          </div>
        </div>
      </div>
      <div v-else class="loading-details">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
    </el-card>
    
    <!-- 空状态 -->
    <el-empty 
      v-if="!loading && (!entities || entities.length === 0)" 
      description="暂无知识图谱数据"
      :image-size="120"
    />
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import cytoscape from 'cytoscape'
import { ZoomIn, ZoomOut, FullScreen, Close, Loading } from '@element-plus/icons-vue'
import { useGraphStore } from '../../stores/graphStore'

const props = defineProps({
  conversationId: {
    type: String,
    default: null
  },
  filterOptions: {
    type: Object,
    default: () => ({
      searchText: '',
      selectedTypes: [],
      minDegree: 0
    })
  }
})

const emit = defineEmits(['node-click', 'node-hover', 'doc-click'])

const cyContainer = ref(null)
const cy = ref(null)
const loading = ref(false)
const selectedEntity = ref(null)
const entityDetails = ref(null)
const graphStore = useGraphStore()

// 计算节点连接度
const calculateNodeDegrees = (entities, relations) => {
  const degreeMap = new Map()
  entities.forEach(entity => {
    degreeMap.set(entity.entity_id || entity.name, 0)
  })
  
  relations.forEach(relation => {
    const source = relation.source
    const target = relation.target
    degreeMap.set(source, (degreeMap.get(source) || 0) + 1)
    degreeMap.set(target, (degreeMap.get(target) || 0) + 1)
  })
  
  return degreeMap
}

// 过滤实体和关系
const filterGraphData = (entities, relations, filterOptions) => {
  if (!filterOptions) return { entities, relations }
  
  const { searchText = '', selectedTypes = [], minDegree = 0 } = filterOptions
  
  // 计算连接度
  const degreeMap = calculateNodeDegrees(entities, relations)
  
  // 过滤实体
  let filteredEntities = entities.filter(entity => {
    const entityId = entity.entity_id || entity.name
    const entityName = entity.name || entity.entity_id
    const entityType = (entity.type || 'unknown').toLowerCase()
    
    // 搜索过滤
    if (searchText && !entityName.toLowerCase().includes(searchText.toLowerCase())) {
      return false
    }
    
    // 类型过滤
    if (selectedTypes.length > 0 && !selectedTypes.includes(entityType)) {
      return false
    }
    
    // 连接度过滤
    const degree = degreeMap.get(entityId) || 0
    if (degree < minDegree) {
      return false
    }
    
    return true
  })
  
  // 根据过滤后的实体过滤关系
  const filteredEntityIds = new Set(filteredEntities.map(e => e.entity_id || e.name))
  const filteredRelations = relations.filter(relation => {
    return filteredEntityIds.has(relation.source) && filteredEntityIds.has(relation.target)
  })
  
  return { entities: filteredEntities, relations: filteredRelations }
}

// 将API数据转换为Cytoscape格式
const convertToCytoscapeData = (entities, relations, filterOptions = null) => {
  // 先过滤数据
  const { entities: filteredEntities, relations: filteredRelations } = 
    filterOptions ? filterGraphData(entities, relations, filterOptions) : { entities, relations }
  
  const nodes = filteredEntities.map(entity => ({
    data: {
      id: entity.entity_id || entity.name,
      label: entity.name || entity.entity_id,
      type: entity.type || 'unknown',
      description: entity.description || '',
      // 保存完整实体数据
      entityData: entity
    }
  }))
  
  const edges = filteredRelations.map(relation => ({
    data: {
      id: relation.relation_id || `${relation.source}-${relation.target}`,
      source: relation.source,
      target: relation.target,
      label: relation.type || '',
      description: relation.description || '',
      // 保存完整关系数据
      relationData: relation
    }
  }))
  
  return { nodes, edges }
}

// 初始化Cytoscape
const initCytoscape = () => {
  if (!cyContainer.value) return
  
  // 销毁旧实例
  if (cy.value) {
    cy.value.destroy()
  }
  
  // 获取数据
  const entities = graphStore.entities || []
  const relations = graphStore.relations || []
  
  if (entities.length === 0) {
    return
  }
  
  // 转换数据（应用过滤）
  const { nodes, edges } = convertToCytoscapeData(entities, relations, props.filterOptions)
  
  // 创建Cytoscape实例
  cy.value = cytoscape({
    container: cyContainer.value,
    elements: [...nodes, ...edges],
    style: [
      {
        selector: 'node',
        style: {
          'background-color': '#409EFF',
          'label': 'data(label)',
          'text-valign': 'center',
          'text-halign': 'center',
          'color': '#fff',
          'font-size': '12px',
          'width': 60,
          'height': 60,
          'shape': 'round-rectangle',
          'border-width': 2,
          'border-color': '#fff'
        }
      },
      {
        selector: 'node[type = "concept"]',
        style: {
          'background-color': '#409EFF'
        }
      },
      {
        selector: 'node[type = "person"]',
        style: {
          'background-color': '#67C23A'
        }
      },
      {
        selector: 'node[type = "location"]',
        style: {
          'background-color': '#E6A23C'
        }
      },
      {
        selector: 'node[type = "organization"]',
        style: {
          'background-color': '#F56C6C'
        }
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 4,
          'border-color': '#FFD700',
          'background-opacity': 0.8
        }
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#999',
          'target-arrow-color': '#999',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(label)',
          'text-rotation': 'autorotate',
          'text-margin-y': -10,
          'font-size': '10px',
          'color': '#666'
        }
      },
      {
        selector: 'edge:selected',
        style: {
          'width': 4,
          'line-color': '#409EFF',
          'target-arrow-color': '#409EFF'
        }
      }
    ],
    layout: {
      name: 'breadthfirst', // 使用内置的广度优先布局（类似力导向效果）
      animate: true,
      animationDuration: 1000,
      fit: true,
      padding: 30,
      directed: false,
      spacingFactor: 1.5
    },
    userPanningEnabled: true,
    userZoomingEnabled: true,
    boxSelectionEnabled: true
  })
  
  // 绑定事件
  setupEvents()
}

// 设置事件监听
const setupEvents = () => {
  if (!cy.value) return
  
  // 节点点击
  cy.value.on('tap', 'node', (event) => {
    const node = event.target
    const entityData = node.data('entityData')
    
    if (entityData) {
      selectedEntity.value = entityData
      loadEntityDetails(entityData.entity_id || entityData.name)
      emit('node-click', entityData)
    }
  })
  
  // 节点悬停高亮
  cy.value.on('mouseover', 'node', (event) => {
    const node = event.target
    node.style('border-width', 4)
    node.style('border-color', '#FFD700')
    
    // 高亮连接的边
    node.connectedEdges().style('width', 4)
    node.connectedEdges().style('line-color', '#409EFF')
    
    // 高亮邻居节点
    node.neighborhood('node').style('opacity', 0.8)
    
    // 降低其他节点透明度
    cy.value.elements().difference(node.union(node.neighborhood())).style('opacity', 0.3)
  })
  
  cy.value.on('mouseout', 'node', (event) => {
    const node = event.target
    
    // 如果不是选中的节点，恢复样式
    if (!node.selected()) {
      node.style('border-width', 2)
      node.style('border-color', '#fff')
    }
    
    // 恢复边的样式
    node.connectedEdges().style('width', 2)
    node.connectedEdges().style('line-color', '#999')
    
    // 恢复所有节点透明度
    cy.value.elements().style('opacity', 1)
  })
  
  // 画布点击（取消选择）
  cy.value.on('tap', (event) => {
    if (event.target === cy.value) {
      cy.value.elements().unselect()
      selectedEntity.value = null
      entityDetails.value = null
    }
  })
}

  // 加载实体详情
  const loadEntityDetails = async (entityId) => {
    if (!props.conversationId || !entityId) return
    
    entityDetails.value = null
    
    try {
      const details = await graphStore.getEntity(props.conversationId, entityId)
      entityDetails.value = details
    } catch (error) {
      console.error('加载实体详情失败:', error)
    }
  }
  
  // 处理文档点击
  const handleDocClick = (doc) => {
    emit('doc-click', doc)
  }

// 工具栏操作
const handleZoomIn = () => {
  if (cy.value) {
    cy.value.zoom(cy.value.zoom() * 1.2)
  }
}

const handleZoomOut = () => {
  if (cy.value) {
    cy.value.zoom(cy.value.zoom() * 0.8)
  }
}

const handleResetView = () => {
  if (cy.value) {
    cy.value.elements().unselect()
    cy.value.fit()
    cy.value.center()
    selectedEntity.value = null
    entityDetails.value = null
  }
}

const handleFit = () => {
  if (cy.value) {
    cy.value.fit()
  }
}

const closeDetails = () => {
  selectedEntity.value = null
  entityDetails.value = null
  if (cy.value) {
    cy.value.elements().unselect()
  }
}

// 监听数据变化
watch(
  () => [graphStore.entities, graphStore.relations],
  () => {
    if (graphStore.entities && graphStore.entities.length > 0) {
      nextTick(() => {
        initCytoscape()
      })
    }
  },
  { deep: true }
)

// 监听过滤选项变化，重新渲染
watch(
  () => props.filterOptions,
  () => {
    if (graphStore.entities && graphStore.entities.length > 0) {
      nextTick(() => {
        initCytoscape()
      })
    }
  },
  { deep: true }
)

// 监听对话变化
watch(
  () => props.conversationId,
  async (newId) => {
    if (newId) {
      loading.value = true
      try {
        await graphStore.loadGraph(newId)
      } catch (error) {
        console.error('加载图谱失败:', error)
      } finally {
        loading.value = false
      }
    } else {
      graphStore.clearGraph()
      if (cy.value) {
        cy.value.destroy()
        cy.value = null
      }
    }
  },
  { immediate: true }
)

onMounted(async () => {
  // 如果已有对话ID，加载数据
  if (props.conversationId) {
    loading.value = true
    try {
      await graphStore.loadGraph(props.conversationId)
    } catch (error) {
      console.error('加载图谱失败:', error)
    } finally {
      loading.value = false
    }
  }
})

onUnmounted(() => {
  if (cy.value) {
    cy.value.destroy()
  }
})
</script>

<style scoped>
.graph-canvas-container {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 600px;
  background-color: #f5f5f5;
  flex: 1;
}

.cy-container {
  width: 100%;
  height: 100%;
  min-height: 600px;
  flex: 1;
}

.graph-toolbar {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 100;
  background-color: rgba(255, 255, 255, 0.9);
  padding: 8px;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.node-details-panel {
  position: absolute;
  top: 10px;
  left: 10px;
  width: 300px;
  max-height: 400px;
  z-index: 100;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.details-content {
  padding: 0;
}

.detail-item {
  margin-bottom: 12px;
}

.detail-item label {
  font-weight: bold;
  color: #606266;
  display: inline-block;
  min-width: 60px;
}

.detail-item p {
  margin: 4px 0 0 0;
  color: #303133;
  line-height: 1.5;
}

.loading-details {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
}

.description-text {
  white-space: pre-wrap;
  line-height: 1.5;
  margin: 0;
}

.source-documents {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.source-doc-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.source-doc-tag:hover {
  transform: scale(1.05);
  opacity: 0.8;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background-color: rgba(255, 255, 255, 0.8);
  z-index: 200;
  color: #909399;
}

.loading-overlay .el-icon {
  font-size: 32px;
}
</style>

