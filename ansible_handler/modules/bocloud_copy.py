#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import tarfile

DOCUMENTATION = '''
---
module: bocloud_copy
version_added: "historical"
short_description: Copies files to remote locations.
description:
     - The M(copy) module copies a file on the local box to remote locations. Use the M(fetch) module to copy files from remote locations to the local box. If you need variable interpolation in copied files, use the M(template) module.
options:
  src:
    description:
      - Local path to a file to copy to the remote server; can be absolute or relative.
        If path is a directory, it is copied recursively. In this case, if path ends
        with "/", only inside contents of that directory are copied to destination.
        Otherwise, if it does not end with "/", the directory itself with all contents
        is copied. This behavior is similar to Rsync.
    required: false
    default: null
    aliases: []
  content:
    version_added: "1.1"
    description:
      - When used instead of 'src', sets the contents of a file directly to the specified value.
        This is for simple values, for anything complex or with formatting please switch to the template module.
    required: false
    default: null
  dest:
    description:
      - Remote absolute path where the file should be copied to. If src is a directory,
        this must be a directory too.
    required: true
    default: null
  backup:
    description:
      - Create a backup file including the timestamp information so you can get
        the original file back if you somehow clobbered it incorrectly.
    version_added: "0.7"
    required: false
    choices: [ "yes", "no" ]
    default: "no"
  force:
    description:
      - the default is C(yes), which will replace the remote file when contents
        are different than the source. If C(no), the file will only be transferred
        if the destination does not exist.
    version_added: "1.1"
    required: false
    choices: [ "yes", "no" ]
    default: "yes"
    aliases: [ "thirsty" ]
  directory_mode:
    description:
      - When doing a recursive copy set the mode for the directories. If this is not set we will use the system
        defaults. The mode is only set on directories which are newly created, and will not affect those that
        already existed.
    required: false
    version_added: "1.5"
  remote_src:
    description:
      - If False, it will search for src at originating/master machine, if True it will go to the remote/target machine for the src. Default is False.
      - Currently remote_src does not support recursive copying.
    choices: [ "True", "False" ]
    required: false
    default: "no"
    version_added: "2.0"
  follow:
    required: false
    default: "no"
    choices: [ "yes", "no" ]
    version_added: "1.8"
    description:
      - 'This flag indicates that filesystem links, if they exist, should be followed.'
extends_documentation_fragment:
    - files
    - validate
author:
    - "Ansible Core Team"
    - "Michael DeHaan"
notes:
   - The "copy" module recursively copy facility does not scale to lots (>hundreds) of files.
     For alternative, see synchronize module, which is a wrapper around rsync.
'''

EXAMPLES = '''
# Example from Ansible Playbooks
- copy: src=/srv/myfiles/foo.conf dest=/etc/foo.conf owner=foo group=foo mode=0644

# The same example as above, but using a symbolic mode equivalent to 0644
- copy: src=/srv/myfiles/foo.conf dest=/etc/foo.conf owner=foo group=foo mode="u=rw,g=r,o=r"

# Another symbolic mode example, adding some permissions and removing others
- copy: src=/srv/myfiles/foo.conf dest=/etc/foo.conf owner=foo group=foo mode="u+rw,g-wx,o-rwx"

# Copy a new "ntp.conf file into place, backing up the original if it differs from the copied version
- copy: src=/mine/ntp.conf dest=/etc/ntp.conf owner=root group=root mode=644 backup=yes

# Copy a new "sudoers" file into place, after passing validation with visudo
- copy: src=/mine/sudoers dest=/etc/sudoers validate='visudo -cf %s'
'''

RETURN = '''
dest:
    description: destination file/path
    returned: success
    type: string
    sample: "/path/to/file.txt"
src:
    description: source file used for the copy on the target machine
    returned: changed
    type: string
    sample: "/home/httpd/.ansible/tmp/ansible-tmp-1423796390.97-147729857856000/source"
md5sum:
    description: md5 checksum of the file after running copy
    returned: when supported
    type: string
    sample: "2a5aeecc61dc98c4d780b14b330e3282"
checksum:
    description: checksum of the file after running copy
    returned: success
    type: string
    sample: "6e642bb8dd5c2e027bf21dd923337cbb4214f827"
backup_file:
    description: name of backup file created
    returned: changed and if backup=yes
    type: string
    sample: "/path/to/file.txt.2015-02-12@22:09~"
gid:
    description: group id of the file, after execution
    returned: success
    type: int
    sample: 100
group:
    description: group of the file, after execution
    returned: success
    type: string
    sample: "httpd"
owner:
    description: owner of the file, after execution
    returned: success
    type: string
    sample: "httpd"
uid:
    description: owner id of the file, after execution
    returned: success
    type: int
    sample: 100
mode:
    description: permissions of the target, after execution
    returned: success
    type: string
    sample: "0644"
size:
    description: size of the target, after execution
    returned: success
    type: int
    sample: 1220
state:
    description: state of the target, after execution
    returned: success
    type: string
    sample: "file"
'''


def split_pre_existing_dir(dirname):
    '''
    Return the first pre-existing directory and a list of
    the new directories that will be created.
    '''

    head, tail = os.path.split(dirname)
    if not os.path.exists(head):
        (pre_existing_dir, new_directory_list) = split_pre_existing_dir(head)
    else:
        return (head, [tail])
    new_directory_list.append(tail)
    return (pre_existing_dir, new_directory_list)


def adjust_recursive_directory_permissions(pre_existing_dir,
                                           new_directory_list,
                                           module,
                                           directory_args,
                                           changed):
    '''
    Walk the new directories list and make sure that permissions are
    as we would expect
    '''

    if len(new_directory_list) > 0:
        working_dir = os.path.join(pre_existing_dir,
                                   new_directory_list.pop(0))
        directory_args['path'] = working_dir
        changed = module.set_fs_attributes_if_different(directory_args,
                                                        changed)
        changed = adjust_recursive_directory_permissions(working_dir,
                                                         new_directory_list,
                                                         module,
                                                         directory_args,
                                                         changed)
    return changed


def main():
    module = AnsibleModule(argument_spec=dict(src=dict(required=False),
                                              # used to handle 'dest is a directory' via template, a slight hack
                                              original_basename=dict(required=False),
                                              content=dict(required=False, no_log=True),
                                              dest=dict(required=True),
                                              backup=dict(default=False, type='bool'),
                                              force=dict(default=True, aliases=['thirsty'], type='bool'),
                                              validate=dict(required=False, type='str'),
                                              directory_mode=dict(required=False),
                                              remote_src=dict(required=False, type='bool'),
                                              decompress=dict(required=False, type='bool')),
                           add_file_common_args=True,
                           supports_check_mode=True)

    src = os.path.expanduser(module.params['src'])
    dest = os.path.expanduser(module.params['dest'])
    backup = module.params['backup']
    force = module.params['force']
    original_basename = module.params.get('original_basename', None)
    validate = module.params.get('validate', None)
    follow = module.params['follow']
    mode = module.params['mode']
    remote_src = module.params['remote_src']
    decompress = module.params['decompress']

    if not os.path.exists(src):
        module.fail_json(msg="Source %s not found" % (src))
    if not os.access(src, os.R_OK):
        module.fail_json(msg="Source %s not readable" % (src))
    if os.path.isdir(src):
        module.fail_json(msg="Remote copy does not support recursive copy of directory: %s" % (src))

    checksum_src = module.sha1(src)
    checksum_dest = None
    # Backwards compat only.  This will be None in FIPS mode
    try:
        md5sum_src = module.md5(src)
    except ValueError:
        md5sum_src = None

    changed = False

    # Special handling for recursive copy - create intermediate dirs
    if original_basename and dest.endswith(os.sep):
        dest = os.path.join(dest, original_basename)
        dirname = os.path.dirname(dest)
        if not os.path.exists(dirname) and os.path.isabs(dirname):
            (pre_existing_dir, new_directory_list) = split_pre_existing_dir(dirname)
            os.makedirs(dirname)
            directory_args = module.load_file_common_arguments(module.params)
            directory_mode = module.params["directory_mode"]
            if directory_mode is not None:
                directory_args['mode'] = directory_mode
            else:
                directory_args['mode'] = None
            adjust_recursive_directory_permissions(pre_existing_dir, new_directory_list,
                                                   module, directory_args, changed)

    if os.path.exists(dest):
        if os.path.islink(dest) and follow:
            dest = os.path.realpath(dest)
        if not force:
            module.exit_json(msg="file already exists", src=src, dest=dest, changed=False)
        if (os.path.isdir(dest)):
            basename = os.path.basename(src)
            if original_basename:
                basename = original_basename
            dest = os.path.join(dest, basename)
        if os.access(dest, os.R_OK):
            checksum_dest = module.sha1(dest)
    else:
        if not os.path.exists(os.path.dirname(dest)):
            try:
                # os.path.exists() can return false in some
                # circumstances where the directory does not have
                # the execute bit for the current user set, in
                # which case the stat() call will raise an OSError
                os.stat(os.path.dirname(dest))
            except OSError, e:
                if "permission denied" in str(e).lower():
                    module.fail_json(msg="Destination directory %s is not accessible" % (os.path.dirname(dest)))
            module.fail_json(msg="Destination directory %s does not exist" % (os.path.dirname(dest)))
    if not os.access(os.path.dirname(dest), os.W_OK):
        module.fail_json(msg="Destination %s not writable" % (os.path.dirname(dest)))

    backup_file = None
    if checksum_src != checksum_dest or os.path.islink(dest):
        if not module.check_mode:
            try:
                if backup:
                    if os.path.exists(dest):
                        backup_file = module.backup_local(dest)
                # allow for conversion from symlink.
                if os.path.islink(dest):
                    os.unlink(dest)
                    open(dest, 'w').close()
                if validate:
                    # if we have a mode, make sure we set it on the temporary
                    # file source as some validations may require it
                    # FIXME: should we do the same for owner/group here too?
                    if mode is not None:
                        module.set_mode_if_different(src, mode, False)
                    if "%s" not in validate:
                        module.fail_json(msg="validate must contain %%s: %s" % (validate))

                    (rc, out, err) = module.run_command(validate % src)
                    if rc != 0:
                        module.fail_json(msg="failed to validate", exit_status=rc,
                                         stdout=out, stderr=err)
                if remote_src:
                    _, tmpdest = tempfile.mkstemp(dir=os.path.dirname(dest))
                    shutil.copy2(src, tmpdest)
                    module.atomic_move(tmpdest, dest)
                elif decompress:
                    extract_path = os.path.dirname(dest)
                    if not tarfile.is_tarfile(src):
                        module.fail_json(msg="Destination file %s is not tar.gz" % src)

                    if original_basename.endswith('.gz'):
                        open_type = "r:gz"
                    else:
                        open_type = "r"

                    try:
                        tar_file = tarfile.open(src, open_type)
                        file_names = tar_file.getnames()
                        if dest.endswith(os.sep):
                            for file_name in file_names:
                                tar_file.extract(file_name, dest)
                        else:
                            if len(file_names) > 1:
                                module.fail_json(msg="Source file %s includes mutil-files" % src)

                            extract_path = os.path.dirname(dest)
                            tar_file.extract(file_names[0], extract_path)
                    except (OSError, IOError) as e:
                        module.fail_json(msg="Failed extract file %s to %s :%s" % (dest, extract_path, str(e)))
                    except Exception as e:
                        module.fail_json(
                            msg="Unknown Exception(%s) in bocloud_copy module when extract %s to %s" % (
                            str(e), dest, extract_path))
                    finally:
                        tar_file.close()
                else:
                    module.atomic_move(src, dest)
            except IOError:
                module.fail_json(msg="failed to copy: %s to %s" % (src, dest),
                                 traceback=traceback.format_exc())
        changed = True
    else:
        changed = False

    if decompress:
        res_args = dict(dest=dest,
                        changed=changed)
    else:
        res_args = dict(dest=dest,
                        src=src,
                        md5sum=md5sum_src,
                        checksum=checksum_src,
                        changed=changed)
    if backup_file:
        res_args['backup_file'] = backup_file

    module.params['dest'] = dest
    if not module.check_mode and not decompress:
        file_args = module.load_file_common_arguments(module.params)
        res_args['changed'] = module.set_fs_attributes_if_different(file_args, res_args['changed'])

    module.exit_json(**res_args)


# import module snippets
from ansible.module_utils.basic import *

main()
