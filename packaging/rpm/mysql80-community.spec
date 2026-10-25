# ---------------------------------------------------------------------------
# MySQL 8.0.37 全量 RPM spec —— 与 5.7 版（mysql-community.spec）并列
#
# 与 5.7 的关键差异（都已在下面体现）：
#   1. Boost 1.77.0，且是 .tar.bz2；5.7 是 1.59.0/.tar.gz
#   2. systemd 单元是 Type=notify，mysqld 前台运行，没有 PermissionsStartOnly，
#      因此不需要 5.7 那个 sed 补丁
#   3. 客户端库是 libmysqlclient.so.21（5.7 是 .20）
#   4. 初始化靠 mysqld --initialize，没有 mysql_install_db
#   5. EL8 上 CMake 默认强制 gcc-toolset-12，但用它会引入 GLIBCXX_3.4.29+ 依赖，
#      麒麟的 libstdc++ 不提供 → 显式指定系统 gcc/g++（CMakeLists 允许这么做）
#   6. 不单独出 test 子包：8.0 的测试插件与正式插件同目录，用通配符打包会冲突，
#      这里直接 -DINSTALL_MYSQLTESTDIR= 不安装测试套件
# ---------------------------------------------------------------------------

%global srcname      mysql
%global product      community
%global src_dir      mysql-8.0.37
%global mysqldatadir /var/lib/mysql

%global __requires_exclude ^perl\\((GD|hostnames|lib::mtr|lib::v1|mtr_|My::)
%global __provides_exclude_from ^(/usr/share/(mysql|mysql-test)/.*|%{_libdir}/mysql/plugin/.*\\.so)$

# debuginfo 体积大，提高压缩比
# protobuf：内置 24.4 的动态库在麒麟 GCC 7 上链接会缺
# std::allocator<std::basic_string_view<char>> 符号；给 CXXFLAGS 加
# -static-libgcc 后，MySQL 的 protobuf 子工程会改编译静态库，绕开该问题。
%if 0%{?kylin}
%global proto_ldflags -static-libgcc
%global proto_private 0
%else
%global proto_ldflags %{nil}
%global proto_private 1
%endif

%global _binary_payload w2.xzdio

# 8.0 的 CMake 会给编译加 -fdebug-prefix-map=...=. ，DWARF 里是相对路径，
# rpm 的 find-debuginfo 无法据此收集源码 → debugsource 包必为空，直接关掉。
# 符号（debuginfo）不受影响。
# 注意：必须用 %%undefine —— redhat-rpm-config 里是 %%{?_debugsource_packages}
# 只判断「是否定义」，写 0 无效。
%undefine _debugsource_packages

# openEuler 24.03 (gcc 12)：新版告警抑制
%if 0%{?oe2403}
%global extra_warn -Wno-free-nonheap-object -Wno-array-bounds -Wno-stringop-overflow -Wno-maybe-uninitialized
%else
%global extra_warn %{nil}
%endif

Name:           mysql80-%{product}
Version:        8.0.37
Release:        1%{?dist}
Summary:        MySQL 8.0.37 Community Server (RPM build)
License:        GPLv2
URL:            https://github.com/mysql/mysql-server
Source0:        %{src_dir}.tar.gz
Source1:        boost_1_77_0.tar.bz2
# 麒麟 GCC 7.3 无 <charconv>，ndb 里唯一一处 std::from_chars 用 strtoul 替代
Patch0:         mysql80-charconv-gcc7.patch

BuildRequires:  cmake >= 3.11
BuildRequires:  gcc gcc-c++ make
BuildRequires:  ncurses-devel
BuildRequires:  openssl-devel
BuildRequires:  zlib-devel
BuildRequires:  libaio-devel
BuildRequires:  libtirpc-devel
BuildRequires:  rpcgen
BuildRequires:  numactl-devel
BuildRequires:  bison m4
BuildRequires:  perl perl(Getopt::Long) perl(Data::Dumper)
BuildRequires:  systemd-devel
%if 0%{?oe2403}
BuildRequires:  rpm-build openEuler-rpm-config
%else
%if 0%{?kylin}
BuildRequires:  rpm-build kylin-rpm-config
%else
BuildRequires:  rpm-build redhat-rpm-config
%endif
%endif
BuildRequires:  findutils which tar gzip bzip2

%description
MySQL Server 8.0.37，基于 mysql/mysql-server 的 mysql-8.0.37 源码重新编译打包，
面向国产化 Linux（麒麟 V10 / openEuler 24.03）提供可离线安装的 RPM 包。

本包为 meta 包，实际内容见 mysql80-community-server / -client / -libs / -common / -devel。

%package        common
Summary:        MySQL 8.0.37 共享字符集与错误信息
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}

%description    common
MySQL 客户端与服务端共用的字符集、多语言错误信息等只读数据。

%package        libs
Summary:        MySQL 8.0.37 共享客户端库
Provides:       mysql80-libs%{?_isa} = %{version}-%{release}
Conflicts:      mariadb-libs
Obsoletes:      mariadb-libs

%description    libs
MySQL 客户端共享库 libmysqlclient.so.21。

%package        client
Summary:        MySQL 8.0.37 客户端工具
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Requires:       %{name}-common%{?_isa} = %{version}-%{release}
Conflicts:      mariadb

%description    client
mysql、mysqldump、mysqladmin、mysqlbinlog、mysqlpump 等命令行工具。

%package        server
Summary:        MySQL 8.0.37 数据库服务端
Requires:       %{name}-client%{?_isa} = %{version}-%{release}
Requires:       %{name}-common%{?_isa} = %{version}-%{release}
Requires:       coreutils grep procps-ng shadow-utils net-tools
Requires:       numactl-libs
Requires(pre):  shadow-utils
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd
Provides:       mysql80-server = %{version}-%{release}
Conflicts:      mariadb-server

%description    server
mysqld 服务端进程、插件、systemd 单元、默认配置与数据目录骨架。

首次 systemctl start 时由 /usr/bin/mysqld_pre_systemd 初始化数据目录，
临时 root 密码写入 /var/log/mysqld.log。

%package        devel
Summary:        MySQL 8.0.37 开发头文件与库
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Conflicts:      mariadb-devel

%description    devel
编译 MySQL 客户端程序所需的头文件、静态库、mysql_config 与 pkgconfig 文件。

# ---------------------------------------------------------------------------
%prep
%setup -q -n %{src_dir}

# GCC 7 的 libstdc++ 没有 <charconv>，麒麟平台需要打兼容补丁
%if 0%{?kylin}
%patch0 -p1
# GCC 7 不会为 std::allocator<std::string_view> 发射内联构造符号，
# 让 abseil 用自有 string_view 实现，避免 protoc 链接失败
sed -i 's/^#define ABSL_OPTION_USE_STD_STRING_VIEW 2$/#define ABSL_OPTION_USE_STD_STRING_VIEW 0/' \
    extra/abseil/abseil-cpp-20230802.1/absl/base/options.h
%endif

# Boost：8.0 用 1.77.0（.tar.bz2），解到与源码平级的独立目录
mkdir -p %{_builddir}/boost
tar -xf %{SOURCE1} -C %{_builddir}/boost

%build
mkdir -p build
pushd build

cmake .. \
  -DBUILD_CONFIG=mysql_release \
  -DINSTALL_LAYOUT=RPM \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_COMPILER=%{_bindir}/gcc \
  -DCMAKE_CXX_COMPILER=%{_bindir}/g++ \
  -DCMAKE_C_FLAGS="%{optflags} -fno-omit-frame-pointer %{extra_warn}" \
  -DCMAKE_CXX_FLAGS="%{optflags} -fno-omit-frame-pointer %{extra_warn} %{proto_ldflags}" \
  -DWITH_BOOST=%{_builddir}/boost \
  -DWITH_SYSTEMD=1 \
  -DWITH_SSL=%{?with_ssl}%{!?with_ssl:system} \
  -DWITH_ZLIB=bundled \
  -DWITH_NUMA=1 \
  -DWITH_LIBEVENT=bundled \
  -DWITH_LZ4=bundled \
  -DWITH_ZSTD=bundled \
  -DWITH_PROTOBUF=bundled \
  -DWITH_EDITLINE=bundled \
  -DWITH_ROUTER=OFF \
  -DWITH_UNIT_TESTS=OFF \
  -DENABLED_LOCAL_INFILE=0 \
  -DINSTALL_LIBDIR="%{_lib}/mysql" \
  -DINSTALL_PLUGINDIR="%{_lib}/mysql/plugin" \
  -DINSTALL_MYSQLSHAREDIR="share/mysql" \
  -DINSTALL_MYSQLTESTDIR="" \
  -DINSTALL_SQLBENCHDIR="" \
  -DINSTALL_MYSQLDATADIR="%{mysqldatadir}" \
  -DMYSQL_DATADIR="%{mysqldatadir}" \
  -DMYSQL_UNIX_ADDR="%{mysqldatadir}/mysql.sock" \
  -DCOMPILATION_COMMENT="MySQL Community Server (RPM build)"

make %{?_smp_mflags} VERBOSE=1
popd

%install
rm -rf %{buildroot}

pushd build
make DESTDIR=%{buildroot} install
popd

# 目录骨架
install -d -m 0751 %{buildroot}%{mysqldatadir}
install -d -m 0755 %{buildroot}/var/run/mysqld
install -d -m 0750 %{buildroot}/var/lib/mysql-files
install -d -m 0750 %{buildroot}/var/lib/mysql-keyring

# 配置文件（CMake 用 packaging/rpm-common/my.cnf.in 生成）
install -D -m 0644 build/packaging/rpm-common/my.cnf \
        %{buildroot}%{_sysconfdir}/my.cnf
install -D -m 0644 build/packaging/rpm-common/mysql.logrotate \
        %{buildroot}%{_sysconfdir}/logrotate.d/mysql
install -d %{buildroot}%{_sysconfdir}/my.cnf.d

# 动态库搜索路径
install -d -m 0755 %{buildroot}%{_sysconfdir}/ld.so.conf.d
echo "%{_libdir}/mysql" > %{buildroot}%{_sysconfdir}/ld.so.conf.d/mysql-%{_arch}.conf

# 清理不需要打包的产物
rm -rf %{buildroot}%{_infodir}/mysql.info*
rm -f  %{buildroot}%{_datadir}/mysql/mysql.server
rm -f  %{buildroot}%{_datadir}/mysql/mysqld_multi.server
rm -f  %{buildroot}%{_bindir}/mysql_embedded
rm -f  %{buildroot}%{_bindir}/my_openssl
rm -f  %{buildroot}%{_mandir}/man1/mysqld_safe.1*
rm -f  %{buildroot}%{_mandir}/man1/mysqld_multi.1*
rm -f  %{buildroot}%{_mandir}/man1/ndb*.1*
rm -rf %{buildroot}%{_datadir}/mysql-test
rm -f  %{buildroot}%{_bindir}/comp_err \
       %{buildroot}%{_bindir}/mysqltest \
       %{buildroot}%{_bindir}/mysqltest_safe_process \
       %{buildroot}%{_bindir}/mysqlxtest \
       %{buildroot}%{_bindir}/mysql_client_test \
       %{buildroot}%{_bindir}/mysql_keyring_encryption_test
rm -rf %{buildroot}%{_libdir}/mysqlrouter \
       %{buildroot}%{_bindir}/mysqlrouter* \
       %{buildroot}%{_unitdir}/mysqlrouter.service \
       %{buildroot}%{_prefix}/lib/tmpfiles.d/mysqlrouter.conf

# 供 %%files 校准用
find %{buildroot} -type f -o -type l | sed "s|%{buildroot}||" | sort > %{_builddir}/buildroot-files.txt

# ---------------------------------------------------------------------------
%pre server
getent group mysql >/dev/null 2>&1 || /usr/sbin/groupadd -r mysql >/dev/null 2>&1 || :
getent passwd mysql >/dev/null 2>&1 || \
    /usr/sbin/useradd -r -g mysql -d %{mysqldatadir} -s /sbin/nologin \
        -c "MySQL Server" mysql >/dev/null 2>&1 || :

%post server
[ -e /var/log/mysqld.log ] || install -m 0640 -o mysql -g mysql /dev/null /var/log/mysqld.log >/dev/null 2>&1 || :
%systemd_post mysqld.service
if [ $1 -eq 1 ]; then
    /usr/bin/systemctl enable mysqld.service >/dev/null 2>&1 || :
fi

%preun server
%systemd_preun mysqld.service

%postun server
%systemd_postun_with_restart mysqld.service

%post libs -p /sbin/ldconfig
%postun libs -p /sbin/ldconfig

# ---------------------------------------------------------------------------
%files
%doc LICENSE
%doc README

%files common
%doc LICENSE
%{_datadir}/mysql/charsets/
%{_datadir}/mysql/messages_to_error_log.txt
%{_datadir}/mysql/messages_to_clients.txt
%{_datadir}/mysql/bulgarian/
%{_datadir}/mysql/czech/
%{_datadir}/mysql/danish/
%{_datadir}/mysql/dutch/
%{_datadir}/mysql/english/
%{_datadir}/mysql/estonian/
%{_datadir}/mysql/french/
%{_datadir}/mysql/german/
%{_datadir}/mysql/greek/
%{_datadir}/mysql/hungarian/
%{_datadir}/mysql/italian/
%{_datadir}/mysql/japanese/
%{_datadir}/mysql/korean/
%{_datadir}/mysql/norwegian-ny/
%{_datadir}/mysql/norwegian/
%{_datadir}/mysql/polish/
%{_datadir}/mysql/portuguese/
%{_datadir}/mysql/romanian/
%{_datadir}/mysql/russian/
%{_datadir}/mysql/serbian/
%{_datadir}/mysql/slovak/
%{_datadir}/mysql/spanish/
%{_datadir}/mysql/swedish/
%{_datadir}/mysql/ukrainian/

%files libs
%dir %attr(755, root, root) %{_libdir}/mysql
%attr(644, root, root) %{_sysconfdir}/ld.so.conf.d/mysql-%{_arch}.conf
%{_libdir}/mysql/libmysqlclient.so.21*

%files client
%attr(755, root, root) %{_bindir}/mysql
%attr(755, root, root) %{_bindir}/mysqladmin
%attr(755, root, root) %{_bindir}/mysqlbinlog
%attr(755, root, root) %{_bindir}/mysqlcheck
%attr(755, root, root) %{_bindir}/mysqldump
%attr(755, root, root) %{_bindir}/mysqlimport
%attr(755, root, root) %{_bindir}/mysqlpump
%attr(755, root, root) %{_bindir}/mysqlshow
%attr(755, root, root) %{_bindir}/mysqlslap
%attr(755, root, root) %{_bindir}/mysql_config_editor
%attr(755, root, root) %{_bindir}/mysql_migrate_keyring
%attr(644, root, root) %{_mandir}/man1/*.1*

%files server
%config(noreplace) %{_sysconfdir}/my.cnf
%dir %{_sysconfdir}/my.cnf.d

%attr(755, root, root) %{_sbindir}/mysqld
%attr(755, root, root) %{_bindir}/mysqld_pre_systemd
%attr(755, root, root) %{_bindir}/mysqld_safe
%attr(755, root, root) %{_bindir}/innochecksum
%attr(755, root, root) %{_bindir}/ibd2sdi
%attr(755, root, root) %{_bindir}/my_print_defaults
%attr(755, root, root) %{_bindir}/myisam_ftdump
%attr(755, root, root) %{_bindir}/myisamchk
%attr(755, root, root) %{_bindir}/myisamlog
%attr(755, root, root) %{_bindir}/myisampack
%attr(755, root, root) %{_bindir}/mysql_secure_installation
%attr(755, root, root) %{_bindir}/mysql_ssl_rsa_setup
%attr(755, root, root) %{_bindir}/mysql_tzinfo_to_sql
%attr(755, root, root) %{_bindir}/mysql_upgrade
%attr(755, root, root) %{_bindir}/mysqldumpslow
%attr(755, root, root) %{_bindir}/perror
%attr(755, root, root) %{_bindir}/lz4_decompress
%attr(755, root, root) %{_bindir}/zlib_decompress

# 私有依赖（protobuf / 自带 OpenSSL）；麒麟用静态 protobuf，无此目录
%if %{proto_private}
%dir %{_libdir}/mysql/private
%{_libdir}/mysql/private/*
%endif

%dir %{_libdir}/mysql/plugin
%{_libdir}/mysql/plugin/*.so
%attr(644, root, root) %{_libdir}/mysql/plugin/*.ini

%{_datadir}/mysql/*.sql
%attr(644, root, root) %{_datadir}/mysql/dictionary.txt

%attr(644, root, root) %{_unitdir}/mysqld.service
%attr(644, root, root) %{_unitdir}/mysqld@.service
%attr(644, root, root) %{_prefix}/lib/tmpfiles.d/mysql.conf
%attr(644, root, root) %{_mandir}/man8/*.8*
%attr(644, root, root) %{_datadir}/mysql-*/mysql-log-rotate

%attr(644, root, root) %config(noreplace,missingok) %{_sysconfdir}/logrotate.d/mysql
%dir %attr(751, mysql, mysql) %{mysqldatadir}
%dir %attr(755, mysql, mysql) /var/run/mysqld
%dir %attr(750, mysql, mysql) /var/lib/mysql-files
%dir %attr(750, mysql, mysql) /var/lib/mysql-keyring

%files devel
%attr(755, root, root) %{_bindir}/mysql_config
%{_includedir}/mysql
%{_datadir}/aclocal/mysql.m4
%{_libdir}/mysql/libmysqlclient.a
%{_libdir}/mysql/libmysqlservices.a
%{_libdir}/mysql/libmysqlclient.so
%{_libdir}/pkgconfig/mysqlclient.pc

# ---------------------------------------------------------------------------
%changelog
* Sat Oct 24 2026 Build Team <ops@example.com> - 8.0.37-1
- 基于 mysql/mysql-server 标签 mysql-8.0.37 构建
- 双平台：麒麟 V10 SP3 (aarch64) / openEuler 24.03 LTS (x86_64)
- Boost 1.77.0；systemd Type=notify + mysqld_pre_systemd 首启初始化
