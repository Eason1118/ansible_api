#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import os
import random
import time

from kazoo.client import KazooClient
from kazoo.exceptions import NodeExistsError, NoAuthError
from kazoo.protocol.states import KazooState
from kazoo.recipe.watchers import ChildrenWatch

from common.aes_encrptor import AESEncrptor
from common.utils import get_ip_port, logger, ZOOKEEPER_CONFIG
from zookeeper_handler.zk_thread import ZkThread


class NodeRegister:
    def __init__(self, zk_server):
        self.zk_server = zk_server
        self.auth_info = ZOOKEEPER_CONFIG['user'] + ':' + ZOOKEEPER_CONFIG['password']
        self.zk = KazooClient(hosts=zk_server, auth_data=[("digest", self.auth_info)])
        self.info = get_ip_port()
        self.zk_node = None
        self.node_path = os.path.join('bocloud', 'services', 'worker')
        self.children_watch = ChildrenWatch(client=self.zk, path=self.node_path, func=self.watcher)
        self.zk.add_listener(self.conn_state_watcher)
        self.zk.start()
        self.workers = []
        self.is_master = False
        self.running = True
        self.register()

    def __del__(self):
        self.zk.close()

    def watcher(self, children):
        if hasattr(self, 'info') and self.info not in children:
            self.register()
            return

        if hasattr(self, 'is_master') and self.is_master:
            for worker in self.workers:
                if worker not in children:
                    # this worker is down
                    # assign online worker to to down worker unfinished task
                    assign_worker = random.choice(children)
                    logger.info('{} is down,assign {} to do its unfinished tasks'.format(worker, assign_worker))
                    if assign_worker == self.info:
                        # call self function
                        from bocloud_worker import recovery_exec
                        recovery_exec(worker.split(":")[0], int(worker.split(":")[1]))
                        logger.info("recovery task by myself end")
                    else:
                        # sent http to this online_worker
                        from common.base_http_handler import BasicHttpClient
                        client = BasicHttpClient()
                        result = client.post(host=assign_worker, path='/job/recovery',
                                             headers={"Content-Type": "application/json"},
                                             data=json.dumps(
                                                 {
                                                     "host": worker.split(":")[0],
                                                     "port": int(worker.split(":")[1])
                                                 }
                                             ))
                        logger.info("recovery task by {} end,result {}".format(assign_worker, result))

        # refresh online workers
        self.workers = children

    def register(self):
        # register services path
        try:
            self.zk_node = self.zk.create(self.node_path + "/" + self.info, ephemeral=True,
                                          sequence=False,
                                          makepath=True)
        except NodeExistsError as s:
            pass
        except NoAuthError as e:
            error = "connect to zookeeper {} failed, authentication {} failure".format(self.zk_server, self.auth_info)
            logger.info(error)
            self.running = False
            raise Exception(error)

    def service(self):
        # zk register
        self.register()
        # zk election
        election = self.zk.Election(os.path.join('bocloud', 'leadership', 'worker'), self.info)
        election.run(self.poller)

    def close(self):
        self.zk.stop()
        self.zk.close()
        self.running = False

    def conn_state_watcher(self, state):
        if state == KazooState.CONNECTED:
            logger.info("{} connect to zk server {}".format(self.info, self.zk_server))
            if self.zk_node is None:
                logger.warn("must call register method first")
                return
            info_keeper = ZkThread(self)
            info_keeper.start()
        else:
            logger.debug("listener state %s" % state)

    def poller(self):
        """
        this poller is for zk election
        :return:
        """
        self.is_master = True
        while True:
            if self.running:
                # logger.debug("{} is master".format(self.info))
                time.sleep(5)
            else:
                break
