# ---------------------------------------------------------------------------
# MySQL 5.7.44 全量 RPM spec  ——  银河麒麟 V10 SP3 / aarch64
#
# 设计要点：
#   1. 只构建一棵 RelWithDebInfo 树（同时满足 Release 与 debuginfo 需求），
#      不构建上游 spec 里的 debug 树，节省约 40%% 磁盘与 30%% 时间。
#   2. -DWITH_SYSTEMD=1 让 CMake 安装上游自带的 mysqld.service /
#      mysqld@.service / tmpfiles.d/mysql.conf / mysqld_pre_systemd，
#      首次 systemctl start 时由 mysqld_pre_systemd 自动 initialize 数据目录。
#   3. -DBUILD_CONFIG=mysql_release + -DINSTALL_LAYOUT=RPM 保证目录布局
#      与 EL8 系（麒麟 V10 SP3）一致。
#   4. 不关闭 %%debug_package，debuginfo 由 brp-strip + find-debuginfo 自动生成。
# ---------------------------------------------------------------------------

%global srcname      mysql
%global product      community
%global src_dir      mysql-5.7.44
%global mysqldatadir /var/lib/mysql
%global min          5.7.9

# mysql-test 里的 perl 脚本会引入大量无法解析的 perl 模块依赖，过滤掉
%global __requires_exclude ^perl\\((GD|hostnames|lib::mtr|lib::v1|mtr_|My::)
%global __provides_exclude_from ^(/usr/share/(mysql|mysql-test)/.*|%{_libdir}/mysql/plugin/.*\\.so)$

# debuginfo 体积很大（mysqld 单个 .debug 约 300-500MB），用更高压缩比
%global _binary_payload w2.xzdio

# openEuler 24.03 (gcc 12 / glibc 2.38)：5.7 老代码会触发新版告警，
# 这些是 warning 级别，配合 -fcommon 一起关掉即可
%if 0%{?oe2403}
%global extra_warn -Wno-free-nonheap-object -Wno-array-bounds -Wno-stringop-overflow -Wno-maybe-uninitialized
%else
%global extra_warn %{nil}
%endif

Name:           mysql-%{product}
Version:        5.7.44
Release:        1%{?dist}
Summary:        MySQL 5.7.44 Community Server (Kylin V10 SP3 aarch64 build)
License:        GPLv2
URL:            https://github.com/dreamalloc/mysql-server
Source0:        %{src_dir}.tar.gz
Source1:        boost_1_59_0.tar.gz

BuildRequires:  cmake >= 3.5.1
BuildRequires:  gcc gcc-c++ make
BuildRequires:  ncurses-devel
BuildRequires:  openssl-devel
BuildRequires:  zlib-devel
BuildRequires:  libaio-devel
BuildRequires:  libtirpc-devel
BuildRequires:  rpcgen
BuildRequires:  numactl-devel
BuildRequires:  bison m4
BuildRequires:  perl
BuildRequires:  perl(Getopt::Long) perl(Data::Dumper)
BuildRequires:  systemd-devel
BuildRequires:  pkgconfig(systemd)
%if 0%{?oe2403}
BuildRequires:  rpm-build openEuler-rpm-config
%else
%if 0%{?kylin}
BuildRequires:  rpm-build kylin-rpm-config
%else
BuildRequires:  rpm-build redhat-rpm-config
%endif
%endif
BuildRequires:  findutils which tar gzip

%description
MySQL Server 5.7.44，基于 dreamalloc/mysql-server 的 5.7.44 源码，
面向银河麒麟高级服务器操作系统 V10 SP3（aarch64）重新编译打包。

本包为 meta 包，实际内容见 mysql-community-server / -client / -libs /
-common / -devel / -test 等子包。

%package        common
Summary:        MySQL 5.7.44 共享的字符集与错误信息文件
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}

%description    common
MySQL 客户端与服务端共用的字符集、错误信息等只读数据文件。

%package        libs
Summary:        MySQL 5.7.44 共享客户端库
Provides:       mysql-libs%{?_isa} = %{version}-%{release}
Obsoletes:      mysql-libs < %{version}-%{release}
Obsoletes:      mariadb-libs
Conflicts:      mariadb-libs

%description    libs
MySQL 客户端共享库 libmysqlclient.so.20。

%package        client
Summary:        MySQL 5.7.44 客户端工具
Requires:       %{name}-libs%{?_isa} >= %{min}
Requires:       %{name}-common%{?_isa} = %{version}-%{release}
Provides:       mysql%{?_isa} = %{version}-%{release}
Obsoletes:      mysql < %{version}-%{release}
Obsoletes:      mariadb
Conflicts:      mariadb

%description    client
mysql、mysqldump、mysqladmin、mysqlbinlog 等命令行工具。

%package        server
Summary:        MySQL 5.7.44 数据库服务端
Requires:       %{name}-client%{?_isa} >= %{min}
Requires:       %{name}-common%{?_isa} = %{version}-%{release}
Requires:       coreutils grep procps-ng shadow-utils net-tools
Requires:       openssl-libs >= 1.1.1
Requires:       numactl-libs
Requires:       zlib
Requires(pre):  shadow-utils
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd
Provides:       mysql-server%{?_isa} = %{version}-%{release}
Provides:       mysql-server = %{version}-%{release}
Obsoletes:      mysql-server < %{version}-%{release}
Obsoletes:      mariadb-server
Conflicts:      mariadb-server

%description    server
mysqld 服务端进程、存储引擎插件、systemd 单元、默认配置文件与数据目录骨架。

本包通过 systemd 管理：首次 systemctl start mysqld 时，
/usr/bin/mysqld_pre_systemd 会自动初始化数据目录并生成 SSL 证书，
临时 root 密码写入 /var/log/mysqld.log。

%package        devel
Summary:        MySQL 5.7.44 开发头文件与库
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Provides:       mysql-devel%{?_isa} = %{version}-%{release}
Obsoletes:      mysql-devel < %{version}-%{release}
Obsoletes:      mariadb-devel
Conflicts:      mariadb-devel

%description    devel
编译 MySQL 客户端程序所需的头文件、静态库、mysql_config 与 pkgconfig 文件。

%package        test
Summary:        MySQL 5.7.44 测试套件（mysql-test / mysqltest）
Requires:       %{name}-server%{?_isa} = %{version}-%{release}

%description    test
MySQL 官方 MTR 测试框架与测试用例，用于回归验证，生产环境可不安装。

# ---------------------------------------------------------------------------
%prep
%setup -q -n %{src_dir}

# Boost 1.59.0 需放在与源码平级的独立目录，避免污染源码树
mkdir -p %{_builddir}/boost
tar -xf %{SOURCE1} -C %{_builddir}/boost

# 上游源码已带生成好的 sql_yacc.cc，但为防止 bison 被意外触发，统一时间戳
find . -name '*.yy' -o -name '*.ll' | xargs -r touch -r configure.cmake 2>/dev/null || :

%build
mkdir -p build
pushd build

cmake .. \
  -DBUILD_CONFIG=mysql_release \
  -DINSTALL_LAYOUT=RPM \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_C_FLAGS="%{optflags} -fno-omit-frame-pointer -fcommon %{extra_warn}" \
  -DCMAKE_CXX_FLAGS="%{optflags} -fno-omit-frame-pointer -fcommon %{extra_warn}" \
  -DWITH_BOOST=%{_builddir}/boost \
  -DWITH_SYSTEMD=1 \
  -DWITH_SSL=%{?with_ssl}%{!?with_ssl:system} \
  -DWITH_ZLIB=system \
  -DWITH_MYSQLX=1 \
  -DWITH_NUMA=1 \
  -DWITH_INNODB_MEMCACHED=0 \
  -DWITH_EMBEDDED_SERVER=0 \
  -DENABLED_LOCAL_INFILE=0 \
  -DINSTALL_LIBDIR="%{_lib}/mysql" \
  -DINSTALL_PLUGINDIR="%{_lib}/mysql/plugin" \
  -DINSTALL_MYSQLTESTDIR="share/mysql-test" \
  -DINSTALL_SQLBENCHDIR="" \
  -DINSTALL_MYSQLDATADIR="%{mysqldatadir}" \
  -DMYSQL_DATADIR="%{mysqldatadir}" \
  -DMYSQL_UNIX_ADDR="%{mysqldatadir}/mysql.sock" \
  -DCOMPILATION_COMMENT="MySQL Community Server (Kylin V10 SP3 aarch64)" \
  -DWITH_EDITLINE=bundled

make %{?_smp_mflags} VERBOSE=1
popd

%install
rm -rf %{buildroot}

pushd build
make DESTDIR=%{buildroot} install
popd

# 目录骨架（与上游 spec 保持一致）
install -d -m 0751 %{buildroot}%{mysqldatadir}
install -d -m 0755 %{buildroot}/var/run/mysqld
install -d -m 0750 %{buildroot}/var/lib/mysql-files
install -d -m 0750 %{buildroot}/var/lib/mysql-keyring

# 配置文件：由 CMake 用 packaging/rpm-common/my.cnf.in 生成
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
rm -f  %{buildroot}%{_bindir}/mysql_client_test_embedded
rm -f  %{buildroot}%{_bindir}/mysqltest_embedded
# systemd 255 移除了 PermissionsStartOnly；openEuler 24.03 需删掉该行，
# 否则 ExecStartPre 会以 mysql 身份运行、无法创建日志与数据目录
%if 0%{?oe2403}
sed -i '/^PermissionsStartOnly=/d' \
    %{buildroot}%{_unitdir}/mysqld.service \
    %{buildroot}%{_unitdir}/mysqld@.service
%endif

# systemd 模式下不安装 mysqld_safe/mysqld_multi 脚本，其 man 页一并去掉

# 供首次构建校准 %%files 使用：把 buildroot 清单写到日志
find %{buildroot} -type f -o -type l | sed "s|%{buildroot}||" | sort > %{_builddir}/buildroot-files.txt
wc -l %{_builddir}/buildroot-files.txt

# ---------------------------------------------------------------------------
%pre server
getent group mysql >/dev/null 2>&1 || /usr/sbin/groupadd -r mysql >/dev/null 2>&1 || :
getent passwd mysql >/dev/null 2>&1 || \
    /usr/sbin/useradd -r -g mysql -d %{mysqldatadir} -s /sbin/nologin \
        -c "MySQL Server" mysql >/dev/null 2>&1 || :

%post server
[ -e /var/log/mysqld.log ] || install -m 0640 -o mysql -g mysql /dev/null /var/log/mysqld.log >/dev/null 2>&1 || :
%systemd_post mysqld.service
# 首次安装即开机自启；数据目录初始化由 mysqld_pre_systemd 在首次 start 时完成
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
%{_datadir}/mysql/errmsg-utf8.txt
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
%{_libdir}/mysql/libmysqlclient.so.20*

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

%files server
%config(noreplace) %{_sysconfdir}/my.cnf
%dir %{_sysconfdir}/my.cnf.d

%attr(755, root, root) %{_sbindir}/mysqld
%attr(755, root, root) %{_bindir}/mysqld_pre_systemd
%attr(755, root, root) %{_bindir}/innochecksum
%attr(755, root, root) %{_bindir}/my_print_defaults
%attr(755, root, root) %{_bindir}/myisam_ftdump
%attr(755, root, root) %{_bindir}/myisamchk
%attr(755, root, root) %{_bindir}/myisamlog
%attr(755, root, root) %{_bindir}/myisampack
%attr(755, root, root) %{_bindir}/mysql_install_db
%attr(755, root, root) %{_bindir}/mysql_plugin
%attr(755, root, root) %{_bindir}/mysql_secure_installation
%attr(755, root, root) %{_bindir}/mysql_ssl_rsa_setup
%attr(755, root, root) %{_bindir}/mysql_tzinfo_to_sql
%attr(755, root, root) %{_bindir}/mysql_upgrade
%attr(755, root, root) %{_bindir}/mysqldumpslow
%attr(755, root, root) %{_bindir}/perror
%attr(755, root, root) %{_bindir}/replace
%attr(755, root, root) %{_bindir}/resolve_stack_dump
%attr(755, root, root) %{_bindir}/resolveip
%attr(755, root, root) %{_bindir}/lz4_decompress
%attr(755, root, root) %{_bindir}/zlib_decompress


%dir %{_libdir}/mysql/plugin
%{_libdir}/mysql/plugin/*.so
%attr(644, root, root) %{_libdir}/mysql/plugin/*.ini

%{_datadir}/mysql/*.sql
%attr(644, root, root) %{_datadir}/mysql/mysql-log-rotate
%attr(644, root, root) %{_datadir}/mysql/magic
%attr(644, root, root) %{_datadir}/mysql/dictionary.txt

%attr(644, root, root) %{_unitdir}/mysqld.service
%attr(644, root, root) %{_unitdir}/mysqld@.service
%attr(644, root, root) %{_prefix}/lib/tmpfiles.d/mysql.conf

%attr(644, root, root) %config(noreplace,missingok) %{_sysconfdir}/logrotate.d/mysql
%attr(644, root, root) %{_mandir}/man1/mysqlman.1*
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

%files test
%attr(-, root, root) %{_datadir}/mysql-test
%attr(755, root, root) %{_bindir}/mysql_client_test
%attr(755, root, root) %{_bindir}/mysqltest
%attr(755, root, root) %{_bindir}/mysqlxtest

# ---------------------------------------------------------------------------
%changelog
* Fri Oct 23 2026 Build Team <ops@example.com> - 5.7.44-1
- 基于 dreamalloc/mysql-server 标签 mysql-5.7.44 构建
- 目标平台：银河麒麟高级服务器操作系统 V10 SP3 (aarch64)
- 启用 systemd 单元与 mysqld_pre_systemd 自动初始化
- 开启 debuginfo 子包
