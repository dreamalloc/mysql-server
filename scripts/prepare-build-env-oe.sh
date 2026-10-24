#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# openEuler 24.03 LTS 构建环境准备（x86_64）
# 与 EL8 的差异：
#   - OpenSSL 3.0，MySQL 5.7 的 WITH_SSL=system 不兼容 → 用自带 yaSSL
#   - gcc 12 默认 -fno-common → spec 里已加 -fcommon
#   - openEuler 仓库结构与 EL8 不同，rpcgen 需单独确认
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi  # GitHub 步骤会带 -o pipefail 并被继承

BOOST_VER="boost_1_59_0"
BOOST_TARBALL="${BOOST_CACHE_DIR:-/var/cache/mysql-build}/${BOOST_VER}.tar.gz"

echo "==> 系统信息"
cat /etc/openEuler-release 2>/dev/null || cat /etc/os-release | sed -n '1,3p'
gcc --version | sed -n '1p'
ldd --version | sed -n '1p'

echo "==> 安装构建依赖"
dnf -y makecache >/dev/null 2>&1 || :

# 核心依赖：缺任何一个都直接失败
dnf -y install \
    cmake gcc gcc-c++ make \
    ncurses-devel openssl-devel zlib-devel libaio-devel libtirpc-devel numactl-devel \
    bison \
    perl perl-Getopt-Long perl-Data-Dumper \
    systemd-devel \
    rpm-build redhat-rpm-config \
    tar gzip curl which findutils diffutils file cpio procps-ng shadow-utils

# 可选依赖：缺了会导致 group_replication 配置阶段报 "Could not find rpcgen"
if dnf -y install rpcgen >/dev/null 2>&1; then
    echo "    rpcgen: $(command -v rpcgen)"
else
    echo "    !! rpcgen 安装失败，MySQL 5.7 的 group_replication 插件将无法构建"
    echo "       可尝试: dnf --enablerepo=everything install -y rpcgen"
fi

dnf clean all >/dev/null 2>&1 || :
rm -rf /var/cache/dnf

echo "==> 准备 Boost ${BOOST_VER}"
mkdir -p "$(dirname "$BOOST_TARBALL")"
if [ ! -s "$BOOST_TARBALL" ]; then
    for url in \
        "https://archives.boost.io/release/1.59.0/source/${BOOST_VER}.tar.gz" \
        "https://downloads.sourceforge.net/boost/${BOOST_VER}.tar.gz" \
        "https://sourceforge.net/projects/boost/files/boost/1.59.0/${BOOST_VER}.tar.gz/download"
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
tar -tzf "$BOOST_TARBALL" >/dev/null
echo "    OK: $(du -h "$BOOST_TARBALL" | cut -f1)  $BOOST_TARBALL"
