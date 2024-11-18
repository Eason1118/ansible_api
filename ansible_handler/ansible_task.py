#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import yaml
import datetime

from jinja2 import Template
from tempfile import NamedTemporaryFile

from ansible_handler.ansible_utils import generate_script_by_content
from common.utils import logger
from common.utils import BOCLOUD_WORKER_CONFIG
from common.utils import BOCLOUD_ANSIBLE_CONFIG
from ansible_handler.ansible_utils import crypted_plain_text
from ansible_handler.ansible_utils import parse_module_args

RELEASED = False


class AnsibleTask(object):
    """
    Parase and manage task information
    """

    def __init__(self, request, queue, node_id, result_signal=None):
        self.hosts = self.get_hosts(request)
        self.module = self.get_module(request)
        self.queue = queue
        self.node_id = node_id
        self.groups = self.get_groups(request)
        self.options = self.get_options(request)
        self.playbook_vars = dict()
        self.connection = 'smart'
        self.ip_list = None
        self.is_windows = self.check_windows(request)
        self.original_args = self.get_args(request)
        self.temp_files = list()
        self.playbooks = list()
        # result_signal is variable of thread event.
        if result_signal:
            self.response_type = "sync"
        else:
            self.response_type = request.get("response", "async_result")
        self.initialize(request)

    def __str__(self):
        _format = '''
        module = %s
        queue = %s
        ip_list = %s
        options = %s
        playbooks = %s
        connection = %s
        '''
        return _format % (self.module, self.queue, self.ip_list, self.options, self.playbooks, self.connection)

    def initialize(self, request):
        """
        parase and initialize task infomation
        """
        self.get_connection(request)

        # we MUST get ip list after parasing connection,
        # because ip dependent the connection type.
        self.get_ip_list()

        # generate playbook vars value
        self.generate_playbook_vars(request)

        playbook = self.generate_playbook()
        if playbook is not None:
            self.playbooks.append(playbook)

    def cleanup(self):
        """
        cleanup task temp file. If worker is not release version,
        the temp files will be reserved.
        """
        if RELEASED is False:
            return

        for temp_file in self.temp_files:
            os.remove(temp_file)

        for playbook in self.playbooks:
            os.remove(playbook)

    def append_temp_file(self, filename):
        """
        append temp file to temp_files list
        """
        self.temp_files.append(filename)

    @staticmethod
    def get_hosts(request):
        """
        parase hosts infor of target machines from requestment.
        """
        hosts = []
        for host in request.get('targets', []):
            # no category in request, append default host category Linux
            if 'category' not in host:
                host['category'] = 'Linux'
            # no port in request, append default host port by os category
            if 'port' not in host:
                host['port'] = 5986 if host.get('category', 'Linux') == 'Windows' else 22
            hosts.append(host)
        return hosts

    def get_ip_list(self):
        """
        generate ip list from target information
        """
        if self.connection == 'localhost':
            self.ip_list = ['localhost'] * len(self.hosts)
        else:
            self.ip_list = [host['host'] for host in self.hosts]

    @staticmethod
    def get_args(request):
        """
        get original args value from requestment if it exist
        """
        args = None
        if "module" in request:
            args = request['module'].get("args", None)

        return args

    def get_groups(self, request):
        """
        get original groups value from requestment if it exist
        """
        groups = None
        if "groups" in request:
            groups = request.get("groups", None)

        return groups

    def get_module(self, request):
        """
        parase module name from requestment
        """
        if 'module' in request:
            module = "command"
            if "name" in request['module']:
                module = request['module']["name"]
        else:
            module = "script"

        return module

    def get_options(self, request):
        """
        the options are optional, it include sudo, become, becomeUser and becomePass args
        """
        if 'module' in request:
            options = request['module'].get('options', None)
        else:
            options = request['script'].get('options', None)

        # it is temporary code to be compatible old interface
        if options is None and "sudo" in request["targets"][0]:
            options = dict()
            options["become"] = request["targets"][0]["sudo"]

        return options

    @staticmethod
    def check_windows(request):
        """
        check target machines whether or not are windows.
        A requestment just includes a kind of machine. So, we just check the first target.
        category exist and value is "Windows", it is windows type. Otherwise. it is Linux.
        """
        if "category" in request["targets"][0] and "windows" == request["targets"][0]["category"].lower():
            return True
        else:
            return False

    def generate_playbook_vars(self, request):
        """
        parase playbook vars value
        """
        if "script" in request:
            # if the script is bat or powershell, we can directly use the args in "script"
            if request["script"]["type"].upper() not in ["SHELL", "PYTHON", "PERL"]:
                request["script"]["content"] = request["script"]["content"].replace("\n", "\n        ")
                self.playbook_vars["args"] = request["script"]
            else:
                # for the linux script, we need input the content a temp script to run.
                self.playbook_vars["args"] = dict()
                # need add to local file to operate
                source = "/tmp/ansible_script_%s" % self.node_id
                generate_script_by_content(request["script"]["content"],
                                           source,
                                           request["script"]["type"])
                self.temp_files.append(source)
                self.playbook_vars["args"]["source"] = source
                self.playbook_vars["args"]["type"] = request["script"]["type"]
                if "params" in request["script"]:
                    self.playbook_vars["args"]["params"] = request["script"]["params"]

        if "module" in request:
            self.playbook_vars["args"] = request["module"].get("args", dict())

        self.playbook_vars["ip_list"] = self.ip_list
        self.playbook_vars["bocloud_worker"] = BOCLOUD_WORKER_CONFIG
        self.playbook_vars["bocloud_ansible"] = BOCLOUD_ANSIBLE_CONFIG
        self.playbook_vars["is_windows"] = self.is_windows
        self.special_playbook_vars()

    def special_playbook_vars(self):
        """
        for some tasks, we need add some specail vars to playbook template.
        """
        if "args" not in self.playbook_vars:
            self.playbook_vars["args"] = dict()

        if self.module == "bocloud_backup":
            self.playbook_vars["args"]["src_base_name"] = self.original_args['src'].split('\\')[-1]

        self._crypted_password()

    def _crypted_password(self):
        """
        provide crypted password if the request include password field
        """
        if self.module == "authority" and "users" in self.playbook_vars["args"]:
            for user_info in self.playbook_vars["args"]["users"]:
                if "password" in user_info:
                    user_info["crypted_password"] = crypted_plain_text(user_info["password"],
                                                                       user_info.get("crypted_type", "sha512"))

    def is_sudo(self):
        """
        to check whether or not use sudo to run the task.
        """
        become = None
        sudo = None
        if self.options and 'become' in self.options:
            become = self.options.get('become')
        if self.options and 'sudo' in self.options:
            sudo = self.options.get('sudo')
        if become or sudo:
            return True

        return False

    def get_connection(self, request):
        """
        check how to connect to target hosts
        """
        connection_list = [host.get('connection', None) for host in self.hosts]
        if 'local' in connection_list:
            self.connection = 'local'
        # use module judge connection
        if 'module' in request and 'name' in request['module']:
            # ipmi is special, target is worker localhost
            if request['module']['name'].startswith('ipmi'):
                self.connection = "local"
            # snmp is special, target is worker localhost
            if request['module']['name'] == 'snmp_facts':
                self.connection = "local"
            # for bocloud_logview, if target is worker and file_path is worker log then connection is local
            elif request['module']['name'] == 'bocloud_logview':
                if BOCLOUD_WORKER_CONFIG['host'] == self.hosts[0]['host'] \
                        and request['module']['args']['log_file'] == BOCLOUD_WORKER_CONFIG['log']['file']:
                    self.connection = 'local'
            # use windows remote management to connect windows hosts
            elif request['module']['name'].startswith('win'):
                self.connection = "winrm"
        # use targets judge connection
        if len(self.hosts) == 0:
            self.connection = 'localhost'
        category_list = [host.get('category', 'Linux') for host in self.hosts]
        if 'Windows' in category_list:
            self.connection = 'winrm'

    def generate_playbook(self):
        """
        generate playbook by the template of the task
        """
        template_folder = BOCLOUD_ANSIBLE_CONFIG["playbook_template"]
        playbook_folder = BOCLOUD_ANSIBLE_CONFIG["playbook_folder"]

        if self.is_windows:
            # Firstly, check whether exist task template that name include 'win', if the task is for windows
            # If not, check the task template that not include 'win'
            template_file = "%s/%s_playbook_win.yml" % (template_folder, self.module)
            if not os.path.exists(template_file):
                template_file = "%s/%s_playbook.yml" % (template_folder, self.module)
        else:
            template_file = "%s/%s_playbook.yml" % (template_folder, self.module)

        # if the task template don't exist, use common template to parase.
        if not os.path.exists(template_file):
            template_file = "%s/common_playbook.yml" % template_folder
            # append playbook vars for common template
            result, module_args = parse_module_args(self.module, self.original_args, False)
            if result is True:
                self.playbook_vars["args"] = module_args

        logger.info("The task template is %s" % template_file)
        if not os.path.exists(template_file):
            logger.error("can't find a valid playbook template")
            return

        with open(template_file, 'r') as _file:
            data = _file.read()

        template = Template(data)

        # generate the playbook data
        my_data = template.render(self.playbook_vars)
        if not os.path.exists(playbook_folder):
            try:
                os.makedirs(playbook_folder)
            except OSError as msg:
                logger.error("Can't create the temp folder %s, msg: %s",
                             playbook_folder, msg)
                return None

        prefix = "playbook_%s_%s_" % (self.module, self.node_id)
        target_file = NamedTemporaryFile(delete=False, suffix='.yml', prefix=prefix, dir=playbook_folder)
        # FIXME: It is just a temporary method to resovle unicode issue
        if my_data.find('u\'') == -1:
            target_file.write(my_data.encode("utf-8"))
        else:
            target_file.write(my_data.replace('u\'', '\'').decode("unicode-escape"))
        target_file.close()

        logger.debug("By template: %s, generate temp file: %s",
                     template_file, target_file.name)
        return target_file.name

    @staticmethod
    def remove_object_unicode(vals):
        """
        remove the 'u' in front of string.
        """
        temp = json.dumps(vals, ensure_ascii=False)
        return yaml.safe_load(temp)
