#!/usr/bin/env python
# -*- coding: utf-8 -*-

import yaml

import json
import sqlite3
import threading
import traceback

from io import StringIO
from passlib.hash import sha512_crypt
from passlib.hash import sha256_crypt
from passlib.hash import sha1_crypt
from passlib.hash import des_crypt
from passlib.hash import md5_crypt
from passlib.hash import bigcrypt

import common.utils
from common.db.bocloud_worker_db import BocloudWorkerDB
from common.rabbitmq_handler import RabbitmqHandler
from common.utils import BOCLOUD_WORKER_CONFIG
from common.utils import BOCLOUD_WORKER_SQLITEDB
from common.utils import logger

result_lock = threading.Lock()


def get_playbook_vars(request):
    module = request['module']["name"]
    vars = dict()
    if module == "user":
        args = request['module']["args"]
        vars["sudoer_specs"] = list()
        for arg in args:
            vars["sudoer_specs"].append(arg)

        return vars


def append_result(result, key, message, expect_size, type="normal"):
    """Intergate result to a global variable for every hosts of a job.

       Args:
         - result: the global variable for all jobs result.
         - key: special job rabbitmq queue
         - message: result message of a host come from ansible callback.
         - expect_size: the host number of the whole job.
         - type: for specail result. we need to update the result.
       Return:
         The result of whole job if the number of rabbitmq messages
         is equal with whole job hosts. Otherwise, is None.
    """
    msg_result = None
    if result_lock.acquire():
        logger.debug("Append_result get lock for %s" % key)
        if key not in result:
            result[key] = []
        # append result for /server/status/scan
        if type != "normal":
            message = update_ansible_message(message, type)

        result[key].append(message)
        size = len(result[key])
        if size >= expect_size:
            msg_result = result[key]

        result_lock.release()
        logger.debug("Append_result release lock for %s" % key)

    return msg_result


def delete_result(result, key):
    """Clean up job result from global variable

       Args:
         - result: the global variable for all jobs result.
         - key: special job rabbitmq queue
       Return:
         N/A
    """
    if result_lock.acquire():
        logger.debug("delete_result get lock for %s" % key)
        if key in result:
            result.pop(key)

        result_lock.release()
        logger.debug("delete_result release lock for %s" % key)

    logger.debug("After clean up queue %s, the messages result is %s" %
                 (key, result))

    return


def update_ansible_message(message, type):
    result = {}
    if type == "scan":
        result["host"] = message["host"].encode("utf-8")
        if message["success"]:
            result["status"] = "online"
        else:
            result["status"] = "offline"

    return result


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


def generate_script_by_content(content, dest, type="python"):
    script_command_map = {"SHELL": "#!/usr/bin/env bash\n",
                          "PYTHON": "#!/usr/bin/env python\n",
                          "PERL": "#!/usr/bin/env perl\n"}
    file = open(dest, "w")
    try:
        first_line = content.split("\n")[0]
        if first_line.startswith("#!"):
            file.writelines(content)
        elif type.upper() in script_command_map:
            operation = script_command_map[type.upper()]
            if operation:
                file.writelines(operation)
            file.writelines(content)
        else:
            raise Exception("can't find suitable script operation. %s" % type)
    except IOError:
        raise Exception("Disk write exception on %s" % dest)
    finally:
        file.close()

    return True


def parse_module_args(module, args, is_playbook):
    # is_playbook is special, args is a dict not string like "key=value"
    # args为字典，在生成playbook的时候转化为ansible可识别的参数
    if is_playbook:
        return True, {module: args}
    if module == "bocloud_copy":
        parse_copy_args(args)
    elif module == "bocloud_backup":
        parse_bocloud_backup_args(args)
    elif module == "user":
        parse_user_args(args)

    new_args = []
    try:
        if args:
            if isinstance(args, dict):
                for k, v in args.items():
                    # 防止args的value里面有空格，增加单引号
                    new_args.append("%s=\'%s\'" % (k, v))
            # 支持ansible自带的command模块，args不是dict，是str，为command的内容，如uptime
            # 此时 tasks为{"command" : "uptime"}
            else:
                new_args.append("%s" % args)
    except:
        logger.info("module args %s error", args)
        return False, "module args %s error" % args

    return True, {module: " ".join(new_args)}


def parse_bocloud_backup_args(args):
    '''Parse backup request args. If client don't give the dest path,
       BOCLOUD worker will give configured backup path as it. Otherwise,
       worker will add the nfs path in front of dest path.

       Args:
         - args: the original args
       Return:
         the args after add the nfs path
    '''
    nfs_path = common.utils.get_nfs_path()
    backup_nfs_path = common.utils.get_backup_nfs_path()

    if "dest" in args:
        # Add nfs path in dest path
        args["dest"] = nfs_path + args["dest"]
    else:
        # use the default nfs path as the dest path
        args["dest"] = backup_nfs_path

    # add nfs path to modules.
    args["nfs_path"] = nfs_path


def parse_user_args(args):
    if "action" not in args:
        action = "UPDATE"
    else:
        action = args["action"]

    if "name" not in args:
        return False, "User name should be in requirement"

    if "action" == "DELETE":
        args.update(dict(remove='yes', state='absent'))
        return

    # The arguments for updatting password in ansible is
    # "name=myname password=\"{{ 'password' | password_hash('sha512') }}\" update_password=always"
    if "pasd" in args:
        args['pasd'] = "{{ '%s' | password_hash('sha512') }}" % args["pasd"]
        if action == "UPDATE":
            args["update_password"] = "always"
        else:
            args["update_password"] = "on_create"

    if "home" in args:
        if action == "UPDATE":
            args["move_home"] = "yes"
    return


def parse_copy_args(args):
    file_list = []
    if "src" in args:
        file_list = args["src"].split(",")

    # add nfs_path in front of file path
    nfs_path = common.utils.get_nfs_path()

    first = True
    for file in file_list:
        if first:
            args["src"] = "%s%s" % (nfs_path, file)
            first = False
        else:
            new_file = "%s%s" % (nfs_path, file)
            args["src"] = args["src"] + "," + new_file


def handle_job_exception(queue, msg, result_signal, ansible_result, node_id, worker_db=BOCLOUD_WORKER_SQLITEDB):
    # if result_signal is None, it means that we need to send the exception to special rabbitmq queue
    # otherwise, we send directly the error message to ansible_handler result variable
    if result_signal is None:
        exchange = BOCLOUD_WORKER_CONFIG['external_mq']['exchange']
        mq_type = BOCLOUD_WORKER_CONFIG['external_mq']['type']
        message = {"success": False,
                   "message": "Failed operate job %s" % queue,
                   "taskNodeId": node_id,
                   "data": msg}
        logger.error("The job %s is failue, The error message is %s" %
                     (queue, message))
        rabbitmq_handler = RabbitmqHandler(exchange, mq_type,
                                           durable=True, auto_delete=True)
        rabbitmq_handler.send_message(queue, message)
        rabbitmq_handler.clearup()

        if BOCLOUD_WORKER_CONFIG["is_not_db"] is False:
            # update sqlite3 DB and set the status to completed
            try:
                db = BocloudWorkerDB(worker_db)
                db.insert_async_task_result(queue, "", json.dumps(message), 1, commit=False)
                db.set_task_as_finished(queue, commit=False)
                db.commit()
            except sqlite3.Error as e:
                logger.error("Failed to update task status with sqlite3 exception: %s" % str(e))
                db.rollback()
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("Failed to update task status with unknown exception: %s" % str(e))
                db.rollback()
            finally:
                db.close()
    else:
        if isinstance(ansible_result, dict):
            ansible_result.clear()
            ansible_result["success"] = False
            ansible_result["message"] = msg

        result_signal.set()


def generate_tasks_list(tasks):
    tasks_list = []
    for task in tasks:
        for k, v in task.items():
            if v is not None:
                tasks_list.append(dict(action=dict(module=k, args=v)))
            else:
                tasks_list.append(dict(action=dict(module=k)))
    return tasks_list


def crypted_plain_text(plain_text, type="sha512"):
    '''
    crypted plain text with ansible method
    '''
    if type == "sha512":
        return sha512_crypt.using(rounds=5000).hash(plain_text)
    elif type == "sha256":
        return sha256_crypt.using(rounds=5000).hash(plain_text)
    elif type == "sha1":
        return sha1_crypt.using(rounds=5000).hash(plain_text)
    elif type == "des":
        return des_crypt.hash(plain_text)


def playbook_vars(ip_list, task, request, is_windows=False):
    '''
    playbook vars is used to generate playbook,these vars define playbook perfectly
    this function is called to deal with one task,and only support one task
    :param ip_list: ['192.168.2.73','192.168.2.74']
    :param task: {u'bocloud_backup': {u'dest': u'/platform/backup', u'src': u'c:\\a.bat'}}
    :param facts:
    :return:
    {'hosts': ['192.168.2.73'],
      'gather_facts': False,
      'tasks': [{'include': '../telegraf/tasks/main.yml'}],
      'handlers': [{'include': '../telegraf/handlers/main.yml'}],
      'vars_files': ['../../../telegraf_config.yml'],
      'vars': {'telegraf_plugins_extra': [{'name': 'kernel'}]}}
    '''
    result = dict(hosts=ip_list, tasks=[], handlers=[], vars_files=[], vars={})
    for module, args in task.items():
        if module == 'bocloud_collector':
            if is_windows:
                result['tasks'].append({'include': '../telegraf/tasks/windows.yml'})
            else:
                result['tasks'].append({'include': '../telegraf/tasks/main.yml'})
            result['handlers'].append({'include': '../telegraf/handlers/main.yml'})
            result['vars_files'].append('../../../telegraf_config.yml')
            result['vars'] = {'telegraf_plugins_extra': args.get('input-filters', [])}
        elif module == 'bocloud_backup':
            # gather_facts to get ansible_user_dir and decide where to put temp zip file
            result['gather_facts'] = True
            result['tasks'].append({'set_fact': {'timestamp': "{{ lookup('pipe', 'date +%Y%m%d%H%M%SZ') }}"}})
            result['tasks'].append(
                {
                    'name': 'zip src file or directory',
                    'win_zip': {
                        'dest': '{{ ansible_user_dir }}/{{ src_base_name }}_{{ timestamp }}.zip',
                        'src': '{{ src }}',
                        'force': True},
                    'register': 'zip_out'
                })
            result['tasks'].append({'set_fact': {'library_path': '{{ zip_out.win_zip }}'}})
            result['tasks'].append(
                {
                    'name': 'fetch remote zip file to dest',
                    'fetch': {
                        'dest': '{{ bocloud_worker.nfs_path }}/{{ dest }}/{{ inventory_hostname }}/',
                        'src': '{{ zip_out.win_zip.dest }}',
                        'flat': True},
                    'register': 'bocloud_backup_msg'
                })
            result['tasks'].append(
                {
                    'name': 'remove remote temp zip file',
                    'win_file': {
                        'path': '{{ zip_out.win_zip.dest }}',
                        'state': 'absent'},
                    'ignore_errors': True
                })
            # use debug module to return backup result rather then remove tmp zip file result
            result['tasks'].append(
                {
                    'debug': {
                        'var': 'bocloud_backup_msg'
                    }
                })
            result['vars_files'].append('../../../bocloud_worker_config.yml')
            result['vars'] = args
            if result['vars']['src'].endswith('\\'):
                result['vars']['src'] = result['vars']['src'][:-1]
                result['vars']['src_base_name'] = result['vars']['src'].split('\\')[-1]
            else:
                result['vars']['src_base_name'] = result['vars']['src'].split('\\')[-1]

        elif module == 'bocloud_copy':
            result['gather_facts'] = False
            src_list = args['src'].split(',')
            if len(src_list) > 1:
                # multi src need to check if dest is a dir
                result['tasks'].append(
                    {
                        'name': 'Get dest {{ dest }} stat.',
                        'win_stat': {
                            'path': '{{ dest }}'
                        },
                        'register': 'stat'
                    })
                result['tasks'].append(
                    {
                        'name': 'Create dest {{ dest }} directory is not exists.',
                        'win_file': {
                            'path': '{{ dest }}',
                            'state': 'directory'
                        },
                        'when': 'not stat.stat.exists'
                    })
                result['tasks'].append(
                    {
                        'name': 'Copy files {{ src }} to {{ dest }}',
                        'win_copy': {
                            'dest': '{{ dest }}',
                            'src': '{{ bocloud_worker.nfs_path }}/{{ item }}',
                            'creates': '{{ dest }}'},
                        'with_items': '{{ src_items }}'
                    })
                result['vars_files'].append('../../../bocloud_worker_config.yml')
                result['vars'] = args
                result['vars']['src_items'] = args['src'].split(',')
            else:
                result['tasks'].append(
                    {
                        'name': 'Copy files {{ src }} to {{ dest }}',
                        'win_copy': {
                            'src': '{{ bocloud_worker.nfs_path }}/{{ src }}',
                            'dest': '{{ dest }}'
                        }
                    })
                result['vars_files'].append('../../../bocloud_worker_config.yml')
                result['vars'] = args
        elif module == 'win_shell':
            result['tasks'].append(
                {
                    'win_shell': args['content'],
                    'args': {'executable': 'cmd'} if args['type'] == 'bat' else {}
                })
        elif module == 'playbook_script':
            result = yaml.load(StringIO(args))[0]
        elif module == "user":
            result["vars"] = get_playbook_vars(request)
            result["roles"] = ["ansible-sudoers"]
        else:
            result['gather_facts'] = False
            result['tasks'].append({module: args})
    logger.debug("playbook_vars is %s" % result)
    return result


def log_result(tasks, result):
    result_dict = {0: "RUN_OK", 1: "RUN_ERROR", 2: "RUN_FAILED_HOSTS", 3: "RUN_UNREACHABLE_HOSTS",
                   4: "RUN_FAILED_BREAK_PLAY", 255: "RUN_UNKNOWN_ERROR"}
    logger.info("tasks=%s, result=%s" % (tasks, result_dict.get(result, "RUN_UNKNOWN_ERROR")))
