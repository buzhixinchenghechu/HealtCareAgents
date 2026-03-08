
# 阿片类药物辅助决策系统（Web）

基于 Streamlit 构建的临床决策支持网站，面向阿片类药物处方场景，包含以下模块：

- 工作台总览
- 临床辅助（病例输入、ORT 风险分层、处方建议、合规提示）
- 虚拟训练场（病例生成、方案评分、训练记录）
- 文献与政策库（政策检索、合规核查、政策问答）
- 个人中心
- 登录与安全

## 1. 环境要求

- Python 3.9+
- Windows / macOS / Linux

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 启动方式

方式一（推荐，Windows）：

```bat
run.bat
```

方式二（通用）：

```bash
streamlit run app.py
```

默认访问地址：`http://localhost:8501`

## 4. API Key（可选）

系统支持无 Key 运行（使用本地规则建议）。

如需启用 AI 增强建议，可配置任一 Key：

- `DASHSCOPE_API_KEY`（优先使用）
- `OPENAI_API_KEY`

可在环境变量中配置，或创建 `.streamlit/secrets.toml`：

```toml
DASHSCOPE_API_KEY = "your_key"
OPENAI_API_KEY = "your_key"
```

## 5. 数据文件

示例病例数据位于：

`data/cases/sample_cases.json`

