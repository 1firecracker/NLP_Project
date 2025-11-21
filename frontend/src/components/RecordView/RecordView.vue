<template>
  <div class="record-viewer">
    <div class="record-header">
      <h2>📊 学生成绩记录</h2>
      <el-button type="primary" @click="refreshRecords" :loading="loading">
        <el-icon><refresh /></el-icon>
        刷新记录
      </el-button>
    </div>

    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="5" animated />
    </div>

    <div v-else-if="records.length === 0" class="empty-state">
      <el-empty description="暂无成绩记录">
        <template #default>
          <span></span>
        </template>
      </el-empty>
    </div>

    <div v-else class="record-list">
      <el-card
        v-for="(record, index) in records"
        :key="record.id || index"
        class="record-card"
        shadow="hover"
      >
        <div class="record-item">
          <div class="record-rank">
            <span class="rank-number" :class="getRankClass(index)">
              {{ index + 1 }}
            </span>
          </div>
          
          <div class="record-info">
            <div class="student-info">
              <el-icon class="info-icon" color="#409eff"><user /></el-icon>
              <span class="student-name">{{ record.studentName || '未知学生' }}</span>
            </div>
            
            <div class="exam-info">
              <el-icon class="info-icon" color="#67c23a"><document /></el-icon>
              <span class="exam-name">{{ record.examName || '试卷批改记录' }}</span>
            </div>
            
            <div class="time-info">
              <el-icon class="info-icon" color="#909399"><clock /></el-icon>
              <span class="submit-time">{{ formatTime(record.submitTime) }}</span>
            </div>
          </div>

          <div class="record-score">
            <div class="score-display">
              <span class="score-value" :class="getScoreClass(record.score)">
                {{ record.score }}
              </span>
              <span class="score-total">/ {{ record.maxScore || 100 }}</span>
            </div>
            <el-progress
              :percentage="getScorePercentage(record.score, record.maxScore)"
              :color="getProgressColor(record.score, record.maxScore)"
              :stroke-width="8"
            />
          </div>

          <div class="record-actions">
            <el-button 
              v-if="record.pdfPath" 
              size="small" 
              type="primary"
              @click="downloadPDF(record)"
            >
              <el-icon><download /></el-icon>
              下载PDF报告
            </el-button>
            <el-button size="small" @click="viewDetail(record)">
              查看详情
            </el-button>
            <el-button size="small" type="danger" @click="deleteRecord(record)" text>
              删除
            </el-button>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="成绩详情"
      width="70%"
      :close-on-click-modal="false"
    >
      <div v-if="currentRecord" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="学生姓名">
            {{ currentRecord.studentName }}
          </el-descriptions-item>
          <el-descriptions-item label="提交时间">
            {{ formatTime(currentRecord.submitTime) }}
          </el-descriptions-item>
          <el-descriptions-item label="总分">
            {{ currentRecord.score }} / {{ currentRecord.maxScore || 100 }}
          </el-descriptions-item>
          <el-descriptions-item label="得分率">
            {{ getScorePercentage(currentRecord.score, currentRecord.maxScore) }}%
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="currentRecord.details" class="question-details" style="margin-top: 20px;">
          <h3>题目详情</h3>
          <el-table :data="currentRecord.details" style="width: 100%">
            <el-table-column prop="id" label="题号" width="120" />
            <el-table-column prop="question_type" label="题型" width="150" />
            <el-table-column prop="score" label="得分" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.score >= 60 ? 'success' : 'danger'">
                  {{ scope.row.score }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="feedback" label="评语" min-width="250" />
          </el-table>
        </div>

        <div v-if="currentRecord.recommendations" class="recommendations" style="margin-top: 20px;">
          <h3>学习建议</h3>
          <ul>
            <li v-for="(rec, idx) in currentRecord.recommendations" :key="idx">
              {{ rec }}
            </li>
          </ul>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, User, Document, Clock, Download } from '@element-plus/icons-vue'
import { useConversationStore } from '../../stores/conversationStore'

const convStore = useConversationStore()
const currentConversationId = computed(() => convStore.currentConversationId)

const loading = ref(false)
const records = ref([])
const detailDialogVisible = ref(false)
const currentRecord = ref(null)

// 获取成绩记录
const fetchRecords = async () => {
  const cid = currentConversationId.value
  if (!cid) {
    ElMessage.warning('请先选择一个会话')
    return
  }

  loading.value = true
  try {
    const response = await fetch(`/api/conversations/${cid}/exercises/records`)
    if (!response.ok) {
      throw new Error('获取记录失败')
    }
    const data = await response.json()
    console.log('[DEBUG] 获取到的记录数据:', data)
    console.log('[DEBUG] 记录数量:', data.records?.length || 0)
    
    // 按得分降序排序
    records.value = (data.records || []).sort((a, b) => b.score - a.score)
    console.log('[DEBUG] 排序后的记录:', records.value)
  } catch (error) {
    console.error('获取记录失败:', error)
    ElMessage.error('获取成绩记录失败: ' + error.message)
    records.value = []
  } finally {
    loading.value = false
  }
}

const refreshRecords = () => {
  fetchRecords()
}

const viewDetail = (record) => {
  currentRecord.value = record
  detailDialogVisible.value = true
}

const deleteRecord = async (record) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 ${record.studentName} 的成绩记录吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    const cid = currentConversationId.value
    const response = await fetch(
      `/api/conversations/${cid}/exercises/records/${record.id}`,
      { method: 'DELETE' }
    )

    if (!response.ok) {
      throw new Error('删除失败')
    }

    ElMessage.success('删除成功')
    await fetchRecords()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + error.message)
    }
  }
}

const downloadPDF = (record) => {
  if (!record.pdfPath) {
    ElMessage.warning('该记录没有PDF报告')
    return
  }
  
  const cid = currentConversationId.value
  const downloadUrl = `/api/conversations/${cid}/exercises/grading-report/download?pdf_path=${encodeURIComponent(record.pdfPath)}`
  
  // 创建隐藏的下载链接
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = `批改报告_${record.studentName}.pdf`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  
  ElMessage.success('开始下载PDF报告')
}

const getRankClass = (index) => {
  if (index === 0) return 'rank-gold'
  if (index === 1) return 'rank-silver'
  if (index === 2) return 'rank-bronze'
  return ''
}

const getScoreClass = (score) => {
  if (score >= 90) return 'score-excellent'
  if (score >= 80) return 'score-good'
  if (score >= 60) return 'score-pass'
  return 'score-fail'
}

const getScorePercentage = (score, maxScore = 100) => {
  return ((score / maxScore) * 100).toFixed(1)
}

const getProgressColor = (score, maxScore = 100) => {
  const percentage = (score / maxScore) * 100
  if (percentage >= 90) return '#67c23a'
  if (percentage >= 80) return '#409eff'
  if (percentage >= 60) return '#e6a23c'
  return '#f56c6c'
}

const formatTime = (time) => {
  if (!time) return '未知时间'
  const date = new Date(time)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  fetchRecords()
})
</script>

<style scoped>
.record-viewer {
  height: 100%;
  padding: 20px;
  background-color: #f5f7fa;
  overflow-y: auto;
}

.record-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 15px 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.record-header h2 {
  margin: 0;
  color: #303133;
  font-size: 20px;
}

.loading-state,
.empty-state {
  background: white;
  border-radius: 8px;
  padding: 40px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.record-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.record-card {
  transition: transform 0.2s;
}

.record-card:hover {
  transform: translateY(-2px);
}

.record-item {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 10px 0;
}

.record-rank {
  flex-shrink: 0;
  width: 50px;
  text-align: center;
}

.rank-number {
  display: inline-block;
  width: 40px;
  height: 40px;
  line-height: 40px;
  border-radius: 50%;
  background: #e4e7ed;
  color: #606266;
  font-weight: bold;
  font-size: 18px;
}

.rank-gold {
  background: linear-gradient(135deg, #ffd700, #ffed4e);
  color: #8b6914;
}

.rank-silver {
  background: linear-gradient(135deg, #c0c0c0, #e8e8e8);
  color: #5a5a5a;
}

.rank-bronze {
  background: linear-gradient(135deg, #cd7f32, #e9a75b);
  color: #5d3a1a;
}

.record-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.student-info,
.exam-info,
.time-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-icon {
  font-size: 16px;
}

.student-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.exam-name {
  font-size: 14px;
  color: #606266;
}

.submit-time {
  font-size: 13px;
  color: #909399;
}

.record-score {
  flex-shrink: 0;
  width: 200px;
  text-align: center;
}

.score-display {
  margin-bottom: 8px;
}

.score-value {
  font-size: 32px;
  font-weight: bold;
}

.score-total {
  font-size: 18px;
  color: #909399;
  margin-left: 4px;
}

.score-excellent {
  color: #67c23a;
}

.score-good {
  color: #409eff;
}

.score-pass {
  color: #e6a23c;
}

.score-fail {
  color: #f56c6c;
}

.record-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-content {
  padding: 10px;
}

.question-details h3,
.recommendations h3 {
  margin: 0 0 15px 0;
  color: #303133;
  font-size: 16px;
}

.recommendations ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.recommendations li {
  padding: 8px 12px;
  margin-bottom: 8px;
  background: #f0f9ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  color: #606266;
}
</style>
