# 审查服务器端

审查服务器端接收来自客户端的通知，执行代码审查并发送结果到飞书。

## 功能

- HTTP服务接收客户端通知
- 自动拉取代码更新
- 执行代码审查
- 发送审查结果到飞书

## 安装

### 1. 环境要求

- Python 3.8+
- Git 2.0+
- 网络访问（调用LLM API和飞书webhook）
- 能够访问Git服务器（用于git pull）

### 2. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 3. 克隆工作仓库

审查机器需要有自己的工作仓库副本：

```bash
git clone <repository_url> E:\ReviewWork\your-project
```

### 4. 配置

编辑 `config/config.yaml`：

```yaml
git:
  # 审查机器上的工作仓库路径
  work_repo_path: "E:\\ReviewWork\\your-project"

# ... 其他配置（LLM、飞书等）...

# 审查服务器配置
review_server:
  host: "0.0.0.0"          # 监听所有网络接口
  port: 5000               # 监听端口
  review_branches:         # 要审查的分支列表
    - "MergeBattle"
```

### 5. 启动服务

**方式1：直接运行**
```bash
python src/review_server.py
```

**方式2：后台运行（Windows）**
```bash
# 创建 start_review_server.bat
@echo off
cd /d E:\Hooks\server
python src/review_server.py
```

**方式3：使用nssm创建Windows服务**
```bash
nssm install ReviewServer "python" "E:\Hooks\server\src\review_server.py"
nssm start ReviewServer
```

服务器启动后会显示：
```
审查服务器启动
监听地址: http://0.0.0.0:5000
审查端点: http://0.0.0.0:5000/review
健康检查: http://0.0.0.0:5000/health
```

## 目录结构

```
server/
├── src/
│   ├── review_server.py   # HTTP服务
│   ├── review_engine.py   # 审查引擎
│   ├── git_handler.py     # Git操作
│   ├── llm_client.py      # LLM客户端
│   ├── feishu_client.py   # 飞书客户端
│   ├── main.py            # 主入口（服务器端模式）
│   └── config1.py         # 配置类
├── config/
│   ├── config.yaml        # 服务器配置文件
│   └── prompts/
│       ├── code_review.txt
│       └── asset_review.txt
├── requirements.txt       # Python依赖
└── README.md             # 本文档
```

## API接口

### POST /review

接收审查请求。

**请求格式：**
```json
{
  "repository_url": "git@server:/path/to/repo.git",
  "branch": "MergeBattle",
  "old_rev": "abc123...",
  "new_rev": "def456...",
  "ref_name": "refs/heads/MergeBattle",
  "commits": [...],
  "push_time": "2024-01-01T12:00:00Z"
}
```

**响应格式：**
```json
{
  "status": "success",
  "message": "审查完成",
  "old_rev": "abc123",
  "new_rev": "def456",
  "branch": "MergeBattle"
}
```

### GET /health

健康检查端点。

## 测试

### 健康检查
```bash
curl http://localhost:5000/health
```

### 手动发送审查请求
```bash
curl -X POST http://localhost:5000/review \
  -H "Content-Type: application/json" \
  -d "{\"branch\":\"MergeBattle\",\"old_rev\":\"abc123\",\"new_rev\":\"def456\",\"ref_name\":\"refs/heads/MergeBattle\"}"
```

## 故障排查

### 服务器无法启动

1. 检查端口是否被占用：
   ```bash
   netstat -ano | findstr :5000
   ```

2. 检查配置文件路径是否正确

3. 检查Python依赖是否安装完整

### 无法接收请求

1. 检查防火墙设置（确保5000端口开放）

2. 检查网络连通性

3. 查看服务器日志：
   ```bash
   type logs\review.log
   ```

### Git pull失败

1. 检查工作仓库路径配置是否正确

2. 检查Git服务器访问权限

3. 手动测试git pull：
   ```bash
   cd E:\ReviewWork\your-project
   git pull origin MergeBattle
   ```

