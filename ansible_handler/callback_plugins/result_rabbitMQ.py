#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import sqlite3
import time
import traceback

from ansible import constants as C
from ansible.plugins.callback import CallbackBase

try:
    from __main__ import display as global_display
except ImportError:
    from ansible.utils.display import Display

    global_display = Display()
from common.utils import logger, BOCLOUD_WORKER_CONFIG

from common.db.bocloud_worker_db import BocloudWorkerDB
from common.rabbitmq_handler import intergrate_send_result_to_rabbitmq
from common.rabbitmq_handler import send_message_to_rabbitmq
from common.utils import intergrate_messages_by_host
from common.utils import BOCLOUD_WORKER_SQLITEDB


class CallbackModule(CallbackBase):
    """
    This Ansible callback plugin send running result to sqlite3 DB.
    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'result_sqlite3'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, task, result=None, result_signal=None,
                 worker_db=BOCLOUD_WORKER_SQLITEDB, playbook_script=False):
        self._play = None
        self._last_task_banner = None
        super(CallbackModule, self).__init__(display=global_display)
        self.result_signal = result_signal
        self.task = task
        self.node_id = task.node_id
        self.ansible_result = result
        self.ansible_result["data"] = list()
        self.task_modules = [task.module]
        self.errors = 0
        self.time_stamp = time.time()
        self.task_name = None
        self.worker_db = worker_db
        self.playbook_script = playbook_script
        self.playbook_result = dict()
        self.failed_msg = ""
        # the rabbitmq instance just send playbook result
        self.rabbitmq = None

    def filter_result(self, message, result):
        logger.debug("************** Original Ansilbe result **************")
        logger.info(result)
        my_result = {}

        valid_fields = ["msg", "stderr", "stdout", "checksum", "md5sum", "content", "curr_position", "rc", "warnings",
                        "end", "start", "dest", "src", "powerstate", "state", "ansible_facts", "skipped", "results",
                        "module_stdout", "bocloud_script_msg", "bocloud_backup_msg", "bocloud_worker_msg"]
        must_fields = ["changed"]
        for field in valid_fields:
            # if result include the field and the value in the
            # field is valid. Output the field to our result.
            if field in result and result[field]:
                my_result[field] = result[field]

        for field in must_fields:
            # if result include the field, output the field to our result.
            if field in result:
                my_result[field] = result[field]

        message['message'] = self.modify_result(my_result)
        # 这个的cost是从callback开始到该task执行结束的时间
        # 多个task时最后一个task的cost就是真实的执行时间
        message['cost'] = time.time() - self.time_stamp
        return message

    def modify_result(self, result):
        # delete nfs path for windows bocloud_backup module
        # windows backup module is written by powershell and is hard to  be modifie
        try:
            if 'bocloud_backup_msg' in result:
                result = result['bocloud_backup_msg']
                dest = result['dest']
                nfs_path = BOCLOUD_WORKER_CONFIG['nfs_path']
                # new dest path that remove nfs path
                if nfs_path and dest.startswith(nfs_path):
                    size = len(nfs_path)
                    dest = dest[size:]
                result['dest'] = dest
        except:
            pass

        try:
            if 'bocloud_script_msg' in result:
                result = result['bocloud_script_msg']
        except:
            pass

        return result

    def modify_msg(self, msg, result):
        """
        append name,user,port to send back
        :param msg:
        :param result:
        :return:
        """
        try:
            # result._host.name is group alias
            # match host info with request target
            if self.task.groups:
                for group in self.task.groups:
                    for group_host in group['hosts']:
                        if 'vars' in group_host and 'alias' in group_host['vars'] \
                                and group_host['vars']['alias'] == result._host.name:
                            for host in self.task.hosts:
                                if host.get('host', None) and group_host.get('host', None) \
                                        and host.get('host', None) == group_host.get('host', None):
                                    # modify host alias to ip addr
                                    if host.get('host', None):
                                        msg['host'] = host['host']
                                    self.merge(host, msg)
                                    break

            # result._host.name is ip address
            # match host info with request target
            for host in self.task.hosts:
                if host["host"] == result._host.name:
                    # 'host' is already in msg object, here host is ip address
                    self.merge(host, msg)
                    break
        except Exception as e:
            logger.warning(traceback.format_exc())
            logger.warning("Exception that get host from result: %s" % str(e))
            pass

        return msg

    def merge(self, host, msg):
        """
        merge cache host info to task result
        :param host:
        :param msg:
        :return:
        """
        if host.get('name', None):
            msg['name'] = host['name']
        if host.get('user', None):
            msg['user'] = host['user']
        if host.get('port', None):
            msg['port'] = host['port']
        if host.get('id', None):
            msg['id'] = host['id']
        if host.get('rawName', None):
            msg['rawName'] = host['rawName']
        if host.get('category', None):
            msg['category'] = host['category']

    def insert_message_to_sqlite(self, message, result):
        # if we don't need to sync the task result, we just send ansible result to sqlite3
        # otherwise, just insert the result to a variable that share with
        # thread of the ansible task
        message = self.filter_result(message, result)
        logger.info('message after filter is %s' % message)
        if self.result_signal is None and BOCLOUD_WORKER_CONFIG["is_not_db"] is False:
            # insert result to sqlite3 async_task_result table
            try:
                db = BocloudWorkerDB(self.worker_db)
                valid = 0 if self.task.playbooks else 1
                db.insert_async_task_result(self.task.queue, message['host'],
                                            json.dumps(message), valid)
                # check whether is the finally result
                # if so, send total result to rabbitmq, except playbook
                total_count, results = db.get_task_all_result(self.task.queue)
                if not self.task.playbooks and total_count == len(results):
                    intergrate_send_result_to_rabbitmq(self.task.queue,
                                                       intergrate_messages_by_host(results, self.playbook_script),
                                                       self.node_id)
                    db.set_task_as_finished(self.task.queue)
            except sqlite3.Error as e:
                logger.error("Failed to update task status with sqlite3 exception: %s" % str(e))
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("Failed to update task status with unknown exception: %s" % str(e))
            finally:
                db.close()
        else:
            if message not in self.ansible_result["data"]:
                self.ansible_result["data"].append(message)

    def send_playbook_result(self, msg):
        # send playbook step result to rabbitmq queue
        if msg and len(msg) > 0:
            # print(msg)
            send_message_to_rabbitmq(self.rabbitmq, self.task.queue, msg, self.node_id)

    def v2_runner_on_ok(self, result):
        if "Gathering Facts" != result._task.get_name():
            logger.debug("v2_runner_on_ok called by ansible, "
                         "host=%s, task=%s, result=%s" % (result._host,
                                                          result._task.get_name(),
                                                          self._dump_results(result._result)))
        else:
            logger.debug("just to gathering Facts, is ok")

        try:
            # ansible 2.3 check if setup
            try:
                if result._result['ansible_facts']['module_setup']:
                    logger.info("this is ansible 2.3 setup facts")
                    return
            except:
                pass
            # ansible 2.1 check if setup
            if self.task_name == 'setup' and 'setup' not in self.task_modules:
                logger.info("this is ansible setup facts, nothing to do.")
                return
            # if task execute ok,only the task called by bocloud needs to send msg to sqlite3
            host = result._host.get_name()
            # msg = {"host": host, "success": True, "task": self.task}
            msg = {"host": host, "success": True, "task": self.task.module}
            if self.task_name.startswith('ipmi'):
                msg['host'] = result._result['invocation']['module_args']['name']
            msg = self.modify_msg(msg, result)
            self.insert_message_to_sqlite(msg, result._result)
            if self.task.response_type == "async_playbook":
                self.send_playbook_result(self._format_runner_on_ok(result))
        except:
            logger.error(traceback.format_exc())

    def v2_runner_on_unreachable(self, result):
        logger.debug("v2_runner_on_unreachable called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))
        self.errors += 1
        host = result._host.get_name()
        msg = {"host": host, "success": False,
               "task": self.task_modules[0]
               if self.task_name == "setup" and 'setup' not in self.task_modules
               else self.task_name}
        msg = self.modify_msg(msg, result)
        self.insert_message_to_sqlite(msg, result._result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        logger.debug("v2_runner_on_failed called by ansible, "
                     "host=%s, task=%s, result=%s, ignore_errors=%s" % (result._host,
                                                                        result._task.get_name(),
                                                                        self._dump_results(result._result),
                                                                        ignore_errors))
        # When ignore_errors is True, no need to insert this message to sqlite3
        if not ignore_errors:
            try:
                if "results" in result._result:
                    self.failed_msg = result._result["results"][0]["msg"]
                elif "msg" in result._result:
                    self.failed_msg = result._result["msg"]
                    if "module_stdout" in result._result and result._result["module_stdout"] != "":
                        self.failed_msg += " - " + result._result["module_stdout"]
            except Exception as e:
                self.failed_msg = ""
                logger.error("didn't parse the failed message: %s" % str(e))

            self.errors += 1
            host = result._host.get_name()
            msg = {"host": host, "success": False,
                   "task": self.task_modules[0]
                   if self.task_name == "setup" and 'setup' not in self.task_modules
                   else self.task_name}
            msg = self.modify_msg(msg, result)
            self.insert_message_to_sqlite(msg, result._result)
            if self.task.response_type == "async_playbook":
                self.send_playbook_result(self._format_runner_on_failed(result, ignore_errors))

    def v2_runner_on_skipped(self, result):
        logger.debug("v2_runner_on_skipped called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))
        # When skipped, no need to insert this message to sqlite3
        if self.task.response_type == "async_playbook":
            self.send_playbook_result(self._format_runner_on_skipped(result))

    def v2_runner_on_async_failed(self, result):
        logger.debug("v2_runner_on_async_failed called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))
        self.errors += 1
        self.failed_msg = result._result["results"][0]["msg"]
        host = result._host.get_name()
        self.task_name = result._task.get_name()
        msg = {"host": host, "success": False,
               "task": self.task_modules[0]
               if self.task_name == "setup" and 'setup' not in self.task_modules
               else self.task_name}
        msg = self.modify_msg(msg, result)
        self.insert_message_to_sqlite(msg, result._result)
        # if self.task.response_type == "async_playbook":
        #    self.send_playbook_result(self._format_runner_on_async_failed(result))

    def v2_runner_on_async_ok(self, result):
        logger.debug("v2_runner_on_async_ok called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))

    def v2_runner_item_on_ok(self, result):
        logger.debug("v2_runner_item_on_ok called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))
        logger.debug("item_task=%s" % result._task.get_name())

    def v2_runner_item_on_failed(self, result):
        logger.debug("v2_runner_item_on_failed called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))

    def v2_runner_on_async_poll(self, result):
        logger.debug("v2_runner_on_async_poll called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))

    def v2_runner_on_no_hosts(self, task):
        logger.debug("v2_runner_on_no_hosts called by ansible, "
                     "task=%s" % task)

    def v2_runner_on_file_diff(self, result, diff):
        logger.debug("v2_runner_on_file_diff called by ansible, "
                     "host=%s, task=%s, result=%s, diff=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result), diff))

    def v2_runner_item_on_skipped(self, result):
        logger.debug("v2_runner_item_on_skipped called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))

    def v2_playbook_on_import_for_host(self, result, imported_file):
        logger.debug("v2_playbook_on_import_for_host called by ansible, "
                     "host=%s, task=%s, result=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result)))
        logger.debug("imported_file=%s" % imported_file)

    def v2_playbook_on_not_import_for_host(self, result, missing_file):
        logger.debug("v2_playbook_on_not_import_for_host called by ansible, "
                     "result=%s, missing_file=%s" % (result, missing_file))

    def v2_playbook_on_play_start(self, play):
        logger.debug("v2_playbook_on_play_start called by ansible, "
                     "play=%s" % play)

        if "queue" in play._variable_manager._extra_vars:
            logger.info("this is bocloud play, queue =%s" % play._variable_manager._extra_vars['queue'])
        else:
            logger.info("ansible internal play, play=%s" % play.get_name())

        if self.task.response_type == "async_playbook":
            self.send_playbook_result(self._format_playbook_on_play_start(play))

    def v2_playbook_on_include(self, included_file):
        logger.debug("v2_playbook_on_include called by ansible, "
                     "included_file=%s" % included_file)

    def v2_playbook_on_task_start(self, task, is_conditional):
        logger.debug("v2_playbook_on_task_start called by ansible, "
                     "task=%s, is_conditional=%s" % (task, is_conditional))
        self.task_name = task.get_name()

    def v2_playbook_on_vars_prompt(self, varname, private=True, prompt=None, encrypt=None, confirm=False,
                                   salt_size=None, salt=None, default=None):
        logger.debug("v2_playbook_on_vars_prompt called by ansible, "
                     "varname=%s" % varname)

    def v2_playbook_on_handler_task_start(self, task):
        logger.debug("v2_playbook_on_handler_task_start called by ansible, "
                     "task=%s" % task)

    def v2_playbook_on_no_hosts_matched(self):
        logger.debug("v2_playbook_on_no_hosts_matched called by ansible")
        self.errors += 1
        msg = {"host": "",
               "success": False,
               "task": self.task_modules[0]
               if self.task_name == "setup" and 'setup' not in self.task_modules
               else self.task_name}
        self.insert_message_to_sqlite(msg, {"msg": "no_hosts_matched"})

    def v2_playbook_on_start(self, playbook):
        logger.debug("v2_playbook_on_start called by ansible, "
                     "hosts=%s, file_name=%s" % (playbook._entries, playbook._file_name))

    def v2_playbook_on_cleanup_task_start(self, task):
        logger.debug("v2_playbook_on_cleanup_task_start called by ansible, "
                     "task=%s" % task)

    def v2_playbook_on_notify(self, result, handler):
        logger.debug("v2_playbook_on_notify called by ansible, "
                     "host=%s, task=%s, result=%s, handler=%s" % (
                         result._host, result._task.get_name(), self._dump_results(result._result), handler))

    def v2_playbook_on_stats(self, stats):
        logger.debug("v2_playbook_on_stats called by ansible, "
                     "changed=%s, dark=%s, failures=%s, ok=%s, processed=%s, skipped=%s" % (
                         stats.changed, stats.dark, stats.failures, stats.ok, stats.processed, stats.skipped))
        summarize_stat = {}
        for host in stats.processed.keys():
            summarize_stat[host] = stats.summarize(host)
        logger.debug("summarize_stat=%s" % summarize_stat)
        if self.errors == 0:
            status = "OK"
        else:
            status = "FAILED"
        logger.debug("all task status %s" % status)

        if self.task.response_type != "sync":
            # insert the finally result to async_task_result
            if BOCLOUD_WORKER_CONFIG["is_not_db"] is True:
                operate_result = intergrate_messages_by_host(self.ansible_result["data"], self.playbook_script)
                operate_result = self._instead_failed_message(operate_result)
                intergrate_send_result_to_rabbitmq(self.task.queue, operate_result, self.node_id)
            else:
                db = None
                try:
                    db = BocloudWorkerDB(self.worker_db)
                    _, results = db.get_task_all_result(self.task.queue, valid=0)
                    operate_result = intergrate_messages_by_host(results, self.playbook_script)
                    db.insert_async_task_result(self.task.queue, '0.0.0.0',
                                                json.dumps(operate_result), 1)

                    operate_result = self._instead_failed_message(operate_result)
                    intergrate_send_result_to_rabbitmq(self.task.queue, operate_result, self.node_id)
                    db.set_task_as_finished(self.task.queue)
                except sqlite3.Error as e:
                    logger.error("Failed to update task status with sqlite3 exception: %s" % str(e))
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error("Failed to update task status with unknown exception: %s" % str(e))
                finally:
                    if db:
                        db.close()

                if self.task.response_type == "async_playbook":
                    self.send_playbook_result(self._format_playbook_on_stats(stats))
                    if self.rabbitmq:
                        self.rabbitmq.clearup()
        else:
            success = True if status == "OK" else False
            for result in self.ansible_result["data"]:
                if result["success"] is False:
                    success = False

            self.ansible_result["success"] = success
            self.ansible_result["taskNodeId"] = self.node_id
            self.ansible_result["message"] = "The sync job Finished"
            self.result_signal.set()

    def _instead_failed_message(self, result):
        try:
            if self.failed_msg != "":
                result[0]["message"]["msg"] = self.failed_msg
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("Failed to update result with failed message: %s" % str(e))
        finally:
            return result

    # below function to format playbook result
    def _format_runner_on_failed(self, result, ignore_errors=False):

        ret_string = ''
        if self._last_task_banner != result._task._uuid:
            ret_string = self._print_task_banner(result._task)

        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        ret_string += self._handle_exception(result._result)
        # self._handle_warnings(result._result)

        if result._task.loop and 'results' in result._result:
            self._process_items(result)

        else:
            if delegated_vars:
                ret_string += "fatal: [%s -> %s]: FAILED! => %s" % (result._host.get_name(),
                                                                    delegated_vars['ansible_host'],
                                                                    self._dump_results(result._result))
            else:
                ret_string += "fatal: [%s]: FAILED! => %s" % (result._host.get_name(),
                                                              self._dump_results(result._result))

        if ignore_errors:
            ret_string += "...ignoring"

    def _format_runner_on_ok(self, result):

        ret_string = ''
        if self._last_task_banner != result._task._uuid:
            ret_string = self._print_task_banner(result._task)

        self._clean_results(result._result, result._task.action)

        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        self._clean_results(result._result, result._task.action)
        if result._task.action in ('include', 'include_role'):
            return
        elif result._result.get('changed', False):
            if delegated_vars:
                msg = "changed: [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
            else:
                msg = "changed: [%s]" % result._host.get_name()
        else:
            if delegated_vars:
                msg = "ok: [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
            else:
                msg = "ok: [%s]" % result._host.get_name()

        # self._handle_warnings(result._result)

        if result._task.loop and 'results' in result._result:
            self._process_items(result)
        else:
            if (self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) \
                    and not '_ansible_verbose_override' in result._result:
                msg += " => %s" % (self._dump_results(result._result),)
            ret_string += msg

        return ret_string

    def _format_runner_on_skipped(self, result):
        ret_string = ''
        if C.DISPLAY_SKIPPED_HOSTS:
            if self._last_task_banner != result._task._uuid:
                ret_string = self._print_task_banner(result._task)

            if result._task.loop and 'results' in result._result:
                self._process_items(result)
            else:
                msg = "skipping: [%s]" % result._host.get_name()
                if (self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) \
                        and not '_ansible_verbose_override' in result._result:
                    msg += " => %s" % self._dump_results(result._result)
                ret_string += msg

        return ret_string

    def _format_runner_on_unreachable(self, result):
        ret_string = ''
        if self._last_task_banner != result._task._uuid:
            ret_string = self._print_task_banner(result._task)

        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            ret_string += "fatal: [%s -> %s]: UNREACHABLE! => %s" % (result._host.get_name(),
                                                                     delegated_vars['ansible_host'],
                                                                     self._dump_results(result._result))
        else:
            ret_string += "fatal: [%s]: UNREACHABLE! => %s" % (result._host.get_name(),
                                                               self._dump_results(result._result))

        return ret_string

    def _format_playbook_on_no_hosts_matched(self):
        return "skipping: no hosts matched"

    def _format_playbook_on_no_hosts_remaining(self):
        return "NO MORE HOSTS LEFT"

    def _format_playbook_on_task_start(self, task, is_conditional):
        return self._print_task_banner(task)

    def _print_task_banner(self, task):
        # args can be specified as no_log in several places: in the task or in
        # the argument spec.  We can check whether the task is no_log but the
        # argument spec can't be because that is only run on the target
        # machine and we haven't run it thereyet at this time.
        #
        # So we give people a config option to affect display of the args so
        # that they can secure this if they feel that their stdout is insecure
        # (shoulder surfing, logging stdout straight to a file, etc).
        args = ''
        ret_string = ''
        if not task.no_log and C.DISPLAY_ARGS_TO_STDOUT:
            args = u', '.join(u'%s=%s' % a for a in task.args.items())
            args = u' %s' % args

        ret_string = self._show_banner(u"TASK [%s%s]" % (task.get_name().strip(), args))
        if self._display.verbosity >= 2:
            path = task.get_path()
            if path:
                ret_string += u"task path: %s" % path

        self._last_task_banner = task._uuid
        return ret_string

    def _format_playbook_on_cleanup_task_start(self, task):
        return self._show_banner("CLEANUP TASK [%s]" % task.get_name().strip())

    def _format_playbook_on_handler_task_start(self, task):
        return self._show_banner("RUNNING HANDLER [%s]" % task.get_name().strip())

    def _format_playbook_on_play_start(self, play):
        name = play.get_name().strip()
        if not name:
            msg = u"PLAY"
        else:
            msg = u"PLAY [%s]" % name

        self._play = play

        return self._show_banner(msg)

    def _format_on_file_diff(self, result):
        ret_string = ''
        if result._task.loop and 'results' in result._result:
            for res in result._result['results']:
                if 'diff' in res and res['diff'] and res.get('changed', False):
                    diff = self._get_diff(res['diff'])
                    if diff:
                        ret_string = diff
        elif 'diff' in result._result and result._result['diff'] and result._result.get('changed', False):
            diff = self._get_diff(result._result['diff'])
            if diff:
                ret_string = diff

        return ret_string

    def _format_runner_item_on_ok(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if result._task.action in ('include', 'include_role'):
            return ''
        elif result._result.get('changed', False):
            msg = 'changed'
        else:
            msg = 'ok'

        if delegated_vars:
            msg += ": [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
        else:
            msg += ": [%s]" % result._host.get_name()

        msg += " => (item=%s)" % (self._get_item(result._result),)

        if (self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) \
                and not '_ansible_verbose_override' in result._result:
            msg += " => %s" % self._dump_results(result._result)
        return msg

    def _format_runner_item_on_failed(self, result):

        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        ret_string = self._handle_exception(result._result)

        msg = "failed: "
        if delegated_vars:
            msg += "[%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
        else:
            msg += "[%s]" % (result._host.get_name())

        # self._handle_warnings(result._result)
        ret_string += msg + " (item=%s) => %s" % (self._get_item(result._result), self._dump_results(result._result))
        return ret_string

    def _format_runner_item_on_skipped(self, result):
        ret_string = ''
        if C.DISPLAY_SKIPPED_HOSTS:
            msg = "skipping: [%s] => (item=%s) " % (result._host.get_name(), self._get_item(result._result))
            if (self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) \
                    and not '_ansible_verbose_override' in result._result:
                msg += " => %s" % self._dump_results(result._result)
            ret_string = msg

        return ret_string

    def _format_playbook_on_include(self, included_file):
        return 'included: %s for %s' % (included_file._filename, ", ".join([h.name for h in included_file._hosts]))

    def _format_playbook_on_stats(self, stats):
        ret_string = self._show_banner("PLAY RECAP")

        hosts = sorted(stats.processed.keys())
        for h in hosts:
            t = stats.summarize(h)

            ret_string += u"%-26s: ok=%-4s changed=%-4s unreachable=%-4s failed=%-4s" % (
                h, t['ok'], t['changed'], t['unreachable'], t['failures'])

        # print custom stats
        if C.SHOW_CUSTOM_STATS and stats.custom:
            self._show_banner("CUSTOM STATS: ")
            # per host
            # TODO: come up with 'pretty format'
            for k in sorted(stats.custom.keys()):
                if k == '_run':
                    continue
                ret_string += '\t%s: %s' % (k, self._dump_results(stats.custom[k], indent=1).replace('\n', ''))

            # print per run custom stats
            if '_run' in stats.custom:
                ret_string += "\n"
                ret_string += '\tRUN: %s' % self._dump_results(stats.custom['_run'], indent=1).replace('\n', '')

        return ret_string

    def _format_playbook_on_start(self, playbook):
        ret_string = ''
        if self._display.verbosity > 1:
            from os.path import basename
            ret_string = self._show_banner("PLAYBOOK: %s" % basename(playbook._file_name))

        if self._display.verbosity > 3:
            if self._options is not None:
                for option in dir(self._options):
                    if option.startswith('_') or option in ['read_file', 'ensure_value', 'read_module']:
                        continue
                    val = getattr(self._options, option)
                    if val:
                        ret_string += '%s: %s' % (option, val)

        return ret_string

    def _format_runner_retry(self, result):
        task_name = result.task_name or result._task
        msg = "FAILED - RETRYING: %s (%d retries left)." % (
            task_name, result._result['retries'] - result._result['attempts'])
        if (self._display.verbosity > 2 or '_ansible_verbose_always' in result._result) \
                and not '_ansible_verbose_override' in result._result:
            msg += "Result was: %s" % self._dump_results(result._result)
        return msg

    def _show_banner(self, msg):
        '''
        Prints a header-looking line with cowsay or stars wit hlength depending on terminal width (3 minimum)
        '''
        columns = 120
        msg = msg.strip()
        star_len = columns - len(msg)
        if star_len <= 3:
            star_len = 3
        stars = u"*" * star_len
        return "\n%s %s\n" % (msg, stars)

    def _handle_exception(self, result):

        msg = ''
        if 'exception' in result:
            msg = "An exception occurred during task execution. "
            if self._display.verbosity < 3:
                # extract just the actual error message from the exception text
                error = result['exception'].strip().split('\n')[-1]
                msg += "To see the full traceback, use -vvv. The error was: %s" % error
            else:
                msg = "The full traceback is:\n" + result['exception']
                del result['exception']

        return msg
