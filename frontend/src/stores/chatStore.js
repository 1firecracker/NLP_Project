import { defineStore } from 'pinia'
import { ref } from 'vue'
import chatService from '../services/chatService'

export const useChatStore = defineStore('chat', () => {
  // 状态：每个对话的消息列表 { conversationId: [messages] }
  const messages = ref({})
  
  // Actions
  /**
   * 获取对话的消息列表
   */
  function getMessages(conversationId) {
    if (!conversationId) return []
    return messages.value[conversationId] || []
  }
  
  /**
   * 添加消息到对话
   */
  function addMessage(conversationId, message) {
    if (!conversationId) return
    
    if (!messages.value[conversationId]) {
      messages.value[conversationId] = []
    }
    
    messages.value[conversationId].push(message)
  }
  
  /**
   * 加载对话历史消息
   */
  async function loadMessages(conversationId) {
    if (!conversationId) return
    
    try {
      const history = await chatService.getHistory(conversationId)
      const loadedMessages = history.messages || []
      // console.log(`📥 [前端] 加载消息历史，对话ID: ${conversationId}，共 ${loadedMessages.length} 条消息`)
      
      // 处理历史消息，修复 pending 状态的工具调用
      // 如果工具调用已经保存到历史，说明已经执行完成，应该将 pending 状态改为 success 或 error
      const processedMessages = loadedMessages.map(msg => {
        const processedMsg = { ...msg }
        
        // 处理 streamItems 中的 pending 状态或缺失的 status 字段
        if (processedMsg.streamItems && Array.isArray(processedMsg.streamItems)) {
          processedMsg.streamItems = processedMsg.streamItems.map(item => {
            if (item.type === 'tool_call') {
              // 检查 status 是否为 pending 或缺失（undefined、null、空字符串）
              const needsFix = !item.status || item.status === 'pending' || item.status === '' || item.status === null || item.status === undefined
              
              if (needsFix) {
                // 如果已经有结果，说明执行成功了；如果有错误信息，说明执行失败了
                if (item.result) {
                  item.status = 'success'
                  // console.log(`🔧 [前端] 修复工具调用状态: ${item.toolName} ${item.status || '缺失'} -> success (已有结果)`)
                } else if (item.errorMessage) {
                  item.status = 'error'
                  // console.log(`🔧 [前端] 修复工具调用状态: ${item.toolName} ${item.status || '缺失'} -> error (有错误信息)`)
                } else {
                  // 如果既没有结果也没有错误信息，但状态是 pending 或缺失，说明可能还在执行中
                  // 但既然已经保存到历史，说明已经执行完成了，默认改为 success
                  item.status = 'success'
                  // console.log(`🔧 [前端] 修复工具调用状态: ${item.toolName} ${item.status || '缺失'} -> success (默认，已保存到历史)`)
                }
              }
            }
            return item
          })
        }
        
        // 处理 toolCalls 中的 pending 状态或缺失的 status 字段（向后兼容）
        if (processedMsg.toolCalls && Array.isArray(processedMsg.toolCalls)) {
          processedMsg.toolCalls = processedMsg.toolCalls.map(tc => {
            // 检查 status 是否为 pending 或缺失（undefined、null、空字符串）
            const needsFix = !tc.status || tc.status === 'pending' || tc.status === '' || tc.status === null || tc.status === undefined
            
            if (needsFix) {
              // 如果已经有结果，说明执行成功了；如果有错误信息，说明执行失败了
              if (tc.result) {
                tc.status = 'success'
                // console.log(`🔧 [前端] 修复工具调用状态: ${tc.toolName} ${tc.status || '缺失'} -> success (已有结果)`)
              } else if (tc.errorMessage) {
                tc.status = 'error'
                // console.log(`🔧 [前端] 修复工具调用状态: ${tc.toolName} ${tc.status || '缺失'} -> error (有错误信息)`)
              } else {
                // 如果既没有结果也没有错误信息，但状态是 pending 或缺失，说明可能还在执行中
                // 但既然已经保存到历史，说明已经执行完成了，默认改为 success
                tc.status = 'success'
                // console.log(`🔧 [前端] 修复工具调用状态: ${tc.toolName} ${tc.status || '缺失'} -> success (默认，已保存到历史)`)
              }
            }
            return tc
          })
        }
        
        return processedMsg
      })
      
      // 统计各类型消息数量
      const roleCounts = {}
      processedMessages.forEach(msg => {
        const role = msg.role || 'unknown'
        roleCounts[role] = (roleCounts[role] || 0) + 1
      })
      // console.log(`📊 [前端] 消息类型统计:`, roleCounts)
      
      // 打印前几条消息的详细信息（用于调试）
      processedMessages.slice(0, 5).forEach((msg, index) => {
        // console.log(`📝 [前端] 消息 ${index + 1}: role="${msg.role}", content长度=${msg.content ? msg.content.length : 0}, hasStreamItems=${!!msg.streamItems}, hasToolCalls=${!!msg.toolCalls}`)
      })
      
      messages.value[conversationId] = processedMessages
    } catch (error) {
      console.error('加载消息历史失败:', error)
      // 如果加载失败，初始化为空数组
      if (!messages.value[conversationId]) {
        messages.value[conversationId] = []
      }
    }
  }
  
  /**
   * 流式查询
   */
  async function queryStream(conversationId, query, mode, agentIntent, onChunk) {
    if (!conversationId) throw new Error('请先选择对话')
    
    await chatService.queryStream(conversationId, query, mode, agentIntent, onChunk)
  }
  
  /**
   * 保存消息到后端
   */
  async function saveMessage(conversationId, query, answer, toolCalls = null, streamItems = null) {
    if (!conversationId) return
    
    try {
      await chatService.saveMessage(conversationId, query, answer, toolCalls, streamItems)
    } catch (error) {
      console.error('保存消息失败:', error)
      // 保存失败不影响用户体验，只记录错误
    }
  }
  
  /**
   * 清空对话消息
   */
  function clearMessages(conversationId = null) {
    if (conversationId) {
      delete messages.value[conversationId]
    } else {
      messages.value = {}
    }
  }
  
  return {
    messages,
    getMessages,
    addMessage,
    loadMessages,
    queryStream,
    saveMessage,
    clearMessages
  }
})

