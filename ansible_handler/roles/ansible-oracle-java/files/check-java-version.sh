#!/bin/bash
# simple script to query the existance of specific Oracle jdk executable, if installed.
#
# @return: JSON string : { "found": true/false, "not_found": true/false }
#

PACKAGE="\"$1\""

output=$(java -version 2>&1)
result=$?

line=$(java -version 2>&1 | grep $PACKAGE | grep -iv openjdk | wc -l)

if [[ $line =~ 0 ]]; then
  if [[ $result =~ 0 ]]; then
    echo '{ "not_installed": false,  "found": false , "not_found": true  }'
  else
    echo '{ "not_installed": true,  "found": false , "not_found": true  }'
  fi
else
  echo '{ "not_installed": false,  "found": true  , "not_found": false }'
fi
