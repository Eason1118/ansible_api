# !/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2019/1/11 19:16
# @Author  : LKX
# @Site    : www.bocloud.com.cn
# @File    : aes_encrptor.py
# @Software: BoCloud


# coding:utf-8
import base64
from Crypto.Cipher import AES


class AESEncrptor():
    def __init__(self):
        self.key = "BocloudCMPV587!!"

    def encrypt(self, data):
        try:
            while len(data) % 16 != 0:  # 补足字符串长度为16的倍数
                data += (16 - len(data) % 16) * chr(16 - len(data) % 16)
            data = str.encode(data)
            aes = AES.new(str.encode(self.key), AES.MODE_ECB)  # 初始化加密器
            return str(base64.encodebytes(aes.encrypt(data)), encoding='utf8').replace('\n', '')  # 加密
        except Exception as e:
            raise Exception("encrypt string {} failed: {}".format(data, e))

    def decrypt(self, data):
        try:
            aes = AES.new(str.encode(self.key), AES.MODE_ECB)  # 初始化加密器
            decrypted_text = aes.decrypt(base64.decodebytes(bytes(data, encoding='utf8'))).decode("utf8")  # 解密
            decrypted_text = decrypted_text[:-ord(decrypted_text[-1])]  # 去除多余补位
        except Exception as e:
            raise Exception("decrypt string {} failed: {}".format(data, e))
        return decrypted_text


