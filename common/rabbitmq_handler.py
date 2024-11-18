#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import random
import traceback
import ssl
import pika

from common.utils import RABBITMQ_CONFIG, BOCLOUD_WORKER_CONFIG
from common.utils import logger


class RabbitmqHandler(object):
    '''
    The class handle submit and custom rabbitmq messages
    '''

    def __init__(self, exchange, message_type,
                 timeout=None, durable=False, passive=False, auto_delete=False):
        self.message_type = message_type
        self.exchange = exchange
        self.connection = None
        self.channel = None
        self.timeout = timeout if timeout else BOCLOUD_WORKER_CONFIG['job_timeout']
        self.durable = durable
        self.passive = passive
        self.auto_delete = auto_delete
        self.init_connection_channel()

    def init_connection_channel(self):
        try:
            random.shuffle(RABBITMQ_CONFIG)
            for mq_config in RABBITMQ_CONFIG:
                try:
                    logger.info("start to init rabbitmq connection channel by %s", mq_config['host'])
                    credentials = pika.PlainCredentials(mq_config['user'], mq_config['password'])
                    # 获取ssl证书, 没有则返回None
                    ssl_options = self.get_ssl_options(host=mq_config['host'], client_cert=mq_config['client_cert'],
                                                       client_key=mq_config['client_key'])
                    parameters = pika.ConnectionParameters(mq_config['host'], mq_config['port'],
                                                           mq_config['vhost'], credentials, ssl_options=ssl_options,
                                                           socket_timeout=100)
                    logger.info("start SSL authentication connection %s", mq_config['host'])

                    self.connection = pika.BlockingConnection(parameters)
                    logger.info("rabbitmq connection channel connected with %s.", mq_config['host'])
                except:
                    pass
                else:
                    break
            if self.connection is None:
                raise Exception("Failed to connect to rabbitmq cluster %s", RABBITMQ_CONFIG)
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange=self.exchange,
                                          exchange_type=self.message_type,
                                          passive=self.passive,
                                          durable=self.durable,
                                          auto_delete=self.auto_delete,
                                          arguments={"x-ha-policy": "all"})
        except Exception as e:
            logger.error(traceback.format_exc())
            raise Exception("init rabbitmq connection channel exception %s", e)

    def send_message(self, routing_key, message):
        body = message
        if isinstance(message, dict):
            body = json.dumps(message, sort_keys=True)

        try:
            self.channel.basic_publish(exchange=self.exchange,
                                       routing_key=routing_key,
                                       body=body)
        except:
            logger.error(traceback.format_exc())
            raise Exception("Failed to send message %s to rabbitmq %s" %
                            (message, routing_key))

    def custom_message(self, routing_key, callback, cond=None, timeout=None):
        try:
            result = self.channel.queue_declare(exclusive=True)
            queue_name = result.method.queue

            self.channel.queue_bind(exchange=self.exchange,
                                    queue=queue_name,
                                    routing_key=routing_key)

            self.channel.basic_consume(callback,
                                       queue=queue_name,
                                       no_ack=True)

            if not timeout:
                timeout = BOCLOUD_WORKER_CONFIG['job_timeout']

            def on_timeout():
                logger.info('custom rabbitmq message timeout with timeout value %s' % timeout)
                self.clearup()

            self.connection.add_timeout(timeout, on_timeout)

            # Notify operator handler thread to start work after
            # cutome message is ready
            if cond and cond.acquire():
                logger.info("custom message %s is ready, Notify operate handler thread to work."
                            % routing_key)
                cond.notify()
                cond.release()
            self.channel.start_consuming()
        except:
            logger.error(traceback.format_exc())
            raise Exception("Failed to custom rabbitmq message %s" %
                            routing_key)

    def clearup(self):
        try:
            if not self.channel.is_closed:
                self.channel.close()
            if not self.connection.is_closed:
                self.connection.close()
        except:
            raise Exception("Failed to close rabbitmq message")

    def get_ssl_options(self, host, client_cert, client_key):
        try:
            # 忽略证书信任
            context = ssl._create_unverified_context()
            context.load_cert_chain(client_cert, client_key)
            return pika.SSLOptions(context, host)
        except Exception as e:
            logger.error(" get ssl options fail: %s, client_cert: %s  client_key:%s" % (str(e), client_cert, client_key))
            return None


def check_result(result):
    for msg in result:
        # skipped task is also ok.
        try:
            if msg["message"]["skipped"]:
                continue
        except:
            pass
        if "success" in msg and msg["success"] is False:
            return False

    return True


def intergrate_send_result_to_rabbitmq(queue, results, node_id=None):
    exchange = BOCLOUD_WORKER_CONFIG['external_mq']['exchange']
    mq_type = BOCLOUD_WORKER_CONFIG['external_mq']['type']
    success = check_result(results)
    message = {"success": success,
               "message": "Finished the job %s" % queue,
               "taskNodeId": node_id,
               "data": results}
    rabbitmq_handler = RabbitmqHandler(exchange, mq_type,
                                       durable=True, auto_delete=True)
    logger.info("The collective messages of %s are %s" %
                (queue, json.dumps(message)))
    rabbitmq_handler.send_message(queue, message)
    rabbitmq_handler.clearup()


def send_message_to_rabbitmq(rabbitmq, queue, msg, node_id):
    if rabbitmq is None:
        if node_id:
            msg.update({"taskNodeId": node_id})
        exchange = BOCLOUD_WORKER_CONFIG['external_mq']['exchange']
        mq_type = BOCLOUD_WORKER_CONFIG['external_mq']['type']
        logger.debug("The job %s is running, The response message is %s" %
                     (queue, msg))
        rabbitmq = RabbitmqHandler(exchange, mq_type,
                                   durable=True, auto_delete=True)
    rabbitmq.send_message(queue, msg)
