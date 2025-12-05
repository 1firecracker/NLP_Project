<template>
  <el-card class="mindmap-viewer-card">
    <template #header>
      <div class="viewer-header">
        <div class="header-left">
          <h3>思维脑图</h3>
          <el-text v-if="mindmapStore.hasMindMap" class="mindmap-stats">
            {{ mindmapStore.mindmapContent.split('\n').length }} 行
          </el-text>
        </div>
        <div class="header-right">
          <el-button 
            :icon="Expand" 
            circle 
            plain 
            size="small" 
            @click="handleExpandAll"
            :disabled="!markmapInstance || !mindmapStore.hasMindMap"
            title="全部展开"
          />
          <el-button 
            :icon="Refresh" 
            circle 
            plain 
            size="small" 
            @click="handleRefresh"
            :loading="mindmapStore.loading"
            title="刷新脑图"
          />
          <el-button 
            :icon="FullScreen" 
            circle 
            plain 
            size="small" 
            @click="handleFullscreen"
            title="全屏查看"
          />
        </div>
      </div>
    </template>
    
    <!-- 思维脑图容器 -->
    <div class="mindmap-container">
      <!-- 加载中 -->
      <div v-if="mindmapStore.loading" class="mindmap-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      
      <!-- 错误提示 -->
      <el-alert
        v-else-if="mindmapStore.error"
        :title="mindmapStore.error.message || '加载失败'"
        type="error"
        :closable="false"
        show-icon
      />
      
      <!-- 生成中或已有内容：显示思维脑图容器（支持流式实时显示） -->
      <div v-else-if="mindmapStore.generating || mindmapStore.mindmapContent" class="mindmap-wrapper">
        <!-- 生成中时显示进度条（覆盖在思维脑图上方） -->
        <div v-if="mindmapStore.generating" class="generating-overlay">
          <el-progress 
            :percentage="generationProgress" 
            :status="generationProgress === 100 ? 'success' : ''"
            :stroke-width="6"
            :show-text="true"
          />
          <div class="generating-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>正在生成思维脑图...</span>
          </div>
        </div>
        
        <!-- 思维脑图渲染容器 -->
        <div 
          ref="mindmapContainer"
          class="mindmap-canvas"
          :class="{ 'generating': mindmapStore.generating }"
        />
      </div>
      
      <!-- 空状态 -->
      <el-empty
        v-else
        description="暂无思维脑图，上传文档后将自动生成"
        :image-size="120"
      />
    </div>
    
    <!-- 全屏弹窗 -->
    <el-dialog
      v-model="fullscreenVisible"
      title="思维脑图 - 全屏视图"
      width="95%"
      :close-on-click-modal="false"
      :close-on-press-escape="true"
      class="mindmap-fullscreen-dialog"
    >
      <div ref="fullscreenContainer" class="fullscreen-mindmap-container" />
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Refresh, FullScreen, Loading, Expand } from '@element-plus/icons-vue'
import { useMindMapStore } from '../../stores/mindmapStore'
import { useConversationStore } from '../../stores/conversationStore'
import { useDocumentStore } from '../../stores/documentStore'

// 导入 markmap（使用标准 ES6 import）
import { Markmap } from 'markmap-view'
import { Transformer } from 'markmap-lib'

const mindmapStore = useMindMapStore()
const convStore = useConversationStore()
const docStore = useDocumentStore()

const mindmapContainer = ref(null)
const fullscreenContainer = ref(null)
const fullscreenVisible = ref(false)
const generationProgress = ref(0)

const markmapInstance = ref(null)
let fullscreenMarkmapInstance = null
let renderDebounceTimer = null // 防抖定时器
let renderRAFId = null // requestAnimationFrame ID
const processingDocs = new Set() // 记录正在流式生成的文档ID，避免重复调用

// 初始化 transformer
let transformer = null
const getTransformer = () => {
  if (!Transformer) {
    console.error('Transformer 类未加载')
    return null
  }
  if (!transformer) {
    try {
      transformer = new Transformer()
    } catch (error) {
      console.error('创建 Transformer 实例失败:', error)
      return null
    }
  }
  return transformer
}

// 渲染思维脑图
const renderMindMap = async (container, content) => {
  if (!container || !content) {
    return
  }
  
  if (!Markmap) {
    console.warn('Markmap 未加载，无法渲染思维脑图')
    return
  }
  
  if (!Transformer) {
    console.warn('Transformer 未加载，无法解析 Markdown')
    return
  }

  try {
    const transformer = getTransformer()
    if (!transformer) {
      console.error('无法创建 Transformer 实例')
      return
    }
    
    // 解析 Markdown 为 MindMap 数据
    const result = transformer.transform(content)
    // 减少日志输出（只在非生成中时输出详细日志）
    if (!mindmapStore.generating) {
      console.log('📊 Transformer 解析结果:', result)
    }
    
    let root = result.root
    
    if (!root) {
      console.warn('Markdown 解析结果为空', result)
      return
    }
    
    // 检查 root 数据格式
    if (!root.content && !root.children) {
      // 只在非生成中时输出警告（生成中时可能频繁出现）
      if (!mindmapStore.generating) {
        console.warn('⚠️ root 数据格式异常，可能不是有效的思维导图数据:', root)
      }
      // 尝试使用整个 result 作为 root
      const altRoot = result.root || result
      if (altRoot && (altRoot.content || altRoot.children)) {
        if (!mindmapStore.generating) {
          console.log('🔄 使用替代 root 数据')
        }
        root = altRoot
      }
    }
    
    // 递归解码 HTML 实体编码
    const decodeHtmlEntities = (obj) => {
      if (typeof obj === 'string') {
        // 解码 HTML 实体（如 &#x6587; -> 文）
        const textarea = document.createElement('textarea')
        textarea.innerHTML = obj
        return textarea.value
      } else if (Array.isArray(obj)) {
        return obj.map(decodeHtmlEntities)
      } else if (obj && typeof obj === 'object') {
        const decoded = { ...obj }
        if (decoded.content) {
          decoded.content = decodeHtmlEntities(decoded.content)
        }
        if (decoded.children) {
          decoded.children = decodeHtmlEntities(decoded.children)
        }
        return decoded
      }
      return obj
    }
    
    // 解码 root 中的 HTML 实体
    root = decodeHtmlEntities(root)
    
    // 减少日志输出（只在非生成中时输出详细日志）
    if (!mindmapStore.generating) {
      console.log('📊 解析后的 root 数据:', root)
      console.log('📊 root 类型:', typeof root)
      console.log('📊 root 键:', Object.keys(root || {}))
    }
    
    // 获取或创建 markmap 实例
    let instance = null
    const options = {
      color: (node) => {
        const depth = node.depth || 0
        const colors = [
          '#409eff', // 一级节点：蓝色
          '#67c23a', // 二级节点：绿色
          '#e6a23c', // 三级节点：橙色
          '#f56c6c', // 四级节点：红色
          '#909399'  // 其他：灰色
        ]
        return colors[Math.min(depth, colors.length - 1)]
      },
      duration: 300,
      maxWidth: 300,
      initialExpandLevel: 4, // 默认展开到第 2 层，更深层级默认折叠
    }
    
    if (container === mindmapContainer.value) {
      if (!markmapInstance.value) {
        console.log('🆕 创建新的 markmap 实例（主容器）')
        // 确保容器是空的
        container.innerHTML = ''
        // 创建 SVG 元素
        const svgElement = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
        svgElement.setAttribute('width', '100%')
        svgElement.setAttribute('height', '100%')
        svgElement.style.display = 'block'
        container.appendChild(svgElement)
        // 使用 SVG 元素创建实例
        markmapInstance.value = Markmap.create(svgElement, options)
      }
      instance = markmapInstance.value
    } else if (container === fullscreenContainer.value) {
      if (!fullscreenMarkmapInstance) {
        console.log('🆕 创建新的 markmap 实例（全屏容器）')
        // 确保容器是空的
        container.innerHTML = ''
        // 创建 SVG 元素
        const svgElement = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
        svgElement.setAttribute('width', '100%')
        svgElement.setAttribute('height', '100%')
        svgElement.style.display = 'block'
        container.appendChild(svgElement)
        // 使用 SVG 元素创建实例
        fullscreenMarkmapInstance = Markmap.create(svgElement, options)
      }
      instance = fullscreenMarkmapInstance
    }

    // 更新数据
    if (instance) {
      // 减少日志输出（只在非生成中时输出详细日志）
      if (!mindmapStore.generating) {
        console.log('🔄 更新 markmap 数据，root:', root)
        console.log('📐 容器尺寸:', container.offsetWidth, 'x', container.offsetHeight)
      }
      
      // 确保容器有尺寸
      if (container.offsetWidth === 0 || container.offsetHeight === 0) {
        console.warn('⚠️ 容器尺寸为 0，等待容器渲染...')
        setTimeout(() => {
          if (container.offsetWidth > 0 && container.offsetHeight > 0) {
            instance.setData(root)
            instance.fit()
            console.log('✅ 思维脑图渲染成功（延迟）')
          }
        }, 300)
        return
      }
      
      // 使用 setData 更新数据（支持流式更新，不需要重新创建实例）
      try {
        instance.setData(root)
        if (typeof instance.fit === 'function') {
          instance.fit()
        }
        // 减少日志输出，只在非生成中时输出（生成中时日志太多）
        if (!mindmapStore.generating) {
          console.log('✅ 思维脑图数据更新成功')
        }
        return // 更新成功，直接返回
      } catch (error) {
        console.error('❌ 更新数据失败，尝试重新创建实例:', error)
        // 如果更新失败，清空容器并重新创建
        const existingSvg = container.querySelector('svg')
        if (existingSvg) {
          existingSvg.remove()
        }
        Array.from(container.children).forEach(child => {
          if (child.tagName !== 'SVG') {
            child.remove()
          }
        })
        
        // 重新创建实例
        // 清空容器
        container.innerHTML = ''
        // 创建 SVG 元素
        const svgElement = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
        svgElement.setAttribute('width', '100%')
        svgElement.setAttribute('height', '100%')
        svgElement.style.display = 'block'
        container.appendChild(svgElement)
        
        if (container === mindmapContainer.value) {
          // 如果实例已存在，先销毁
          if (markmapInstance.value) {
            try {
              markmapInstance.value.destroy?.()
            } catch (e) {
              console.warn('销毁旧实例失败:', e)
            }
          }
          // 使用 SVG 元素创建实例
          markmapInstance.value = Markmap.create(svgElement, options)
          instance = markmapInstance.value
        } else if (container === fullscreenContainer.value) {
          // 如果实例已存在，先销毁
          if (fullscreenMarkmapInstance) {
            try {
              fullscreenMarkmapInstance.destroy?.()
            } catch (e) {
              console.warn('销毁旧实例失败:', e)
            }
          }
          // 使用 SVG 元素创建实例
          fullscreenMarkmapInstance = Markmap.create(svgElement, options)
          instance = fullscreenMarkmapInstance
        }
        
        console.log('✅ Markmap 实例已重新创建，SVG 元素:', svgElement)
        
        if (instance) {
          // 设置数据
          try {
            instance.setData(root)
            console.log('✅ setData 调用成功')
          } catch (error) {
            console.error('❌ setData 调用失败:', error)
            return
          }
          
          // 调用 fit 方法
          if (typeof instance.fit === 'function') {
            try {
              instance.fit()
              console.log('✅ fit 调用成功')
            } catch (error) {
              console.error('❌ fit 调用失败:', error)
            }
          }
        }
      }
    } else {
      console.warn('⚠️ 无法创建 markmap 实例，container:', container)
    }
  } catch (error) {
    console.error('渲染思维脑图失败:', error)
  }
}

// 监听思维脑图内容变化（使用防抖 + requestAnimationFrame，支持流式更新）
watch(() => mindmapStore.mindmapContent, async (newContent, oldContent) => {
  if (newContent && newContent.trim()) {
    // 清除之前的定时器和 RAF
    if (renderDebounceTimer) {
      clearTimeout(renderDebounceTimer)
      renderDebounceTimer = null
    }
    if (renderRAFId) {
      cancelAnimationFrame(renderRAFId)
      renderRAFId = null
    }
    
    // 检查内容是否足够完整（至少包含一个标题或列表项）
    const hasValidContent = newContent.includes('##') || newContent.includes('#') || newContent.includes('-')
    
    if (!hasValidContent) {
      // 内容不完整，不渲染
      return
    }
    
    // 如果正在生成中，使用较短的防抖时间（50ms）以实现更实时的更新
    // 如果不在生成中，使用较长的防抖时间（300ms）
    const debounceTime = mindmapStore.generating ? 50 : 300
    
    // 使用防抖，避免过于频繁的渲染（流式场景）
    renderDebounceTimer = setTimeout(() => {
      // 使用 requestAnimationFrame 确保在浏览器重绘前渲染
      renderRAFId = requestAnimationFrame(async () => {
        await nextTick()
        
        if (mindmapContainer.value && Markmap && Transformer) {
          // 减少日志输出（只在非生成中时输出）
          if (!mindmapStore.generating) {
            console.log('🔄 流式更新思维脑图，内容长度:', newContent.length)
          }
          renderMindMap(mindmapContainer.value, newContent)
        }
        if (fullscreenVisible.value && fullscreenContainer.value && Markmap && Transformer) {
          renderMindMap(fullscreenContainer.value, newContent)
        }
        
        renderRAFId = null
      })
      
      renderDebounceTimer = null
    }, debounceTime)
  } else if (!newContent && oldContent) {
    // 内容被清空，清空渲染
    if (renderDebounceTimer) {
      clearTimeout(renderDebounceTimer)
      renderDebounceTimer = null
    }
    if (renderRAFId) {
      cancelAnimationFrame(renderRAFId)
      renderRAFId = null
    }
    
    if (mindmapContainer.value) {
      mindmapContainer.value.innerHTML = ''
    }
    if (fullscreenContainer.value) {
      fullscreenContainer.value.innerHTML = ''
    }
    // 重置实例
    markmapInstance.value = null
    fullscreenMarkmapInstance = null
  }
}, { immediate: true })

// 监听对话变化
watch(() => convStore.currentConversationId, async (newId, oldId) => {
  if (newId) {
    console.log('🔄 对话变化，自动加载思维脑图:', newId)
    try {
      await mindmapStore.loadMindMap(newId)
      // 加载完成后渲染
      await nextTick()
      if (mindmapStore.mindmapContent && mindmapContainer.value && Markmap && Transformer) {
        setTimeout(async () => {
          await renderMindMap(mindmapContainer.value, mindmapStore.mindmapContent)
        }, 300)
      }
    } catch (error) {
      console.error('对话变化时加载思维脑图失败:', error)
    }
  } else {
    mindmapStore.clearMindMap()
    // 清空实例
    if (markmapInstance.value) {
      markmapInstance.value = null
    }
    if (fullscreenMarkmapInstance) {
      fullscreenMarkmapInstance = null
    }
  }
}, { immediate: true })

// 监听文档处理状态，自动触发流式生成或加载思维脑图
watch(() => docStore.extractionProgress, async (progress, oldProgress) => {
  if (!convStore.currentConversationId) {
    console.log('⚠️ 没有当前对话ID，跳过思维脑图生成')
    return
  }
  
  const convId = convStore.currentConversationId
  const currentProgress = progress[convId] || {}
  const oldProgressData = oldProgress?.[convId] || {}
  
  console.log('📊 文档状态变化:', {
    currentProgress: Object.keys(currentProgress).length,
    oldProgress: oldProgressData ? Object.keys(oldProgressData).length : 0,
    currentStatuses: Object.entries(currentProgress).map(([id, data]) => ({ id: id.substring(0, 8), status: data.status }))
  })
  
  // 1. 检查是否有新文档开始处理（状态从非 processing 变为 processing）
  let hasNewProcessing = false
  let processingDocId = null
  for (const [docId, docData] of Object.entries(currentProgress)) {
    const oldDocData = oldProgressData[docId]
    const oldStatus = oldDocData?.status || 'unknown'
    const newStatus = docData.status
    
    console.log(`📋 文档 ${docId.substring(0, 8)}... 状态: ${oldStatus} -> ${newStatus}`)
    
    // 状态从非 processing 变为 processing
    if (newStatus === 'processing' && oldStatus !== 'processing') {
      hasNewProcessing = true
      processingDocId = docId
      console.log(`✅ 检测到文档开始处理: ${docId.substring(0, 8)}...`)
      break
    }
  }
  
  // 2. 如果检测到新文档开始处理，且当前没有在生成，则启动流式生成
  if (hasNewProcessing && processingDocId) {
    console.log('🔍 检查是否可以启动流式生成:', {
      hasNewProcessing,
      processingDocId: processingDocId.substring(0, 8),
      alreadyProcessing: processingDocs.has(processingDocId),
      generating: mindmapStore.generating,
      loading: mindmapStore.loading
    })
    
    if (!processingDocs.has(processingDocId) &&
        !mindmapStore.generating && 
        !mindmapStore.loading) {
      console.log('🚀 启动流式生成思维脑图，文档ID:', processingDocId.substring(0, 8))
      
      // 标记该文档正在处理
      processingDocs.add(processingDocId)
      
      try {
        // 调用流式生成 API，实时接收和渲染内容
        console.log('📡 调用流式生成 API...')
        await mindmapStore.generateMindMap(convId, processingDocId, (content) => {
          // 进度回调（可选，用于更新进度条）
          if (content) {
            // 可以根据内容长度估算进度（最大95%，留5%给最终处理）
            const estimatedProgress = Math.min(95, Math.floor((content.length / 5000) * 100))
            generationProgress.value = estimatedProgress
            console.log(`📈 流式生成进度: ${estimatedProgress}%, 内容长度: ${content.length}`)
          }
        })
        
        // 流式生成完成，设置进度为100%
        generationProgress.value = 100
        console.log('✅ 流式生成思维脑图完成')
      } catch (error) {
        console.error('❌ 流式生成思维脑图失败:', error)
        console.error('错误详情:', error.message, error.stack)
        generationProgress.value = 0
        // 流式生成失败，不抛出错误，等待 completed 状态时从文件加载（兜底）
      } finally {
        // 移除处理标记
        processingDocs.delete(processingDocId)
        console.log('🧹 清理处理标记')
      }
    } else {
      console.log('⏸️ 跳过流式生成，原因:', {
        alreadyProcessing: processingDocs.has(processingDocId),
        generating: mindmapStore.generating,
        loading: mindmapStore.loading
      })
    }
  }
  
  // 3. 检查是否有新文档完成处理（状态从非 completed 变为 completed）
  // 这作为兜底方案：如果流式生成失败或未触发，至少可以从文件加载
  let hasNewCompleted = false
  for (const [docId, docData] of Object.entries(currentProgress)) {
    const oldDocData = oldProgressData[docId]
    if (docData.status === 'completed' && 
        (!oldDocData || oldDocData.status !== 'completed')) {
      hasNewCompleted = true
      break
    }
  }
  
  // 4. 如果文档完成处理，但思维脑图还没有生成（可能流式生成失败），则加载已保存的
  if (hasNewCompleted && 
      !mindmapStore.generating && 
      !mindmapStore.loading && 
      !mindmapStore.hasMindMap) {
    console.log('🔄 检测到文档处理完成，但思维脑图未生成，尝试从文件加载...')
    // 延迟一下，确保后端思维脑图生成完成
    setTimeout(async () => {
      try {
        await mindmapStore.loadMindMap(convId)
        // 加载完成后自动渲染
        await nextTick()
        if (mindmapStore.mindmapContent && mindmapContainer.value && Markmap && Transformer) {
          setTimeout(async () => {
            await renderMindMap(mindmapContainer.value, mindmapStore.mindmapContent)
          }, 200)
        }
      } catch (error) {
        console.error('从文件加载思维脑图失败:', error)
      }
    }, 2000) // 延迟2秒，确保后端思维脑图生成完成
  }
}, { deep: true, immediate: false })

// 刷新
const handleRefresh = async () => {
  console.log('🔄 手动刷新思维脑图')

  // 刷新前先销毁主容器中的旧实例和 SVG，避免 Markmap 在旧 SVG 上二次挂载导致错误
  if (mindmapContainer.value) {
    try {
      // 尝试销毁旧的 markmap 实例
      if (markmapInstance.value && typeof markmapInstance.value.destroy === 'function') {
        markmapInstance.value.destroy()
      }
    } catch (e) {
      console.warn('销毁旧 Markmap 实例时出错（忽略）：', e)
    }
    // 清空容器中的 SVG 和其他内容
    mindmapContainer.value.innerHTML = ''
    // 重置实例引用
    markmapInstance.value = null
  }

  if (convStore.currentConversationId) {
    try {
      await mindmapStore.loadMindMap(convStore.currentConversationId)
      console.log('✅ 思维脑图加载完成，内容长度:', mindmapStore.mindmapContent?.length || 0)
      // 刷新后重新渲染
      await nextTick()
      if (mindmapStore.mindmapContent && mindmapContainer.value && Markmap && Transformer) {
        console.log('🔄 开始渲染思维脑图...')
        setTimeout(async () => {
          await renderMindMap(mindmapContainer.value, mindmapStore.mindmapContent)
        }, 200)
      } else {
        console.warn('⚠️ 刷新时渲染条件不满足:', {
          hasContent: !!mindmapStore.mindmapContent,
          hasContainer: !!mindmapContainer.value,
          hasMarkmap: !!Markmap,
          hasTransformer: !!Transformer
        })
      }
    } catch (error) {
      console.error('❌ 刷新思维脑图失败:', error)
    }
  } else {
    console.warn('⚠️ 刷新时没有对话ID')
  }
}

// 全部展开
const handleExpandAll = () => {
  if (!markmapInstance.value || !mindmapStore.mindmapContent) {
    console.warn('⚠️ markmap 实例或内容不存在，无法展开')
    return
  }
  
  try {
    // 直接从 markdown 内容重新解析，确保获取最新数据
    const transformer = getTransformer()
    if (!transformer) {
      console.warn('⚠️ Transformer 不可用')
      return
    }
    
    const result = transformer.transform(mindmapStore.mindmapContent)
    let root = result.root
    
    if (!root) {
      console.warn('⚠️ 无法解析 markdown 数据')
      return
    }
    
    // 递归展开所有节点
    const expandNode = (node) => {
      if (node && typeof node === 'object') {
        // 设置节点状态为展开（collapsed: false 表示展开）
        if (!node.state) {
          node.state = {}
        }
        node.state.collapsed = false
        
        // 递归处理子节点
        if (node.children && Array.isArray(node.children)) {
          node.children.forEach(expandNode)
        }
      }
    }
    
    // 展开根节点及其所有子节点
    expandNode(root)
    
    // 更新数据以应用展开状态
    markmapInstance.value.setData(root)
    if (typeof markmapInstance.value.fit === 'function') {
      markmapInstance.value.fit()
    }
    
    console.log('✅ 已展开所有节点')
  } catch (error) {
    console.error('❌ 展开所有节点失败:', error)
  }
}

// 全屏
const handleFullscreen = async () => {
  fullscreenVisible.value = true
  await nextTick()
  if (fullscreenContainer.value && mindmapStore.mindmapContent) {
    await renderMindMap(fullscreenContainer.value, mindmapStore.mindmapContent)
  }
}

// 组件挂载
onMounted(async () => {
  console.log('🔄 MindMapViewer 组件挂载')
  if (convStore.currentConversationId) {
    console.log('🔄 组件挂载，自动加载思维脑图，对话ID:', convStore.currentConversationId)
    try {
      await mindmapStore.loadMindMap(convStore.currentConversationId)
      console.log('✅ 思维脑图加载完成，内容长度:', mindmapStore.mindmapContent?.length || 0)
      // 加载完成后自动渲染
      await nextTick()
      if (mindmapStore.mindmapContent && mindmapContainer.value && Markmap && Transformer) {
        console.log('🔄 开始渲染思维脑图...')
        setTimeout(async () => {
          await renderMindMap(mindmapContainer.value, mindmapStore.mindmapContent)
        }, 300)
      } else {
        console.warn('⚠️ 渲染条件不满足:', {
          hasContent: !!mindmapStore.mindmapContent,
          hasContainer: !!mindmapContainer.value,
          hasMarkmap: !!Markmap,
          hasTransformer: !!Transformer
        })
      }
    } catch (error) {
      console.error('组件挂载时加载思维脑图失败:', error)
    }
  } else {
    console.warn('⚠️ 组件挂载时没有对话ID')
  }
})

// 组件卸载
onUnmounted(() => {
  if (markmapInstance.value) {
    markmapInstance.value = null
  }
  if (fullscreenMarkmapInstance) {
    fullscreenMarkmapInstance = null
  }
})
</script>

<style scoped>
.mindmap-viewer-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.mindmap-viewer-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.mindmap-stats {
  font-size: 12px;
  color: #909399;
}

.header-right {
  display: flex;
  gap: 8px;
}

.mindmap-container {
  flex: 1;
  position: relative;
  min-height: 400px;
  overflow: hidden;
}

.mindmap-loading,
.mindmap-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  gap: 16px;
}

.generating-text {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #606266;
}

.mindmap-wrapper {
  width: 100%;
  height: 100%;
  min-height: 400px;
  position: relative;
  overflow: hidden;
}

.mindmap-canvas {
  width: 100%;
  height: 100%;
  min-height: 400px;
  position: relative;
  overflow: auto;
  background-color: #fff;
  /* 确保容器内只有 SVG，没有文本 */
  font-size: 0;
  line-height: 0;
}

.mindmap-canvas.generating {
  opacity: 0.9;
}

.generating-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.8));
  padding: 20px;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-radius: 0 0 8px 8px;
}

.mindmap-canvas :deep(svg) {
  width: 100% !important;
  height: 100% !important;
  display: block !important;
  min-height: 400px;
  position: relative;
  z-index: 1;
}

.mindmap-canvas :deep(.markmap) {
  width: 100%;
  height: 100%;
}

.mindmap-canvas :deep(g) {
  display: block;
}

/* 隐藏容器内的文本节点和非 SVG 元素 */
.mindmap-canvas > *:not(svg) {
  display: none !important;
}

.mindmap-fullscreen-dialog :deep(.el-dialog__body) {
  padding: 0;
  height: 80vh;
}

.fullscreen-mindmap-container {
  width: 100%;
  height: 100%;
  min-height: 600px;
}
</style>

