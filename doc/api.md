## bocloud_worker API设计 ##

### API名称 ###
**/job/submit**

### 请求方法 ###
**POST**

### 请求参数 ###
    {
        "timeout": 200,                  # 执行超时，单位为s，非必须
        "queue": "aa-bb-cc-dd",          # 消息队列名
        "targets": [                     # 目标机器信息
                                         # 字段名修改为targets，类型变为list
            {
                "host": "192.168.1.14",
                "category": "Linux",     # category为Linux或Windows
                "pasd": "password",
                "user": "root"
            },
            {
                "host": "192.168.2.74",
                "category": "Linux",
                "port": 22,             # port非必须，默认为22。对于windows机器需要指定为windows remote manager的端口，一般为5986
                "pasd": "password",
                "user": "root"
            }
        ],
        "groups": [
            {
                "name": "group_name1",
                "hosts": [
                    {
                        "host": "192.168.2.97",
                        "vars": {
                            "myhost_vars";"this is 192.168.2.97"
                    }
                ],
                "vars": {
                    "mygroup_vars": "this is group_name1"
                }
            },
            {
                "name": "group_name2",
                "hosts": [
                    {
                        "host": "192.168.2.96",
                        "vars": {
                            "myhost_vars";"this is 192.168.2.96"
                        }
                    },
                    {
                        "host": "192.168.2.95",
                        "vars": {
                            "myhost_vars";"this is 192.168.2.95"
                        }
                    }
                ],
                "vars": {
                    "mygroup_vars": "this is group_name2"
                }
            }
        ],                              
        # 删除了原有的user字段
        "script": {                     # 执行脚本
            "type": "perl|shell|python|bat|powershell|playbook",
            "content": "import platform;print platform.system()",
            "params": "a a a a",
            "options": {                # options是可选字段，附加信息，用于变换用户执行任务
                "sudo":"true",          # sudo是可选字段，sudo=true,使用sudo执行命令，becomeUser为root，becomePass不用设置
                "become":"true",        # become是可选字段，默认情况下become=true等价于sudo=true
                "becomeUser":"mysql",  # becomeUser是可选字段，如果设置becomeUser就使用该用户执行
                "becomePass":"12"      # becomePass是可选字段，如果设置becomePass就使用该用户密码执行
            }
        },
        "module":{                      # script和module二选一
            "name": "service",
            "args": {                   # args字段必须的，可以没有字段
                "name": "telegraf",
                "state": "restarted"
            },
            "options": {                # options是可选字段，附加信息，用于变换用户执行任务
                "sudo":"true",          # sudo是可选字段，sudo=true,使用sudo执行命令，becomeUser为root，becomePass不用设置
                "become":"true",        # become是可选字段，默认情况下become=true等价于sudo=true
                "becomeUser":"mysql",  # becomeUser是可选字段，如果设置becomeUser就使用该用户执行
                "becomePass":"12"      # becomePass是可选字段，如果设置becomePass就使用该用户密码执行
            }
        }
    }
### rest返回结果 ###
    {
        "message": "The aa-bb-cc-dd job is sent to worker successful.",  
        "success": true
    }

### rabbitmq返回结果 ###
    {
        "message": "Finished the job aa-bb-cc-dd",   
        "data": [
            {
                "host": "192.168.1.14",
                "cost": "1.792",
                "message": {
                    "state": "started",
                    "changed": true
                },
                "success": true
            },
            {
                "host": "192.168.2.74",
                "cost": "2.701",
                "message": {
                    "state": "started",
                    "changed": true
                },
                "success": true
            }
        ],
        "success": true
    }
### API使用说明： ###
##### 虽然支持了多host，但是targets里面不能既有windows，又有linux，即以下targets接口是不支持的  



    "targets": [
        {
           "host": "192.168.1.14",        # Windows host
           "category": "Windows",
           "port": 5986,
           "pasd": "password",
           "user": "Administrator"
        },
        {
           "host": "192.168.2.74",        # Linux host
           "category": "Linux",
           "port": 22,
           "pasd": "password",
           "user": "root"
        }
    ]   

##### 请求多个windows targets，正确请求如下所示  


    {
        "queue": "aa-bb-cc-dd",
        "targets": [
            {
                "host": "192.168.1.14",
                "category": "Windows",
                "port": 5986,
                "pasd": "password",
                "user": "Administrator"
            },
            {
                "host": "192.168.2.74",
                "category": "Windows",
                "port": 5986,
                "pasd": "password",
                "user": "Administrator"
            }
        ], 
        "module": {
            "user": "win_msi", {        # 所有ansible支持的windows模块都是win_开头
                "path": "c:\\Windows6.1-KB2842230-x64.msu"
            }
        }
    }  

