#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 生成源码 tarball 并执行 rpmbuild -ba
#   -ba 同时产出：二进制 RPM、debuginfo RPM、debugsource RPM、SRPM
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi  # GitHub 步骤会带 -o pipefail 并被继承

SRC_DIR="${SRC_DIR:?需要指定 SRC_DIR（MySQL 源码 checkout 路径）}"
SRC_NAME="${SRC_NAME:-mysql-5.7.44}"
DIST_TAG="${DIST_TAG:-.ky10}"
TOP="${RPMBUILD_TOP:-/build/rpmbuild}"
BOOST_VER="${BOOST_VER:-boost_1_59_0}"
BOOST_EXT="${BOOST_EXT:-tar.gz}"
BOOST_TARBALL="${BOOST_CACHE_DIR:-/var/cache/mysql-build}/${BOOST_VER}.${BOOST_EXT}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC_FILE="${SPEC_FILE:-mysql-community.spec}"
SPEC="${REPO_ROOT}/packaging/rpm/${SPEC_FILE}"
SPEC_NAME="$(basename "${SPEC}")"

[ -f "$SPEC" ]              || { echo "!! 找不到 spec: $SPEC"; exit 1; }
[ -d "$SRC_DIR" ]           || { echo "!! 找不到源码目录: $SRC_DIR"; exit 1; }
[ -s "$BOOST_TARBALL" ]     || { echo "!! 找不到 Boost 包: $BOOST_TARBALL"; exit 1; }

mkdir -p "${TOP}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

echo "==> 打包源码（顶层目录 ${SRC_NAME}/）"
if [ ! -s "${TOP}/SOURCES/${SRC_NAME}.tar.gz" ]; then
    tar -C "$SRC_DIR" \
        --exclude=./.git \
        --transform "s,^\./,${SRC_NAME}/," \
        -czf "${TOP}/SOURCES/${SRC_NAME}.tar.gz" .
fi
tar -tzf "${TOP}/SOURCES/${SRC_NAME}.tar.gz" > "${TOP}/tar.list"
sed -n '1,3p' "${TOP}/tar.list" | sed 's/^/    /'
echo "    entries: $(wc -l < "${TOP}/tar.list"), size: $(du -h "${TOP}/SOURCES/${SRC_NAME}.tar.gz" | cut -f1)"

cp -f "$BOOST_TARBALL" "${TOP}/SOURCES/${BOOST_VER}.${BOOST_EXT}"
cp -f "$SPEC"          "${TOP}/SPECS/${SPEC_NAME}"

echo "==> 校验 spec 可解析"
rpmspec -q --qf '    %{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' "${TOP}/SPECS/${SPEC_NAME}"

JOBS="$(nproc)"
echo "==> rpmbuild -ba  (dist=${DIST_TAG}, -j${JOBS})"

# 用 set -- 组装参数，避免引号/空值被词分割搞坏
set -- -ba "${TOP}/SPECS/${SPEC_NAME}" \
    --define "_topdir ${TOP}" \
    --define "dist ${DIST_TAG}" \
    --define "_smp_mflags -j${JOBS}"

# 发行版差异开关（用 if 而不是 &&，避免 set -e 下的返回值歧义）
if [ -n "${WITH_SSL:-}" ]; then
    set -- "$@" --define "with_ssl ${WITH_SSL}"
    echo "    (SSL: ${WITH_SSL})"
fi
if [ -n "${BUILD_FLAVOR:-}" ]; then
    set -- "$@" --define "${BUILD_FLAVOR} 1"
    echo "    (flavor: ${BUILD_FLAVOR})"
fi

if [ "${ALLOW_UNPACKAGED:-0}" = "1" ]; then
    echo "    [调试模式] 容忍未打包文件（产物不完整，禁止发布）"
    set -- "$@" --define "_unpackaged_files_terminate_build 0"
fi

set +e
rpmbuild "$@" > "${TOP}/build.log" 2>&1
RC=$?
set -e
tail -n 30 "${TOP}/build.log"

if [ "$RC" -ne 0 ]; then
    echo
    echo "=========================================================="
    echo " 构建失败。常见原因：%files 与实际安装文件不一致"
    echo "=========================================================="
    # rpmbuild 会把未打包的文件全部列出来，直接抄进 spec 对应子包即可
    sed -n '/Installed (but unpackaged) file(s) found/,/^$/p' "${TOP}/build.log" | sed -n '1,100p'
    echo
    echo "完整 buildroot 清单见: ${TOP}/BUILD/${SRC_NAME}/buildroot-files.txt"
    echo "完整日志: ${TOP}/build.log"
    exit "$RC"
fi

echo
echo "==> 构建成功，产物："
find "${TOP}/RPMS" "${TOP}/SRPMS" -name '*.rpm' | sort | while read -r f; do
    printf '    %-70s %8s\n' "$(basename "$f")" "$(du -h "$f" | cut -f1)"
done
