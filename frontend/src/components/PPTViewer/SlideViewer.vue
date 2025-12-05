<template>
  <div class="slide-viewer" @contextmenu.prevent @mousedown="handleMouseDown">
    <!-- 竖向滚动容器：显示所有幻灯片 -->
    <div class="slides-container">
      <div 
        v-for="(slideItem, index) in props.slides" 
        :key="slideItem.slide_number"
        :ref="el => slideRefs[index] = el"
        class="slide-item"
        :class="{ 'current-slide': slideItem.slide_number === props.currentSlideNumber }"
        @click.stop="handleSlideClick(slideItem.slide_number)"
        @mousedown.stop
      >
        <div class="slide-content-wrapper">
          <!-- 渲染的图片（背景层） -->
          <div class="slide-image-container" v-if="getImageUrl(slideItem.slide_number) && enableImageRender">
            <img
              :src="getImageUrl(slideItem.slide_number)"
              :alt="slideItem.title || `幻灯片 ${slideItem.slide_number}`"
              class="slide-image"
              @load="onImageLoad(slideItem.slide_number)"
              @error="onImageError(slideItem.slide_number)"
              :style="{ display: isImageLoaded(slideItem.slide_number) ? 'block' : 'none' }"
            />
            <div v-if="!isImageLoaded(slideItem.slide_number) && !isImageError(slideItem.slide_number)" class="image-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>加载中...</span>
            </div>
            <div v-if="isImageError(slideItem.slide_number)" class="image-error">
              <el-icon><WarningFilled /></el-icon>
              <span>图片加载失败</span>
            </div>
            
            <!-- 简单高亮层（HTML绝对定位） -->
            <!-- 仅支持PPTX的文本位置高亮，PDF禁用高亮功能 -->
            <SimpleHighlightLayer
              v-if="enableCanvasTextLayer && isImageLoaded(slideItem.slide_number) && isHighlightEnabled && slideItem.text_positions && slideItem.text_positions.length > 0 && slideItem.slide_dimensions"
              :text-positions="slideItem.text_positions"
              :slide-dimensions="slideItem.slide_dimensions"
              :image-loaded="isImageLoaded(slideItem.slide_number)"
              @entity-click="handleEntityClick"
            />
          </div>

          <!-- 文本层（叠加在图片上方，用于实体标注和文本选择） -->
          <div class="slide-text-layer" :class="{ 'text-selectable': showTextLayer }" v-if="showTextLayer">
            <div class="slide-title" v-if="slideItem.title">
              {{ slideItem.title }}
            </div>
            <div 
              class="slide-text" 
              v-html="getHighlightedText(slideItem)"
            ></div>
          </div>

          <!-- 降级显示：如果图片加载失败或未启用图片渲染，显示文本内容 -->
          <div v-if="isImageError(slideItem.slide_number) || !enableImageRender" class="slide-fallback">
            <!-- 幻灯片标题 -->
            <div class="slide-title" v-if="slideItem.title">
              {{ slideItem.title }}
            </div>

            <!-- 文本内容 -->
            <div class="slide-text" v-html="getHighlightedText(slideItem)"></div>

            <!-- 图片占位框 -->
            <div v-if="slideItem.images && slideItem.images.length > 0" class="slide-images">
              <div
                v-for="(image, imgIndex) in slideItem.images"
                :key="imgIndex"
                class="image-placeholder"
              >
                <el-icon class="image-icon"><Picture /></el-icon>
                <div class="image-info">
                  <div class="image-alt">{{ image.alt_text || `图片 ${imgIndex + 1}` }}</div>
                  <div class="image-size">位置: ({{ formatPosition(image.position) }})</div>
                </div>
              </div>
            </div>

            <!-- 结构信息 -->
            <div v-if="slideItem.structure" class="slide-structure">
              <el-tag size="small">布局: {{ slideItem.structure.layout || '未知' }}</el-tag>
              <el-tag size="small" style="margin-left: 8px;">
                元素数: {{ slideItem.structure.shapes_count || 0 }}
              </el-tag>
            </div>
          </div>
        </div>
        <!-- 页码标识 -->
        <div class="slide-number-badge">
          第 {{ slideItem.slide_number }} / {{ totalSlides }} 页
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Picture, Loading, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useGraphStore } from '../../stores/graphStore'
import documentService from '../../services/documentService'
import SimpleHighlightLayer from './SimpleHighlightLayer.vue'

const props = defineProps({
  slides: {
    type: Array,
    default: () => []
  },
  currentSlideNumber: {
    type: Number,
    required: true
  },
  totalSlides: {
    type: Number,
    required: true
  },
  conversationId: {
    type: String,
    required: true
  },
  fileId: {
    type: String,
    required: true
  },
  fileExtension: {
    type: String,
    default: null  // 文件扩展名（用于判断是否启用高亮）
  },
  enableImageRender: {
    type: Boolean,
    default: true  // 默认启用图片渲染
  },
  showTextLayer: {
    type: Boolean,
    default: false  // 不使用简单文本层，改用Canvas精确叠加
  },
  enableCanvasTextLayer: {
    type: Boolean,
    default: true  // 启用Canvas文本层（精确位置对齐）
  }
})

const emit = defineEmits(['slide-change'])

const graphStore = useGraphStore()

// 图片加载状态（使用 Map 存储每个幻灯片的加载状态）
const imageLoadedMap = ref(new Map())
const imageErrorMap = ref(new Map())
const slideRefs = ref([])

// 计算属性：是否启用高亮功能（仅PPTX启用，PDF禁用）
const isHighlightEnabled = computed(() => {
  // 只有PPTX文件才启用高亮功能，PDF禁用
  return props.fileExtension === 'pptx'
})

// 获取图片 URL
const getImageUrl = (slideNumber) => {
  if (!props.enableImageRender || !props.conversationId || !props.fileId) {
    return null
  }
  return documentService.getSlideImageUrl(
    props.conversationId,
    props.fileId,
    slideNumber,
    true
  )
}

// 检查图片是否已加载
const isImageLoaded = (slideNumber) => {
  return imageLoadedMap.value.get(slideNumber) || false
}

// 检查图片是否加载失败
const isImageError = (slideNumber) => {
  return imageErrorMap.value.get(slideNumber) || false
}

// 高亮文本中的实体
const getHighlightedText = (slide) => {
  if (!slide || !slide.text_content) return ''
  
  let text = slide.text_content
  
  // 转义 HTML 特殊字符
  text = text.replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  // 高亮实体（从知识图谱中获取实体名称）
  if (graphStore.entities && graphStore.entities.length > 0) {
    // 按长度排序，优先匹配较长的实体名
    const sortedEntities = [...graphStore.entities].sort((a, b) => {
      const nameA = (a.name || a.entity_id || '').length
      const nameB = (b.name || b.entity_id || '').length
      return nameB - nameA
    })
    
    sortedEntities.forEach(entity => {
      const entityName = entity.name || entity.entity_id
      if (entityName && entityName.length > 1 && text.includes(entityName)) {
        // 转义特殊字符用于正则
        const escapedName = entityName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        const regex = new RegExp(`(${escapedName})`, 'gi')
        text = text.replace(regex, (match) => {
          // 避免重复替换已经高亮的内容
          if (match.includes('entity-highlight')) return match
          return `<span class="entity-highlight" title="${entityName}">${match}</span>`
        })
      }
    })
  }
  
  // 将换行符转换为 <br>
  text = text.replace(/\n/g, '<br>')
  
  return text
}

// 鼠标点击事件处理（左键上一页，右键下一页）
const handleMouseDown = (event) => {
  // 如果点击在输入框或按钮上，不处理
  if (event.target.tagName === 'INPUT' || 
      event.target.tagName === 'TEXTAREA' || 
      event.target.tagName === 'BUTTON' ||
      event.target.closest('button') ||
      event.target.closest('input') ||
      event.target.closest('textarea')) {
    return
  }
  
  // 如果点击在 slide-item 上，不处理（由 handleSlideClick 处理）
  if (event.target.closest('.slide-item')) {
    return
  }
  
  // 左键：上一页
  if (event.button === 0 && props.currentSlideNumber > 1) {
    emit('slide-change', props.currentSlideNumber - 1)
  }
  // 右键：下一页
  else if (event.button === 2 && props.currentSlideNumber < props.totalSlides) {
    emit('slide-change', props.currentSlideNumber + 1)
  }
}

// 点击某一页，直接定位到该页
const handleSlideClick = (slideNumber) => {
  if (slideNumber === props.currentSlideNumber) return
  // 触发与键盘/鼠标翻页一致的切换逻辑
  emit('slide-change', slideNumber)
  // 立即滚动到目标页（不依赖 watch，避免延迟）
  nextTick(() => {
    const index = slideNumber - 1
    if (slideRefs.value && slideRefs.value[index]) {
      slideRefs.value[index]?.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'center' 
      })
    }
  })
}

const formatPosition = (position) => {
  if (!position) return '未知'
  return `左:${position.left}, 上:${position.top}, 宽:${position.width}, 高:${position.height}`
}

// 图片加载成功
const onImageLoad = (slideNumber) => {
  imageLoadedMap.value.set(slideNumber, true)
  imageErrorMap.value.set(slideNumber, false)
}

// 图片加载失败
const onImageError = (slideNumber) => {
  imageLoadedMap.value.set(slideNumber, false)
  imageErrorMap.value.set(slideNumber, true)
}

// 监听当前幻灯片变化，滚动到对应位置
// 注意：仅在非点击触发的场景下使用（如键盘翻页、缩略图点击等）
watch(
  () => props.currentSlideNumber,
  (newNumber, oldNumber) => {
    // 只有当页码真正变化时才滚动
    if (newNumber === oldNumber || newNumber <= 0) return
    
    // 延迟执行，确保 DOM 已更新
    nextTick(() => {
      const index = newNumber - 1
      if (slideRefs.value && slideRefs.value[index] && slideRefs.value[index]) {
        // 使用 requestAnimationFrame 确保滚动时元素已渲染
        requestAnimationFrame(() => {
          const targetElement = slideRefs.value[index]
          if (targetElement) {
            targetElement.scrollIntoView({ 
              behavior: 'smooth', 
              block: 'center' 
            })
          }
        })
      }
    })
  }
)

// 组件挂载时加载实体数据
onMounted(async () => {
  // 加载知识图谱实体数据（用于Canvas实体高亮）
  if (props.conversationId) {
    try {
      // console.log('📊 加载知识图谱实体数据...')
      await graphStore.loadGraph(props.conversationId)
      // console.log('✅ 实体数据加载完成，实体数:', graphStore.entities.length)
      if (graphStore.entities.length > 0) {
        console.log('实体示例:', graphStore.entities[0])
      }
    } catch (error) {
      console.warn('⚠️ 加载实体数据失败:', error)
    }
  } else {
    console.warn('⚠️ 没有conversationId，无法加载实体数据')
  }
  
  // 滚动到当前幻灯片
  if (props.currentSlideNumber > 0) {
    nextTick(() => {
      if (slideRefs.value && slideRefs.value[props.currentSlideNumber - 1]) {
        slideRefs.value[props.currentSlideNumber - 1]?.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center' 
        })
      }
    })
  }
})

// 处理实体点击
const handleEntityClick = (entity) => {
  // 可以在这里添加实体点击的处理逻辑
  // 例如：显示实体详情、跳转到知识图谱等
  console.log('Entity clicked:', entity)
  
  // 使用Element Plus的消息提示
  ElMessage.info({
    message: `实体: ${entity.name || entity.entity_id}\n类型: ${entity.type || '未知'}`,
    duration: 3000
  })
  
  // TODO: 实现实体详情展示（可以打开对话框或跳转到知识图谱）
}

// 键盘快捷键支持（通过父组件传递）
// 这里不直接监听，避免多个实例冲突
</script>

<style scoped>
.slide-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f5;
  position: relative;
}

/* 竖向滚动容器 */
.slides-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

/* 单个幻灯片项 */
.slide-item {
  width: 100%;
  max-width: 1200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 20px;
  scroll-margin: 20px;
}

.slide-item.current-slide {
  outline: 3px solid #409eff;
  outline-offset: 10px;
  border-radius: 8px;
}

.slide-number-badge {
  margin-top: 12px;
  padding: 6px 16px;
  background-color: rgba(64, 158, 255, 0.1);
  color: #409eff;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
}

.slide-item.current-slide .slide-number-badge {
  background-color: #409eff;
  color: #fff;
}

.slide-content-wrapper {
  position: relative;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  width: 100%;
  overflow: hidden;
}

.slide-image-container {
  position: relative;
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f5f5f5;
  min-height: 600px;
}

.slide-image {
  max-width: 100%;
  height: auto;
  display: block;
}

.image-loading,
.image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: #909399;
}

.image-loading .el-icon {
  font-size: 32px;
}

.image-error .el-icon {
  font-size: 32px;
  color: #f56c6c;
}

.slide-text-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  padding: 40px;
  background: transparent;
  /* 文本几乎透明，但可选中 */
  color: rgba(0, 0, 0, 0.01);
  user-select: text;
  -webkit-user-select: text;
}

.slide-text-layer.text-selectable {
  pointer-events: auto;
}

/* 实体高亮保持可见，并支持交互 */
.slide-text-layer :deep(.entity-highlight) {
  background-color: rgba(255, 243, 205, 0.7) !important;
  color: rgba(0, 0, 0, 0.9) !important;
  padding: 2px 4px;
  border-radius: 3px;
  pointer-events: auto;
  cursor: pointer;
  transition: background-color 0.2s;
}

.slide-text-layer :deep(.entity-highlight:hover) {
  background-color: rgba(255, 193, 7, 0.9) !important;
}

.slide-fallback {
  padding: 40px;
  background-color: #fff;
}

.slide-title {
  font-size: 32px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid #e4e7ed;
}

.slide-text {
  font-size: 16px;
  line-height: 1.8;
  color: #606266;
  margin-bottom: 24px;
}

/* 实体高亮样式 */
:deep(.entity-highlight) {
  background-color: #fff3cd;
  padding: 2px 4px;
  border-radius: 3px;
  cursor: pointer;
  transition: background-color 0.2s;
}

:deep(.entity-highlight:hover) {
  background-color: #ffc107;
}

.slide-images {
  margin: 24px 0;
}

.image-placeholder {
  display: flex;
  align-items: center;
  padding: 16px;
  margin-bottom: 12px;
  border: 2px dashed #dcdfe6;
  border-radius: 4px;
  background-color: #f5f7fa;
}

.image-icon {
  font-size: 32px;
  color: #909399;
  margin-right: 16px;
}

.image-info {
  flex: 1;
}

.image-alt {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}

.image-size {
  font-size: 12px;
  color: #909399;
}

.slide-structure {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e4e7ed;
}

/* 滚动条样式 */
.slides-container::-webkit-scrollbar {
  width: 8px;
}

.slides-container::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.slides-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.slides-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>

