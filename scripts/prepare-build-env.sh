#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 在目标平台 arm64 容器内准备 MySQL 的 RPM 构建环境
#
# 默认镜像：hxsoong/kylin:v10-sp3（glibc 2.28 / gcc 7.3 / rpm 4.15，与目标机同源）。
# 与早期 rockylinux:8 代跑方案的差异（PG 侧踩过的坑，这里预先规避）：
#   1. 麒麟没有 redhat-rpm-config，宏包叫 kylin-rpm-config —— 逐个尝试、缺了不致命；
#   2. 麒麟没有 powertools/crb 仓库，别把它当成前提（仅非麒麟平台尝试启用）；
#   3. rpcgen / numactl-devel / perl-* 等包在不同发行版命名不一致，
#      放进“可选”清单单独安装，避免一个包不存在导致整条 dnf 事务失败；
#   4. systemd 宏来自 systemd-rpm-macros，显式安装，不依赖 rpm-config 间接带入。
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi  # GitHub 步骤会带 -o pipefail 并被继承

BOOST_VER="${BOOST_VER:-boost_1_59_0}"
BOOST_EXT="${BOOST_EXT:-tar.gz}"
BOOST_REL="${BOOST_REL:-1.59.0}"
BOOST_TARBALL="${BOOST_CACHE_DIR:-/var/cache/mysql-build}/${BOOST_VER}.${BOOST_EXT}"

IS_KYLIN=0
if grep -qi kylin /etc/os-release 2>/dev/null || ls /etc/kylin-release >/dev/null 2>&1; then
    IS_KYLIN=1
fi
echo "==> 发行版：$(cat /etc/kylin-release 2>/dev/null || cat /etc/os-release | sed -n '1,2p' | tr '\n' ' ')"

dnf -y makecache >/dev/null 2>&1 || :

if [ "$IS_KYLIN" = "0" ]; then
    echo "==> 启用 CRB/PowerTools（rpcgen 只在这个仓库里；麒麟无此仓库，跳过）"
    dnf -y install dnf-plugins-core >/dev/null 2>&1 || :
    dnf config-manager --set-enabled powertools >/dev/null 2>&1 \
      || dnf config-manager --set-enabled crb >/dev/null 2>&1 \
      || echo "    (提示：powertools/crb 未启用)"
fi

echo "==> 安装构建依赖（必需）"
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=1 install \
    cmake gcc gcc-c++ make \
    ncurses-devel openssl-devel zlib-devel libaio-devel \
    bison m4 perl \
    systemd-devel \
    rpm-build dnf-plugins-core \
    tar gzip curl which findutils diffutils file cpio procps-ng shadow-utils

# 麒麟 dnf 有个怪癖：请求 foo-devel 时，如果基础包 foo 已安装，dnf 会打印
# "Package foo is already installed" 并以 0 退出，但 -devel 并没有装（实测
# libtirpc-devel 就是如此）。这里逐个复核关键 -devel 包，缺了就用能取到的
# 最高版本 NEVRA 强装，避免 rpmbuild 在 BuildRequires 校验阶段才报错。
ensure_pkg() {
    pkg="$1"
    rpm -q "$pkg" >/dev/null 2>&1 && return 0
    dnf -y --setopt=install_weak_deps=False install "$pkg" >/dev/null 2>&1 || :
    rpm -q "$pkg" >/dev/null 2>&1 && return 0
    nevra="$(dnf -q repoquery --latest-limit 1 \
        --qf '%{name}-%{version}-%{release}.%{arch}' "$pkg" 2>/dev/null | tail -1)"
    if [ -n "$nevra" ]; then
        echo "    以 NEVRA 重试: $nevra"
        dnf -y install "$nevra" >/dev/null 2>&1 || :
    fi
    rpm -q "$pkg" >/dev/null 2>&1
}

echo "==> 复核关键 -devel 包（规避上述 dnf 怪癖）"
for p in libtirpc-devel ncurses-devel openssl-devel zlib-devel libaio-devel systemd-devel; do
    if ensure_pkg "$p"; then
        echo "    OK   $p"
    else
        echo "    !! 缺少构建依赖: $p"; exit 1
    fi
done

echo "==> 安装构建依赖（可选，按发行版命名差异逐个尝试）"
for pkg in dnf-plugins-core rpcgen numactl-devel systemd-rpm-macros \
           perl-Getopt-Long perl-Data-Dumper perl-File-Temp; do
    if dnf -y --setopt=install_weak_deps=False install "$pkg" >/dev/null 2>&1; then
        echo "    OK   $pkg"
    else
        echo "    SKIP $pkg（该发行版无此包，构建可继续）"
    fi
done

# rpm 宏包：EL8 是 redhat-rpm-config，麒麟是 kylin-rpm-config，openEuler 是 openEuler-rpm-config
echo "==> rpm 宏包"
RPMCFG=""
for pkg in redhat-rpm-config kylin-rpm-config openEuler-rpm-config; do
    if dnf -y install "$pkg" >/dev/null 2>&1; then
        RPMCFG="$pkg"; break
    fi
done
if [ -n "$RPMCFG" ]; then
    echo "    $RPMCFG"
else
    echo "    !! 未找到 rpm 宏包；systemd-rpm-macros 已单独安装，%systemd_post 仍可用"
fi

dnf clean metadata >/dev/null 2>&1 || :
rm -rf /var/cache/dnf

echo "==> 组件版本"
gcc --version | sed -n '1p'
cmake --version | sed -n '1p'
make --version | sed -n '1p'
ldd --version | sed -n '1p'
rpm --version

echo "==> 准备 Boost ${BOOST_VER}（离线预置，规避 sourceforge 抖动）"
mkdir -p "$(dirname "$BOOST_TARBALL")"

if [ ! -s "$BOOST_TARBALL" ]; then
    for url in \
        "https://archives.boost.io/release/${BOOST_REL}/source/${BOOST_VER}.${BOOST_EXT}" \
        "https://downloads.sourceforge.net/boost/${BOOST_VER}.${BOOST_EXT}" \
        "https://sourceforge.net/projects/boost/files/boost/${BOOST_REL}/${BOOST_VER}.${BOOST_EXT}/download"
    do
        echo "    尝试: $url"
        if curl -fL --retry 3 --retry-delay 5 --connect-timeout 20 \
                -o "${BOOST_TARBALL}.part" "$url"; then
            mv "${BOOST_TARBALL}.part" "$BOOST_TARBALL"
            break
        fi
    done
fi

[ -s "$BOOST_TARBALL" ] || { echo "!! Boost 下载失败"; exit 1; }

# 校验压缩包完整性（截断的包会让 cmake 在半小时后才报错）
tar -tf "$BOOST_TARBALL" >/dev/null
echo "    OK: $(du -h "$BOOST_TARBALL" | cut -f1)  $BOOST_TARBALL"
