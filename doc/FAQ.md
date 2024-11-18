
## 常见报错

### 响应报错
#### 问题1：you must install the sshpass program
```
{
	"data": [{
		"host": "192.168.91.100",
		"success": false,
		"task": "operate shell script by ansible script module",
		"user": "root",
		"port": 22,
		"id": 22144,
		"rawName": "BSM",
		"category": "Linux",
		"message": {
			"msg": "to use the ssh connectiontype with passwords,you must install the sshpass program "
		},
		"cost ": 0.0890505313873291
	}],
	"success ": false,
	"taskNodeId": 22,
	"message": "The sync job Finished"
}
```
#### 解决2： ansible提示安装sshpass这个软件包
```shell
yum -y install sshpass
```