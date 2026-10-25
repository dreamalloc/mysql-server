#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 产物校验：架构 / debuginfo / glibc 符号版本 / systemd 单元 / 校验和
# 任何一项不过就让流水线红掉，避免把"看起来能装"的包发出去
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi  # GitHub 步骤会带 -o pipefail 并被继承

TOP="${RPMBUILD_TOP:-/build/rpmbuild}"
TARGET_NAME="${TARGET_NAME:-Kylin V10 SP3 (aarch64)}"
GLIBC_MAX="${GLIBC_MAX:-2.28}"
EXPECT_ARCH="${EXPECT_ARCH:-aarch64}"
ARCH_HINT="${ARCH_HINT:-ARM aarch64}"
SRC_NAME="${SRC_NAME:-mysql-5.7.44}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$TOP"

RPMS="$(find RPMS -name '*.rpm' | sort)"
[ -n "$RPMS" ] || { echo "!! 没有任何 RPM 产物"; exit 1; }

echo "======================= 产物清单 ======================="
printf '%-64s %9s %9s\n' "FILE" "ARCH" "SIZE"
for f in $RPMS; do
    printf '%-64s %9s %9s\n' \
        "$(basename "$f")" \
        "$(rpm -qp --qf '%{ARCH}' "$f" 2>/dev/null || echo src)" \
        "$(du -h "$f" | cut -f1)"
done

echo
echo "=================== 1. 架构一致性 ====================="
ARCHS="$(rpm -qp --qf '%{ARCH}\n' $RPMS | sort -u | grep -v '^src$' || true)"
echo "    架构集合: ${ARCHS}"
if echo "$ARCHS" | grep -qv "^${EXPECT_ARCH}$"; then
    echo "!! 存在非 ${EXPECT_ARCH} 产物"; exit 1
fi

echo
echo "=================== 2. debuginfo ======================"
# EL8 按子包拆 debuginfo；openEuler 默认只出一个总包，两种都接受
DBG="$(find RPMS -name '*server-debuginfo-*.rpm' | sort | sed -n '1p' || true)"
if [ -z "$DBG" ]; then
    DBG="$(find RPMS -name '*-debuginfo-*.rpm' | grep -v debugsource | sort | sed -n '1p' || true)"
fi
DBG_ALL="$(find RPMS -name '*-debuginfo-*.rpm' | wc -l)"
if [ -n "$DBG" ]; then
    echo "    debuginfo 包 ${DBG_ALL} 个，代表: $(basename "$DBG") ($(du -h "$DBG" | cut -f1))"
    echo "    其中 .debug 文件 $(rpm -qlp "$DBG" | grep -c '\.debug$') 个（布局随发行版默认，不做路径断言）"
else
    echo "!! 未生成 debuginfo 包"
    exit 1
fi

DSRC="$(find RPMS -name '*-debugsource-*.rpm' | sed -n '1,1p' || true)"
[ -n "$DSRC" ] && echo "    debugsource: $(basename "$DSRC")" || echo "    debugsource: 未生成（可选）"

echo
echo "=================== 3. glibc 符号版本 ================="
MAXV=""
for f in $RPMS; do
    v="$(rpm -qpR "$f" 2>/dev/null | grep -o 'GLIBC_[0-9][0-9.]*' | sed 's/GLIBC_//' | sort -Vu | tail -1 || true)"
    [ -z "$v" ] && continue
    if [ -z "$MAXV" ] || [ "$(printf '%s\n%s\n' "$MAXV" "$v" | sort -V | tail -1)" = "$v" ]; then
        MAXV="$v"
    fi
done
echo "    最高依赖符号版本: ${MAXV:-未知}  (目标平台 ${TARGET_NAME} 上限 ${GLIBC_MAX})"
# 取 MAXV 与 2.28 的较大者：若较大者不是 2.28，说明依赖了更高的符号版本
if [ -n "$MAXV" ] && [ "$(printf '%s\n%s\n' "$MAXV" "$GLIBC_MAX" | sort -V | tail -1)" != "$GLIBC_MAX" ]; then
    echo "!! 产物依赖 GLIBC_${MAXV}，高于 ${TARGET_NAME} 的 ${GLIBC_MAX}，装不上"
    exit 1
fi

echo
echo "=================== 4. systemd 单元 ==================="
# 包名前缀随版本变化（mysql-community / mysql80-community），用通配避免写死
SRV="$TOP/$(find RPMS -name '*-server-*.rpm' -not -name '*debug*' -not -name '*.src.rpm' | sed -n '1p')"
[ -n "$SRV" ] && [ "$SRV" != "$TOP/" ] || { echo "!! 找不到 server 主包"; exit 1; }
mkdir -p "$WORK/u"
( cd "$WORK" && rpm2cpio "$SRV" | cpio -idm --quiet 2>/dev/null ) || true
for u in mysqld.service 'mysqld@.service'; do
    p="$WORK/usr/lib/systemd/system/$u"
    if [ -f "$p" ]; then
        echo "    --- $u ---"
        grep -E '^(Type|PIDFile|ExecStart|ExecStartPre|User|Group)=' "$p" | sed 's/^/        /'
    else
        echo "!! 单元文件缺失: $u"; exit 1
    fi
done
grep -q 'mysqld_pre_systemd' "$WORK/usr/lib/systemd/system/mysqld.service" \
    || { echo "!! 单元未引用 mysqld_pre_systemd，首次安装不会自动初始化数据目录"; exit 1; }
[ -x "$WORK/usr/bin/mysqld_pre_systemd" ] || [ -f "$WORK/usr/bin/mysqld_pre_systemd" ] \
    || { echo "!! 缺少 /usr/bin/mysqld_pre_systemd"; exit 1; }

echo "    systemd-analyze verify:"
for u in mysqld.service; do
    systemd-analyze verify "$WORK/usr/lib/systemd/system/$u" 2>&1 \
        | sed 's/^/        /' || true
done

echo
echo "=================== 5. 二进制 ELF 架构 ================"
file "$WORK/usr/sbin/mysqld" | sed 's/^/    /'
file "$WORK/usr/sbin/mysqld" | grep -q "${ARCH_HINT}" \
    || { echo "!! mysqld 不是 ${EXPECT_ARCH} ELF"; exit 1; }

echo
echo "=================== 6. 脚本片段 ======================="
rpm -qp --scripts "$SRV" | grep -E 'systemd_post|systemd_preun|useradd|groupadd' | sed 's/^/    /' | sed -n '1,10p'

echo
echo "=================== 7. 生成校验和与构建信息 ==========="
( cd "$TOP" && find RPMS SRPMS -name '*.rpm' | sort | xargs sha256sum > SHA256SUMS )
sed 's/^/    /' SHA256SUMS | sed -n '1,20p'

{
    echo "MySQL ${SRC_NAME#mysql-} RPM build for ${TARGET_NAME}"
    echo "=============================================================="
    echo "build time   : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "source repo  : ${GITHUB_REPOSITORY:-dreamalloc/mysql-server}"
    echo "source ref   : ${SRC_REF:-mysql-5.7.44}"
    echo "source commit: $(cat /tmp/src_commit.txt 2>/dev/null || echo unknown)"
    echo "runner       : $(uname -m) / $(nproc) vCPU"
    echo "build rootfs : $(cat /etc/kylin-release 2>/dev/null || cat /etc/rocky-release 2>/dev/null || cat /etc/os-release | sed -n '1,2p' | tr '\n' ' ')"
    echo "gcc          : $(gcc --version | sed -n '1,1p')"
    echo "glibc        : $(ldd --version | sed -n '1,1p')"
    echo "cmake        : $(cmake --version | sed -n '1,1p')"
    echo "rpm          : $(rpm --version)"
    echo
    echo "Packages"
    echo "--------"
    for f in $RPMS; do
        printf '  %-64s %8s\n' "$(basename "$f")" "$(du -h "$f" | cut -f1)"
    done
    echo
    echo "Install on ${TARGET_NAME}"
    echo "----------------------------------"
    echo "  tar xf mysql-5.7.44-kylin10-aarch64-rpm.tar.gz"
    echo "  dnf install ./*.rpm            # 或 rpm -Uvh ./*.rpm"
    echo "  systemctl enable --now mysqld  # 首次启动自动 initialize 数据目录"
    echo "  grep 'temporary password' /var/log/mysqld.log"
    echo "  mysql -uroot -p -e \"ALTER USER 'root'@'localhost' IDENTIFIED BY '...';\""
} > BUILD-INFO.txt
cat BUILD-INFO.txt | sed 's/^/    /'
