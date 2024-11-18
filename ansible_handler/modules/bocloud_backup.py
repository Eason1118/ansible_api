#!/usr/bin/python
# -*- coding: utf-8 -*-

import tarfile
import uuid

DOCUMENTATION = '''
---
module: bocloud_backup
short_description: backup a file or directory from remote nodes
description:
     - This module works like M(copy), but in reverse. It is used for fetching
       file or directory from remote machines and storing them locally in a file tree,
       organized by hostname.
options:
  src:
    description:
      - The file on the remote system to fetch. This is a file or a directory.
    required: true
    default: null
    aliases: []
  dest:
    description:
      - A directory to save the file into. For example, if the I(dest)
        directory is C(/backup) a I(src) file named C(/etc/profile) on host
        C(host.example.com), would be saved into
        C(/backup/host.example.com/etc/profile)
    required: true
    default: null
requirements: []
author:
    - "Bocloud CMP team"
notes:
    - When running fetch with C(become), the M(slurp) module will also be
      used to fetch the contents of the file for determining the remote
      checksum. This effectively doubles the transfer size, and
      depending on the file size can consume all available memory on the
      remote or local hosts causing a C(MemoryError). Due to this it is
      advisable to run this module without C(become) whenever possible.
'''

EXAMPLES = '''
# Store file into /tmp/fetched/host.example.com/tmp/somefile
- bocloud_backup: src=/tmp/somefile dest=/tmp/fetched
'''


def compress_targz_file(file_name):
    if not os.path.exists(file_name):
        msg = "file or directory not found: %s" % file_name
        return False, msg

    if file_name.endswith('/'):
        base_dir = file_name[:-1]
        dest_dir = os.path.dirname(base_dir)
        basename = os.path.basename(base_dir)
    else:
        base_dir = os.path.dirname(file_name)
        base_dir = base_dir[:-1] if base_dir.endswith('/') else base_dir
        basename = os.path.basename(file_name)
        dest_dir = base_dir

    # To avoid permission issue, set dest_dir to /tmp
    dest_dir = '/tmp'
    dest_file = "%s/Ansible_backup_%s_%s.tar.gz" % \
                (dest_dir, basename, str(uuid.uuid1()))

    tar_file = tarfile.open(dest_file, "w:gz")
    try:
        if os.path.isfile(file_name):
            tar_file.add(file_name, arcname=basename)
        else:
            for dir_path, dir_name, files in os.walk(file_name):
                rel_dir = os.path.relpath(dir_path, start=base_dir)
                for file in files:
                    fullpath = os.path.join(dir_path, file)
                    tar_file.add(fullpath,
                                 arcname=os.path.join(rel_dir, file))
    except IOError as e:
        msg = "IOError exception: %s" % str(e)
        return False, msg
    except Exception as e:
        msg = "Failed to compress the file or directory %s : %s" % \
              (file_name, str(e))
        return False, msg
    finally:
        tar_file.close()

    return True, dest_file


def main():
    module = AnsibleModule(argument_spec=dict(src=dict(required=True, aliases=['path'], type='path')),
                           supports_check_mode=False)
    source = module.params['src']

    result, tar_file = compress_targz_file(source)
    if result is False:
        module.fail_json(msg=tar_file)

    try:
        md5sum_tar = module.md5(tar_file)
    except ValueError:
        md5sum_tar = None

    module.exit_json(tarfile=tar_file, md5sum=md5sum_tar)


# import module snippets
from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
