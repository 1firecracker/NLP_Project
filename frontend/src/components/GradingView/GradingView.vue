<template>
  <div class="grading-viewer">
    <div class="grading-container">
      <!-- 左侧：试卷上传和批改控制 -->
      <div class="grading-sidebar">
        <div class="upload-section">
          <h3>试卷上传</h3>
          
          <!-- 使用原生文件输入以确保可靠性 -->
          <div class="native-upload">
            <input 
              ref="fileInput"
              type="file" 
              accept=".pdf,.docx,.txt"
              @change="handleNativeFileChange"
              style="display: none"
            />
            <el-button 
              type="primary" 
              :icon="UploadFilled" 
              @click="$refs.fileInput.click()"
              style="width: 100%"
            >
              选择答卷文件
            </el-button>
            <div class="file-tip">支持 PDF、DOCX、TXT 格式，不超过 50MB</div>
          </div>
          
          <!-- 显示已选择的文件 -->
          <div v-if="uploadedFile" class="selected-file">
            <el-tag type="success" closable @close="clearFile">
              <el-icon><document /></el-icon>
              {{ uploadedFile.name }}
              <span class="file-size">({{ (uploadedFile.size / 1024).toFixed(1) }} KB)</span>
            </el-tag>
          </div>
        </div>

        <div class="grading-controls">
          <h3>批改设置</h3>
          <el-form :model="gradingForm" label-width="80px">
            <el-form-item label="学生姓名">
              <el-input v-model="gradingForm.studentName" placeholder="请输入学生姓名" />
            </el-form-item>
          </el-form>
          
          <el-button 
            type="primary" 
            :loading="isGrading" 
            @click="startGrading"
            style="width: 100%; margin-top: 20px;"
          >
            {{ isGrading ? '批改中...' : '开始批改' }}
          </el-button>
        </div>
      </div>

      <!-- 右侧：批改结果展示 -->
      <div class="grading-results">
        <div class="results-header">
          <h2>批改结果</h2>
          <div class="result-stats">
            <el-statistic title="总分" :value="gradingResult.totalScore || 0" />
            <el-statistic title="满分" :value="gradingResult.maxScore || 100" />
            <el-statistic title="得分率" :value="scoreRate" suffix="%" />
          </div>
        </div>

        <div v-if="!gradingResult.details" class="empty-state">
          <el-empty description="暂无批改结果，请先上传试卷并开始批改" />
        </div>

        <div v-else class="results-content">
          <!-- 题目批改详情 -->
          <div class="question-results">
            <h3>题目批改详情</h3>
            <el-table :data="gradingResult.details" style="width: 100%">
              <el-table-column prop="questionId" label="题号" width="100" />
              <el-table-column prop="questionType" label="题型" width="150" />
              <el-table-column prop="score" label="得分" width="120">
                <template #default="scope">
                  <el-tag :type="getScoreTagType(scope.row.score, scope.row.maxScore)">
                    {{ scope.row.score }} / {{ scope.row.maxScore }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="feedback" label="评语" min-width="200" />
            </el-table>
          </div>

          <!-- 知识点分析 -->
          <div class="knowledge-analysis">
            <h3>知识点掌握分析</h3>
            <div class="knowledge-chart">
              <div 
                v-for="(analysis, knowledge) in gradingResult.knowledgeAnalysis" 
                :key="knowledge"
                class="knowledge-item"
              >
                <div class="knowledge-header">
                  <span class="knowledge-name">{{ knowledge }}</span>
                  <span class="knowledge-score">{{ (analysis.masteryLevel * 100).toFixed(1) }}%</span>
                </div>
                <el-progress 
                  :percentage="analysis.masteryLevel * 100" 
                  :status="getKnowledgeStatus(analysis.masteryLevel)"
                  :stroke-width="8"
                />
                <div class="knowledge-details">
                  <span>题目数量: {{ analysis.questionCount }}</span>
                  <span class="performance-tag" :class="getPerformanceClass(analysis.performance)">
                    {{ analysis.performance }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 学习建议 -->
          <div class="recommendations">
            <h3>学习建议</h3>
            <el-card shadow="never">
              <ul class="recommendation-list">
                <li 
                  v-for="(recommendation, index) in gradingResult.recommendations" 
                  :key="index"
                  class="recommendation-item"
                >
                  <el-icon><info-filled /></el-icon>
                  {{ recommendation }}
                </li>
              </ul>
            </el-card>
          </div>

          <!-- Agent H 学习诊断与个性化建议 -->
          <div v-if="gradingResult.learningAdvice" class="learning-advice-section">
            <h3>📚 个性化学习诊断（Agent H）</h3>
            
            <!-- 薄弱知识点分析 -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-icon color="#e6a23c"><warning-filled /></el-icon>
                  <span>薄弱知识点分析</span>
                </div>
              </template>
              <div v-if="gradingResult.learningAdvice.weak_analysis?.weak_knowledge_points?.length > 0">
                <div 
                  v-for="(wkp, idx) in gradingResult.learningAdvice.weak_analysis.weak_knowledge_points" 
                  :key="idx"
                  class="weak-point-item"
                >
                  <div class="weak-point-header">
                    <span class="weak-point-name">{{ wkp.name }}</span>
                    <el-tag type="danger" size="small">掌握度: {{ (wkp.mastery * 100).toFixed(0) }}%</el-tag>
                  </div>
                  <el-progress 
                    :percentage="wkp.mastery * 100" 
                    status="exception"
                    :stroke-width="6"
                  />
                  <div class="weak-point-meta">
                    <span>涉及题目: {{ wkp.count }} 道</span>
                    <span class="performance-tag performance-need-improve">{{ wkp.performance }}</span>
                  </div>
                </div>
              </div>
              <el-empty v-else description="未发现明显薄弱知识点" :image-size="80" />
            </el-card>

            <!-- 优先学习主题 -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-icon color="#409eff"><reading /></el-icon>
                  <span>优先学习主题</span>
                  <el-tag v-if="gradingResult.learningAdvice.summary" size="small" type="info">
                    预计 {{ gradingResult.learningAdvice.summary.estimated_hours }} 小时
                  </el-tag>
                </div>
              </template>
              <div v-if="gradingResult.learningAdvice.learning_plan?.priority_topics?.length > 0">
                <div 
                  v-for="(topic, idx) in gradingResult.learningAdvice.learning_plan.priority_topics" 
                  :key="idx"
                  class="priority-topic-item"
                >
                  <div class="topic-header">
                    <el-tag type="warning" size="small">优先级 {{ idx + 1 }}</el-tag>
                    <strong>{{ topic.topic }}</strong>
                  </div>
                  <p class="topic-reason">{{ topic.reason }}</p>
                  <div v-if="topic.resources && topic.resources.length > 0" class="topic-resources">
                    <span style="color: #909399; font-size: 13px;">学习资源:</span>
                    <ul>
                      <li v-for="(res, ridx) in topic.resources" :key="ridx">{{ res }}</li>
                    </ul>
                  </div>
                </div>
              </div>
              <el-empty v-else description="暂无优先学习主题" :image-size="80" />
            </el-card>

            <!-- 学习计划 -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-icon color="#67c23a"><calendar /></el-icon>
                  <span>分阶段学习计划</span>
                </div>
              </template>
              <div v-if="gradingResult.learningAdvice.learning_plan?.study_plan" class="study-plan-text">
                {{ gradingResult.learningAdvice.learning_plan.study_plan }}
              </div>
            </el-card>

            <!-- 练习建议 -->
            <el-card shadow="never">
              <template #header>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-icon color="#f56c6c"><edit /></el-icon>
                  <span>练习建议</span>
                </div>
              </template>
              <ul v-if="gradingResult.learningAdvice.learning_plan?.practice_suggestions" class="practice-list">
                <li 
                  v-for="(sug, idx) in gradingResult.learningAdvice.learning_plan.practice_suggestions" 
                  :key="idx"
                >
                  {{ sug }}
                </li>
              </ul>
            </el-card>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, InfoFilled, Document } from '@element-plus/icons-vue'
import { useConversationStore } from '../../stores/conversationStore'

// get current conversation id from store
const convStore = useConversationStore()
const currentConversationId = computed(() => convStore.currentConversationId)

// 响应式数据
const isGrading = ref(false)
const uploadedFile = ref(null)
const fileInput = ref(null)

const gradingForm = reactive({
  studentName: ''
})

const gradingResult = reactive({
  totalScore: 0,
  maxScore: 100,
  details: null,
  knowledgeAnalysis: null,
  recommendations: [],
  learningAdvice: null
})

// 计算属性
const scoreRate = computed(() => {
  return gradingResult.maxScore > 0 
    ? (gradingResult.totalScore / gradingResult.maxScore * 100).toFixed(1)
    : 0
})

// 方法
const handleNativeFileChange = (event) => {
  const file = event.target.files[0]
  
  if (!file) {
    return
  }
  
  console.log('[DEBUG] 原生文件选择:', file)
  
  // 检查文件扩展名
  const fileName = file.name.toLowerCase()
  const isValidExt = fileName.endsWith('.pdf') || fileName.endsWith('.docx') || fileName.endsWith('.txt')
  
  if (!isValidExt) {
    ElMessage.error('只能上传 PDF、DOCX、TXT 格式的文件')
    event.target.value = '' // 清空input
    return
  }
  
  const isValidSize = file.size / 1024 / 1024 < 50
  if (!isValidSize) {
    ElMessage.error('文件大小不能超过 50MB!')
    event.target.value = '' // 清空input
    return
  }
  
  uploadedFile.value = file
  console.log('[DEBUG] 文件已保存:', {
    name: file.name,
    type: file.type,
    size: file.size
  })
  ElMessage.success('文件已选择: ' + file.name)
}

const clearFile = () => {
  uploadedFile.value = null
  if (fileInput.value) {
    fileInput.value.value = '' // 清空input
  }
}

const startGrading = async () => {
  const cid = currentConversationId.value
  if (!cid) {
    ElMessage.warning('请先在左侧选择或创建一个会话（Conversation）')
    return
  }

  console.log('[DEBUG] uploadedFile.value:', uploadedFile.value)
  
  if (!uploadedFile.value) {
    ElMessage.warning('请先上传学生答卷文件（支持 PDF、DOCX、TXT 格式）')
    return
  }

  // 验证文件对象
  if (!(uploadedFile.value instanceof File)) {
    console.error('[ERROR] uploadedFile.value 不是 File 对象:', uploadedFile.value)
    ElMessage.error('文件对象无效，请重新选择文件')
    uploadedFile.value = null
    return
  }

  isGrading.value = true
  try {
    const form = new FormData()
    
    // 确保使用原始 File 对象
    form.append('file', uploadedFile.value, uploadedFile.value.name)
    form.append('studentName', gradingForm.studentName || 'anonymous')

    console.log('========== 开始批改 ==========')
    console.log('会话ID:', cid)
    console.log('上传文件信息:', {
      name: uploadedFile.value.name,
      type: uploadedFile.value.type,
      size: uploadedFile.value.size,
      lastModified: uploadedFile.value.lastModified
    })
    console.log('FormData entries:')
    for (let [key, value] of form.entries()) {
      if (value instanceof File) {
        console.log(`  ${key}: File(name=${value.name}, type=${value.type}, size=${value.size})`)
      } else {
        console.log(`  ${key}: ${value}`)
      }
    }
    console.log('请求URL:', `/api/conversations/${cid}/exercises/submissions`)

    const resp = await fetch(`/api/conversations/${cid}/exercises/submissions`, {
      method: 'POST',
      body: form
    })

    console.log('响应状态:', resp.status, resp.statusText)

    if (!resp.ok) {
      const txt = await resp.text()
      throw new Error(`批改请求失败: ${resp.status} ${txt}`)
    }

    const report = await resp.json()

    // Map report to gradingResult used by the UI
    const details = (report.per_question || []).map(p => ({
      questionId: p.id || p.questionId || 'unknown',
      questionType: p.question_type || p.questionType || '未知',
      studentAnswer: p.studentAnswer || p.student_answer || '',
      score: p.score || 0,
      maxScore: 100,
      feedback: p.feedback || ''
    }))

    gradingResult.totalScore = Math.round(report.average_score || 0)
    gradingResult.maxScore = 100
    gradingResult.details = details
    gradingResult.knowledgeAnalysis = report.knowledgeAnalysis || {}
    gradingResult.recommendations = report.recommendations || []
    gradingResult.learningAdvice = report.learning_advice || null

    ElMessage.success('试卷批改完成!')
  } catch (error) {
    ElMessage.error('批改过程中出现错误: ' + (error.message || error))
  } finally {
    isGrading.value = false
  }
}

// The UI previously used a mocked runAgentGrading function; real backend calls are used instead.

const getScoreTagType = (score, maxScore) => {
  const rate = score / maxScore
  if (rate >= 0.8) return 'success'
  if (rate >= 0.6) return 'warning'
  return 'danger'
}

const getKnowledgeStatus = (masteryLevel) => {
  if (masteryLevel >= 0.8) return 'success'
  if (masteryLevel >= 0.6) return 'warning'
  return 'exception'
}

const getPerformanceClass = (performance) => {
  switch (performance) {
    case '优秀': return 'performance-excellent'
    case '良好': return 'performance-good'
    default: return 'performance-need-improve'
  }
}
</script>

<style scoped>
.grading-viewer {
  height: 100%;
  padding: 20px;
  background-color: #f5f7fa;
}

.grading-container {
  display: flex;
  height: 100%;
  gap: 20px;
}

.grading-sidebar {
  width: 300px;
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.grading-results {
  flex: 1;
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow-y: auto;
}

.upload-section {
  margin-bottom: 30px;
}

.upload-section h3,
.grading-controls h3 {
  margin-bottom: 15px;
  color: #303133;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;
}

.result-stats {
  display: flex;
  gap: 30px;
}

.question-results,
.knowledge-analysis,
.recommendations {
  margin-bottom: 30px;
}

.knowledge-chart {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.knowledge-item {
  padding: 15px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.knowledge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.knowledge-name {
  font-weight: 500;
}

.knowledge-score {
  font-weight: bold;
  color: #409eff;
}

.knowledge-details {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.performance-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.performance-excellent {
  background: #f0f9ff;
  color: #409eff;
}

.performance-good {
  background: #f0f9e8;
  color: #67c23a;
}

.performance-need-improve {
  background: #fef0f0;
  color: #f56c6c;
}

.recommendation-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.recommendation-item {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.recommendation-item:last-child {
  border-bottom: none;
}

.recommendation-item .el-icon {
  margin-right: 8px;
  color: #409eff;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 300px;
}

/* Agent H Learning Advice Styles */
.learning-advice-section {
  margin-top: 30px;
}

.learning-advice-section h3 {
  font-size: 18px;
  color: #303133;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.weak-point-item {
  padding: 15px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  margin-bottom: 12px;
  background: #fef0f0;
}

.weak-point-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.weak-point-name {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}

.weak-point-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}

.priority-topic-item {
  padding: 15px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  margin-bottom: 12px;
}

.topic-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.topic-header strong {
  font-size: 15px;
  color: #303133;
}

.topic-reason {
  color: #606266;
  font-size: 14px;
  margin: 8px 0;
  line-height: 1.6;
}

.topic-resources {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e6a23c;
}

.topic-resources ul {
  margin: 8px 0 0 0;
  padding-left: 20px;
  list-style: disc;
}

.topic-resources li {
  color: #606266;
  font-size: 13px;
  line-height: 1.8;
}

.study-plan-text {
  color: #606266;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  padding: 15px;
  background: #f0f9ff;
  border-radius: 6px;
}

.practice-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.practice-list li {
  padding: 10px 15px;
  margin-bottom: 8px;
  background: #fff0f0;
  border-left: 3px solid #f56c6c;
  border-radius: 4px;
  color: #606266;
  font-size: 14px;
  line-height: 1.6;
}

.selected-file {
  margin-top: 12px;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 4px;
  text-align: center;
}

.file-size {
  color: #909399;
  font-size: 12px;
  margin-left: 4px;
}

.native-upload {
  width: 100%;
}

.file-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  text-align: center;
}

.practice-list li:before {
  content: '';
  color: #f56c6c;
  font-weight: bold;
  margin-right: 10px;
}
</style>