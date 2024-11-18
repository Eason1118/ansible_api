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
            "db2_tarball_file"："v11.1_linuxx64_server_t.tar.gz",
            "db2_tmp_dest"："/tmp",
            "db2_prod"："DB2_SERVER_EDITION",
            "db2_file"："/opt/ibm/db2/V11.1",
            "db2_lic_agreement":"ACCEPT",
            "db2_install_type": "TYPICAL",
            "db2_make_cache"： "no",
            "db2_instance"： "DB2INST",
            "db2_name"："db2inst1",
            "db2_group_name"："db2iadm1",
            "db2_fenced_username"："db2fenc1",
            "db2_fenced_group_name"："db2fadm1",
            "db2_create_instances"：true ,
            "db2_ansible_os_family"："CentOS",
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

## 参数
``` python
db2_tarball_file："v11.1_linuxx64_server_t.tar.gz"
db2_tmp_dest："/tmp"
db2_prod："DB2_SERVER_EDITION"
db2_file："/opt/ibm/db2/V11.1"
db2_lic_agreement:"ACCEPT"  or "DECLINE" 二选一 默认："ACCEPT"
db2_install_type: "TYPICAL" or "COMPACT" or "CUSTOM" 三选一 默认："TYPICAL"
db2_make_cache： "no" or "yes" 二选一 默认："no"
db2_instance： "DB2INST"
db2_name："db2inst1"
db2_group_name："db2iadm1"
db2_fenced_username："db2fenc1"
db2_fenced_group_name："db2fadm1"
db2_create_instances：true or false 二选一 默认：true
db2_ansible_os_family："CentOS" or "RedHat" or "Debian" 三选一 默认："CentOS"
```

