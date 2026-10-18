# 华为PC营销软文智能体

面向华为PC门店导购与内容运营的**自研营销Agent**（AI+华为PC营销软文智能体赛题作品）。
ima共享知识库仅作为产品事实与图片素材来源；本系统负责理解业务场景、匹配平台规则、
设计系统提示词、组织图文内容，并完成事实核验和营销合规检查。

## 功能

| 功能板块 | 说明 |
|---|---|
| 账号与知识库 | 识别当前账号配置；连接指定共享知识库「任德耀新建华为PC知识库」；界面脱敏展示凭证状态 |
| 任务输入 | 自然语言任务解析；产品/人群/场景/渠道四要素识别；信息不足时智能追问；相近型号歧义澄清 |
| 知识与图片检索 | 按型号与任务调用 ima OpenAPI（search_knowledge_base / get_knowledge_list / search_knowledge / get_media_info）；检索产品资料与图片并保留来源记录；凭证未配置时自动回退同源本地知识库 |
| 场景与平台策略 | 提取人群、问题、购买阶段、内容目标，形成可解释内容策略；换场景切入点实质变化，换平台结构/语气/配图数/引导全部改变 |
| 图文软文生成 | 输出标题、导语、正文、行动引导、配图方案（图片来源、说明、建议插入位置）、平台标签 |
| 事实核验 | 逐项核对产品声明与知识库事实；相近型号混淆检测（如 X Pro vs X）；无依据内容标记或删除 |
| 合规检查 | 规则引擎+语义复核：绝对化用语、虚假承诺、价格误导、无依据对比、竞品贬低、伪造体验 |
| 修改与导出 | 临时要求重新生成（删减/换渠道/替换卖点）；导出统一输出格式 Markdown 与完整 JSON |

## 标准流程

```
场景解析 → 平台策略 → ima资料与图片检索 → 事实点提取 → 图文编排 → 软文生成
→ 事实与图片核验 → 合规检查 → 导出
```

## 安装

要求 Python 3.9+。

```bash
cd huawei-pc-marketing-agent
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 配置

复制环境变量模板并填写（**密钥严禁写入源码或提交仓库**）：

```bash
cp .env.example .env
```

也可以不建 `.env`：启动Web界面后，在侧边栏 **「🔑 接口凭证配置」** 中直接填写
LLM Key 与 ima 凭证并点击「保存并应用」，可选同步写入本地 `.env`（已被 .gitignore 排除）。
界面全程不展示完整密钥。

**ima凭证获取**：安装并登录 ima Windows 客户端 → 用加入知识库的同一账号进入
「Claw配置」→ 接口凭证页面获取 Client ID 和 API Key（或访问 `https://ima.qq.com/agent-interface`）。

| 变量 | 必填 | 说明 |
|---|---|---|
| `LLM_API_KEY` | 是 | OpenAI兼容接口Key（OpenAI/DeepSeek/通义等） |
| `LLM_BASE_URL` | 是 | OpenAI兼容服务地址 |
| `LLM_MODEL` | 是 | 模型名，如 `gpt-4o` / `deepseek-chat` |
| `IMA_OPENAPI_CLIENTID` | 否* | ima接口凭证（ima客户端→Claw配置→接口凭证） |
| `IMA_OPENAPI_APIKEY` | 否* | 同上 |
| `LOCAL_KB_ROOT` | 否 | 本地知识库兜底路径，默认上级目录P1-P8知识库 |

\* 赛题要求最终调用ima OpenAPI；未配置时自动使用与ima同源的本地知识库兜底，界面与输出中会标注实际来源。

## 运行

### Web界面（推荐）

```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501`：左侧填任务 → 生成 → 查看执行过程、图文软文、配图方案、
核验结果 → 导出统一输出格式 / 按临时要求重新生成。

### 命令行Demo

```bash
python scripts/run_demo.py --product "HUAWEI MateBook Pro" --audience 大学新生 \
    --scenario 开学季 --platform 小红书
```

结果按赛题统一输出格式打印，并保存到 `data/outputs/`。

## 统一输出格式

```
一、场景判断   目标人群 / 使用场景 / 用户问题 / 内容目标 / 平台
二、知识库依据 产品型号 / 事实点 / 资料标题（依据可追溯）
三、图文软文   标题 / 导语 / 正文 / 行动引导 / 图片名称 / 来源 / 插入位置 / 图片说明
四、核验结果   产品事实 / 图片型号 / 合规 / 待确认信息
```

## 项目结构

```
huawei-pc-marketing-agent/
├── app.py                  # Streamlit界面
├── agent/
│   ├── config.py           # 环境变量配置（密钥脱敏）
│   ├── models.py           # 数据模型（任务/策略/事实/图片/核验）
│   ├── ima_client.py       # ima OpenAPI客户端（A-D四步接口）
│   ├── local_kb.py         # 本地P1-P8知识库兜底检索
│   ├── knowledge.py        # 统一知识检索层（ima优先，本地兜底）
│   ├── llm_client.py       # OpenAI兼容LLM客户端
│   ├── prompts.py          # 系统提示词（八模块）与各阶段提示词
│   ├── compliance.py       # 合规规则引擎
│   ├── enrich/             # 增强库：官网公开页爬取 → 结构化入库
│   └── pipeline.py         # Agent主管线（九步标准流程）
├── data/
│   ├── enriched/           # 增强库样例（公开官网页结构化数据）
│   └── outputs/            # 导出样例（统一输出格式 md + 完整 json）
└── scripts/
    ├── run_demo.py         # 命令行Demo
    └── build_package.py    # 打包
```

## 示例数据

仓库自带一份真实跑通的示例数据，clone 后即可查看效果，无需重新抓取或调用模型：

| 路径 | 内容 | 来源 |
|---|---|---|
| `data/enriched/index.json` | 增强库总索引（型号 → 本地文件映射 / 抓取页数） | 程序生成 |
| `data/enriched/<型号>/product.json` | 单个型号的结构化数据：本地资料映射 + 官网功能页/规格页正文与标题结构 | 华为官网**公开**产品页与规格页，抓取日期见文件 `fetched_at` |
| `data/outputs/*.md` | 统一输出格式成品（场景判断 / 知识库依据 / 图文软文 / 核验结果） | 本地同源知识库 + LLM 真实生成 |
| `data/outputs/*.json` | 同一次生成的完整 JSON（含事实点、图片方案、核验与合规明细） | 同上 |

说明：

- 示例数据只含**公开可查**的产品事实与官网页面内容，不含价格、补贴、库存、销量、返点等内部信息。
- 所有来源路径均为**相对知识库根目录**的形式（如 `P1-产品参数库/...`），不包含任何本机绝对路径。
- `data/cache/`（接口缓存）与 `data/logs/`（运行日志）属于本机运行状态，不进入仓库，首次运行自动生成。
- 想换成自己的数据：把 `LOCAL_KB_ROOT` 指向你的 P1-P8 知识库根目录，或在界面「增强库」面板里扫描型号文件夹并爬取官网链接，产物会覆盖写入 `data/enriched/`。

## 安全说明

- API Key / Client ID 仅经环境变量注入，代码、README、输出中只展示脱敏形态。
- 生成内容禁止绝对化宣传、虚假承诺、无依据对比、价格误导与竞品贬低；知识库无依据的价格、
  补贴、销量、奖项、用户评价一律不生成。
- 知识库资料仅按开放权限读取，不修改、不外传。
