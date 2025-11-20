import { api } from './api'

/**
 * 样本试题服务
 */
class ExerciseService {
  /**
   * 上传样本试题
   * @param {string} conversationId - 对话ID
   * @param {FileList|File[]} files - 文件列表
   * @returns {Promise<Object>} 上传结果
   */
  async uploadSamples(conversationId, files) {
    const formData = new FormData()
    Array.from(files).forEach(file => {
      formData.append('files', file)
    })
    
    const response = await api.post(
      `/api/conversations/${conversationId}/exercises/samples/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      }
    )
    return response
  }

  /**
   * 获取样本试题列表
   * @param {string} conversationId - 对话ID
   * @returns {Promise<Object>} 样本列表
   */
  async listSamples(conversationId) {
    const response = await api.get(
      `/api/conversations/${conversationId}/exercises/samples`
    )
    return response
  }

  /**
   * 获取样本试题详情
   * @param {string} conversationId - 对话ID
   * @param {string} sampleId - 样本ID
   * @returns {Promise<Object>} 样本详情
   */
  async getSample(conversationId, sampleId) {
    const response = await api.get(
      `/api/conversations/${conversationId}/exercises/samples/${sampleId}`
    )
    return response
  }

  /**
   * 获取样本试题文本内容
   * @param {string} conversationId - 对话ID
   * @param {string} sampleId - 样本ID
   * @returns {Promise<Object>} 文本内容
   */
  async getSampleText(conversationId, sampleId) {
    const response = await api.get(
      `/api/conversations/${conversationId}/exercises/samples/${sampleId}/text`
    )
    return response
  }

  /**
   * 获取样本试题图片
   * @param {string} conversationId - 对话ID
   * @param {string} sampleId - 样本ID
   * @param {string} imageName - 图片名称
   * @returns {string} 图片URL
   */
  getSampleImageUrl(conversationId, sampleId, imageName) {
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    return `${baseURL}/api/conversations/${conversationId}/exercises/samples/${sampleId}/images/${imageName}`
  }

  /**
   * 获取样本试题原始文件URL
   * @param {string} conversationId - 对话ID
   * @param {string} sampleId - 样本ID
   * @returns {string} 文件URL
   */
  getSampleFileUrl(conversationId, sampleId) {
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    return `${baseURL}/api/conversations/${conversationId}/exercises/samples/${sampleId}/file`
  }

  /**
   * 删除样本试题
   * @param {string} conversationId - 对话ID
   * @param {string} sampleId - 样本ID
   * @returns {Promise<void>}
   */
  async deleteSample(conversationId, sampleId) {
    await api.delete(
      `/api/conversations/${conversationId}/exercises/samples/${sampleId}`
    )
  }


  /**
   * 获取当前会话生成的题目列表
   * @param {string} conversationId - 对话ID
   * @returns {Promise<Object>} { conversation_id, question_count, questions }
   */
  async getGeneratedQuestions(conversationId) {
    const response = await api.get(
      `/api/conversations/${conversationId}/exercises/generated_questions`
    )
    return response
  }
}

export default new ExerciseService()

