#!/bin/sh
set -x

aclocal -I m4 -I common || exit 1
# autoheader || exit 1
autoconf || exit 1
automake -a -c -f || exit 1
echo "./autogen.sh $@" > autoregen.sh
chmod +x autoregen.sh
./configure $@
