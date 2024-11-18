#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import os
import re
import socket
import sys
from logging.handlers import RotatingFileHandler

import yaml


def get_log(name, file_path, log_level="INFO"):
    """Generate a standard logger

      Args:
        name - logger object
        file_path - the log file path
        log_level - log level, defalt value is INFO
    """
    # Create the directory if it does not exist
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
        except OSError as msg:
            raise Exception("Can't make directory %s. %s" % (directory, msg))

    # Get log level
    if log_level.upper() == "DEBUG":
        logging_level = logging.DEBUG
    elif log_level.upper() == "INFO":
        logging_level = logging.INFO
    elif log_level.upper() == "WARNING":
        logging_level = logging.WARNING
    elif log_level.upper() == "ERROR":
        logging_level = logging.ERROR
    elif log_level.upper() == "CRITICAL":
        logging_level = logging.CRITICAL
    else:
        logging_level = logging.INFO

    file_handler = RotatingFileHandler(file_path, maxBytes=10 * 1024 * 1024,
                                       backupCount=5, encoding="UTF-8")
    fmt = "%(asctime)s [%(levelname)s] %(threadName)s %(filename)s:%(lineno)d - %(message)s"
    formatter = logging.Formatter(fmt)
    file_handler.setFormatter(formatter)
    _logger = logging.getLogger(name)
    _logger.addHandler(file_handler)
    _logger.setLevel(logging_level)

    class ContextualFilter(logging.Filter):
        def filter(self, log_record):
            # no logger for logview thread
            if log_record.threadName.startswith('logview'):
                return False
            return True

    _logger.addFilter(ContextualFilter())

    return _logger


def get_ip_port():
    ip = str(BOCLOUD_WORKER_CONFIG["host"]) \
        if not '0.0.0.0' == str(BOCLOUD_WORKER_CONFIG["host"]) \
        else get_ip()
    return ip + ':' + str(BOCLOUD_WORKER_CONFIG["port"])


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 0))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def load_yaml(yaml_file, default=None):
    """
    load the data from a yaml file
    """
    # check the yaml file exists
    if not os.path.exists(yaml_file):
        if default and os.path.exists(default):
            yaml_file = default
        else:
            raise Exception('The yaml file: %s does not exist' % yaml_file)

    # load the configure files
    with open(yaml_file, 'r') as stream:
        data_map = yaml.load(stream)
        return data_map


#BOCLOUD_WORKER_CONFIG_FILE = os.path.join(os.path.dirname(sys.argv[0]), "bocloud_worker_config.yml")
BOCLOUD_WORKER_CONFIG_FILE = "./bocloud_worker_config.yml"
BOCLOUD_WORKER_CONFIG_DEFAULT = '/opt/worker/bocloud_worker/bocloud_worker_config.yml'
BOCLOUD_WORKER_CONFIG = load_yaml(BOCLOUD_WORKER_CONFIG_FILE, default=BOCLOUD_WORKER_CONFIG_DEFAULT)["bocloud_worker"]
BOCLOUD_ANSIBLE_CONFIG = load_yaml(BOCLOUD_WORKER_CONFIG_FILE, default=BOCLOUD_WORKER_CONFIG_DEFAULT)["bocloud_ansible"]
RABBITMQ_CONFIG = load_yaml(BOCLOUD_WORKER_CONFIG_FILE, default=BOCLOUD_WORKER_CONFIG_DEFAULT)["rabbitmq"]
ZOOKEEPER_CONFIG = load_yaml(BOCLOUD_WORKER_CONFIG_FILE, default=BOCLOUD_WORKER_CONFIG_DEFAULT)["zookeeper"]
# BOCLOUD_WORKER_SQLITEDB = "{0[nfs_path]}/{0[host]}_{0[port]}/bocloud_worker.db".format(BOCLOUD_WORKER_CONFIG)
BOCLOUD_WORKER_SQLITEDB = "{0[nfs_path]}/bocloud_worker_db/bocloud_worker.db".format(BOCLOUD_WORKER_CONFIG)
CELERY_CONFIG = load_yaml(BOCLOUD_WORKER_CONFIG_FILE, default=BOCLOUD_WORKER_CONFIG_DEFAULT)["celery"]


def get_nfs_path():
    nfs_path = BOCLOUD_WORKER_CONFIG["nfs_path"]
    if nfs_path.endswith("/"):
        nfs_path = nfs_path[:-1]

    return nfs_path


def global_dict_update(dict_arg, key, lock=None, value=None, operate="pop"):
    result = None
    if lock and lock.acquire():
        if operate == "pop":
            if key in dict_arg:
                dict_arg.pop(key)
        elif operate == "append":
            dict_arg[key] = value
        elif operate == "get":
            if key in dict_arg:
                result = dict_arg[key]

        lock.release()

    return result


def get_backup_nfs_path():
    return BOCLOUD_WORKER_CONFIG["nfs_path"].replace('//', '/')


def write_content_to_file(file_name, content):
    _file = open(file_name, "w")
    try:
        _file.writelines(content)
    except IOError:
        return False
    finally:
        _file.close()
    return True


def intergrate_messages_by_host(results, playbook_script):
    """ bocloud server需要的结果是一个host一个result
    但是在同一个host上执行多个task时，这个host的结果会有多条
    这里统合结果为一个host一个result
    只有playbook脚本执行的时候会把所有结果返回出去
    intergrate messages by host ip
    :param results:
    :param playbook_script:
    :return:
    """
    try:
        logger.info("original results is {}, playbook_script is {}".format(results, playbook_script))
        if playbook_script:
            # update cost in results and return all results
            host_results = {}
            for result in results:
                host = result.get('host', None)
                if result['host'] in host_results:
                    host_results[host].append(result)
                    continue
                else:
                    host_results[result['host']] = [result]

            for host, results in host_results.items():
                for i in reversed(range(len(results))):
                    if i == 0:
                        results[i]['cost'] = float('%.3f' % results[i]['cost'])
                    else:
                        results[i]['cost'] = float('%.3f' % (results[i]['cost'] - results[i - 1]['cost']))
                host_results[host] = results
            new_results = []
            for host, results in host_results.items():
                new_results += results
            return new_results

        hosts = []
        for result in results:
            if result['host'] in hosts:
                continue
            else:
                hosts.append(result['host'])

        # get tasks cost
        # 多个task时最后一个task的cost就是真实的执行时间
        cost_dict = dict()
        for host in hosts:
            for result in results:
                if result['host'] == host:
                    if cost_dict.get(host, None):
                        # task execute fail, cost is this task
                        if not result.get('success', True):
                            cost_dict[host] = result.get('cost', 0)
                            continue
                        # find max
                        if cost_dict[host] < result.get('cost', 0):
                            cost_dict[host] = result.get('cost', 0)
                            continue
                    else:
                        cost_dict[host] = result.get('cost', 0)

        # find min_index for failed task
        min_index_dict = dict()
        for host in hosts:
            for i in range(len(results)):
                if host == results[i]['host']:
                    # task fail
                    if 'message' in results[i] and \
                            'skipped' in results[i]['message'] \
                            and results[i]['message']['skipped']:
                        continue
                    if 'message' in results[i] and 'results' in results[i]['message']:
                        try:
                            skip = True
                            # if all results are skipped, this task result needs to be skipped
                            for result in results[i]['message']['results']:
                                if not result['skipped']:
                                    skip = False
                            if skip:
                                continue
                        except:
                            pass
                    if 'success' in results[i] and not results[i]['success']:
                        min_index_dict[host] = i
                        break
        # find max_index for all success tasks
        max_index_dict = dict()
        for host in hosts:
            for i in reversed(range(len(results))):
                if host == results[i]['host']:
                    max_index_dict[host] = i
                    break
        # return last success task result
        new_results = [results[value] for value in max_index_dict.values()]
        # update for fail tasks
        if min_index_dict:
            # return first failed task result
            for i in range(len(new_results)):
                if new_results[i]['host'] in min_index_dict:
                    new_results[i] = results[min_index_dict[new_results[i]['host']]]
        # update cost
        for result in new_results:
            for host, cost in cost_dict.items():
                if host == result['host']:
                    result['cost'] = float('%.3f' % cost)
        return new_results
    except Exception as ex:
        logger.error("intergrate_messages_by_host exception %s" % str(ex))
        return results


# set logger
# can't use the bocloud_loger, it has a bug that can't show file path and
# line number in log
# logger = bocloud_logger(get_log(__name__, BOCLOUD_WORKER_CONFIG["log"]["file"],
#                            log_level=BOCLOUD_WORKER_CONFIG["log"]["level"]))
logger = get_log(__name__, BOCLOUD_WORKER_CONFIG["log"]["file"],
                 log_level=BOCLOUD_WORKER_CONFIG["log"]["level"])


def check_white_blacklist(ip):
    whitelist = BOCLOUD_WORKER_CONFIG.get("whitelist", "").strip()
    blacklist = BOCLOUD_WORKER_CONFIG.get("blacklist", "").strip()

    # Firstly, check whether or not blacklist include the ip
    # if the blacklist is NOT empty and the ip is in the blacklist,
    # return False
    result = is_include_ip(ip, blacklist)
    if blacklist and result:
        logger.info("IP %s is in blacklist %s" % (ip, blacklist))
        return False

    # Secondly, check whether or not whitelist include the ip
    # if whitelist is NOT empty and the ip is NOT in the whitelist,
    # return False
    result = is_include_ip(ip, whitelist)
    if not result:
        logger.info("IP %s is NOT in whitelist %s" % (ip, whitelist))
        return False

    return True


def is_include_ip(ip, iplist):
    """check whether or not IP in the iplist
       return:
         False: iplist is NOT empty and ip is NOT in the iplist
         True: iplist is empty or ip is in the iplist
    """
    if not iplist:
        return True

    ip_code = ip.split('.')
    ip_list = re.split(',|;|:', iplist)
    for ipstring in ip_list:
        ipstr_code = ipstring.strip().split('.')
        match = True
        for i in range(0, 4):
            # the ip string is a ip scope
            if ipstr_code[i].find('-') > 0:
                start = int(ipstr_code[i].split('-')[0].strip())
                end = int(ipstr_code[i].split('-')[1].strip())
                if int(ip_code[i]) < start or int(ip_code[i]) > end:
                    match = False
                    break
            elif ipstr_code[i] != '*' and ipstr_code[i] != ip_code[i]:
                match = False
                break

        if match:
            return True

    return False


def get_file_content(file_name, position, presize):
    """ Get a file specialized content by start position and read size
          file_name: the targetted file
          position: the start position to read
          presize: the size that need to read content
    """
    if not os.path.exists(file_name):
        msg = "file %s not found" % file_name
        return False, msg, None
    if not os.access(file_name, os.R_OK):
        msg = "file %s not be readable" % file_name
        return False, msg, None

    curr_position = 0
    content = ""
    with open(file_name, 'r+b') as f:
        f.seek(0, os.SEEK_END)
        end_position = f.tell()
        start_line = False
        half_line_size = 40
        extra = half_line_size
        if position is 0:
            # if the provide the position is zero, we need to compute the real
            # start position.
            if end_position > presize:
                # move 40 positions forward to find the line start position
                # if don't find the start position, will ignore the line.
                if (end_position - presize) < half_line_size:
                    extra = end_position - presize
                new_position = (-1) * (presize + extra)
                f.seek(new_position, os.SEEK_END)
            else:
                # presize is more than size of the log file.
                # position will be the start of the file
                start_line = True
                f.seek(0)
        else:
            # if provide the position, we think the position is a start of line
            start_line = True
            f.seek(position)

        # To find the start position of the first line
        if not start_line:
            line = f.readline()
            seekps = f.tell()
            count = len(line)
            # if the read lines size is more than extra size, the latest line is start line.
            while count < extra:
                seekps = f.tell()
                line = f.readline()
                count += len(line)
            else:
                # find the latest line start
                f.seek(seekps)

        content = f.read(presize)
        # avoid the final line is incompleted
        if not content.endswith(os.linesep):
            content += f.readline()

        curr_position = f.tell()

    return True, content, curr_position
