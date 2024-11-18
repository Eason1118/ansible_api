#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2017/8/14 17:16
# @Author  : LKX
# @Site    : www.bocloud.com.cn
# @File    : zookeeper_handler.py
# @Software: BoCloud

import json
import logging
import random
import traceback
from os.path import basename, join

from kazoo.client import KazooClient
from kazoo.protocol.states import KazooState

from common.aes_encrptor import AESEncrptor
from common.base_http_handler import BasicHttpClient
from common.utils import logger, get_ip_port, ZOOKEEPER_CONFIG

logging.getLogger("kazoo.client").addHandler(logger)
logging.getLogger("kazoo.handlers.threading").addHandler(logger)
logging.getLogger("kazoo.recipe.watchers").addHandler(logger)


class ZkHandler(object):
    LEADERSHIP_PATH = join("/bocloud", "leadership", "worker")
    SERVICE_PATH = join("/bocloud", "services", "worker")
    MASTER_NUM = 1
    TIMEOUT = 10000

    def __init__(self, hosts, verbose=True):
        self.ZK_HOST = hosts
        self.VERBOSE = verbose
        self.master = None
        self.is_master = False
        self.path = None
        self.info = get_ip_port()
        self.zk = None
        self._init_zk()
        self.workers = []

    def listener(self, state):
        """
        this listener check connection state and reconnect to zk
        :param state:
        :return:
        """
        if state == KazooState.CONNECTED:
            # Handle being connected/reconnected to Zookeeper
            try:
                # clean old transition
                if self.zk:
                    self.zk._reset()
                self._init_zk()
                self.register()
                self.workers = self.get_workers()
                logger.info("reconnect to zookeeper successfully")
            except:
                logger.error(traceback.format_exc())
                self.zk = None
        else:
            if self.VERBOSE:
                logger.debug("listener state %s" % state)

    def _init_zk(self):
        """
        start zk instance
        create the zookeeper node if not exist
        |-bocloud
            |-leadership
                |-worker
        """
        try:
            # clean old transition
            if self.zk:
                self.zk._reset()
            auth_info = ZOOKEEPER_CONFIG['user'] + ':' + ZOOKEEPER_CONFIG['password']
            self.zk = KazooClient(self.ZK_HOST, timeout=self.TIMEOUT, auth_data=[("digest", auth_info)])
            self.zk.start()
            self.zk.add_listener(listener=self.listener)
            self.zk.ensure_path(self.LEADERSHIP_PATH)
            self.zk.ensure_path(self.SERVICE_PATH)
        except Exception as e:
            logger.error('Fail to connect to zk hosts %s, exception %s' %
                         (self.ZK_HOST, e))
            self.zk = None
            raise e

    @property
    def is_slave(self):
        return not self.is_master

    def register(self):
        logger.debug("register start")
        """
        register a node for this worker,znode type : EPHEMERAL | SEQUENCE
        |-bocloud
            |-leadership
                |-worker
                    |-worker000000000x         ==>>master
                    |-worker000000000x+1       ==>>worker
                    ....
        register a node for this worker,znode type : EPHEMERAL
        |-bocloud
            |-services
                |-worker
                    |-192.168.1.100:8888
                    |-192.168.1.200:8888
                    ....
        """
        try:
            self.zk.ensure_path(self.LEADERSHIP_PATH)
            self.zk.ensure_path(self.SERVICE_PATH)
            self.workers = self.get_workers()

            self.register_leadership()
            self.register_service()

            # add poller for worker path
            logger.debug("register call poller start")
            self.poller()
            logger.debug("register call poller end")

            # check who is the master
            logger.debug("register call get_master start")
            self.get_master()
            logger.debug("register call get_master end")
        except:
            logger.error("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", traceback.format_exc()))
        finally:
            logger.debug("register end")

    def register_leadership(self):
        # register leadership
        if self.path and self.zk.exists(self.LEADERSHIP_PATH + "/" + self.path):
            data, stat = self.zk.get(self.LEADERSHIP_PATH + "/" + self.path)
            if not data == self.info:
                self.path = self.zk.create(self.LEADERSHIP_PATH + "/worker", self.info, ephemeral=True, sequence=True)
                self.path = basename(self.path)
                logger.info(
                    "[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", "register leadership ok!"))
        else:
            self.path = self.zk.create(self.LEADERSHIP_PATH + "/worker", self.info, ephemeral=True, sequence=True)
            self.path = basename(self.path)
            logger.info(
                "[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", "register leadership ok!"))

    def register_service(self):
        # register services
        services_path = join("bocloud", "services", "worker", str(self.info))
        if not self.zk.exists(services_path):
            self.zk.create(services_path, value="", ephemeral=True, sequence=False)
            logger.info("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", "register services ok!"))

    def get_workers(self, leader=False):
        """
        get online workers
        :return:
        """
        workers = []
        leaderships = self.zk.get_children(self.LEADERSHIP_PATH)
        for leadership in leaderships:
            data, stat = self.zk.get(self.LEADERSHIP_PATH + "/" + leadership)
            if leader:
                if self.zk.exists(self.SERVICE_PATH + "/" + data):
                    workers.append(data)
                    logger.debug("[ %s(%s) ] online" % (leadership, data))
            else:
                workers.append(data)
        return workers

    def poller(self):
        """
        monitor worker path,if deleted, register
        :return:
        """

        def watcher(watched_event):
            if watched_event.type and watched_event.path:
                msg = "child changed, try to get master again. type %s, state %s, path %s." % (
                    watched_event.type, watched_event.state, watched_event.path)
                logger.info("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", msg))
                self.workers = self.get_workers()
                logger.debug("poller call register start")
                self.register_service()
                self.register_leadership()
                logger.debug("poller call register end")

        try:
            children = self.zk.get_children(self.SERVICE_PATH, watcher)
        except:
            logger.error(traceback.format_exc())
            return
        logger.debug("current worker services are %s" % children)

    def get_master(self):
        """
        get children, and check who is the smallest child
        """

        def watcher(watched_event):
            if watched_event.type and watched_event.path:
                msg = "child changed, try to get master again.type %s, state %s, path %s." % (
                    watched_event.type, watched_event.state, watched_event.path)
                logger.info("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", msg))
                self.workers = self.get_workers()
                logger.debug("watcher call get_master start")
                self.get_master()
                logger.debug("watcher call get_master end")

        try:
            children = self.zk.get_children(self.LEADERSHIP_PATH, watcher)
        except:
            logger.error(traceback.format_exc())
            return

        # self register
        infos = []
        for child in children:
            data, stat = self.zk.get(self.LEADERSHIP_PATH + "/" + child)
            infos.append(data)

        # make sure leadship and services exists
        if self.info not in infos or \
                not self.zk.exists(self.SERVICE_PATH + "/" + self.info):
            logger.debug("get_master call register start")
            self.register_leadership()
            self.register_service()
            logger.debug("get_master call register end")

        children.sort()
        logger.debug("%s's children: %s" % (self.LEADERSHIP_PATH, children))
        # check if I'm master
        self.master = children[:self.MASTER_NUM]
        if self.path in self.master:
            self.is_master = True
            logger.info("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", "I am master!"))
            # get slave status and assign undone task to them
            online_workers = self.get_workers()
            self.assign_task(online_workers)
            self.workers = online_workers

    def assign_task(self, online_workers):
        """
        assign unfinished task to online workers
        :param online_workers:
        :return:
        """
        msg = "online_workers are %s, workers are %s" % (online_workers, self.workers)
        logger.debug("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", msg))
        if not self.workers == online_workers:
            # check if has down worker
            for worker in self.workers:
                if worker not in online_workers:
                    # this worker is down
                    logger.info("[ %s(%s) ] %s is down." % (self.path, "master" if self.is_master else "slave", worker))
                    # assign online worker to to down worker unfinished task
                    assign_worker = random.choice(online_workers)
                    logger.info("[ %s(%s) ] assign %s to do %s's unfinished task" % (
                        self.path, "master" if self.is_master else "slave", assign_worker, worker))
                    if assign_worker == self.info:
                        # call self function
                        logger.info("[ %s(%s) ] %s" % (
                            self.path, "master" if self.is_master else "slave", "start to recovery task by myself"))
                        from bocloud_worker import recovery_exec
                        recovery_exec(worker.split(":")[0], int(worker.split(":")[1]))
                        logger.info("[ %s(%s) ] %s" % (
                            self.path, "master" if self.is_master else "slave", "recovery task by myself end"))
                    else:
                        # sent http to this online_worker
                        client = BasicHttpClient()
                        result = client.post(host=assign_worker, path='/job/recovery',
                                             headers={"Content-Type": "application/json"},
                                             data=json.dumps(
                                                 {
                                                     "host": worker.split(":")[0],
                                                     "port": int(worker.split(":")[1])
                                                 }
                                             ))
                        logger.info("[ %s(%s) ] %s" % (self.path, "master" if self.is_master else "slave", result))

    def unregister(self):
        """
        unregister worker info
        :return:
        """
        try:
            logger.info("unregister worker info")
            self.zk.delete(self.SERVICE_PATH + "/" + self.info)
            leaderships = self.zk.get_children(self.LEADERSHIP_PATH)
            for leadership in leaderships:
                data, stat = self.zk.get(self.LEADERSHIP_PATH + "/" + leadership)
                if data == self.info:
                    self.zk.delete(self.LEADERSHIP_PATH + "/" + leadership)
        except:
            pass

    def terminate(self):
        """
        terminate and unregister in zk
        :return:
        """
        self.unregister()
        self.zk.stop()
        self.zk.close()
