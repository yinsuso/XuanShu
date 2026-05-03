// cluster.js - 集群协作辅助逻辑 (保留兼容性)

// 这些函数现在由 main.js 统一管理
// 此处仅保留向后兼容的包装，避免覆盖已有实现

// 如果 main.js 未定义 createCluster，则提供一个默认实现
if (typeof window.createCluster === 'undefined') {
  window.createCluster = function() {
    console.warn('createCluster 未就绪');
    alert('协作功能暂不可用');
  };
}

if (typeof window.joinCluster === 'undefined') {
  window.joinCluster = function() {
    console.warn('joinCluster 未就绪');
    alert('协作功能暂不可用');
  };
}

// 不再重新定义，避免覆盖 main.js 的实现
// window.createCluster = createCluster;
// window.joinCluster = joinCluster;
