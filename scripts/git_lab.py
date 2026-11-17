# -*- coding: utf-8 -*-
"""Run real Git experiments locally and record every command + its real output.

Everything is written to a UTF-8 log; the console only prints ASCII status lines.
Each experiment gets a fresh sandbox repo under 排错实验/_lab_work/<name>.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 沙箱放在短 ASCII 临时目录：中文长路径下新建目录后立刻起子进程，
# 会命中 Windows 的瞬时占用（PermissionError 13 / 0xC0000005）。
LAB = os.path.join(tempfile.gettempdir(), "c5a_lab")
LOGP = os.path.join(ROOT, "\u6392\u9519\u5b9e\u9a8c", "experiments.log")

GIT = "git"
ENV = dict(os.environ)
ENV.update({
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "C5A Lab",
    "GIT_AUTHOR_EMAIL": "lab@example.com",
    "GIT_COMMITTER_NAME": "C5A Lab",
    "GIT_COMMITTER_EMAIL": "lab@example.com",
    "LC_ALL": "C",
})
logf = None


def log(text):
    logf.write(text + "\n")
    logf.flush()


def _exec(cmd, cwd):
    """执行 git；stdin 置空避免子进程等待输入导致挂死，瞬时占用则退避重试。"""
    last = None
    for attempt in range(5):
        try:
            return subprocess.run([GIT] + cmd, cwd=cwd, env=ENV, capture_output=True,
                                  stdin=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=60)
        except subprocess.TimeoutExpired:
            raise
        except (PermissionError, OSError) as exc:
            last = exc
            time.sleep(0.4 * (attempt + 1))
    raise last


def run(cwd, args, note=""):
    """Run a git (or shell-ish) command and record the real result."""
    cmd = args if isinstance(args, list) else [args]
    log("$ git " + " ".join(cmd))
    try:
        proc = _exec(cmd, cwd)
    except subprocess.TimeoutExpired:
        log("[TIMEOUT] 命令 60s 未返回，已终止（如实记录）")
        log("")
        return -9, "", "timeout"
    out = (proc.stdout or "").rstrip()
    err = (proc.stderr or "").rstrip()
    if out:
        log(out)
    if err:
        log("[stderr] " + err)
    log("[exit=%d]" % proc.returncode)
    if note:
        log(">> " + note)
    log("")
    return proc.returncode, out, err


def _clear_readonly(path):
    """Windows: .git 下的对象/包文件是只读的，rmtree 会 PermissionError。"""
    for dirpath, dirnames, filenames in os.walk(path):
        for nm in filenames + dirnames:
            p = os.path.join(dirpath, nm)
            try:
                os.chmod(p, 0o777)
            except OSError:
                pass
    try:
        os.chmod(path, 0o777)
    except OSError:
        pass


def force_rmtree(path):
    """删除目录树，先清只读位；失败则重试，仍失败则改名隔离并如实报告。"""
    if not os.path.exists(path):
        return True
    for attempt in range(3):
        _clear_readonly(path)
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return True
        time.sleep(0.2)
    _clear_readonly(path)
    try:
        shutil.rmtree(path, onerror=lambda f, p, e: (os.chmod(p, 0o777), f(p)))
    except OSError:
        pass
    if not os.path.exists(path):
        return True
    try:
        os.rename(path, path + "_stale_" + time.strftime("%H%M%S"))
        return True
    except OSError:
        return False


def fresh(name):
    d = os.path.join(LAB, name)
    if os.path.isdir(d):
        ok = force_rmtree(d)
        if not ok:
            raise RuntimeError("cannot clean sandbox: " + name)
    os.makedirs(d, exist_ok=True)
    return d


def write(d, rel, text):
    p = os.path.join(d, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def section(title, why):
    log("")
    log("=" * 72)
    log("## " + title)
    log("疑问: " + why)
    log("=" * 72)
    log("")


def exp_objects():
    section("E1 Git 对象模型：commit / tree / blob 到底是什么",
            "commit 里存的不是一个目录快照，而是一串哈希引用；改一个字节会怎样？")
    d = fresh("e1_objects")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "a.txt", "hello\n")
    run(d, ["add", "a.txt"])
    run(d, ["commit", "-q", "-m", "add a.txt"])
    _, sha, _ = run(d, ["rev-parse", "HEAD"], "HEAD 指向 commit 对象")
    sha = sha.strip()
    run(d, ["cat-file", "-t", sha])
    run(d, ["cat-file", "-p", sha], "commit 对象只含 tree/parent/author/message")
    _, tree, _ = run(d, ["rev-parse", "HEAD^{tree}"])
    tree = tree.strip()
    run(d, ["cat-file", "-p", tree], "tree 对象是 模式+类型+哈希+文件名 的列表")
    _, blob, _ = run(d, ["rev-parse", "HEAD:a.txt"])
    blob = blob.strip()
    run(d, ["cat-file", "-p", blob], "blob 对象只存文件内容，不含文件名")
    write(d, "a.txt", "hello\n")
    run(d, ["hash-object", "a.txt"], "内容不变 -> 哈希不变（内容寻址）")
    write(d, "a.txt", "hello!\n")
    run(d, ["hash-object", "a.txt"], "改一个字符 -> blob 哈希彻底不同")
    run(d, ["count-objects", "-v"], "Git 靠这套对象+引用成立，而不是靠'文件夹'")
    return d


def exp_detached():
    section("E2 detached HEAD：为什么提交会'丢'",
            "checkout 到某个 commit 后做的提交，为什么第二天不见了？")
    d = fresh("e2_detached")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "f.txt", "v1\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "c1"])
    write(d, "f.txt", "v2\n")
    run(d, ["commit", "-qam", "c2"])
    _, c1, _ = run(d, ["rev-parse", "HEAD~1"])
    run(d, ["switch", "--detach", c1.strip()], "进入 detached HEAD")
    run(d, ["status", "-sb"], "注意 HEAD detached 提示")
    write(d, "g.txt", "work on detached\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "detached-work"], "这个 commit 只被 HEAD 直接引用")
    _, lost, _ = run(d, ["rev-parse", "HEAD"])
    lost = lost.strip()
    run(d, ["switch", "main"], "切回 main：没有分支引用那个提交")
    run(d, ["log", "--oneline", "--all"], "分支上看不到 detached-work")
    run(d, ["cat-file", "-t", lost], "对象仍在（还没被 gc），但已无可达引用")
    run(d, ["branch", "rescue", lost], "救援：给它一个分支或标签引用")
    run(d, ["log", "--oneline", "rescue"], "现在它可达了")
    run(d, ["reflog", "-n", "5"], "reflog 是本地'后悔药'（默认 90 天）")
    return d


def exp_conflict():
    section("E3 分支 + 合并冲突：冲突标记长什么样、怎么收尾",
            "两个人改同一行必然冲突，冲突文件到底该怎么读？")
    d = fresh("e3_conflict")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "config.ini", "timeout=30\nretry=3\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "base config"])
    run(d, ["switch", "-c", "feature-a"])
    write(d, "config.ini", "timeout=60\nretry=3\n")
    run(d, ["commit", "-qam", "feature-a: timeout 60"])
    run(d, ["switch", "main"])
    write(d, "config.ini", "timeout=30\nretry=5\n")
    run(d, ["commit", "-qam", "main: retry 5"])
    run(d, ["merge", "feature-a", "--no-edit"], "冲突返回非 0，这不是 bug")
    run(d, ["status", "-sb"])
    with io.open(os.path.join(d, "config.ini"), "r", encoding="utf-8") as f:
        conflicted = f.read()
    log("--- 冲突后的 config.ini 真实内容 ---")
    log(conflicted)
    log("--- end ---")
    log("")
    write(d, "config.ini", "timeout=60\nretry=5\n")
    run(d, ["add", "config.ini"], "手工合并两边的意图后再 add")
    run(d, ["commit", "-q", "--no-edit", "-m", "merge feature-a"])
    run(d, ["log", "--graph", "--oneline", "--decorate"], "三方合并产生两个 parent")
    return d


def exp_rebase():
    section("E4 merge 与 rebase 的区别（同一组提交的两种历史）",
            "同样的改动，为什么一条历史是分叉的、一条是直线的？")
    d = fresh("e4_rebase")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "a.txt", "1\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "c1"])
    run(d, ["switch", "-c", "feat"])
    write(d, "b.txt", "feat\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "feat work"])
    run(d, ["switch", "main"])
    write(d, "c.txt", "main\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "main work"])
    _, before_feat_sha, _ = run(d, ["rev-parse", "feat"])
    run(d, ["merge", "feat", "--no-ff", "--no-edit"], "方式一: merge 保留分叉")
    run(d, ["log", "--graph", "--oneline", "--decorate", "-5"])
    run(d, ["reset", "--hard", "HEAD~1"])
    _, rebased, _ = run(d, ["rebase", "feat"], "方式二: rebase 把 main 的提交搬到 feat 之上")
    run(d, ["log", "--graph", "--oneline", "--decorate", "-5"], "历史被改写成直线")
    run(d, ["rev-parse", "feat"], "注意：feat 指向的原始 commit sha 是 %s" % before_feat_sha.strip()[:10])
    run(d, ["status", "-sb"], "rebase 改写 sha => 已推送的分支上 rebase 会引发强推")
    return d


def exp_reset_revert():
    section("E5 reset 与 revert：为什么共享分支只能用 revert",
            "误提交一行密码到 main，删掉那行有几种做法，哪种不会伤到别人？")
    d = fresh("e5_reset_revert")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "conf.py", "user='app'\npassword='s3cr3t'\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "add config (with secret)"])
    write(d, "conf.py", "user='app'\n")
    run(d, ["commit", "-qam", "remove secret"])
    _, bad, _ = run(d, ["rev-parse", "HEAD~1"])
    bad = bad.strip()
    run(d, ["reset", "--soft", "HEAD~1"], "soft: 只动 HEAD，改动留在暂存区")
    run(d, ["status", "-sb"])
    run(d, ["reset", "--hard", bad], "回到含密码的那个提交（模拟历史里已经有它）")
    run(d, ["reset", "--mixed", "HEAD"], "mixed: 动 HEAD+暂存区，工作区不变")
    run(d, ["status", "-sb"])
    run(d, ["reset", "--hard", bad])
    run(d, ["revert", "--no-edit", "HEAD"], "共享分支正确做法：revert 生成反向提交")
    run(d, ["log", "--oneline", "-3"], "历史保留，两条记录都在（明文仍在历史里！）")
    run(d, ["log", "-p", "-1"], "revert 只是抵消，不是抹除")
    log(">> 关键结论: reset 改写历史（只能用于未共享的本地分支）；")
    log(">> revert 追加历史（可用于已推送/被他人拉取的分支）。")
    log(">> 真正的密钥泄露要靠吊销凭据 + 历史重写（filter-repo/BFG），revert 不够。")
    log("")
    return d


def exp_ignore():
    section("E6 .gitignore 为什么不生效",
            "明明写进 .gitignore 了，git status 还显示 .env，为什么？")
    d = fresh("e6_ignore")
    run(d, ["init", "-q", "-b", "main"])
    write(d, ".env", "TOKEN=abc\n")
    write(d, "app.py", "print(1)\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "oops: committed .env"])
    write(d, ".gitignore", ".env\n")
    run(d, ["add", ".gitignore"])
    run(d, ["commit", "-q", "-m", "add gitignore"])
    run(d, ["status", "-sb", "--ignored"], "已跟踪的文件不受 .gitignore 影响")
    run(d, ["check-ignore", "-v", ".env"], "check-ignore 说它被规则命中")
    run(d, ["ls-files", ".env"], "但它依然在索引里 -> 这就是原因")
    run(d, ["rm", "--cached", ".env"], "从索引移除，保留本地文件")
    run(d, ["commit", "-q", "-m", "untrack .env"])
    run(d, ["status", "-sb", "--ignored"], "现在才真的被忽略")
    return d


def exp_crlf():
    section("E7 Windows 上'改了 5 个文件其实没改'（CRLF/LF 假象）",
            "git status 说 5 个文件 M，git diff 却看不到差异，是怎么回事？")
    d = fresh("e7_crlf")
    run(d, ["init", "-q", "-b", "main"])
    with io.open(os.path.join(d, "x.txt"), "wb") as f:
        f.write(b"line1\nline2\n")
    run(d, ["-c", "core.autocrlf=false", "add", "x.txt"])
    run(d, ["-c", "core.autocrlf=false", "commit", "-q", "-m", "lf version"])
    run(d, ["config", "core.autocrlf", "true"], "开启 Windows 常见的 autocrlf=true")
    os.remove(os.path.join(d, "x.txt"))
    run(d, ["checkout", "--", "x.txt"], "重新签出 -> 工作区变成 CRLF")
    run(d, ["status", "-sb"], "看起来'被修改'了")
    run(d, ["diff", "--stat"], "但统计里没有真实内容差异")
    run(d, ["diff", "-w", "--ignore-cr-at-eol"], "忽略行尾差异后为空")
    run(d, ["config", "core.autocrlf", "false"], "统一策略：仓库内一律 LF")
    run(d, ["add", "--renormalize", "."], "把索引里的行尾归一化")
    run(d, ["status", "-sb"], "状态恢复干净")
    return d


def exp_stash():
    section("E8 stash 的坑：未跟踪文件不会进 stash",
            "stash 完切分支再回来，为什么新写的文件没了？")
    d = fresh("e8_stash")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "tracked.txt", "v1\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "base"])
    write(d, "tracked.txt", "v1-modified\n")
    write(d, "new_file.py", "print('new')\n")
    run(d, ["stash", "push", "-m", "wip"], "默认不含未跟踪文件")
    run(d, ["status", "-sb"], "new_file.py 还在工作区（没被收走）")
    run(d, ["stash", "push", "-u", "-m", "wip2"], "-u 才包含未跟踪文件")
    run(d, ["status", "-sb"], "现在工作区干净")
    run(d, ["stash", "list"], "两条 stash 记录")
    run(d, ["stash", "pop"], "pop 最近一条（含未跟踪文件）")
    run(d, ["status", "-sb"])
    return d


def exp_push_reject():
    section("E9 push 被拒：non-fast-forward 的真实处理",
            "两个人改同一个分支，后推的人被拒，该 merge 还是 rebase？")
    d = fresh("e9_push")
    origin = os.path.join(d, "origin.git")
    run(d, ["init", "-q", "--bare", origin], "本地裸仓库模拟远端")
    run(d, ["clone", "-q", origin, "alice"])
    alice = os.path.join(d, "alice")
    run(alice, ["init", "-q", "-b", "main"]) if False else None
    run(alice, ["checkout", "-q", "-b", "main"])
    write(alice, "readme.md", "v1\n")
    run(alice, ["add", "."])
    run(alice, ["commit", "-q", "-m", "alice: base"])
    run(alice, ["push", "-q", "-u", "origin", "main"], "alice 先推成功")
    run(d, ["clone", "-q", origin, "bob"])
    bob = os.path.join(d, "bob")
    write(alice, "readme.md", "v1\nalice line\n")
    run(alice, ["commit", "-qam", "alice: change"])
    write(bob, "readme.md", "v1\nbob line\n")
    run(bob, ["commit", "-qam", "bob: change"])
    run(alice, ["push", "-q", "origin", "main"], "alice 再推成功")
    rc, _, err = run(bob, ["push", "origin", "main"], "bob 的推送被拒")
    log(">> 被拒原因（真实 stderr）已在上方；rejected 即 non-fast-forward。")
    log(">> 处置 A：git pull --rebase（把 bob 的提交搬到 alice 之上）")
    log("")
    run(bob, ["pull", "--rebase", "origin", "main"])
    run(bob, ["log", "--graph", "--oneline", "--decorate", "-6"])
    run(bob, ["push", "-q", "origin", "main"], "rebase 后推送成功")
    run(bob, ["log", "--oneline", "-3"])
    log(">> 提醒：--force 会覆盖别人提交；共享分支上如需强推只能用 --force-with-lease。")
    log("")
    return d


def exp_pr_flow():
    section("E10 一个最小但完整的 PR 式协作流程",
            "分支 - 提交 - 合并 - 删除分支，一个功能在 Git 层面到底发生了什么？")
    d = fresh("e10_pr_flow")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "main.py", "def add(a, b):\n    return a + b\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "feat: base add()"])
    run(d, ["switch", "-c", "feat/div"])
    write(d, "main.py", "def add(a, b):\n    return a + b\n\ndef div(a, b):\n    return a / b\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "feat(calc): add div()"])
    run(d, ["switch", "main"])
    run(d, ["merge", "--no-ff", "-m", "Merge branch 'feat/div'", "feat/div"], "PR 合并默认等价于 --no-ff")
    run(d, ["log", "--graph", "--oneline", "--decorate", "-4"], "能看出这是一个独立功能分支")
    run(d, ["branch", "-d", "feat/div"], "合并后删本地分支不影响历史")
    run(d, ["branch", "-a"])
    run(d, ["show", "--stat", "HEAD"], "合并提交本身不改代码，只记录拓扑")
    return d


def exp_amend():
    section("E11 改 commit message / 补文件：amend 与 force-with-lease",
            "刚推上去的提交 message 写错了，怎么改而不搞坏别人的分支？")
    d = fresh("e11_amend")
    run(d, ["init", "-q", "-b", "main"])
    write(d, "a.txt", "1\n")
    run(d, ["add", "."])
    run(d, ["commit", "-q", "-m", "tpyo message"])
    run(d, ["commit", "-q", "--amend", "-m", "fix: correct message"], "amend 改写了 sha")
    run(d, ["log", "--oneline", "-2"])
    write(d, "b.txt", "2\n")
    run(d, ["add", "b.txt"], "忘了带文件")
    run(d, ["commit", "-q", "--amend", "--no-edit"], "amend 把新文件并进上一个提交")
    run(d, ["show", "--stat", "HEAD"])
    log(">> 已推送后再 amend 必须强推；安全形式是 --force-with-lease（远端没变才允许覆盖）。")
    log("")
    return d


def main():
    global logf
    if os.path.isdir(LAB):
        force_rmtree(LAB)
    os.makedirs(LAB, exist_ok=True)
    logf = io.open(LOGP, "w", encoding="utf-8")
    log("# C5A Git 排错实验原始日志")
    log("# 生成时间: " + __import__("time").strftime("%Y-%m-%d %H:%M:%S"))
    log("# 说明: 每条 $ 开头为真实执行命令，其后为真实 stdout/stderr 与 exit code。")
    log("")
    _, ver, _ = run(LAB, ["--version"])
    log("git_version=" + ver.strip())
    log("")

    exps = [
        ("E1", exp_objects), ("E2", exp_detached), ("E3", exp_conflict),
        ("E4", exp_rebase), ("E5", exp_reset_revert), ("E6", exp_ignore),
        ("E7", exp_crlf), ("E8", exp_stash), ("E9", exp_push_reject),
        ("E10", exp_pr_flow), ("E11", exp_amend),
    ]
    done = []
    for tag, fn in exps:
        try:
            fn()
            done.append(tag)
            sys.stdout.write("%s OK\n" % tag)
        except Exception as exc:
            log("EXCEPTION in %s: %r" % (tag, exc))
            sys.stdout.write("%s FAIL %s\n" % (tag, type(exc).__name__))
    logf.write("\nDONE %d/%d: %s\n" % (len(done), len(exps), ",".join(done)))
    logf.close()
    sys.stdout.write("LAB_DONE %d/%d log=%s\n" % (len(done), len(exps), LOGP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
