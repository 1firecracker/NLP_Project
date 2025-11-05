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
            <div class="message-text" v-html="formatMessageWithWarning(message.content)"></div>
            <div class="message-time">{{ formatTime(message.timestamp) }}</div>
          </div>
        </div>
      </div>
      
      <!-- 流式输出中显示加载 -->
      <div v-if="isStreaming" class="message assistant-message">
        <div class="message-content">
          <div class="message-text">
            <span v-if="currentStreamWarning" class="warning-text" v-html="formatMarkdown(currentStreamWarning)"></span>
            <span v-if="currentStreamWarning && currentStreamContent" v-html="formatMarkdown('\n\n')"></span>
            <span v-html="formatMarkdown(currentStreamContent)"></span>
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
          <el-option label="混合模式" value="mix" />
          <el-option label="本地模式" value="local" />
          <el-option label="全局模式" value="global" />
          <el-option label="简单模式" value="naive" />
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
const selectedMode = ref('mix')
const isStreaming = ref(false)
const currentStreamContent = ref('')
const currentStreamWarning = ref('')

// 消息列表（从 chatStore 获取）
const messages = computed(() => {
  if (!convStore.currentConversationId) return []
  return chatStore.getMessages(convStore.currentConversationId)
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
      chatStore.addMessage(convStore.currentConversationId, {
        role: 'assistant',
        content: fullContent,
        timestamp: Date.now()
      })
      
      // 保存到后端
      await chatStore.saveMessage(convStore.currentConversationId, query, fullContent)
    }
    
    currentStreamContent.value = ''
    currentStreamWarning.value = ''
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

// 简单的 Markdown 格式化（基础版本）
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

// 格式化消息，识别警告提示并应用斜体样式
const formatMessageWithWarning = (text) => {
  if (!text) return ''
  
  // 先转义 HTML
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  // 处理警告提示（以 ⚠️ 开头，到第一个换行或文本结束）
  const warningPattern = /(⚠️[^：:]*[：:][^\n]*)/
  html = html.replace(warningPattern, '<span class="warning-text">$1</span>')
  
  // 处理其他 Markdown 格式
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
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
</style>

