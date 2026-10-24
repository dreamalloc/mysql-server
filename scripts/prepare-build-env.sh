#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 在 rockylinux:8 (aarch64) 容器内准备 MySQL 5.7.44 的 RPM 构建环境
# 说明：rockylinux:8 的 glibc 2.28 / rpm 4.14 与麒麟 V10 SP3 同代，
#       产出的二进制依赖不会带 GLIBC_2.29+ 符号。
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi  # GitHub 步骤会带 -o pipefail 并被继承

BOOST_VER="${BOOST_VER:-boost_1_59_0}"
BOOST_EXT="${BOOST_EXT:-tar.gz}"
BOOST_REL="${BOOST_REL:-1.59.0}"
BOOST_TARBALL="${BOOST_CACHE_DIR:-/var/cache/mysql-build}/${BOOST_VER}.${BOOST_EXT}"

echo "==> 启用 CRB/PowerTools（rpcgen 只在这个仓库里）"
dnf -y install dnf-plugins-core >/dev/null 2>&1 || :
dnf config-manager --set-enabled powertools >/dev/null 2>&1 \
  || dnf config-manager --set-enabled crb >/dev/null 2>&1 \
  || echo "    (警告：powertools/crb 未启用，若 rpcgen 缺失会导致构建失败)"

echo "==> 安装构建依赖"
dnf -y --setopt=install_weak_deps=False install \
    cmake gcc gcc-c++ make \
    ncurses-devel openssl-devel zlib-devel libaio-devel libtirpc-devel rpcgen numactl-devel \
    bison m4 \
    perl perl-Getopt-Long perl-Data-Dumper perl-File-Temp \
    systemd-devel systemd-rpm-macros \
    rpm-build redhat-rpm-config \
    tar gzip curl which findutils diffutils file cpio procps-ng shadow-utils

# 关掉 dnf 缓存，省磁盘
dnf clean all
rm -rf /var/cache/dnf

echo "==> 组件版本"
gcc --version | sed -n '1,1p'
cmake --version | sed -n '1,1p'
ldd --version | sed -n '1,1p'
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
