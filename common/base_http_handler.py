#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2017/8/15 9:42
# @Author  : LKX
# @Site    : www.bocloud.com.cn
# @File    : base_http_handler.py
# @Software: BoCloud

import json
import time
import urlparse
from urlparse import urljoin

import requests
from requests.exceptions import ReadTimeout

from common.utils import logger

REQUEST_TIMEOUT_SECS = 60
STATUS_CODE_OK = 200


class RequestsWrapper(object):
    """
    Wrapper for Requests
    """

    def request(self, *args, **kwargs):
        response_encoding = kwargs.pop('response_encoding', None)
        timeout = kwargs.get('timeout') or REQUEST_TIMEOUT_SECS
        kwargs.update(timeout=timeout, verify=False)
        resp = requests.request(*args, **kwargs)
        if response_encoding:
            resp.encoding = response_encoding
        return {'text': resp.text,
                'status_code': resp.status_code,
                'headers': resp.headers,
                'reason': resp.reason}


def get_current_http_wrapper():
    return RequestsWrapper()


def encode_dict(d, encoding='utf-8'):
    """
    使用指定的编码来编码给定的字典，否则使用urlencode方法的时候会报编码错误

    :param dict d: 需要转换编码的字典对象
    :param str encoding: 需要转换的目标编码
    """
    result = {}
    for k, v in d.items():
        if isinstance(v, unicode):
            result[k] = v.encode(encoding)
        else:
            result[k] = v

    return result


class BasicHttpClient(object):
    """
    A very basic HTTP Client
    """

    @property
    def smart_http_client(self):
        return get_current_http_wrapper()

    def request(self, *args, **kwargs):
        """
        直接使用 _request 方法来发送请求
        """
        return self._request(*args, **kwargs)

    def request_by_url(self, method, url, *args, **kwargs):
        """
        使用一个完整的 url 来替代 host 和 path 参数
        """
        parsed_url = urlparse.urlparse(url)
        host = '%s://%s' % (parsed_url.scheme, parsed_url.netloc)
        return self.request(method, host, parsed_url.path, *args, **kwargs)

    def _request(self, method, host, path, params=None, data=None, headers={}, response_type='json', max_retries=0,
                 response_encoding=None, request_encoding=None, use_test_env=False, verify=False, cert=None,
                 timeout=None):
        """
        Send a request to given destination

        :param str method: One of "GET/POST/HEAD/DELETE"
        :param str host: host, such as "http://www.qq.com/"
        :param str path: request path, like "/account/login/"
        :param str/dict params: params in query string
        :param str/dict data: data to send in POST request
        :param str response_type: type of response, can be one of "json"
        :param int max_retries: 最多可以重试的次数，默认为0，不重试
        :param str response_encoding: 结果内容的编码，默认自动猜测
        :param str request_encoding: 请求参数编码
        :param str/bool verify: 是否校验crt
        :param string/tuple: 传递客户端crt和key
        :param int timtout: 超时时间
        :returns: response
        """
        url = self.make_url(host, path)
        request_exception = None
        resp, resp_status_code, resp_text = (None, -1, '')
        params_to_send, data_to_send = params, data
        if request_encoding:
            if isinstance(params, dict):
                params_to_send = encode_dict(params, encoding=request_encoding)
            if isinstance(data, dict):
                data_to_send = encode_dict(data, encoding=request_encoding)
        try:
            client = self.smart_http_client
            logger.debug('Starting request to url=%s, params=%s, data=%s', url, params, data)
            resp = client.request(method, url, params=params_to_send, data=data_to_send, headers=headers,
                                  response_encoding=response_encoding, verify=verify, cert=cert, timeout=timeout)
            resp_text = resp['text']
            resp_status_code = resp['status_code']
            # to avoid format json CaseInsensitiveDict error
            # modify resp headers type to dict
            resp['headers'] = dict(resp['headers'])
            logger.debug('Response from url=%s, params=%s, data=%s, response=%s', url, params, data, resp_text)
            if resp_status_code != STATUS_CODE_OK:
                raise Exception('状态码: %s' % (resp_status_code))
            result = self.format_resp(resp_text, response_type=response_type)
        except Exception as e:
            logger.exception('Error occured when sending request to %s', url)
            if isinstance(e, ReadTimeout):
                request_exception = ReadTimeout('第三方系统接口响应时间超过%s秒' % (timeout or REQUEST_TIMEOUT_SECS))
            else:
                request_exception = e
            result = None
            if max_retries > 0:
                seconds_wait = 1
                max_retries -= 1
                logger.info('Will Retry request after %s seconds, remaining retries = %s', seconds_wait, max_retries)
                time.sleep(seconds_wait)
                return self._request(method, host, path, params, data, headers, response_type, max_retries,
                                     response_encoding, request_encoding, use_test_env)

        return dict(url=url, resp=resp, resp_status_code=resp_status_code, resp_text=resp_text, result=result,
                    request_exception=request_exception)

    def get(self, *args, **kwargs):
        return self.request('GET', *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.request('POST', *args, **kwargs)

    def head(self, *args, **kwargs):
        return self.request('GET', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.request('POST', *args, **kwargs)

    @staticmethod
    def make_url(host, path):
        if not host.startswith('http'):
            host = 'http://%s' % host
        return urljoin(host, path)

    @staticmethod
    def format_resp(resp_text, encoding='utf-8', response_type='json'):
        """
        Format the given response
        """
        if response_type == 'json':
            resp = json.loads(resp_text)
        else:
            resp = resp_text
        return resp
