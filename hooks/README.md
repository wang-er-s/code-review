# 客户端 Git Hook

客户端Git Hook用于在本地push后自动通知审查机器进行代码审查。

## 功能

- 自动记录push前的远程分支状态
- push后自动发送通知到审查机器
- 支持分支过滤
- 完整的日志记录

## 安装

### 1. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 2. 安装Hook脚本

在仓库根目录运行：

```bash
install-hooks.bat
```

此脚本会将 `hooks/pre-push` 和 `hooks/post-push` 复制到 `.git/hooks/` 目录。

### 3. 配置

编辑 `config/config.yaml`（或 `client/config/config.yaml`）：

```yaml
client:
  # 审查机器地址（HTTP服务地址）
  review_machine_url: "http://192.168.1.100:5000"
  
  # 要审查的分支列表（空列表表示审查所有分支）
  review_branches:
    - "MergeBattle"
  
  # 客户端hook日志文件路径
  log_file: "logs/client_hook.log"
```

## 目录结构

```
client/
├── hooks/
│   ├── pre-push          # pre-push hook脚本
│   └── post-push         # post-push hook脚本
├── src/
│   └── client_hook_handler.py  # Hook处理核心逻辑
├── config/
│   └── config.yaml       # 客户端配置文件
├── install-hooks.bat      # Windows安装脚本
├── requirements.txt       # Python依赖
└── README.md             # 本文档
```

## 工作原理

1. **pre-push hook**：在push前记录远程分支的commit hash
2. **post-push hook**：在push后
   - 读取pre-push记录的状态
   - 获取本次push的所有commit信息
   - 发送HTTP POST请求到审查机器
   - 记录日志

## 测试

```bash
# 做一次空提交测试
git commit --allow-empty -m "测试hook"
git push origin MergeBattle
```

查看日志：
```bash
type logs\client_hook.log
```

## 故障排查

### Hook没有触发

1. 检查hook是否已安装：
   ```bash
   dir .git\hooks\pre-push
   dir .git\hooks\post-push
   ```

2. 检查客户端hook日志：
   ```bash
   type logs\client_hook.log
   ```

3. 手动测试hook处理程序：
   ```bash
   python src\client_hook_handler.py post-push origin <remote_url>
   ```

### 通知发送失败

1. 检查审查机器地址配置是否正确
2. 检查网络连通性：
   ```bash
   ping 审查机器IP
   curl http://审查机器IP:5000/health
   ```

3. 查看日志文件中的错误信息

