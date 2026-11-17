# C5A · GitHub 入门与仓库理解

用 GitHub REST API 实时抓取 **4 个形态完全不同的真实仓库**，反推一套可复用的「读库方法」；并用 11 组真实 Git 命令做排错实验，把"能跑通的部分"和"本机崩溃跑不通的部分"分开留证。

**公开仓库地址：<https://github.com/Leo-web-lhy/c5a-github-repo-understanding>**

---

## 1. 交付物一览

| 文件 | 内容 | 为什么需要它 |
|---|---|---|
| [`仓库分析.md`](仓库分析.md) | 四仓库「七层读库法」逐层拆解 + 横向对比 + 方法可迁移性论证 | 本挑战的核心交付物 |
| [`README.md`](README.md) | 本文件：项目说明、如何复跑、数据来源 | 让陌生人 30 秒内看懂仓库在做什么 |
| [`AI日志.md`](AI日志.md) | 与 AI 协作的完整过程：指令、错误、纠正、返工 | 证明交付物不是「一句话生成」 |
| [`AAR.md`](AAR.md) | 复盘：目标 vs 结果、失败归因、下一步改进 | 反思质量 |
| [`排错实验/Git排错实验记录.md`](排错实验/Git排错实验记录.md) | 11 组 Git 实验，逐条记录命令 + 真实退出码 | Git 掌握度的**可验证**证据 |
| [`排错实验/experiments.log`](排错实验/experiments.log) | 上述实验的原始日志（未加工） | 可复核，不靠自述 |
| [`scripts/analyze_repos.py`](scripts/analyze_repos.py) | 抓取 GitHub API 并落盘原始 JSON | 数字可复现 |
| [`scripts/digest.py`](scripts/digest.py) | 把 43 KB 原始 JSON 压成 9.4 KB 摘要 | 控制上下文成本 |
| [`data/repos.json`](data/repos.json) | 原始抓取结果（43193 字节） | 一手数据 |
| [`data/digest.md`](data/digest.md) | 压缩摘要（99 行） | 分析时的实际输入 |

## 2. 为什么选这四个仓库

不是为了「挑四个有名的」，而是刻意覆盖四种极端形态，用来检验读库方法是否真的普适：

| 仓库 | 形态 | 极端在哪 | stars |
|---|---|---|---|
| [`psf/requests`](https://github.com/psf/requests) | 库（library） | 老牌 Python HTTP 库，根目录配置最杂（21 个入口） | 54,715 |
| [`pallets/flask`](https://github.com/pallets/flask) | 框架（framework） | 文档占比极高（docs 87 个文件）、锁文件 279 KB | 75,184 |
| [`sindresorhus/awesome`](https://github.com/sindresorhus/awesome) | 纯内容（content） | **一行代码都没有**，但协作纪律最严 | 538,078 |
| [`octocat/Hello-World`](https://github.com/octocat/Hello-World) | 空壳（shell） | 只有 1 个 13 字节的 README；未关 issue 6167 条、未关 PR 1377 条 | 3,938 |

一句话结论：**同一个「七层读库法」在四种形态下都能给出有效判断，但每一层该看什么，随仓库形态变化**——这是 `仓库分析.md` 的核心论点。

## 3. 怎么复跑

需要 **Python 3.9+** 与网络访问 `api.github.com`（脚本按 `--token-file` 读取 GitHub token；本次运行的 `data/analyze.log` 记录 `token_present=True token_len=40`，抓取结束 `rate_remaining=4964`。不提供 token 时走未认证配额 60 次/小时，4 个仓库约 30 次请求容易触发限流）。

```bash
# 1) 抓取四个仓库的元数据（约 30 秒，受 API 速率影响）
python scripts/analyze_repos.py
# 产物：data/repos.json

# 2) 生成压缩摘要
python scripts/digest.py
# 产物：data/digest.md
```

数据抓取时间：**2026-11-17 04:25:36Z – 04:26:17Z（UTC）**。所有数字（stars、文件数、提交采样、PR 数）都来自这一次抓取，**没有做任何人工估算或补齐**。因此复跑会得到略有差异的数字（stars 会涨），这是预期的。

## 4. 方法摘要（完整论证见 `仓库分析.md`）

读一个陌生仓库，按这七层走，**从「不需要理解代码」的信号开始，逐步逼近「必须读代码」**：

1. **L1 门面层** — stars / forks / license / 最后推送时间 / open issues。判断「还活着吗、能商用吗」。
2. **L2 骨架层** — 根目录清单 + `files_per_toplevel`。判断「这是库、应用、还是内容仓库」。
3. **L3 配置层** — `pyproject.toml` / `.pre-commit-config.yaml` / `Makefile` / tox。判断「作者的工程水准」。
4. **L4 自动化层** — `.github/workflows/` 文件数。**这是最被低估的一层**：workflows 多且分工明确（lint / typecheck / test / publish 分离），说明维护者有真实的 CI 纪律；workflows 为 0，说明所有验证靠人。
5. **L5 历史层** — 采样 30 条提交的平均信息长度、作者数、PR 合并比。**提交信息长度是协作成熟度的强信号**：`psf/requests` 平均 716 字符 vs `pallets/flask` 平均 26 字符，前者是 PR 描述被合并进提交正文，后者是单行提交——两种都不是错，但意味着**追溯决策动机的成本完全不同**。
6. **L6 代码层** — `src/` 与 `tests/` 的比例。只有到了这一层才需要真读代码。
7. **L7 维护层** — open/closed issue 与 PR 的比值。`octocat/Hello-World` 的未关 issue 6167 条 / 已关 2592 条，说明**弃养仓库的 issue 只会堆积**。

## 5. 真实性与边界（必读）

这份交付物刻意保留了两类「不好看」的事实：

- **Git 排错实验未全部完成。** 本机 `git.exe` 存在间歇性 `0xC0000005` 崩溃（退出码 `3221225477`，即 `0xC0000005`），11 组实验中 **5 组真实走通并产出可复核结论**（实验 0–4）、**6 组未完成**（E1 / E2 / E3 / E4 部分 / E6 / E7，均为崩溃或依赖前序步骤而中断）、另 **4 条属知识说明、本次未验证**。`排错实验/Git排错实验记录.md` 里逐条写明哪些是真实输出、哪些是「属知识说明、本次未验证」，**不把未跑通的说成跑通了**。故障原因与不再重试的判断也在文末列出。
- **API 抓取是采样，不是全量。** `commits_sampled=30`、`branches_sampled` 与 `tags_sampled` 均为采样值，`仓库分析.md` 中所有基于采样的推论都标注了采样规模，未外推为全仓库结论。

## 6. 环境

- OS：Windows 10/11
- Git：`git version 2.55.0.windows.3`
- Python：3.12
- 平台：EduSeed 挑战 `C5A GitHub 入门与仓库理解`（学号 2023108610260）
