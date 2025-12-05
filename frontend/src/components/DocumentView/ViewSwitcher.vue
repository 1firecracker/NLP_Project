<template>
  <div class="view-switcher">
    <!-- 视图切换按钮 -->
    <div class="switcher-header">
      <el-button-group>
        <el-button
          :type="viewMode === 'ppt' ? 'primary' : 'default'"
          :icon="Document"
          @click="viewMode = 'ppt'"
        >
          PPT 视图
        </el-button>
        <el-button
          :type="viewMode === 'mindmap' ? 'primary' : 'default'"
          :icon="Connection"
          @click="viewMode = 'mindmap'"
        >
          思维脑图
        </el-button>
        <el-button
          :type="viewMode === 'exercise' ? 'primary' : 'default'"
          :icon="EditPen"
          @click="viewMode = 'exercise'"
        >
          Agent试题模拟
        </el-button>
        <el-button
          :type="viewMode === 'grading' ? 'primary' : 'default'"
          :icon="Finished"
          @click="viewMode = 'grading'"
        >
          试卷批改
        </el-button>
        <el-button
          :type="viewMode === 'record' ? 'primary' : 'default'"
          :icon="Finished"
          @click="viewMode = 'record'"
        >
          个人纪录
        </el-button>
      </el-button-group>
    </div>
    
    <!-- 视图内容 -->
    <div class="view-content">
      <!-- PPT 视图 -->
      <div v-show="viewMode === 'ppt'" class="ppt-view">
        <PPTViewer 
          v-if="convStore.currentConversationId" 
          :default-file-id="currentDocumentId"
        />
        <el-empty
          v-else
          description="请先选择或创建一个对话"
          :image-size="120"
        />
      </div>
      
      <!-- 思维脑图视图 -->
      <div v-if="viewMode === 'mindmap'" class="mindmap-view">
        <MindMapViewer 
          v-if="convStore.currentConversationId" 
        />
        <el-empty
          v-else
          description="请先选择或创建一个对话"
          :image-size="120"
        />
      </div>
      
      <!-- Agent试题模拟视图 -->
      <div v-show="viewMode === 'exercise'" class="exercise-view">
        <ExerciseViewer v-if="convStore.currentConversationId" />
        <el-empty
          v-else
          description="请先选择或创建一个对话"
          :image-size="120"
        />
      </div>
      
      <!-- 试卷批改视图 -->
      <div v-show="viewMode === 'grading'" class="grading-view">
        <GradingViewer v-if="convStore.currentConversationId" />
        <el-empty
          v-else
          description="请先选择或创建一个对话"
          :image-size="120"
        />
      </div>

      <!-- 个人纪录视图 -->
      <div v-show="viewMode === 'record'" class="record-view">
        <RecordViewer v-if="convStore.currentConversationId" />
        <el-empty
          v-else
          description="请先选择或创建一个对话"
          :image-size="120"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { Document, Connection, EditPen, Finished } from '@element-plus/icons-vue'
import { useConversationStore } from '../../stores/conversationStore'
import PPTViewer from '../PPTViewer/PPTViewer.vue'
import MindMapViewer from '../MindMapViewer/MindMapViewer.vue'
import ExerciseViewer from '../ExerciseViewer/ExerciseViewer.vue'
import GradingViewer from '../GradingView/GradingView.vue'
import RecordViewer from '../RecordView/RecordView.vue'

const emit = defineEmits(['view-mode-change'])

const props = defineProps({
  currentDocumentId: {
    type: String,
    default: null
  }
})

const convStore = useConversationStore()
const viewMode = ref('ppt')

// 通知父组件视图模式变化
watch(viewMode, (newMode) => {
  console.log('🔄 视图模式切换:', newMode)
  emit('view-mode-change', newMode)
  
  // 当切换到思维脑图视图时，确保组件加载
  if (newMode === 'mindmap' && convStore.currentConversationId) {
    console.log('🔄 切换到思维脑图视图，对话ID:', convStore.currentConversationId)
    // 使用 nextTick 确保组件已经渲染
    nextTick(() => {
      // 组件会自动通过 onMounted 或 watch 加载，这里只是触发一下
      console.log('✅ 思维脑图视图已切换')
    })
  }
})
</script>

<style scoped>
.view-switcher {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.switcher-header {
  padding: 12px;
  border-bottom: 1px solid #e4e7ed;
  background-color: #fff;
  display: flex;
  justify-content: center;
}

.view-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.ppt-view,
.mindmap-view,
.exercise-view,
.grading-view,
.record-view {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>