#!/usr/bin/python
# -*- coding: utf-8 -*-


DOCUMENTATION = '''
---
module: bocloud_logview
short_description: read specail log file content
description:
     - To imitate tail to get log file content. Every requirement is just get the
       the latest content of the log file
options:
  log_file:
    description:
      - The log file name that is read.
    required: true
    default: null
  position:
    description:
      - The start position that to read. The default value is zero.
        If the position is zero, the tool will read specail size from file tail.
    required: False
    default: 0
  presize:
    description:
      - The specail size that the tool will read. The default value is 1024.
    required: False
    default: 1024
requirements: []
author:
    - "Bocloud CMP team"
'''

EXAMPLES = '''
# read the 1024 file content from /var/log/messages tail
- bocloud_logview: log_file=/var/log/messages position=0 presize=1024
'''


def main():
    module = AnsibleModule(argument_spec=dict(log_file=dict(required=True),
                                              position=dict(required=False, default=0, type='int'),
                                              presize=dict(required=False, default=1024, type='int')),
                           supports_check_mode=True)
    log_file = module.params['log_file'].strip()
    position = module.params['position']
    presize = module.params['presize']

    if not os.path.exists(log_file):
        module.fail_json(msg="log file %s not found" % (log_file))
    if os.path.isdir(log_file):
        module.fail_json(msg="log file %s is not a file" % (log_file))
    if not os.access(log_file, os.R_OK):
        module.fail_json(msg="log file %s is not readable" % (log_file))

    curr_position = 0
    content = ""
    with open(log_file, 'r+b') as f:
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

    module.exit_json(content=content, curr_position=curr_position)


# import module snippets
from ansible.module_utils.basic import *

if __name__ == '__main__':
    main()
