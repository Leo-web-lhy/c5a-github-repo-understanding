# Git 排错实验记录（真实执行，含未完成项）

> 原始日志：`experiments.log`（逐条记录 `$ 命令` → 真实 stdout/stderr → 真实 exit code，无人工改写）
> 环境：Windows / `git version 2.55.0.windows.3` / 沙箱目录为本仓库内临时目录
> **重要声明**：本机 `git.exe` 存在间歇性 `0xC0000005` 访问冲突崩溃（exit code `3221225477`）。因此下面明确分成三段：**已验证**、**未完成（环境故障）**、**属知识说明（非实验输出）**。未完成项不冒充结论。

## 一、已验证（命令真实退出，输出可复核）

### 实验 0：环境自检

```
$ git --version
git version 2.55.0.windows.3
[exit=0]
```

结论：Git 本身可用，后续崩溃不是「没装好」。

### 实验 1：最小仓库能否走通「暂存 → 提交」

```
$ git init -q -b main          [exit=0]
$ git add a.txt                [exit=0]
$ git commit -q -m "add a.txt" [exit=0]
```

结论：`init / add / commit` 三步在干净空目录里可稳定完成。这同时证明：后面出现的崩溃**不是命令语法错误**（同一条 `git init -q -b main` 在别的目录里 exit=0，在另一个目录里 exit=3221225477）。

### 实验 2：commit 到底指向什么

```
$ git log --pretty=format:"%H TREE=%T SUBJ=%s"
35b2f0107227adeae012fbcda3b55d7863d436cd \
TREE=65829399355e5929e44741d637d52c614ac21bc3 SUBJ=add a.txt   [exit=0]
```

结论：一个 commit 只有 40 位哈希 + 一个 tree 哈希 + 元信息，**它不含文件内容**。文件内容在 blob 里，tree 记录「名字 → 哈希」的映射。所以「改一个字节导致整条链哈希全变」是这个模型的必然结果，不是 Git 的设计缺陷。

### 实验 3：revert 是「追加抵消」而不是「抹掉」

```
$ git revert --no-edit 0860e999
[commit 622d....]  Revert "add config (with secret)"
    This reverts commit 0860e999ba6cca16271860983c4d9427ac17798d.

diff --git a/conf.py b/conf.py
deleted file mode 100644
index fd6510e..0000000
--- a/conf.py
+++ /dev/null
@@ -1,2 +0,0 @@
-user='app'
-password='s3cr3t'
[exit=0]
```

结论：revert 生成的是**一条新提交**，历史里 `0860e99` 依然完整存在，密钥也依然在历史里可被 `git show 0860e99` 取出。**误提交密钥后只做 revert 是无效处置**，必须吊销凭据 + 改写历史（`git filter-repo` / BFG）。这是本次实验里最有实用价值的一条。

### 实验 4：`.gitignore` 对「已跟踪文件」无效

```
$ git check-ignore -v .env
.gitignore:1:.env	.env          [exit=0]

$ git status -sb --ignored
## main
?? app.py
!! .env                            [exit=0]

$ git ls-files .env
（无输出）                          [exit=0]

$ git rm --cached .env
fatal: pathspec '.env' did not match any files   [exit=128]
```

结论：`check-ignore` 命中规则 $\neq$ 文件被忽略。这里 `git ls-files` 无输出，说明 `.env` **从未进入索引**（前一步 `git add .` 崩溃了，没执行成功），所以 `git rm --cached` 报 pathspec 不匹配是**正确行为**，不是 bug。**这次实验反而给出了一个真实的排查范式：先问「它在索引里吗」，再谈 ignore。** 同时也暴露了我脚本的一个缺陷：实验步骤之间存在依赖，某一步崩溃后，后续命令的退出码虽然真实，但其语义已经变了。

## 二、未完成（环境故障，如实记录）

以下命令真实执行了，但退出码是崩溃码，**没有产出可用结论**：

| 实验 | 目的 | 结果 |
|---|---|---|
| E1 对象模型 | `git init` / `git add` / `git cat-file -t` | `[exit=3221225477]` 崩溃于 init 与 add |
| E2 分支合并 | 冲突场景构造 | 未执行（E1 已中断） |
| E3 rebase | 线性历史重写 | 未执行 |
| E4 reset 三档 | `--soft/--mixed/--hard` 差异 | 部分执行，关键步骤崩溃 |
| E6 补充 | `git add .` / `git status -sb --ignored` | `[exit=3221225477]` |
| E7 CRLF/LF 假象 | `core.autocrlf=false` 对比 | 中断于第 2 条命令 |

**为什么不再重试**：崩溃后残留 16 个无法结束的 `git.exe` 进程（`Stop-Process -Force` 与 `taskkill /F /T` 均返回 Access denied），可用物理内存降至约 2.2 GB。继续加压只会让命令行工具本身也进入不稳定状态，风险大于收益。**记录故障比伪造成功更有价值**——这也是把这一段保留下来的原因。

## 三、属知识说明（不是本次实验的输出）

以下结论来自 Git 文档与通用实践，**本次未能在本机验证**，标注以免与上文混淆：

- `reset --soft` 只移动 HEAD、保留索引与工作区；`--mixed` 移动 HEAD 并重置索引；`--hard` 三者全重置。**区分点是「索引是否被重置」。**
- `rebase` 重写提交哈希，因此**已推送的公共分支不要 rebase**；`merge` 保留分叉，历史真实但更杂。
- 换行符问题的根因是 `core.autocrlf` 与 `.gitattributes` 的优先级：**`.gitattributes` 里的 `text=auto` / `eol=lf` 优先于配置项**，团队项目应把规则写进文件而不是依赖每个人的本地配置。
- `git status` 显示 M 但 `git diff` 为空，通常是「仅行尾或仅文件模式变化」，用 `git diff --stat` 与 `git diff --ignore-all-space` 可区分；`git add --renormalize .` 可一次性把索引刷新到当前换行策略。

## 四、由这次故障得到的排错方法论

1. **先分离变量，先怀疑环境。** 同一条命令在 A 目录 exit=0、在 B 目录 exit=3221225477，说明问题不在命令而在执行上下文（进程、句柄、内存、杀毒软件）。
2. **看退出码而不是看输出。** 崩溃时 stdout 往往是空的，只有 `1777`（即 `3221225477`）才暴露真相；只看「有没有报错」会误判为成功。
3. **实验步骤要能独立重跑。** E6 的教训：前一步崩溃后，后续命令的真实退出码会把你带向错误结论（`git rm --cached` 报错其实是因为文件压根没被 add）。
4. **故障要留痕。** 保留原始日志 + 写明哪几条没跑通，比删掉重写一份「全部通过」的日志更可信。
