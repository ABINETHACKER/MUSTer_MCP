# MUSTer MCP Server

> 一个为了MUSTer准备的MCP服务器。给予 LLM 和 M.U.S.T.(澳门科技大学) 校园系统互动的能力。

![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-Server-orange)
![Package Manager](https://img.shields.io/badge/uv-fast-purple)

它可以帮你搞定 Wemust 和 Moodle 上的那些繁琐操作。

现在 LLM 可以自动登录 Wemust 和 Moodle ，获取课表，查询课程PPT、作业，查看代办事项，下载课件，自动打开页面。

## 工具一览
- `get_class_schedule`：**查课表**。直接拉取本周课程安排。
- `get_pending_events`：**看 DDL**。列出 Moodle 上快到期的作业和待办。
- `get_all_courses`：**列出课程**。获取 Moodle 面板上所有课程的名字和链接。
- `get_course_content`：**查详情**。读取具体课程里的作业 (Assignment) 或测验 (Quiz) 信息。
- `download_resource`：**下课件**。把 Moodle 资源页的文件下回来（尤其是批量下 PPT 很方便）这里还可以让大模型选择某个文件夹。
- `open_URL_with_authorization`：**免密打开**。直接弹出一个已自动登录的 Chrome 窗口，不用手动输账号密码，自动打开指定页面。
- `get_current_time`：获取当前系统时间戳。

## 环境依赖
- Python 3.12+
- 本地可用的 Chrome/Chromedriver（Selenium 使用）。
- 环境变量：`MUSTER_USERNAME`、`MUSTER_PASSWORD`（必填）；`MUSTER_DOWNLOAD_PATH`（可选，下载时默认选择的路径，默认 `~/Downloads`）。

## 安装
1) 安装 [uv](https://docs.astral.sh/uv/)（快速的 Python 包管理工具）。
2) 克隆仓库并安装依赖：
```bash
git clone https://github.com/Cosmostima/MUSTer_MCP

cd MUSTer_MCP

uv sync
```

## MCP 客户端配置示例
```json
{
  "mcpServers": {
    "muster": {
      "command": "UV_PATH_HERE",
      "args": [
        "--directory",
        "MCP_FOLDER_PATH_HERE",
        "run",
        "main.py"
      ],
      "env": {
              "MUSTER_USERNAME": "YOUR_ID_HERE",
              "MUSTER_PASSWORD": "YOUR_PASSWORD_HERE"
      }
    }
}
```

如果需要自定义下载默认路径，可添加`MUSTER_DOWNLOAD_PATH` 如：

```json
{
  "mcpServers": {
    "muster": {
      "command": "UV_PATH_HERE",
      "args": [
        "--directory",
        "MCP_FOLDER_PATH_HERE",
        "run",
        "main.py"
      ],
      "env": {
              "MUSTER_USERNAME": "YOUR_ID_HERE",
              "MUSTER_PASSWORD": "YOUR_PASSWORD_HERE",
              "MUSTER_DOWNLOAD_PATH": "/Users/cosmos/Desktop/"
      }
    }
}
```
