<template>
  <div class="conversation-sidebar">
    <!-- 对话管理区域 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header">
          <span>对话管理</span>
          <el-button 
            type="primary" 
            size="small" 
            :icon="Plus"
            @click="handleCreateConversation"
            :loading="convStore.loading"
          >
            新建
          </el-button>
        </div>
      </template>
      
      <div class="conversation-list">
        <div
          v-for="conv in convStore.conversations"
          :key="conv.conversation_id"
          class="conversation-item"
          :class="{ active: conv.conversation_id === convStore.currentConversationId }"
          @click="handleSelectConversation(conv.conversation_id)"
        >
          <div class="conv-info">
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-meta">
              <span>{{ conv.file_count || 0 }} 个文档</span>
            </div>
          </div>
          <el-button
            text
            type="danger"
            size="small"
            :icon="Delete"
            @click.stop="handleDeleteConversation(conv.conversation_id)"
          />
        </div>
        
        <el-empty 
          v-if="convStore.conversationCount === 0"
          description="暂无对话"
          :image-size="80"
        />
      </div>
    </el-card>
    
    <!-- 文档管理区域 -->
    <el-card class="section-card" shadow="never" v-if="convStore.currentConversationId">
      <template #header>
        <div class="section-header">
          <span>文档管理</span>
        </div>
      </template>
      
      <div class="document-upload">
        <el-upload
          :http-request="handleUpload"
          :before-upload="handleBeforeUpload"
          :multiple="true"
          :limit="5"
          :show-file-list="false"
          :disabled="docStore.uploading"
        >
          <el-button 
            type="primary" 
            :icon="Upload" 
            size="small" 
            style="width: 100%;"
            :loading="docStore.uploading"
            :disabled="docStore.uploading"
          >
            {{ docStore.uploading ? '上传中...' : '上传文档' }}
          </el-button>
        </el-upload>
        <div class="upload-tip">支持 .pptx 和 .pdf，最大 50MB</div>
        
        <!-- 上传进度条 -->
        <div v-if="docStore.uploading" class="upload-progress">
          <div class="progress-info">
            <span class="progress-text">{{ docStore.uploadingFileName }}</span>
            <span class="progress-percent">{{ docStore.uploadProgress }}%</span>
          </div>
          <el-progress 
            :percentage="docStore.uploadProgress" 
            :status="docStore.uploadProgress === 100 ? 'success' : ''"
            :stroke-width="6"
          />
        </div>
        
        <!-- 知识提取进度 -->
        <div v-if="extractionProgressList.length > 0" class="extraction-progress">
          <div class="extraction-title">知识提取进度(约10min/个文档)</div>
          <div 
            v-for="progress in extractionProgressList" 
            :key="progress.fileId"
            class="extraction-item"
          >
            <div class="extraction-info">
              <span class="extraction-file-name">{{ progress.fileName }}</span>
              <span 
                class="extraction-status"
                :class="getStatusClass(progress.status)"
              >
                {{ getStatusText(progress.status, progress.stage) }}
              </span>
            </div>
            <el-progress 
              :percentage="progress.progress" 
              :status="getProgressStatus(progress.status)"
              :stroke-width="5"
            />
            <!-- 错误信息 -->
            <div v-if="progress.error" class="extraction-error">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ progress.error }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <div class="document-list">
        <div
          v-for="doc in documents"
          :key="doc.file_id"
          class="document-item"
          :class="{ active: currentDocumentId === doc.file_id }"
          @click.stop="handleSelectDocument(doc.file_id)"
        >
          <el-icon class="doc-icon"><Document /></el-icon>
          <div class="doc-info" @click.stop="handleSelectDocument(doc.file_id)">
            <div class="doc-name">{{ doc.filename }}</div>
            <div class="doc-meta">
              <el-tag :type="getStatusType(doc.status)" size="small">
                {{ doc.status }}
              </el-tag>
            </div>
          </div>
          <el-button
            text
            type="danger"
            :icon="Delete"
            size="small"
            class="delete-btn"
            @click.stop="handleDeleteDocument(doc.file_id, doc.filename)"
            :loading="deletingFileId === doc.file_id"
          />
        </div>
        
        <el-empty
          v-if="documents.length === 0"
          description="暂无文档"
          :image-size="60"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Plus, Delete, Upload, Document, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useConversationStore } from '../../stores/conversationStore'
import { useDocumentStore } from '../../stores/documentStore'

const emit = defineEmits(['document-select'])

const convStore = useConversationStore()
const docStore = useDocumentStore()

const currentDocumentId = ref(null)
const deletingFileId = ref(null) // 正在删除的文件ID

// 知识提取进度列表
const extractionProgressList = computed(() => {
  if (!convStore.currentConversationId) return []
  return docStore.getExtractionProgress(convStore.currentConversationId)
})

// 当前对话的文档列表
const documents = computed(() => {
  if (!convStore.currentConversationId) return []
  // getDocumentsByConversation 是一个 computed，返回函数，需要调用
  return docStore.getDocumentsByConversation(convStore.currentConversationId)
})

// 监听对话变化，加载文档列表
watch(() => convStore.currentConversationId, async (newId) => {
  if (newId) {
    try {
      await docStore.loadDocuments(newId)
      currentDocumentId.value = null // 重置选中的文档
    } catch (error) {
      console.error('加载文档列表失败:', error)
    }
  }
}, { immediate: true })

onMounted(async () => {
  // 加载对话列表
  try {
    await convStore.loadConversations()
  } catch (error) {
    console.error('加载对话列表失败:', error)
  }
})

// 创建对话
const handleCreateConversation = async () => {
  try {
    const conversation = await convStore.createConversation()
    ElMessage.success(`创建成功: ${conversation.title}`)
    convStore.selectConversation(conversation.conversation_id)
  } catch (error) {
    console.error('创建对话失败:', error)
    ElMessage.error('创建对话失败')
  }
}

// 选择对话
const handleSelectConversation = (conversationId) => {
  convStore.selectConversation(conversationId)
}

// 删除对话
const handleDeleteConversation = async (conversationId) => {
  try {
    await convStore.deleteConversation(conversationId)
    ElMessage.success('删除成功')
    if (conversationId === currentDocumentId.value) {
      currentDocumentId.value = null
    }
  } catch (error) {
    console.error('删除对话失败:', error)
    ElMessage.error('删除对话失败')
  }
}

// 文件上传前验证
const handleBeforeUpload = (file) => {
  const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']
  if (!allowedTypes.includes(file.type)) {
    ElMessage.error('仅支持 .pdf 和 .pptx 格式')
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

// 处理文件上传
const handleUpload = async (options) => {
  const { file } = options
  if (!convStore.currentConversationId) {
    ElMessage.warning('请先选择或创建一个对话')
    return
  }
  
  try {
    const response = await docStore.uploadDocuments(convStore.currentConversationId, file)
    ElMessage.success('上传成功')
    
    // 如果自动创建了对话，选择它
    if (response.conversation_id && response.conversation_id !== convStore.currentConversationId) {
      await convStore.loadConversation(response.conversation_id)
      convStore.selectConversation(response.conversation_id)
    }
    
    // 重新加载文档列表
    await docStore.loadDocuments(convStore.currentConversationId)
  } catch (error) {
    console.error('上传失败:', error)
    ElMessage.error('上传失败')
  }
}

// 选择文档
const handleSelectDocument = (fileId) => {
  currentDocumentId.value = fileId
  emit('document-select', fileId)
}

// 删除文档
const handleDeleteDocument = async (fileId, filename) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${filename}" 吗？此操作不可恢复，将从知识图谱中移除相关数据。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    deletingFileId.value = fileId
    
    try {
      await docStore.deleteDocument(convStore.currentConversationId, fileId)
      ElMessage.success('删除成功')
      
      // 如果删除的是当前选中的文档，清空选中
      if (currentDocumentId.value === fileId) {
        currentDocumentId.value = null
        emit('document-select', null)
      }
      
      // 清理该文件的提取进度
      docStore.removeExtractionProgress?.(convStore.currentConversationId, fileId)
    } catch (error) {
      console.error('删除文档失败:', error)
      ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message || '未知错误'))
    } finally {
      deletingFileId.value = null
    }
  } catch {
    // 用户取消删除
  }
}

// 获取状态类型
const getStatusType = (status) => {
  const statusMap = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return statusMap[status] || 'info'
}

// 获取知识提取状态文本
const getStatusText = (status, stage = null) => {
  const statusMap = {
    pending: '等待处理',
    processing: '处理中...',
    completed: '已完成',
    failed: '处理失败'
  }
  
  let text = statusMap[status] || status
  
  // 如果正在处理且有阶段信息，显示阶段
  if (status === 'processing' && stage) {
    const stageMap = {
      chunking: '文档分块',
      storing: '存储中',
      extracting: '实体提取',
      merging: '合并图谱',
      completed: '完成'
    }
    const stageText = stageMap[stage] || stage
    text = `${text} (${stageText})`
  }
  
  return text
}

// 获取知识提取状态样式类
const getStatusClass = (status) => {
  return {
    'status-pending': status === 'pending',
    'status-processing': status === 'processing',
    'status-completed': status === 'completed',
    'status-failed': status === 'failed'
  }
}

// 获取进度条状态
const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return ''
}

// 监听对话变化，清理提取进度监控
watch(() => convStore.currentConversationId, (newId, oldId) => {
  if (oldId) {
    // 停止旧对话的监控（可选，如果希望切换对话时继续显示进度）
    // docStore.stopExtractionProgress(oldId)
  }
}, { immediate: false })

// 组件卸载时清理所有轮询
onUnmounted(() => {
  if (convStore.currentConversationId) {
    docStore.stopExtractionProgress(convStore.currentConversationId)
  }
})
</script>

<style scoped>
.conversation-sidebar {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px;
  gap: 12px;
}

.section-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conversation-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.conversation-item:hover {
  background-color: #f0f0f0;
}

.conversation-item.active {
  background-color: #ecf5ff;
  border: 1px solid #409eff;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.document-upload {
  margin-bottom: 12px;
}

.upload-tip {
  font-size: 12px;
  color: #909399;
  text-align: center;
  margin-top: 6px;
}

.upload-progress {
  margin-top: 12px;
  padding: 8px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.progress-text {
  color: #606266;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.progress-percent {
  color: #409eff;
  font-weight: 500;
  flex-shrink: 0;
}

.extraction-progress {
  margin-top: 12px;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.extraction-title {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 10px;
}

.extraction-item {
  margin-bottom: 12px;
}

.extraction-item:last-child {
  margin-bottom: 0;
}

.extraction-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.extraction-file-name {
  color: #606266;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.extraction-status {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
}

.status-pending {
  color: #909399;
  background-color: #f4f4f5;
}

.status-processing {
  color: #e6a23c;
  background-color: #fdf6ec;
}

.status-completed {
  color: #67c23a;
  background-color: #f0f9ff;
}

.status-failed {
  color: #f56c6c;
  background-color: #fef0f0;
}

.extraction-error {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  padding: 6px 8px;
  background-color: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 4px;
  font-size: 11px;
  color: #f56c6c;
}

.extraction-error .el-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.document-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
  position: relative;
}

.document-item:hover {
  background-color: #f0f0f0;
}

.document-item:hover .delete-btn {
  opacity: 1;
}

.document-item.active {
  background-color: #ecf5ff;
  border: 1px solid #409eff;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
  margin-left: auto;
  flex-shrink: 0;
}

.delete-btn:hover {
  color: #f56c6c;
}

.doc-icon {
  font-size: 20px;
  color: #409eff;
  flex-shrink: 0;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  margin-top: 4px;
}
</style>

