#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os

from common.utils import logger
from common.db.sqlite_db import BaseSqliteDB

ASYNC_TASK_STATUS_NEW = 0
ASYNC_TASK_STATUS_RUNNING = 1
ASYNC_TASK_STATUS_COMPLETE = 2
TASK_RESULT_VALID = 1
TASK_RESULT_UNVALID = 0


class BocloudWorkerDB(BaseSqliteDB):
    """
    bocloud_worker database operation class
    """

    def __init__(self, worker_db, timeout=30, retry_time=3):
        try:
            logger.debug("The worker db is local at %s" % worker_db)
            BaseSqliteDB.__init__(self, worker_db, timeout, retry_time)
        except Exception as e:
            logger.error("BOCLOUD worker db init failed: %s" % str(e))
            raise

    @classmethod
    def create_bocloud_worker_schema(cls, db_file, init_sql):
        """if don't find bocloud worker database, create it.
        Args:
          - db_file: database file path
          - init_sql: sql script path for database initialization
        """
        # Create db directory if not existing
        path = os.path.dirname(db_file)
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError as ex:
                logger.error("create db directory failed: %s" % str(ex))
                raise
            else:
                logger.info("Created db directory: %s", path)

        if not os.path.exists(db_file):
            BaseSqliteDB.create_schema(db_file, init_sql)

    def insert_task_requests(self, request, commit=True):
        """insert request to task_requests table, if the task is async,
        also, we neet to insert task status at async_task_status
        Args:
        - request: flask request

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            insert_value = dict()
            insert_value["request_data"] = json.dumps(request.json)
            insert_value["request_host"] = str(request.remote_addr)
            insert_value["request_method"] = str(request.method)
            insert_value["request_head"] = str(request.headers)
            insert_value["request_path"] = str(request.path)
            if request.json and "queue" in request.json:
                insert_value["request_queue"] = request.json["queue"]

            request_id = self.insert('task_requests', insert_value, commit)

            # the request data exist queue field, it means the task is async.
            # update status at async_task_status table
            if request.json and "queue" in request.json:
                key_and_value = dict()
                key_and_value["request_id"] = request_id
                key_and_value["status"] = ASYNC_TASK_STATUS_NEW
                self.insert('async_task_status', key_and_value, commit=commit)
        except Exception as e:
            logger.error('insert flask request failed. %s' % e.args[0])
            raise

        return request_id

    def update_task_requests(self, id, key_and_value, commit=True):
        """update respons of request to task_requests table
        Args:
        - key_and_value: the field values for update

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            self.update('task_requests', key_and_value,
                        where_and={'id': id}, commit=commit)
        except Exception as e:
            logger.error('update respons of %d request to task_requests failed. %s' % (id, e.args[0]))
            raise

    def insert_async_task_result(self, queue, target, result, valid, commit=True):
        """insert task result to  async_task_status
        Args:
        - queue: task queue
        - target: the target ip for the result
        - result: task result
        - valid: for playbook, results that send to server just is vavid

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            key_and_value = dict()
            key_and_value["task_id"] = self.get_async_task_status(queue)["id"]
            key_and_value["result"] = result
            key_and_value["target"] = target
            key_and_value["valid"] = valid
            self.insert('async_task_result', key_and_value, commit=commit)
        except Exception as e:
            logger.error('Insert async task result failed. %s' % e.args[0])
            raise

    def get_request_id_by_queue(self, queue):
        """get request_id from task_requests by queue
        Args:
        - queue: task queue

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "task_requests"
            and_values = {'request_queue': queue}

            row = self.select(table, column_name=['id'], and_values=and_values)
        except Exception as e:
            logger.error("get request id from task_requests failure. %s" % e.args[0])
            raise

        return row[0]['id']

    def get_task_id_by_queue(self, queue):
        """get task_id from async_task_status by queue
        Args:
        - queue: task queue

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "task_requests, async_task_status"
            and_values = {'task_requests.request_queue': queue}
            association = dict()
            association["async_task_status.request_id"] = "task_requests.id"

            row = self.select(table, column_name=['async_task_status.id as id'], and_values=and_values)
        except Exception as e:
            logger.error("get task id from async_task_status failure. %s" % e.args[0])
            raise

        return row[0]['id']

    def update_async_task_status(self, queue, key_and_value, commit=True):
        """update task status when the status is changed
        Args:
        - queue: task queue

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            row = self.get_async_task_status(queue)
            if "status" not in key_and_value or \
                            row["status"] != key_and_value["status"]:
                self.update('async_task_status', key_and_value,
                            where_and={'request_id': row["request_id"]}, commit=commit)
        except Exception as e:
            logger.error('update async task status %s failed. %s' % (row["request_id"], e.args[0]))
            raise

    def get_async_task_status(self, queue):
        """get task status by task queue
        Args:
        - queue: task queue

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "task_requests, async_task_status"
            and_values = {'task_requests.request_queue': queue}
            association = dict()
            association["async_task_status.request_id"] = "task_requests.id"

            column = ['async_task_status.id as id',
                      'task_requests.id as request_id',
                      'async_task_status.status as status',
                      'async_task_status.total_count as total_count']
            row = self.select(table, column_name=column, and_values=and_values, association=association)
        except Exception as e:
            logger.error("Failed to get async task status. %s" % e.args[0])
            raise

        return row[0]

    def get_task_all_result(self, queue, valid=1, host=None):
        """get all completed task result by task queue
        Args:
        - queue: task queue
        - valid: wethere or not valid result.

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "task_requests, async_task_status, async_task_result"
            and_values = dict()
            and_values['task_requests.request_queue'] = queue
            and_values["async_task_result.valid"] = valid
            if host:
                and_values["async_task_result.target"] = host

            association = dict()
            association["async_task_status.request_id"] = "task_requests.id"
            association["async_task_result.task_id"] = "async_task_status.id"

            column = ['async_task_status.total_count as total_count',
                      'async_task_status.status as status',
                      'async_task_result.result as result',
                      'async_task_result.target as target']
            rows = self.select(table, column_name=column, and_values=and_values, association=association)
        except Exception as e:
            logger.error("get request id from task_requests failure. %s" % e.args[0])
            raise

        result = []
        for row in rows:
            result.append(json.loads(row['result']))

        # don't get real total_count, directly get it from async_task_status
        if len(rows) == 0:
            total_count = self.get_async_task_status(queue)["total_count"]
        else:
            total_count = rows[0]["total_count"]

        return total_count, result

    def get_new_tasks(self):
        """get all of un-running tasks
        Args:

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "async_task_status, task_requests"
            and_values = {'async_task_status.status': ASYNC_TASK_STATUS_NEW}
            association = dict()
            association["async_task_status.request_id"] = "task_requests.id"

            rows = self.select(table, column_name=['task_requests.request_data as request_data'],
                               and_values=and_values, association=association)
        except Exception as e:
            logger.error("get request id from task_requests failure. %s" % e.args[0])
            raise

        return rows

    def get_uncompleted_tasks(self):
        """get all of running tasks
        Args:

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "async_task_status, task_requests"
            and_values = {'async_task_status.status': ASYNC_TASK_STATUS_RUNNING}
            association = dict()
            association["async_task_status.request_id"] = "task_requests.id"

            column = ['task_requests.request_data as request_data',
                      'async_task_status.request_id as request_id']
            rows = self.select(table, column_name=column,
                               and_values=and_values, association=association)
        except Exception as e:
            logger.error("get request id from task_requests failure. %s" % e.args[0])
            raise

        return rows

    def cleanup_results(self, queue, host_list, commit=True):
        try:
            table = "async_task_result"
            and_values = dict()
            and_values['task_id'] = self.get_task_id_by_queue(queue)
            and_values['valid'] = TASK_RESULT_UNVALID
            or_values = dict()
            or_values['target'] = host_list

            # delete result that have compeleted
            self.delete(table, and_values=and_values, or_values=or_values, commit=commit)
        except Exception as e:
            logger.error("cleanup queue %s results failure. %s" % (queue, e.args[0]))
            raise

    def refresh_request_data_for_uncompleted_target(self, request_id, request_data):
        try:
            table = "async_task_result"
            and_values = {'id': request_id, 'valid': 0}
            # delete unvalid result
            self.delete(table, and_values=and_values)

            # selete all valid task result
            and_values["valid"] = 1
            rows = self.select(table, column_name=['target'], and_values=and_values)
        except Exception as e:
            logger.error("get request id from task_requests failure. %s" % e.args[0])
            raise

        # filter target list that tasks aren't uncompleted
        completed_host_list = [row['target'] for row in rows]
        targets = request_data["targets"]
        new_targets = list()
        for target in targets:
            if target['host'] not in completed_host_list:
                new_targets.append(target)

        request_data["targets"] = new_targets

    def set_task_as_finished(self, queue, commit=True):
        """insert or update async task status
        Args:
        - queue: task queue

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            request_id = self.get_request_id_by_queue(queue)
            self.update('async_task_status', {"status": ASYNC_TASK_STATUS_COMPLETE},
                        where_and={'request_id': request_id}, commit=commit)
        except Exception as e:
            logger.error('update async task status %s failed. %s' % (request_id, e.args[0]))
            raise

    def check_queue_exist(self, queue):
        """make sure all request queue is different
        Args:
        - queue: task queue

        Exceptions:
        - sqlite3.Error: raised if any error happens when executing SQL statements
        """
        try:
            table = "task_requests"
            and_values = {'request_queue': queue}

            row = self.select(table, column_name=['id'], and_values=and_values)
        except Exception as e:
            logger.error("check_queue_exist failure. %s" % e.args[0])
            raise

        return False if len(row) <= 1 else True
