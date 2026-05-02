// cluster.js - 集群协作辅助逻辑 (保留兼容性)

// 这些函数现在由 main.js 统一管理
// 此处仅保留向后兼容的包装函数

function createCluster() {
  // 已在 main.js 中定义
  if(typeof window.createCluster === 'function') {
    window.createCluster();
  }
}

function joinCluster() {
  // 已在 main.js 中定义
  if(typeof window.joinCluster === 'function') {
    window.joinCluster();
  }
}

// 导出给旧版代码使用
window.createCluster = createCluster;
window.joinCluster = joinCluster;
