# Knowledge Base Frontend

简约圆润风格的知识库管理系统前端界面

## 技术栈

- Vue 3
- Vite
- Tailwind CSS
- Vue Router
- Pinia
- Axios

## 启动方式

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

## 项目结构

```
src/
├── api/           # API 接口
├── views/         # 页面组件
├── router/        # 路由配置
├── App.vue        # 根组件
├── main.js        # 入口文件
└── style.css      # 全局样式
```

## 功能特性

- 知识库管理（创建、查看、删除）
- 文档管理（上传、查看、状态跟踪）
- 文档处理进度监控
- 圆润可爱的 UI 设计
- 响应式布局

## API 配置

前端代理配置在 `vite.config.js` 中，默认代理到 `http://localhost:8000`

如需修改后端地址，请编辑：
```javascript
// vite.config.js
proxy: {
  '/api': {
    target: 'http://localhost:8000',  // 修改这里
    changeOrigin: true
  }
}
```

## 页面说明

- `/knowledge-bases` - 知识库列表页
- `/documents` - 文档列表页
- `/kb/:id` - 知识库详情页
