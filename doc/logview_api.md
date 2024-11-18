## Log-view API设计##

### API名称 ###
**/logview**

### 请求方法 ###
**POST**

### 请求参数 ###

    {
        "target":"192.168.1.14",           # 这个要读文件的目标机器IP，必须提供
        "port": 9990,                      # 这个要读文件的目标机器端口，可选（互信认证不需要传)
        "pasd": "password",                # 这个要读文件的目标机器密码，可选（互信认证不需要传)
        "user": "root",                    # 这个要读文件的目标机器用户名，可选（互信认证不需要传)
        "filepath": "/var/log/messages",   # 要读日志的文件名，必须提供
        "position": 2048,                  # 从日志的那个位置去读，如果不提供或者为零，将从文件的尾部读取一定量的文件，大小取决于presize参数。
        "persize": 1024                    # 从日志读取内容的大小，默认值是1024
    }
### 返回结果 ###
    {
        "message": "55555\n666666\n7777777\n88888888\n999999999\n0000000000\n",  # 文件内容或是错误信息
        "filesize": 65,      # 读取了返回的文件内容后，文件最后的位置
        "success": true      # API是否执行成功
    }

### API使用说明： ###
- bocloud_worker端必须已经安装好ansible,且必须和目标机器已经做过互信，或者传入用户名密码参数。
- position如果不在一行的行首，它会向前移动40字节寻找行首，如果还是没有找到的话，它会从下一行的行首开始读取。
- 如读取presize大小的文件内容后，最后一行没有到达行尾，它会继续向下读取，直到读到行尾。
- 获取bocloud_worker的实时日志，传参target为worker的ip，filepath = ""，用户名密码可以不用传。
