<template>
  <div class="exercise-viewer">
    <!-- 样本试题栏（可展开/收起） -->
    <el-card class="sample-section" shadow="never">
      <template #header>
        <div class="section-header" @click="toggleSampleSection">
          <el-icon class="toggle-icon" :class="{ 'collapsed': sampleSectionCollapsed }">
            <ArrowDown />
          </el-icon>
          <span class="section-title">样本试题栏</span>
          <el-tag v-if="samples.length > 0" size="small" type="info">
            {{ samples.length }} 个样本
          </el-tag>
        </div>
      </template>
      
      <div v-show="!sampleSectionCollapsed" class="sample-content">
        <!-- 上传区域 -->
        <div class="upload-area">
          <el-upload
            ref="uploadRef"
            :http-request="handleCustomUpload"
            :file-list="fileList"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :on-remove="handleRemove"
            :before-upload="beforeUpload"
            :limit="50"
            :auto-upload="true"
            multiple
            drag
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              将文件拖到此处，或<em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                支持 PDF、DOCX、TXT 格式，单个文件不超过 50MB
              </div>
            </template>
          </el-upload>
        </div>
        
        <!-- 样本列表 -->
        <div v-if="samples.length > 0" class="sample-list">
          <el-table :data="samples" stripe style="width: 100%">
            <el-table-column prop="filename" label="文件名" min-width="200" />
            <el-table-column prop="file_type" label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small">{{ row.file_type.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag 
                  size="small" 
                  :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'"
                >
                  {{ row.status === 'completed' ? '已完成' : row.status === 'pending' ? '解析中' : row.status === 'processing' ? '解析中' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="image_count" label="图片数" width="80" />
            <el-table-column prop="text_length" label="文本长度" width="120">
              <template #default="{ row }">
                {{ formatFileSize(row.text_length) }}
              </template>
            </el-table-column>
            <el-table-column prop="upload_time" label="上传时间" width="180">
              <template #default="{ row }">
                {{ formatTime(row.upload_time) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  size="small"
                  @click="viewSample(row)"
                >
                  查看
                </el-button>
                <el-button
                  link
                  type="danger"
                  size="small"
                  @click="deleteSample(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-card>
    
    <!-- 生成结果区域 -->
    <div class="result-section" :class="{ 'full-height': sampleSectionCollapsed }">
      <el-card shadow="never" class="result-card">
        <template #header>
          <div class="result-header">
            <span>生成结果</span>
            <el-button
              v-if="samples.length > 0"
              type="primary"
              :icon="MagicStick"
              @click="startGeneration"
              :loading="generating"
            >
              开始生成
            </el-button>
          </div>
        </template>
        
        <div class="result-content scroll-area">
          <el-empty
            v-if="!generating && !generationResult"
            description="暂无生成结果，请先上传样本试题并点击开始生成"
            :image-size="120"
          />

          <div v-else-if="generating" class="generating-status">
            <el-skeleton :rows="5" animated />
            <el-alert
              :title="generationStatus"
              type="info"
              :closable="false"
              style="margin-top: 16px;"
            />
          </div>

          <div v-else-if="generationResult" class="generation-result">
            <!-- 生成结果展示 -->
            <el-alert
              :title="`成功生成 ${generatedQuestions.length || 0} 道试题`"
              type="success"
              :closable="false"
              style="margin-bottom: 16px;"
            />
            <!-- 展示生成的试题摘要 -->
            <div class="questions-summary" v-if="generatedQuestions && generatedQuestions.length">
              <el-descriptions :column="2" border>
                <el-descriptions-item label="试题总数">{{ generatedQuestions.length }} 道</el-descriptions-item>
                <el-descriptions-item label="题型分布">
                  <el-tag v-for="(count, type) in questionTypeStats" :key="type" size="small" style="margin-right: 4px;">
                    {{ type }}: {{ count }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="难度分布">
                  <el-tag v-for="(count, level) in difficultyStats" :key="level" size="small" 
                    :type="level === 'hard' ? 'danger' : level === 'medium' ? 'warning' : 'success'"
                    style="margin-right: 4px;">
                    {{ level }}: {{ count }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="操作">
                  <el-button type="primary" @click="showQuestionsDialog" size="small">
                    查看详情
                  </el-button>
                  <el-button type="success" @click="downloadExamPaper" size="small" style="margin-left: 8px;">
                    下载试卷
                  </el-button>
                </el-descriptions-item>
              </el-descriptions>
            </div>

            <div class="questions-list" v-else>
              <p>暂无试题生成，请先点击上方按钮生成。</p>
            </div>
          </div>
        </div>
      </el-card>
    </div>
    
    <!-- 查看题目详情对话框 -->
    <el-dialog
      v-model="questionsDialogVisible"
      title="生成的试题详情"
      width="900px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-if="generatedQuestions && generatedQuestions.length" class="questions-dialog-content">
        <!-- 题目导航 -->
        <div class="question-navigation">
          <el-button 
            :disabled="currentQuestionIndex === 0"
            @click="prevQuestion"
            size="small"
          >
            上一题
          </el-button>
          <span class="question-progress">
            {{ currentQuestionIndex + 1 }} / {{ generatedQuestions.length }}
          </span>
          <el-button 
            :disabled="currentQuestionIndex === generatedQuestions.length - 1"
            @click="nextQuestion"
            size="small"
          >
            下一题
          </el-button>
        </div>

        <!-- 当前题目展示 -->
        <div v-if="currentQuestion" class="current-question">
          <div class="question-header">
            <h3>{{ currentQuestion.id }}</h3>
            <div class="question-meta">
              <el-tag size="small" type="info">{{ currentQuestion.question_type }}</el-tag>
              <el-tag size="small" 
                :type="currentQuestion.difficulty === 'hard' ? 'danger' : currentQuestion.difficulty === 'medium' ? 'warning' : 'success'"
              >
                {{ currentQuestion.difficulty }}
              </el-tag>
            </div>
          </div>

          <!-- 题目内容（渲染HTML） -->
          <div class="question-stem" v-html="parseQuestionContent(currentQuestion.stem)"></div>

          <!-- 选择题选项 -->
          <div v-if="currentQuestion.options && currentQuestion.options.length > 0" class="question-options">
            <div 
              v-for="(opt, idx) in currentQuestion.options" 
              :key="idx"
              class="option-item"
            >
              <span class="option-label">{{ String.fromCharCode(65 + idx) }}.</span>
              <span v-html="parseQuestionContent(opt)"></span>
            </div>
          </div>

          <!-- 答案 -->
          <div v-if="currentQuestion.answer" class="question-answer">
            <el-divider />
            <div class="answer-section">
              <strong>答案：</strong>
              <span v-html="parseQuestionContent(currentQuestion.answer)"></span>
            </div>
          </div>

          <!-- 解析 -->
          <div v-if="currentQuestion.explanation" class="question-explanation">
            <div class="explanation-section">
              <strong>解析：</strong>
              <span v-html="parseQuestionContent(currentQuestion.explanation)"></span>
            </div>
          </div>

          <!-- 知识点 -->
          <div v-if="currentQuestion.knowledge_points && currentQuestion.knowledge_points.length" class="question-knowledge">
            <el-divider />
            <div class="knowledge-section">
              <strong>知识点：</strong>
              <el-tag 
                v-for="(kp, idx) in currentQuestion.knowledge_points" 
                :key="idx"
                size="small"
                style="margin-right: 4px;"
              >
                {{ kp }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="questionsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 查看样本详情对话框 -->
    <el-dialog
      v-model="viewSampleDialogVisible"
      :title="currentSample ? `查看样本: ${currentSample.filename}` : '查看样本'"
      width="800px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-if="loadingDetail" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>
      
      <div v-else-if="sampleDetail" class="sample-detail-container">
        <!-- 文件预览区域 -->
        <div class="file-preview-area">
          <div class="preview-header">
            <span class="file-info">
              <el-tag size="small" type="info">{{ sampleDetail.file_type?.toUpperCase() }}</el-tag>
              <span style="margin-left: 8px;">{{ sampleDetail.filename }}</span>
            </span>
            <el-button
              type="primary"
              size="small"
              @click="copyText"
              :icon="DocumentCopy"
            >
              复制文本
            </el-button>
          </div>
          
          <div class="preview-content">
            <!-- PDF 预览 -->
            <iframe
              v-if="sampleDetail.file_type === 'pdf'"
              :src="exerciseService.getSampleFileUrl(convStore.currentConversationId, currentSample.sample_id) + '#toolbar=0'"
              class="file-preview-iframe"
              frameborder="0"
            />
            
            <!-- DOCX 和 TXT 预览 - 直接显示文本内容 -->
            <div v-else-if="sampleDetail.file_type === 'docx' || sampleDetail.file_type === 'txt'" class="text-preview">
              <div v-if="sampleDetail.file_type === 'docx'" class="docx-notice">
                <el-alert
                  title="DOCX 文件文本内容预览"
                  type="info"
                  :closable="false"
                  style="margin-bottom: 16px;"
                >
                  <template #default>
                    <p>浏览器不支持直接预览 DOCX 文件，以下是提取的文本内容。如需查看完整格式，请下载文件。</p>
                    <el-button
                      type="primary"
                      size="small"
                      @click="downloadSampleFile"
                      style="margin-top: 8px;"
                    >
                      下载原始文件
                    </el-button>
                  </template>
                </el-alert>
              </div>
              <pre class="text-content">{{ sampleDetail.text_content || '暂无文本内容' }}</pre>
            </div>
            
            <!-- 其他类型 -->
            <div v-else class="unknown-type">
              <el-alert
                title="不支持的文件类型"
                type="warning"
                :closable="false"
              />
            </div>
          </div>
        </div>
      </div>
      
      <template #footer>
        <el-button @click="viewSampleDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, UploadFilled, MagicStick, DocumentCopy } from '@element-plus/icons-vue'
import { useConversationStore } from '../../stores/conversationStore'
import exerciseService from '../../services/exerciseService'
import { useRoute } from 'vue-router'
import { api } from '../../services/api'

const route = useRoute()
const convStore = useConversationStore()

// 状态
const sampleSectionCollapsed = ref(false)
const samples = ref([])
const fileList = ref([])
const generating = ref(false)
const generationStatus = ref('')
const generationResult = ref(null)
const uploadRef = ref(null)
const generatedQuestions = ref([])   // 用来存放后端返回的题目列表
const questionsDialogVisible = ref(false)  // 题目详情弹窗显示状态
const currentQuestionIndex = ref(0)  // 当前显示的题目索引

// MathJax 渲染函数
const renderMathJax = () => {
  nextTick(() => {
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise().catch((err) => {
        console.warn('MathJax rendering error:', err)
      })
    }
  })
}

// 监听弹窗打开和题目切换，触发 MathJax 渲染
watch(questionsDialogVisible, (newVal) => {
  if (newVal) {
    renderMathJax()
  }
})

watch(currentQuestionIndex, () => {
  if (questionsDialogVisible.value) {
    renderMathJax()
  }
})

// 监听会话切换，重新加载试题
watch(() => convStore.currentConversationId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    console.log('🔄 会话切换，重新加载数据:', newId)
    loadSamples()
    loadGeneratedQuestions()
  }
})


// 计算属性
const currentQuestion = computed(() => {
  if (generatedQuestions.value && generatedQuestions.value.length > currentQuestionIndex.value) {
    return generatedQuestions.value[currentQuestionIndex.value]
  }
  return null
})

const questionTypeStats = computed(() => {
  const stats = {}
  generatedQuestions.value.forEach(q => {
    const type = q.question_type || 'unknown'
    stats[type] = (stats[type] || 0) + 1
  })
  return stats
})

const difficultyStats = computed(() => {
  const stats = {}
  generatedQuestions.value.forEach(q => {
    const level = q.difficulty || 'medium'
    stats[level] = (stats[level] || 0) + 1
  })
  return stats
})

// 方法
const toggleSampleSection = () => {
  sampleSectionCollapsed.value = !sampleSectionCollapsed.value
}

const showQuestionsDialog = () => {
  currentQuestionIndex.value = 0
  questionsDialogVisible.value = true
}

const nextQuestion = () => {
  if (currentQuestionIndex.value < generatedQuestions.value.length - 1) {
    currentQuestionIndex.value++
  }
}

const prevQuestion = () => {
  if (currentQuestionIndex.value > 0) {
    currentQuestionIndex.value--
  }
}

const parseQuestionContent = (content) => {
  if (!content) return ''
  
  let html = content
  
  // 🆕 解析Markdown表格（优先处理，在处理HTML之前）
  // 匹配格式：| Header | Header | \n |--------|--------| \n | Cell | Cell |
  const markdownTableRegex = /\|(.+)\|\n\|[\s\-:]+\|\n((?:\|.+\|\n?)+)/g
  html = html.replace(markdownTableRegex, (match, headerRow, bodyRows) => {
    // 解析表头
    const headers = headerRow.split('|').map(h => h.trim()).filter(h => h)
    
    // 解析数据行
    const rows = bodyRows.trim().split('\n').map(row => {
      return row.split('|').map(cell => cell.trim()).filter(cell => cell)
    })
    
    // 构建HTML表格
    let tableHtml = '<table class="question-table" border="1" style="border-collapse: collapse; margin: 10px 0;">'
    
    // 表头
    tableHtml += '<thead><tr>'
    headers.forEach(header => {
      tableHtml += `<th style="padding: 8px; border: 1px solid #ddd; background-color: #f0f0f0;">${header}</th>`
    })
    tableHtml += '</tr></thead>'
    
    // 表体
    tableHtml += '<tbody>'
    rows.forEach(row => {
      tableHtml += '<tr>'
      row.forEach(cell => {
        tableHtml += `<td style="padding: 8px; border: 1px solid #ddd; text-align: center;">${cell}</td>`
      })
      tableHtml += '</tr>'
    })
    tableHtml += '</tbody></table>'
    
    return tableHtml
  })
  
  // 解析图片：将相对路径转换为完整URL
  html = html.replace(/<img([^>]*)src=["']([^"']+)["']([^>]*)>/gi, (match, before, src, after) => {
    // 如果是相对路径，构建完整URL
    if (!src.startsWith('http') && !src.startsWith('data:')) {
      const baseUrl = 'http://localhost:8000'
      const conversationId = convStore.currentConversationId
      // src 格式: images/image_4_1.jpg
      // 尝试从多个可能的目录加载图片
      // 优先尝试 _corrected 目录，然后是原始目录
      const fullSrc = `${baseUrl}/data/${conversationId}_corrected/${src}`
      return `<img${before}src="${fullSrc}"${after} onerror="this.src='${baseUrl}/data/${conversationId}/${src}'" style="max-width: 80%; height: auto; display: block; margin: 10px auto;">`
    }
    return match
  })
  
  // 解析表格：将 <table ...> 标签转换为 HTML
  html = html.replace(/<table([^>]*)>/gi, '<table$1 class="question-table">')
  
  // 解析 LaTeX 数学公式：$ ... $ 和 $$ ... $$
  // 先处理 $$ ... $$ (块级公式)
  html = html.replace(/\$\$([^$]+)\$\$/g, (match, formula) => {
    return `<span class="math-block">\\[${formula}\\]</span>`
  })
  
  // 再处理 $ ... $ (行内公式)
  html = html.replace(/\$([^$]+)\$/g, (match, formula) => {
    return `<span class="math-inline">\\(${formula}\\)</span>`
  })
  
  // 处理换行
  html = html.replace(/\n/g, '<br>')
  
  return html
}

const downloadExamPaper = async () => {
  if (!generatedQuestions.value || generatedQuestions.value.length === 0) {
    ElMessage.warning('暂无试题可下载')
    return
  }

  if (!convStore.currentConversationId) {
    ElMessage.error('请先选择会话')
    return
  }

  try {
    ElMessage.info('正在生成试卷PDF，请稍候...')
    
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const url = `${baseURL}/api/conversations/${convStore.currentConversationId}/exercises/download_exam_paper`
    
    // 使用fetch下载文件
    const response = await fetch(url)
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: '下载失败' }))
      throw new Error(errorData.detail || '下载失败')
    }
    
    // 获取文件blob
    const blob = await response.blob()
    
    // 创建下载链接
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = `试卷_${new Date().toISOString().split('T')[0]}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    // 释放blob URL
    window.URL.revokeObjectURL(downloadUrl)
    
    ElMessage.success('试卷下载成功')
  } catch (error) {
    console.error('下载试卷失败:', error)
    ElMessage.error('下载试卷失败: ' + (error.message || '未知错误'))
  }
}

const handleCustomUpload = async (options) => {
  const { file } = options
  
  if (!convStore.currentConversationId) {
    ElMessage.error('请先选择对话')
    return Promise.reject(new Error('未选择对话'))
  }
  
  try {
    const formData = new FormData()
    formData.append('files', file)
    
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const url = `${baseURL}/api/conversations/${convStore.currentConversationId}/exercises/samples/upload`
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.detail || '上传失败')
    }
    
    const data = await response.json()
    options.onSuccess(data, file)
    return data
  } catch (error) {
    options.onError(error)
    return Promise.reject(error)
  }
}

const beforeUpload = (file) => {
  const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain']
  const isValidType = validTypes.includes(file.type) || 
    file.name.endsWith('.pdf') || 
    file.name.endsWith('.docx') || 
    file.name.endsWith('.txt')
  
  if (!isValidType) {
    ElMessage.error('只支持 PDF、DOCX、TXT 格式！')
    return false
  }
  
  const isLt50M = file.size / 1024 / 1024 < 50
  if (!isLt50M) {
    ElMessage.error('文件大小不能超过 50MB！')
    return false
  }
  
  return true
}

const handleUploadSuccess = (response, file) => {
  ElMessage.success(`${file.name} 上传成功`)
  loadSamples()
  // 清空文件列表，允许继续上传
  fileList.value = []
}

const handleUploadError = (error, file) => {
  const errorMessage = error?.message || error?.detail || (typeof error === 'string' ? error : '未知错误')
  ElMessage.error(`${file.name} 上传失败: ${errorMessage}`)
}

const handleRemove = (file) => {
  // 文件移除处理
}

// 轮询定时器
let pollingTimer = null

const loadSamples = async () => {
  if (!convStore.currentConversationId) return
  
  try {
    const response = await exerciseService.listSamples(convStore.currentConversationId)
    samples.value = response.samples || []
    
    // 检查是否有正在解析的样本
    const hasPending = samples.value.some(s => s.status === 'pending' || s.status === 'processing')
    
    // 如果有pending样本，启动轮询；否则停止轮询
    if (hasPending) {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (error) {
    ElMessage.error('加载样本列表失败: ' + (error.message || '未知错误'))
  }
}

// 加载已生成的试题
const loadGeneratedQuestions = async () => {
  if (!convStore.currentConversationId) return
  
  try {
    const qRes = await exerciseService.getGeneratedQuestions(convStore.currentConversationId)
    if (qRes && qRes.questions && qRes.questions.length > 0) {
      generatedQuestions.value = qRes.questions
      generationResult.value = {
        conversation_id: qRes.conversation_id,
        question_count: qRes.question_count
      }
      generationStatus.value = `✅ 已加载 ${qRes.questions.length} 道试题（从缓存）`
      console.log('✅ 自动加载已生成的试题:', qRes.questions.length, '道')
    } else {
      // 没有已生成的试题，清空状态
      generatedQuestions.value = []
      generationResult.value = null
      generationStatus.value = ''
    }
  } catch (error) {
    // 404 或其他错误表示还没有生成过试题，这是正常情况
    if (error.response?.status === 404 || error.status === 404) {
      console.log('ℹ️ 当前会话暂无生成的试题')
      generatedQuestions.value = []
      generationResult.value = null
      generationStatus.value = ''
    } else {
      console.error('加载生成试题失败:', error)
      // 其他错误也不影响页面正常使用
      generatedQuestions.value = []
      generationResult.value = null
      generationStatus.value = ''
    }
  }
}

// 启动轮询
const startPolling = () => {
  // 避免重复启动
  if (pollingTimer) return
  
  pollingTimer = setInterval(() => {
    loadSamples()
  }, 2000) // 每2秒刷新一次
}

// 停止轮询
const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

const viewSampleDialogVisible = ref(false)
const currentSample = ref(null)
const sampleDetail = ref(null)
const loadingDetail = ref(false)

const viewSample = async (sample) => {
  currentSample.value = sample
  viewSampleDialogVisible.value = true
  loadingDetail.value = true
  sampleDetail.value = null
  
  try {
    const detail = await exerciseService.getSample(convStore.currentConversationId, sample.sample_id)
    console.log('样本详情数据:', detail)
    console.log('text_content 字段:', detail?.text_content)
    console.log('text_content 类型:', typeof detail?.text_content)
    console.log('text_content 长度:', detail?.text_content?.length)
    sampleDetail.value = detail
  } catch (error) {
    console.error('加载样本详情失败:', error)
    ElMessage.error('加载样本详情失败: ' + (error.message || '未知错误'))
  } finally {
    loadingDetail.value = false
  }
}

const copyText = async () => {
  if (!sampleDetail.value) {
    ElMessage.warning('样本详情未加载')
    return
  }
  
  console.log('复制文本 - sampleDetail:', sampleDetail.value)
  console.log('复制文本 - text_content:', sampleDetail.value.text_content)
  
  const textContent = sampleDetail.value.text_content
  if (textContent === null || textContent === undefined) {
    console.warn('text_content 为 null 或 undefined')
    ElMessage.warning('没有可复制的文本内容（数据为空）')
    return
  }
  
  if (typeof textContent === 'string' && textContent.trim() === '') {
    console.warn('text_content 为空字符串')
    ElMessage.warning('没有可复制的文本内容（文本为空）')
    return
  }
  
  try {
    await navigator.clipboard.writeText(textContent)
    ElMessage.success('文本已复制到剪贴板')
  } catch (error) {
    console.error('复制失败:', error)
    // 降级方案
    const textArea = document.createElement('textarea')
    textArea.value = textContent
    textArea.style.position = 'fixed'
    textArea.style.opacity = '0'
    document.body.appendChild(textArea)
    textArea.select()
    try {
      document.execCommand('copy')
      ElMessage.success('文本已复制到剪贴板')
    } catch (err) {
      console.error('降级复制也失败:', err)
      ElMessage.error('复制失败，请手动复制')
    }
    document.body.removeChild(textArea)
  }
}

const downloadSampleFile = () => {
  if (!currentSample.value || !convStore.currentConversationId) return
  const url = exerciseService.getSampleFileUrl(convStore.currentConversationId, currentSample.value.sample_id)
  window.open(url, '_blank')
}

const deleteSample = async (sample) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除样本 "${sample.filename}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await exerciseService.deleteSample(convStore.currentConversationId, sample.sample_id)
    ElMessage.success('删除成功')
    loadSamples()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + (error.message || '未知错误'))
    }
  }
}

const startGeneration = async () => {
  if (samples.value.length === 0) {
    ElMessage.warning('请先上传样本试题')
    return
  }

  // 检查当前会话ID
  if (!convStore.currentConversationId) {
    ElMessage.error('请先选择或创建一个会话')
    return
  }

  // 检查是否有已完成的样本
  const completedSamples = samples.value.filter(s => s.status === 'completed')
  if (completedSamples.length === 0) {
    const pendingSamples = samples.value.filter(s => s.status === 'pending')
    if (pendingSamples.length > 0) {
      ElMessage.warning(`有 ${pendingSamples.length} 个样本正在解析中，请稍等片刻`)
    } else {
      ElMessage.error('样本解析失败，请重新上传')
    }
    return
  }

  generating.value = true
  generationStatus.value = '正在清除旧缓存并生成全新题目...'
  generationResult.value = null
  generatedQuestions.value = []

  try {
    const convId = convStore.currentConversationId

    // 1️⃣ 调用“生成题目”
    const res = await api.post(
      `/api/conversations/${convId}/exercises/generate`
    )

    // ⭐⭐ 修正点 #1：不要再用 res.data
    const data = res
    console.log("🔥 /generate 返回:", data)

    // ⭐⭐ 修正点 #2（可选，但建议）
    if (!data || typeof data.question_count === "undefined") {
      throw new Error("后端未返回 question_count")
    }

    generationResult.value = data
    generationStatus.value = `✅ 成功生成 ${data.question_count} 道全新试题`

    // 2️⃣ 获取题目列表
    try {
      const qRes = await exerciseService.getGeneratedQuestions(convId)
      console.log("📌 getGeneratedQuestions 返回:", qRes)
      generatedQuestions.value = qRes.questions || []
      ElMessage.success(`已生成 ${qRes.questions?.length || 0} 道新题目`)
    } catch (err) {
      console.error('读取生成题目列表失败：', err)
      ElMessage.warning('题目已经生成，但在读取题目列表时出错')
    }

  } catch (error) {
    console.error('生成失败：', error)
    const msg =
      error.response?.data?.detail ||
      error.message ||
      '未知错误'
    
    // 更友好的错误提示
    if (msg.includes('未找到任何样本试卷')) {
      ElMessage.error('当前会话未上传样本试卷，请先在上方上传PDF/DOCX/TXT文件')
    } else if (msg.includes('正在解析中')) {
      ElMessage.warning(msg)
    } else {
      ElMessage.error('生成试题失败：' + msg)
    }
    
    generationStatus.value = '❌ 生成失败'
  } finally {
    generating.value = false
  }
}






const formatFileSize = (bytes) => {
  // 处理 undefined, null, 或非数字情况
  if (bytes === undefined || bytes === null || isNaN(bytes)) {
    return '解析中...'
  }
  // 0 字节是有效值
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

const formatTime = (timeStr) => {
  if (!timeStr) return '-'
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  // 从路由参数同步 conversation_id 到 store
  const conversationId = route.params.conversation_id
  if (conversationId && conversationId !== convStore.currentConversationId) {
    convStore.selectConversation(conversationId)
  }
  
  loadSamples()
  // 自动加载已保存的生成试题
  loadGeneratedQuestions()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.exercise-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sample-section {
  flex-shrink: 0;
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.toggle-icon {
  transition: transform 0.3s;
}

.toggle-icon.collapsed {
  transform: rotate(-90deg);
}

.section-title {
  font-weight: 500;
  flex: 1;
}

.sample-content {
  padding: 16px 0;
}

.upload-area {
  margin-bottom: 16px;
}

.sample-list {
  margin-top: 16px;
}

.result-section {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.result-section.full-height {
  height: 100%;
}

.result-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.result-content {
  flex: 1;
  overflow: auto;
  padding: 16px;
}

.generating-status {
  padding: 16px;
}

.generation-result {
  padding: 16px;
}

.questions-list {
  margin-top: 16px;
}

/* 样本详情对话框样式 */
.loading-container {
  padding: 20px;
}

.sample-detail-container {
  height: 70vh;
  display: flex;
  flex-direction: column;
}

.file-preview-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 16px;
}

.file-info {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: #606266;
}

.preview-content {
  flex: 1;
  overflow: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #f5f5f5;
}

.file-preview-iframe {
  width: 100%;
  height: 100%;
  min-height: 600px;
  border: none;
}

.docx-preview,
.text-preview {
  padding: 20px;
  background: white;
  min-height: 100%;
}

.text-content {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  margin: 0;
  padding: 16px;
  background: #fafafa;
  border-radius: 4px;
}

.unknown-type {
  padding: 20px;
  text-align: center;
}

.scroll-area {
  max-height: 70vh;     /* 可见区域 70% 屏幕高度 */
  overflow-y: auto;     /* 开启纵向滚动条 */
  padding-right: 10px;  /* 防止滚动条遮挡内容 */
}

.question-item {
  word-wrap: break-word; /* 自动换行，避免题干太长撑爆布局 */
  white-space: normal;
}

/* 题目详情对话框样式 */
.questions-dialog-content {
  padding: 16px;
}

.question-navigation {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.question-progress {
  font-size: 16px;
  font-weight: 500;
  color: #409eff;
  min-width: 80px;
  text-align: center;
}

.current-question {
  padding: 20px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  min-height: 400px;
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #409eff;
}

.question-header h3 {
  margin: 0;
  font-size: 18px;
  color: #303133;
  flex: 1;
}

.question-meta {
  display: flex;
  gap: 8px;
}

.question-stem {
  font-size: 15px;
  line-height: 1.8;
  color: #303133;
  margin-bottom: 20px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.question-options {
  margin: 20px 0;
}

.option-item {
  display: flex;
  align-items: flex-start;
  padding: 12px;
  margin-bottom: 8px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  transition: all 0.3s;
}

.option-item:hover {
  background: #ecf5ff;
  border-color: #b3d8ff;
}

.option-label {
  font-weight: 600;
  color: #409eff;
  margin-right: 12px;
  min-width: 24px;
}

.question-answer,
.question-explanation,
.question-knowledge {
  margin-top: 16px;
}

.answer-section,
.explanation-section,
.knowledge-section {
  padding: 12px;
  background: #f0f9ff;
  border-left: 4px solid #409eff;
  border-radius: 4px;
  line-height: 1.8;
}

.answer-section strong,
.explanation-section strong,
.knowledge-section strong {
  color: #409eff;
  margin-right: 8px;
}

/* 题目内容中的表格样式 */
:deep(.question-table) {
  border-collapse: collapse;
  margin: 16px auto;
  max-width: 100%;
  background: white;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

:deep(.question-table td),
:deep(.question-table th) {
  border: 1px solid #dcdfe6;
  padding: 8px 12px;
  text-align: center;
}

:deep(.question-table th) {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}

/* LaTeX 数学公式样式 */
:deep(.math-inline),
:deep(.math-block) {
  font-family: 'Times New Roman', serif;
}

:deep(.math-block) {
  display: block;
  margin: 12px 0;
  text-align: center;
}

/* 问题摘要样式 */
.questions-summary {
  margin-top: 16px;
}

.questions-summary :deep(.el-descriptions__label) {
  font-weight: 600;
  color: #606266;
}

.questions-summary :deep(.el-descriptions__content) {
  color: #303133;
}
</style>



