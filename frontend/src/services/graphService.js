import { api } from './api'

/**
 * 知识图谱查询服务
 */
class GraphService {
  /**
   * 获取知识图谱（实体和关系）
   * @param {string} conversationId - 对话ID
   * @returns {Promise<Object>} 包含 entities, relations, total_entities, total_relations 的对象
   */
  async getGraph(conversationId) {
    const response = await api.get(`/api/conversations/${conversationId}/graph`)
    return response
  }

  /**
   * 获取实体详情
   * @param {string} conversationId - 对话ID
   * @param {string} entityId - 实体ID（实体名称）
   * @returns {Promise<Object>} 实体对象
   */
  async getEntity(conversationId, entityId) {
    const response = await api.get(
      `/api/conversations/${conversationId}/graph/entities/${encodeURIComponent(entityId)}`
    )
    return response
  }

  /**
   * 查询知识图谱
   * @param {string} conversationId - 对话ID
   * @param {string} query - 查询文本
   * @param {string} mode - 查询模式（naive/local/global/mix，默认 mix）
   * @returns {Promise<Object>} 查询结果
   */
  async query(conversationId, query, mode = 'naive') {
    const response = await api.post(`/api/conversations/${conversationId}/query`, {
      query,
      mode
    })
    return response
  }
}

export default new GraphService()

