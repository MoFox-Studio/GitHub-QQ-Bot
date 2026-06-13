# GitHub QQ Bot

一个自动监控GitHub仓库提交并使用AI生成总结发送到QQ群的机器人。

## 功能特性

- 🔍 **智能监控**：定时检查指定GitHub仓库的新提交
- 🚀 **Release通知**：监视指定仓库Release，发送Release Note和指定资源文件到QQ群
- 🤖 **AI总结**：使用大模型（OpenAI/Claude等）智能总结提交内容
- 📱 **QQ集成**：自动发送总结到指定QQ群
- 💾 **状态管理**：SQLite数据库记录检查状态，避免重复通知
- ⚙️ **灵活配置**：支持多仓库监控、自定义检查间隔
- 🛠️ **命令行工具**：简单易用的CLI界面

## 安装要求

- Python 3.8+
- GitHub Personal Access Token
- OpenAI API Key 或其他兼容的大模型API
- go-cqhttp 或其他QQ机器人服务

## 安装步骤

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd github-qq-bot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 初始化配置

```bash
python main.py init-config
```

这会创建一个 `config.json` 配置文件模板。

### 4. 编辑配置文件

打开 `config.json` 并填入你的配置信息：

```json
{
  "github_token": "ghp_your_github_token",
  "github_repos": ["owner/repo1", "owner/repo2"],
  "release_monitors": {
    "owner/repo1": {
      "asset_files": ["app-release-.*\\.apk", "checksums\\.txt"],
      "include_prerelease": false
    }
  },
  "check_interval": 300,
  "openai_api_key": "sk-your_openai_api_key",
  "openai_base_url": "https://api.openai.com/v1",
  "openai_model": "gpt-3.5-turbo",
  "qq_bot_url": "http://127.0.0.1:5700",
  "qq_group_id": "123456789",
  "database_path": "data.db"
}
```

### 5. 设置QQ机器人

#### 使用go-cqhttp（推荐）

1. 下载 [go-cqhttp](https://github.com/Mrs4s/go-cqhttp)
2. 配置你的QQ账号
3. 启动go-cqhttp服务（默认端口5700）
4. 将机器人加入目标QQ群

## 使用方法

### 启动监控服务

```bash
python main.py run
```

### 测试功能

测试指定仓库的监控：

```bash
python main.py test owner/repo
```

### 命令行选项

```bash
# 查看帮助
python main.py --help

# 使用自定义配置文件
python main.py run --config my_config.json

# 查看版本
python main.py --version
```

## 配置说明

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `github_token` | GitHub Personal Access Token | `ghp_xxxxx` |
| `github_repos` | 要监控提交的仓库列表 | `["owner/repo1", "owner/repo2"]` |
| `release_monitors` | Release监视字典，键为 `owner/repo`，值为监视配置 | `{ "owner/repo1": { "asset_files": ["app.zip"] } }` |
| `check_interval` | 检查间隔（秒） | `300` (5分钟) |
| `openai_api_key` | OpenAI API密钥 | `sk-xxxxx` |
| `openai_base_url` | API基础URL | `https://api.openai.com/v1` |
| `openai_model` | 使用的模型 | `gpt-3.5-turbo` |
| `qq_bot_url` | QQ机器人API地址 | `http://127.0.0.1:5700` |
| `qq_group_id` | 目标QQ群号 | `123456789` |

### Release监视配置

`release_monitors` 是一个按仓库名索引的字典；仓库出现在该字典中即表示启用Release监视。每个仓库支持以下字段：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `asset_files` | 要从Release Assets下载并发送到QQ群的文件名或正则表达式列表 | `[]` |
| `include_prerelease` | 是否通知预发布版本 | `false` |

示例：

```json
{
  "release_monitors": {
    "owner/repo": {
      "asset_files": ["app-release-.*\\.apk", "checksums\\.txt"],
      "include_prerelease": false
    }
  }
}
```

`asset_files` 中的每一项会先按完整文件名精确匹配，找不到时再按正则表达式完整匹配文件名。匹配一段可变文字可以使用 `.*`，例如 `app-release-.*\.apk` 可以匹配 `app-release-v1.2.3.apk`；匹配版本号可以使用 `[0-9]+\.[0-9]+\.[0-9]+`，例如 `plugin-v[0-9]+\.[0-9]+\.[0-9]+\.zip` 可以匹配 `plugin-v1.2.3.zip`。因为配置文件是 JSON，正则里的反斜杠需要写成双反斜杠，例如正则 `\.apk` 在 JSON 中写作 `\\.apk`。

Release通知目标QQ群固定使用全局 `qq_group_id`。程序会记录每个仓库最后成功发送的Release ID，只有Release Note和配置的资源文件都发送成功后才更新状态，避免漏发。

## API Token获取

### GitHub Token

1. 访问 [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. 点击 "Generate new token (classic)"
3. 选择以下权限：
   - `repo` (访问仓库)
   - `public_repo` (如果只监控公开仓库)

### OpenAI API Key

1. 访问 [OpenAI API Keys](https://platform.openai.com/api-keys)
2. 点击 "Create new secret key"
3. 复制生成的密钥

## 部署建议

### 使用systemd (Linux)

创建服务文件 `/etc/systemd/system/github-qq-bot.service`：

```ini
[Unit]
Description=GitHub QQ Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/github-qq-bot
ExecStart=/usr/bin/python3 main.py run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl enable github-qq-bot
sudo systemctl start github-qq-bot
```

### 使用Docker

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "main.py", "run"]
```

## 故障排除

### 常见问题

1. **GitHub API限制**
   - 确保token有足够的权限
   - 检查API请求限制

2. **QQ机器人连接失败**
   - 确认go-cqhttp服务正常运行
   - 检查端口和URL配置

3. **AI总结失败**
   - 检查OpenAI API密钥
   - 确认网络连接正常

### 日志查看

程序会输出详细的运行日志，包括：
- 检查状态
- API调用结果
- 错误信息

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 更新日志

### v1.0.0
- 初始版本
- 基本监控功能
- AI总结集成
- QQ机器人支持
- Release Note和Release资源文件QQ群通知支持 