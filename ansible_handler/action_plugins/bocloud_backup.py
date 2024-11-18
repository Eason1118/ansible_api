from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

import os
import time
import datetime

from ansible.plugins.action import ActionBase
from ansible.utils.hashing import md5
from ansible.utils.path import makedirs_safe


class ActionModule(ActionBase):
    def run(self, tmp=None, task_vars=None):
        ''' handler for fetch operations '''
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)

        result.update(dict(start=None, end=None))

        if self._play_context.check_mode:
            result['skipped'] = True
            result['msg'] = 'check mode not (yet) supported for this module'
            return result

        source = self._task.args.get('src', None)
        dest = self._task.args.get('dest', None)
        nfs_path = self._task.args.get('nfs_path', None)

        if source is None or dest is None:
            result['failed'] = True
            result['msg'] = "src and dest are required"
            return result

        ####################################################################
        # start to hard work
        result['start'] = str(datetime.datetime.now())

        source = self._connection._shell.join_path(source)
        source = self._remote_expand_user(source)

        # use slurp if permissions are lacking or
        # privilege escalation is needed
        remote_data = None
        backup_res = self._execute_module(module_name='bocloud_backup',
                                          module_args=dict(src=source),
                                          task_vars=task_vars, tmp=tmp)
        if backup_res.get('failed'):
            result.update(backup_res)
            result['end'] = str(datetime.datetime.now())
            return result

        # get the compession file path at target machine
        remote_source = backup_res.get('tarfile')
        orginal_md5 = backup_res.get('md5sum')

        # calculate the destination name
        if os.path.sep not in self._connection._shell.join_path('a', ''):
            source = self._connection._shell._unquote(source)
            source_local = source.replace('\\', '/')
        else:
            source_local = source

        dest = os.path.expanduser(dest)
        # files are saved in dest dir, with a subdir for each host,
        # then the filename
        if 'inventory_hostname' in task_vars:
            target_name = task_vars['inventory_hostname']
        else:
            target_name = self._play_context.remote_addr
        if source_local.endswith('/'):
            source_local = source_local[:-1]
        base_name = os.path.basename(source_local)
        timestamp = time.strftime("%Y%m%d%H%M%S")
        dest = "%s/%s/%s_%s.tar.gz" % \
               (self._loader.path_dwim(dest), target_name,
                base_name, timestamp)

        dest = dest.replace("//", "/")

        # create the containing directories, if needed
        makedirs_safe(os.path.dirname(dest))

        # fetch the file and check for changes
        self._connection.fetch_file(remote_source, dest)

        # remove the compession file from remote machine
        tmp_rm_cmd = self._connection._shell.remove(remote_source)
        tmp_rm_res = self._low_level_execute_command(tmp_rm_cmd, sudoable=False)
        tmp_rm_data = self._parse_returned_data(tmp_rm_res)
        if tmp_rm_data.get('rc', 0) != 0:
            warning_str = 'Error deleting remote temporary files (rc: {0}, stderr: {1})'.format(tmp_rm_res.get('rc'),
                                                                                                tmp_rm_res.get('stderr',
                                                                                                               'No error string available.'))
            result.update(dict(warning=warning_str))

        # For backwards compatibility. We'll return None on FIPS enabled systems
        try:
            new_md5 = md5(dest)
        except ValueError:
            new_md5 = None

        if new_md5 != orginal_md5:
            result['failed'] = True
            result['msg'] = "The md5sum value is not in accordence with orginal compession file"
            result['end'] = str(datetime.datetime.now())
            return result

        # new dest path that remove nfs path
        if nfs_path and dest.startswith(nfs_path):
            size = len(nfs_path)
            dest = dest[size:]
        result.update(dict(changed=False, md5sum=new_md5, dest=dest))
        result['end'] = str(datetime.datetime.now())

        return result
