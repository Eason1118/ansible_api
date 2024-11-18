#! /bin/sh

sudoer=$1
remove=$2

if [[ "$remove" != true ]]; then
    output1=$(grep -r "^$sudoer[[:space:]]" /etc/sudoers.d)
    output2=$(grep "^$sudoer[[:space:]]" /etc/sudoers)

    echo "$output1" | while read line
    do
        # remove filename 
        [ -z "$line" ] || echo "${line#*:}"
    done

    echo "$output2" | while read line
    do
        [ -z "$line" ] || echo "${line}"
    done
else
    `chmod 0660 /etc/sudoers`
    sed "s/^$sudoer[[:space:]].*//g" /etc/sudoers > /etc/sudoers_new
    rm -f /etc/sudoers
    mv /etc/sudoers_new /etc/sudoers
    `chmod 0440 /etc/sudoers`
fi
