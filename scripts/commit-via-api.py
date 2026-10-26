#!/usr/bin/env python3
"""
用 GitHub Git Data API 把打包工程作为「单个提交」写到目标分支。
适用于 github.com 网页不可达、只有 api.github.com 可用的环境。

用法：
    set GH_TOKEN=ghp_xxx
    python scripts/commit-via-api.py --repo dreamalloc/mysql-server --branch trunk
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

API = "https://api.github.com"
FILES = [
    ".github/workflows/build-mysql57-kylin-arm64.yml",
    ".github/workflows/build-mysql57-openeuler2403-x86_64.yml",
    ".github/workflows/build-mysql80-kylin-arm64.yml",
    ".github/workflows/build-mysql80-openeuler2403-x86_64.yml",
    "packaging/rpm/mysql-community.spec",
    "packaging/rpm/mysql80-community.spec",
    "scripts/prepare-build-env.sh",
    "scripts/prepare-build-env-oe.sh",
    "scripts/build-rpm.sh",
    "scripts/verify-rpm.sh",
    "scripts/push-files-via-api.sh",
    "scripts/commit-via-api.py",
]
MESSAGE = "ci: build mysql 5.7.44 rpm for kylin v10 sp3 aarch64"


def call(method, path, payload=None, token=None):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  !! {method} {path} -> {e.code}: {body[:300]}", file=sys.stderr)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="dreamalloc/mysql-server")
    ap.add_argument("--branch", default="trunk")
    ap.add_argument("--message", default=MESSAGE)
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("请先设置 GH_TOKEN")

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    print(f"==> 读取 {args.branch} 当前提交")
    ref = call("GET", f"/repos/{args.repo}/git/ref/heads/{args.branch}", token=token)
    parent = ref["object"]["sha"]
    base_tree = call("GET", f"/repos/{args.repo}/git/commits/{parent}", token=token)["tree"]["sha"]
    print(f"    {parent}")

    print("==> 上传 blob")
    tree = []
    for rel in FILES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            print(f"    (跳过，本地不存在: {rel})")
            continue
        raw = open(path, "rb").read()
        # Windows 上编辑过的文件可能是 CRLF，推到 Linux runner 会导致
        # "bad interpreter" / "$'\r': command not found"，这里统一成 LF
        if rel.endswith((".sh", ".py", ".yml", ".yaml", ".spec", ".md", ".cnf")):
            raw = raw.replace(b"\r\n", b"\n")
        content = base64.b64encode(raw).decode()
        blob = call("POST", f"/repos/{args.repo}/git/blobs",
                    {"content": content, "encoding": "base64"}, token=token)
        tree.append({"path": rel, "mode": "100755" if rel.endswith((".sh", ".py")) else "100644",
                     "type": "blob", "sha": blob["sha"]})
        print(f"    {rel}  {blob['sha'][:10]}")

    print("==> 创建 tree / commit")
    new_tree = call("POST", f"/repos/{args.repo}/git/trees",
                    {"base_tree": base_tree, "tree": tree}, token=token)
    commit = call("POST", f"/repos/{args.repo}/git/commits",
                  {"message": args.message, "tree": new_tree["sha"], "parents": [parent]}, token=token)
    print(f"    commit {commit['sha']}")

    print(f"==> 更新 refs/heads/{args.branch}")
    call("PATCH", f"/repos/{args.repo}/git/refs/heads/{args.branch}",
         {"sha": commit["sha"], "force": False}, token=token)

    print(f"\n完成：https://github.com/{args.repo}/commit/{commit['sha']}")


if __name__ == "__main__":
    main()
