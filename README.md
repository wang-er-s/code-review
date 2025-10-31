# Git代码审查服务

基于Git Hooks的自动化代码审查系统，支持Unity C#代码和Asset配置文件审查，审查结果自动发送到飞书。

## 功能特性

- ✅ Git提交后自动触发审查
- ✅ 支持C#代码审查（代码规范、逻辑错误、性能、架构）
- ✅ 支持Unity Asset配置文件审查
- ✅ 集成LLM CLI工具进行智能审查
- ✅ 审查结果自动发送飞书消息卡片
- ✅ 支持异步/同步审查模式
- ✅ 审查结果缓存，避免重复审查

## 目录结构

```
Hooks/
├── config/
│   ├── config.yaml              # 主配置文件
│   └── prompts/
│       ├── code_review.txt      # 代码审查prompt模板
│       └── asset_review.txt     # Asset审查prompt模板
├── src/
│   ├── git_handler.py           # Git操作处理
│   ├── llm_client.py            # LLM CLI调用
│   ├── feishu_client.py         # 飞书消息发送
│   ├── review_engine.py         # 审查引擎核心
│   └── main.py                  # 主入口程序
├── hooks/
│   └── post-receive             # Git hook脚本
├── logs/                        # 日志目录
├── temp/                        # 临时文件目录
├── requirements.txt             # Python依赖
└── README.md                    # 本文档
```

## 部署步骤

### 1. 环境准备

**Ubuntu服务器要求：**
- Python 3.8+
- Git 2.0+
- 网络访问（调用LLM API和飞书webhook）

**安装Python依赖：**
```bash
cd /path/to/MergeBattle/Unity/Hooks
pip3 install -r requirements.txt
```

### 2. 配置文件修改

编辑 `config/config.yaml`：

```yaml
git:
  # 修改为你的bare仓库路径
  repo_path: "/path/to/your/repo.git"

llm:
  # 修改为你的LLM CLI工具路径
  cli_path: "/path/to/your/llm-cli"
  
  # 根据你的CLI工具调整参数格式
  cli_args: "--input {input_file} --output {output_file}"

feishu:
  # 修改为你的飞书机器人webhook地址
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN"
```

### 3. 配置LLM CLI工具

你的LLM CLI工具需要满足以下接口规范：

**输入：**
- 通过 `--input` 参数接收文本文件路径
- 文件内容为审查prompt + 代码diff

**输出：**
- 通过 `--output` 参数指定JSON结果文件路径
- 或直接输出JSON到stdout

**JSON格式：**
```json
{
  "issues": [
    {
      "severity": "error",        // error|warning|info
      "file": "BattleScene.cs",
      "line": 42,
      "message": "问题描述",
      "category": "性能"
    }
  ],
  "summary": "总体评价"
}
```

**CLI示例：**
```bash
# 方式1: 输出到文件
your-llm-cli --input /tmp/input.txt --output /tmp/result.json

# 方式2: 输出到stdout
your-llm-cli --input /tmp/input.txt
```

### 4. 安装Git Hook

**复制hook到bare仓库：**
```bash
# 假设你的bare仓库在 /srv/git/myproject.git
cp hooks/post-receive /srv/git/myproject.git/hooks/post-receive
chmod +x /srv/git/myproject.git/hooks/post-receive
```

**编辑hook脚本，修改配置：**
```bash
vim /srv/git/myproject.git/hooks/post-receive
```

修改以下配置项：
```bash
PYTHON="/usr/bin/python3"                                # Python路径
REVIEW_SERVICE_DIR="/path/to/MergeBattle/Unity/Hooks"   # 审查服务路径
ENABLE_REVIEW=true                                       # 是否启用
ASYNC_MODE=true                                          # 是否异步执行
```

### 5. 测试验证

**测试Git hook是否触发：**
```bash
# 在本地仓库做一次提交并push
git commit --allow-empty -m "测试审查系统"
git push origin main
```

**查看日志：**
```bash
# Hook日志
tail -f /path/to/MergeBattle/Unity/Hooks/logs/hook.log

# 审查服务日志
tail -f /path/to/MergeBattle/Unity/Hooks/logs/review.log
```

**手动测试审查服务：**
```bash
cd /path/to/MergeBattle/Unity/Hooks
python3 src/main.py <old_commit_hash> <new_commit_hash> refs/heads/main
```

## 配置说明

### 文件类型过滤

在 `config.yaml` 中配置需要审查的文件类型：

```yaml
review:
  file_rules:
    # C#代码
    - name: "csharp_code"
      extensions: [".cs"]
      exclude_patterns: [".meta", ".csproj", "*.Designer.cs"]
      max_file_size: 10000
      review_type: "code"
    
    # Unity Asset
    - name: "unity_asset"
      path_pattern: "Assets/Config/Unity/**/*.asset"
      extensions: [".asset"]
      max_file_size: 5000
      review_type: "unity_asset"
```

### Prompt模板自定义

编辑 `config/prompts/code_review.txt` 和 `asset_review.txt` 来自定义审查重点。

### 飞书消息格式

消息卡片自动包含：
- 提交信息（commit hash、作者、时间、消息）
- 审查统计（文件数、问题数、错误/警告/建议分类）
- 问题详情（按文件分组，显示严重程度、位置、描述）

## 高级配置

### 分支过滤

在 `hooks/post-receive` 中启用分支过滤：

```bash
case "$refname" in
    refs/heads/main|refs/heads/develop)
        # 只审查这些分支
        ;;
    *)
        continue
        ;;
esac
```

### 性能优化

```yaml
advanced:
  enable_cache: true              # 启用缓存，避免重复审查
  max_files_per_commit: 50        # 限制单次提交审查文件数
  continue_on_error: true         # 某个文件失败时继续审查其他文件
```

### 同步 vs 异步模式

**异步模式（推荐）：**
- Hook立即返回，不阻塞push
- 审查在后台执行
- 适合大多数场景

**同步模式：**
- 等待审查完成后才返回
- push会等待审查结果
- 适合严格要求实时反馈的场景

在 `hooks/post-receive` 中切换：
```bash
ASYNC_MODE=true   # 异步
ASYNC_MODE=false  # 同步
```

## 故障排查

### Hook没有触发

1. 检查hook是否有执行权限：
   ```bash
   ls -l /path/to/repo.git/hooks/post-receive
   chmod +x /path/to/repo.git/hooks/post-receive
   ```

2. 检查hook日志：
   ```bash
   tail -f logs/hook.log
   ```

3. 手动执行hook测试：
   ```bash
   echo "old_hash new_hash refs/heads/main" | /path/to/repo.git/hooks/post-receive
   ```

### 审查服务异常

1. 检查Python依赖：
   ```bash
   pip3 list | grep -E "GitPython|requests|PyYAML"
   ```

2. 检查配置文件路径：
   ```bash
   python3 -c "import yaml; print(yaml.safe_load(open('config/config.yaml')))"
   ```

3. 检查Git仓库访问：
   ```bash
   python3 -c "import git; repo=git.Repo('/path/to/repo.git'); print(repo.head)"
   ```

### LLM调用失败

1. 检查CLI工具路径：
   ```bash
   ls -l /path/to/your/llm-cli
   ```

2. 手动测试CLI：
   ```bash
   echo "测试内容" > /tmp/test.txt
   /path/to/your/llm-cli --input /tmp/test.txt --output /tmp/result.json
   cat /tmp/result.json
   ```

3. 检查超时设置（config.yaml）：
   ```yaml
   llm:
     timeout: 300  # 增加超时时间
   ```

### 飞书消息未收到

1. 检查webhook地址是否正确
2. 检查网络连接：
   ```bash
   curl -X POST "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"msg_type":"text","content":{"text":"测试"}}'
   ```
3. 检查是否禁用了飞书通知（config.yaml）：
   ```yaml
   feishu:
     enable: true
   ```

## 维护

### 日志清理

日志文件位于 `logs/` 目录，建议定期清理：

```bash
# 删除30天前的日志
find logs/ -name "*.log" -mtime +30 -delete
```

或使用logrotate配置自动轮转。

### 缓存清理

```bash
# 清空审查缓存
rm temp/review_cache.json
```

## 扩展开发

### 添加新的文件类型支持

1. 在 `config.yaml` 添加文件规则
2. 在 `config/prompts/` 添加对应的prompt模板
3. 如需特殊处理逻辑，修改 `review_engine.py` 中的 `_review_single_file` 方法

### 集成其他通知渠道

参考 `feishu_client.py` 实现新的通知客户端，如钉钉、企业微信等。

## 许可证

内部项目使用

