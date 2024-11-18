## Worker参数
```
{
    "queue": "aaaa",
    "target": [
        {
            "host": "10.20.2.21",
            "port": 22,
            "user": "root",
            "pasd": "password",
            "type": "linux|windows|unix|switch|router"
        },
        {
            "host": "10.20.2.22",
            "port": 22,
            "user": "root",
            "pasd": "password",
            "type": "linux|windows|unix|switch|router"
        }
    ],
    "group": [
        {
            "name": "mongo_master",
            "hosts": [
                {
                    "host": "10.20.2.21",
                    "vars": {
                        "mongodb_master": true,
                        "mongodb_replication_params": [
                            {
                                "host_name": "192.168.2.97"
                            }
                        ]
                    }
                },
                {
                    "host": "10.20.2.22",
                    "vars": {
                        "mongodb_replication_params": [
                            {
                                "host_name": "192.168.2.96",
                                "host_type": "replica "
                            }
                        ]
                    }
                }
            ],
            "vars": {
                "mongodb_master": true
            }
        },
        {
            "name": "mongo_replicas",
            "host": [],
            "vars": {
                "horeplication_replset": "repli_test"
            }
        }
    ],
    "module": {
        "name": "install_mongodb",
        "options": {
            "become": true,
            "sudo": true,
            "becomeUser": "root",
            "becomePasd": "password"
        },
        "args": {
            "version": "3.6",
            "software_config": {
                "mongodb_net_bindip": "0.0.0.0",
                "mongodb_net_maxconns": 65536,
                "mongodb_net_port": 27017,
                "mongodb_security_authorization": "disabled",
                "mongodb_storage_dbpath": "/data/db",
                "mongodb_storage_engine": "wiredTiger",
                "mongodb_storage_journal_enabled": true,
                "mongodb_storage_prealloc": true,
                "mongodb_login_host": "192.168.2.97",
                "mongodb_replication_replindexprefetch": "all",
                "mongodb_replication_replset": "repltest",
                "mongodb_user_admin_name": "siteUserAdmin",
                "mongodb_user_admin_password": "passw0rd",
                "mongodb_root_admin_name": "siteRootAdmin",
                "mongodb_root_admin_password": "passw0rd",
                "mongodb_root_backup_name": "backupuser",
                "mongodb_root_backup_password": "passw0rd",
                "mongodb_users": [
                    {
                        "database": "admin",
                        "roles": "readWrite",
                        "name": "testUser",
                        "password": "passw0rd"
                    }
                ]
            }
        }
    },
    "script": {
        "type": "perl|shell|python|bat|powershell|playbook",
        "content": "import platform;print platform.system()",
        "params": "a a a a",
        "options": {
            "sudo": "true",
            "become": "true",
            "becomeUser": "mysql",
            "becomePass": "12"
        }
    },
    "timeout": 1000
}
```