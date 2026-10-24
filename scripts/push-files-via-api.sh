#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 在 github.com 网页不可达、但 api.github.com 可用的环境下，
# 用 GitHub Contents API 把打包工程提交到指定分支（等价于 git push）。
#
# 用法：
#   export GH_TOKEN=<有 repo / contents 写权限的 PAT>
#   bash scripts/push-files-via-api.sh
#
# 可选环境变量：
#   REPO=dreamalloc/mysql-server   目标仓库
#   BRANCH=ci/kylin-rpm            目标分支（不存在则从默认分支创建）
#   BASE_BRANCH=trunk              起点分支
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="${REPO:-dreamalloc/mysql-server}"
BRANCH="${BRANCH:-ci/kylin-rpm}"
BASE_BRANCH="${BASE_BRANCH:-trunk}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${GH_TOKEN:?请先 export GH_TOKEN=<PAT>}"
export GH_TOKEN

FILES=(
  ".github/workflows/build-mysql57-kylin-arm64.yml"
  "packaging/kylin/mysql-community.spec"
  "scripts/prepare-build-env.sh"
  "scripts/build-rpm.sh"
  "scripts/verify-rpm.sh"
  "scripts/push-files-via-api.sh"
)

api() { gh api "$@"; }
b64() { base64 < "$1" | tr -d '\n'; }

echo "==> 校验认证与仓库权限"
gh api "repos/${REPO}" --jq '.full_name + "  default_branch=" + .default_branch'

echo "==> 取 ${BASE_BRANCH} 最新 commit"
BASE_SHA="$(gh api "repos/${REPO}/git/ref/heads/${BASE_BRANCH}" --jq '.object.sha')"
echo "    ${BASE_SHA}"

echo "==> 确保分支 ${BRANCH} 存在"
if gh api "repos/${REPO}/git/ref/heads/${BRANCH}" >/dev/null 2>&1; then
    echo "    已存在，沿用"
else
    gh api -X POST "repos/${REPO}/git/refs" \
        -f "ref=refs/heads/${BRANCH}" -f "sha=${BASE_SHA}" --jq '.ref'
    echo "    已从 ${BASE_BRANCH} 创建"
fi

echo "==> 逐个提交文件"
for f in "${FILES[@]}"; do
    src="${REPO_ROOT}/${f}"
    [ -f "$src" ] || { echo "    !! 缺少本地文件: ${f}"; exit 1; }

    # 已存在则需带 sha 做更新
    SHA="$(gh api "repos/${REPO}/contents/${f}?ref=${BRANCH}" --jq '.sha' 2>/dev/null || true)"

    args=(-X PUT "repos/${REPO}/contents/${f}"
          -f "message=ci: add ${f##*/} for kylin v10 sp3 aarch64 build"
          -f "branch=${BRANCH}"
          -f "content=$(b64 "$src")")
    [ -n "$SHA" ] && args+=(-f "sha=${SHA}")

    gh api "${args[@]}" --jq '.commit.sha' | sed "s|^|    ${f}  ->  |"
done

echo
echo "==> 完成。分支 ${BRANCH} 已更新，可用以下命令触发："
echo "    gh workflow run \"Build MySQL 5.7.44 RPM (Kylin V10 SP3 / aarch64)\" \\"
echo "      --repo ${REPO} --ref ${BRANCH} \\"
echo "      -f source_ref=mysql-5.7.44 -f dist_tag=.ky10 -f upload_release=false"
