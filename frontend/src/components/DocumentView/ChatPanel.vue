<template>
  <div class="chat-panel">
    <!-- 消息列表区域 -->
    <div class="messages-container" ref="messagesContainer">
      <div v-if="messages.length === 0" class="empty-state">
        <el-empty description="开始对话吧！" :image-size="120" />
      </div>
      
      <div v-for="(message, index) in messages" :key="index" class="message-wrapper">
        <!-- 用户消息 -->
        <div v-if="message.role === 'user'" class="message user-message">
          <div class="message-content">
            <div class="message-text">{{ message.content }}</div>
            <div class="message-time">{{ formatTime(message.timestamp) }}</div>
          </div>
        </div>
        
        <!-- AI 回复 -->
        <div v-else class="message assistant-message">
          <div class="message-content">
            <!-- Think 内容折叠栏（在顶部） -->
            <div v-if="hasThinkContent(message.content)" class="think-section">
              <el-collapse v-model="thinkCollapseStates">
                <el-collapse-item :name="index" :title="'Thinking Process'" class="think-collapse">
                  <div class="think-content" v-html="formatThinkContent(message.content)"></div>
                </el-collapse-item>
              </el-collapse>
            </div>
            <div class="message-text" v-html="formatMessageWithWarning(message.content)"></div>
            <div class="message-time">{{ formatTime(message.timestamp) }}</div>
          </div>
        </div>
      </div>
      
      <!-- 流式输出中显示加载 -->
      <div v-if="isStreaming" class="message assistant-message">
        <div class="message-content">
          <!-- Think 内容折叠栏（在顶部） -->
          <div v-if="hasStreamingThinkContent" class="think-section">
            <el-collapse v-model="streamingThinkCollapse">
              <el-collapse-item name="streaming" :title="'Thinking Process'" class="think-collapse">
                <div class="think-content" v-html="formatThinkContent(currentStreamContent)"></div>
              </el-collapse-item>
            </el-collapse>
          </div>
          <div class="message-text">
            <span v-if="currentStreamWarning" class="warning-text" v-html="formatMarkdown(currentStreamWarning)"></span>
            <span v-if="currentStreamWarning && currentStreamContent" v-html="formatMarkdown('\n\n')"></span>
            <span v-html="formatMessageWithWarning(currentStreamContent)"></span>
            <span class="streaming-cursor">|</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 输入区域 -->
    <div class="input-container">
      <div class="input-toolbar">
        <el-select
          v-model="selectedMode"
          size="small"
          style="width: 120px;"
          placeholder="查询模式"
        >
          <el-option label="简单模式" value="naive" />
          <el-option label="混合模式" value="mix" />
          <el-option label="本地模式" value="local" />
          <el-option label="全局模式" value="global" /> 
        </el-select>
      </div>
      
      <div class="input-area">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="输入您的问题..."
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.exact="handleNewLine"
        />
        <div class="input-actions">
          <el-button
            type="primary"
            :icon="Promotion"
            @click="handleSend"
            :loading="isStreaming"
            :disabled="!inputText.trim() || !convStore.currentConversationId"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useConversationStore } from '../../stores/conversationStore'
import { useChatStore } from '../../stores/chatStore'
import { useGraphStore } from '../../stores/graphStore'

const convStore = useConversationStore()
const chatStore = useChatStore()
const graphStore = useGraphStore()

const messagesContainer = ref(null)
const inputText = ref('')
const selectedMode = ref('naive')
const isStreaming = ref(false)
const currentStreamContent = ref('')
const currentStreamWarning = ref('')
const thinkCollapseStates = ref([]) // 存储展开的消息索引数组（el-collapse需要数组）
const streamingThinkCollapse = ref([]) // 流式输出时的think折叠状态（默认折叠，空数组）

// 消息列表（从 chatStore 获取）
const messages = computed(() => {
  if (!convStore.currentConversationId) return []
  return chatStore.getMessages(convStore.currentConversationId)
})

// 计算属性：流式输出时是否有think内容（确保响应式更新）
const hasStreamingThinkContent = computed(() => {
  return hasThinkContent(currentStreamContent.value)
})

// 监听对话变化，加载历史消息和图谱
watch(() => convStore.currentConversationId, async (newId) => {
  if (newId) {
    await chatStore.loadMessages(newId)
    // 同时加载图谱数据
    try {
      await graphStore.loadGraph(newId)
    } catch (error) {
      console.error('加载图谱失败:', error)
    }
  } else {
    chatStore.clearMessages()
    graphStore.clearGraph()
  }
}, { immediate: true })

// 监听消息变化，滚动到底部
watch(() => messages.value.length, () => {
  nextTick(() => {
    scrollToBottom()
  })
})

// 滚动到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 发送消息
const handleSend = async () => {
  if (!inputText.value.trim() || !convStore.currentConversationId) {
    return
  }
  
  const query = inputText.value.trim()
  inputText.value = ''
  
  // 添加用户消息到本地
  chatStore.addMessage(convStore.currentConversationId, {
    role: 'user',
    content: query,
    timestamp: Date.now()
  })
  
  // 开始流式查询
  isStreaming.value = true
  currentStreamContent.value = ''
  currentStreamWarning.value = ''
  streamingThinkCollapse.value = [] // 重置流式think折叠状态（默认折叠）
  
  try {
    await chatStore.queryStream(convStore.currentConversationId, query, selectedMode.value, (chunk) => {
      // 检查是否是警告消息
      if (typeof chunk === 'object' && chunk.type === 'warning') {
        currentStreamWarning.value = chunk.content
      } else if (typeof chunk === 'string') {
        // 普通响应内容
        currentStreamContent.value += chunk
      }
      nextTick(() => {
        scrollToBottom()
      })
    })
    
    // 流式结束，保存完整回复（包含警告提示）
    let fullContent = ''
    if (currentStreamWarning.value) {
      fullContent = currentStreamWarning.value + '\n\n'
    }
    if (currentStreamContent.value) {
      fullContent += currentStreamContent.value
    }
    
    if (fullContent) {
      const newMessageIndex = messages.value.length
      chatStore.addMessage(convStore.currentConversationId, {
        role: 'assistant',
        content: fullContent,
        timestamp: Date.now()
      })
      
      // 如果新消息包含think内容，确保默认折叠（不在thinkCollapseStates数组中）
      if (hasThinkContent(fullContent)) {
        // 确保新消息的索引不在折叠状态数组中（默认折叠）
        nextTick(() => {
          const index = thinkCollapseStates.value.indexOf(newMessageIndex)
          if (index > -1) {
            thinkCollapseStates.value.splice(index, 1)
          }
        })
      }
      
      // 保存到后端
      await chatStore.saveMessage(convStore.currentConversationId, query, fullContent)
    }
    
    currentStreamContent.value = ''
    currentStreamWarning.value = ''
    streamingThinkCollapse.value = [] // 重置流式think折叠状态
  } catch (error) {
    console.error('查询失败:', error)
    ElMessage.error('查询失败，请重试')
    
    // 添加错误消息
    chatStore.addMessage(convStore.currentConversationId, {
      role: 'assistant',
      content: '抱歉，查询失败。请检查网络连接或稍后重试。',
      timestamp: Date.now()
    })
  } finally {
    isStreaming.value = false
    nextTick(() => {
      scrollToBottom()
    })
  }
}

// Shift+Enter 换行
const handleNewLine = () => {
  // 默认行为是换行，不需要特殊处理
}

// 格式化时间
const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

// 检查是否有 think 内容（支持流式输出时的部分标签）
const hasThinkContent = (text) => {
  if (!text) return false
  // 检测开始标签即可（支持流式输出时标签未闭合的情况）
  return /<(?:think|redacted_reasoning)>/i.test(text)
}

// 提取并格式化 think 内容（支持流式输出时的部分内容）
const formatThinkContent = (text) => {
  if (!text) return ''
  
  // 支持 <think> 和 <think> 两种标签
  // 先尝试匹配完整的标签对
  let thinkMatch = text.match(/<(?:think|redacted_reasoning)>([\s\S]*?)<\/(?:think|redacted_reasoning)>/i)
  
  // 如果没匹配到完整标签对，尝试匹配只有开始标签的情况（流式输出中）
  if (!thinkMatch) {
    const openTagMatch = text.match(/<(?:think|redacted_reasoning)>([\s\S]*)$/i)
    if (openTagMatch) {
      thinkMatch = openTagMatch
    } else {
      return ''
    }
  }
  
  let thinkText = thinkMatch[1] || ''
  
  // 转义 HTML
  let html = thinkText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  // 应用增强的 Markdown 格式化
  html = formatEnhancedMarkdown(html)
  
  return html
}

// 格式化消息，识别警告提示并应用斜体样式，移除 think 标签
const formatMessageWithWarning = (text) => {
  if (!text) return ''
  
  // 先移除 think 标签（不在主内容中显示），支持两种标签格式
  // 先移除完整的标签对
  let content = text.replace(/<(?:think|redacted_reasoning)>[\s\S]*?<\/(?:think|redacted_reasoning)>/gi, '')
  // 再移除未闭合的开始标签及其内容（流式输出时的情况）
  content = content.replace(/<(?:think|redacted_reasoning)>[\s\S]*$/gi, '')
  
  // 先转义 HTML
  let html = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  // 处理警告提示（以 ⚠️ 开头，到第一个换行或文本结束）
  const warningPattern = /(⚠️[^：:]*[：:][^\n]*)/
  html = html.replace(warningPattern, '<span class="warning-text">$1</span>')
  
  // 处理增强的 Markdown 格式
  html = formatEnhancedMarkdown(html)
  
  return html
}

// 增强的 Markdown 格式化
const formatEnhancedMarkdown = (text) => {
  if (!text) return ''
  
  let html = text
  
  // 代码块（先处理，避免被其他规则影响）
  html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
  
  // 处理表格（在代码块之后，避免代码块内的表格被处理）
  html = html.replace(/\|(.+)\|\s*\n\|[\s\-|:]+\|\s*\n((?:\|.+\|\s*\n?)+)/g, (match, header, rows) => {
    const headers = header.split('|').map(h => h.trim()).filter(h => h)
    if (headers.length === 0) return match
    const headerHtml = headers.map(h => `<th>${h}</th>`).join('')
    const rowsHtml = rows.trim().split('\n').filter(row => row.trim()).map(row => {
      const cells = row.split('|').map(c => c.trim()).filter(c => c)
      return `<tr>${cells.map(cell => `<td>${cell}</td>`).join('')}</tr>`
    }).join('')
    return `<table class="markdown-table"><thead><tr>${headerHtml}</tr></thead><tbody>${rowsHtml}</tbody></table>`
  })
  
  // 标题（#### 到 #）
  html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>')
  
  // 处理无序列表（- 开头）
  // 按行处理，将连续的列表项组合（跳过已处理的HTML标签）
  const lines = html.split('\n')
  const processedLines = []
  let inList = false
  let listItems = []
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()
    // 跳过已处理的HTML标签（标题、代码块、表格等）
    if (line.startsWith('<') && (line.startsWith('<h') || line.startsWith('<pre') || line.startsWith('<code') || line.startsWith('<table'))) {
      if (inList) {
        processedLines.push(`<ul>${listItems.map(item => `<li>${item}</li>`).join('')}</ul>`)
        inList = false
        listItems = []
      }
      processedLines.push(lines[i])
      continue
    }
    
    const listMatch = line.match(/^-\s+(.+)$/)
    
    if (listMatch) {
      if (!inList) {
        inList = true
        listItems = []
      }
      listItems.push(listMatch[1])
    } else {
      if (inList) {
        // 结束列表
        processedLines.push(`<ul>${listItems.map(item => `<li>${item}</li>`).join('')}</ul>`)
        inList = false
        listItems = []
      }
      processedLines.push(lines[i])
    }
  }
  
  // 处理末尾的列表
  if (inList && listItems.length > 0) {
    processedLines.push(`<ul>${listItems.map(item => `<li>${item}</li>`).join('')}</ul>`)
  }
  
  html = processedLines.join('\n')
  
  // 处理有序列表（数字. 开头）
  const lines2 = html.split('\n')
  const processedLines2 = []
  let inOrderedList = false
  let orderedListItems = []
  
  for (let i = 0; i < lines2.length; i++) {
    const line = lines2[i].trim()
    // 跳过已处理的HTML标签
    if (line.startsWith('<') && (line.startsWith('<h') || line.startsWith('<pre') || line.startsWith('<code') || line.startsWith('<ul') || line.startsWith('<table'))) {
      if (inOrderedList) {
        processedLines2.push(`<ol>${orderedListItems.map(item => `<li>${item}</li>`).join('')}</ol>`)
        inOrderedList = false
        orderedListItems = []
      }
      processedLines2.push(lines2[i])
      continue
    }
    
    const orderedMatch = line.match(/^\d+\.\s+(.+)$/)
    
    if (orderedMatch) {
      if (!inOrderedList) {
        inOrderedList = true
        orderedListItems = []
      }
      orderedListItems.push(orderedMatch[1])
    } else {
      if (inOrderedList) {
        // 结束列表
        processedLines2.push(`<ol>${orderedListItems.map(item => `<li>${item}</li>`).join('')}</ol>`)
        inOrderedList = false
        orderedListItems = []
      }
      processedLines2.push(lines2[i])
    }
  }
  
  // 处理末尾的有序列表
  if (inOrderedList && orderedListItems.length > 0) {
    processedLines2.push(`<ol>${orderedListItems.map(item => `<li>${item}</li>`).join('')}</ol>`)
  }
  
  html = processedLines2.join('\n')
  
  // 粗体
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  
  // 换行（但保留在代码块、列表和表格中的换行）
  // 先标记已处理的块
  const blocks = []
  html = html.replace(/(<pre>[\s\S]*?<\/pre>|<ul>[\s\S]*?<\/ul>|<ol>[\s\S]*?<\/ol>|<h[1-4]>.*?<\/h[1-4]>|<table[\s\S]*?<\/table>)/g, (match) => {
    const id = `___BLOCK_${blocks.length}___`
    blocks.push(match)
    return id
  })
  // 处理剩余换行
  html = html.replace(/\n/g, '<br>')
  // 恢复块
  blocks.forEach((block, index) => {
    html = html.replace(`___BLOCK_${index}___`, block)
  })
  
  return html
}

// 简单的 Markdown 格式化（基础版本，保留用于流式输出）
const formatMarkdown = (text) => {
  if (!text) return ''
  
  // 转义 HTML
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  // 粗体
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  
  // 代码块
  html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
  
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  
  // 换行
  html = html.replace(/\n/g, '<br>')
  
  return html
}
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #fff;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-wrapper {
  display: flex;
}

.message {
  max-width: 80%;
  display: flex;
}

.user-message {
  margin-left: auto;
}

.assistant-message {
  margin-right: auto;
}

.message-content {
  padding: 12px 16px;
  border-radius: 8px;
  position: relative;
}

.user-message .message-content {
  background-color: #409eff;
  color: #fff;
}

.assistant-message .message-content {
  background-color: #f0f2f5;
  color: #303133;
}

.message-text {
  line-height: 1.6;
  word-wrap: break-word;
}

.message-text :deep(code) {
  background-color: rgba(0, 0, 0, 0.1);
  padding: 2px 4px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
}

.message-text :deep(pre) {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 8px 0;
}

.warning-text {
  font-style: italic;
  color: #909399;
}

.message-time {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
  margin-top: 6px;
}

.assistant-message .message-time {
  color: #909399;
}

.streaming-cursor {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.input-container {
  border-top: 1px solid #e4e7ed;
  padding: 12px;
  background-color: #fff;
}

.input-toolbar {
  margin-bottom: 8px;
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
}

/* Think 内容样式 */
.think-section {
  margin-top: 0;
  margin-bottom: 5px;
  border-bottom: 1px solid #e4e7ed;
  border-radius: 6px;
  background-color: #fafbfc;
  padding: 3px 8px;
}

.think-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: #909399;
  padding: 3px 0;
  height: auto;
  line-height: 1.5;
  border-radius: 4px;
  background-color: transparent;
}

.think-collapse :deep(.el-collapse-item__content) {
  padding: 0;
  padding-bottom: 3px;
}

.think-content {
  background-color: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: #606266;
  margin-top: 8px;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
}

.think-content :deep(h1),
.think-content :deep(h2),
.think-content :deep(h3),
.think-content :deep(h4) {
  margin: 8px 0 4px 0;
  font-weight: 600;
  color: #303133;
}

.think-content :deep(h1) { font-size: 18px; }
.think-content :deep(h2) { font-size: 16px; }
.think-content :deep(h3) { font-size: 14px; }
.think-content :deep(h4) { font-size: 13px; }

.think-content :deep(ul),
.think-content :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.think-content :deep(li) {
  margin: 4px 0;
}

/* 主消息内容也支持增强的 Markdown */
.message-text :deep(h1),
.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(h4) {
  margin: 12px 0 6px 0;
  font-weight: 600;
}

.message-text :deep(h1) { font-size: 20px; }
.message-text :deep(h2) { font-size: 18px; }
.message-text :deep(h3) { font-size: 16px; }
.message-text :deep(h4) { font-size: 14px; }

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.message-text :deep(li) {
  margin: 4px 0;
  list-style-type: disc;
}

.message-text :deep(ol li) {
  list-style-type: decimal;
}

.message-text :deep(table.markdown-table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 14px;
}

.message-text :deep(table.markdown-table th),
.message-text :deep(table.markdown-table td) {
  border: 1px solid #e4e7ed;
  padding: 8px 12px;
  text-align: left;
}

.message-text :deep(table.markdown-table th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

.message-text :deep(table.markdown-table tr:nth-child(even)) {
  background-color: #fafafa;
}
</style>

