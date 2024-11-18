# oracle db
[TOC]
## 请求参数 POST
``` python
{
    "timeout": "200",                  # 执行超时，单位为s，非必须
    "queue": "aa-bb-cc-dd",          # 消息队列名
    "targets": [                     # 目标机器信息
                                     # 字段名修改为targets，类型变为list
        {
            "host": "192.168.1.14",
            "category": "Linux",     # category为Linux或Windows
            "pasd": "password",
            "user": "root"
        }
    ],
    "module":{                      # script和module二选一
        "name": "service",
        "args": {                   # args字段必须的，可以没有字段
            "install_config": "默认安装配置",
            "oracle_config": "默认oracle配置",
            "sys_config": "默认系统配置"
        },
        "options": { # options是可选字段，附加信息，用于变换用户执行任务
            "sudo":"true",          # sudo是可选字段，sudo=true,使用sudo执行命令，becomeUser为root，becomePass不用设置
            "become":"true",        # become是可选字段，默认情况下become=true等价于sudo=true
            "becomeUser":"mysql",  # becomeUser是可选字段，如果设置becomeUser就使用该用户执行
            "becomePass":"12"      # becomePass是可选字段，如果设置becomePass就使用该用户密码执行
        }
    }
}
```

## 默认安装配置 install_config
``` python
oracle_install_version: "12102"
oracle_user: "oracle"
oracle_os_user_pass: '$6$P7jw3OaWKdR$tRSRPjTey'
oracle_install_group: "oinstall"
oracle_base: "/oracle/app"
```
## 默认oracle配置 oracle_config
``` python
dbhome_name: "dbhome_1"
oracle_edition: "EE"
oracle_dba_group: "dba"
oracle_oper_group: "oper"
oracle_database_type: "GENERAL_PURPOSE"
oracle_globalname: "orcl.oradb3.private"
oracle_sid: "orcl"
create_container_database: "true" or "false" 二选一 默认：true
number_of_pdbs: "1"
oracle_conf_as_container_db: "true" or "false" 二选一 默认：true
pdb_prefix: "db"
oracle_pdb_name: "db01"
oracle_charset: "AL32UTF8"
oracle_memory_option: "true" or "false" 二选一 默认：false
oracle_memory_mb: 1536
oracle_install_samples: "true" or "false" 二选一 默认：true
oracle_management_option: "DEFAULT"
oracle_enable_recovery: "true" or "false" 二选一 默认：true
oracle_storage_type: "FILE_SYSTEM_STORAGE"
oracle_dataloc: "{{ oracle_base }}/oradata"
oracle_recoveryloc: "{{ oracle_base }}/recovery_area"
oracle_decline_security_updates: "True" or "False" 二选一 默认：True
hugepages_nr: 578
oracle_pass_all_users: "oracle"
install_db: INSTALL_DB_SWONLY
oracle_hostname: '{{ server_hostname }}'
inventory_os_group: '{{ oracle_install_group }}'
inventory_location: '{{ oracle_base }}/inventory/'
oracle_home: '{{ oracle_base }}/{{ oracle_user }}/product/{{ oracle_install_version }}/{{ dbhome_name }}'
```

## 默认系统配置 sys_config
``` python
kernel.sem: 250 32000 100 128
kernel.shmmni: 4096
kernel.shmall: 393216
kernel.shmmax: 4398046511104
net.core.rmem_max: 16777216
net.core.wmem_max: 16777216
net.ipv4.tcp_rmem: 4096 87380 16777216
net.ipv4.tcp_wmem: 4096 65536 16777216
vm.swappiness: 10
vm.dirty_background_ratio: 5
vm.dirty_ratio: 10
fs.file-max: 409600
net.ipv4.tcp_keepalive_time: 300
net.ipv4.tcp_keepalive_intvl: 60
net.ipv4.tcp_keepalive_probes: 10
net.ipv4.ip_local_port_range: 9000 65500
```


