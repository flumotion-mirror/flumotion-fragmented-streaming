AC_INIT(flumotion-fragmented-streaming,
   0.7.0.2,
   https://code.area51.fluendo.com/private/trac/newticket?component=flumotion-fragmentedstreaming,
   flumotion-fragmented-streaming)

AS_VERSION

AS_NANO

AM_INIT_AUTOMAKE([foreign tar-pax])

AC_SUBST_FILE(AUTHORS)
AUTHORS=$srcdir/AUTHORS

AC_SUBST(FLU_REQ, 0.5.4)
AC_SUBST(PYGST_REQ, 0.10.11)
AC_SUBST(GST_REQ, 0.10.22)

dnl Start commit used to autogenrate ChangeLog from 'git log'
AC_SUBST(GIT_LOG_START_COMMIT, "df8212259ce446d0393976eeb9256be1b7380332")

dnl Add parameters for aclocal
AC_SUBST(ACLOCAL_AMFLAGS, "-I common")
AC_CONFIG_MACRO_DIR([common])


AS_AC_EXPAND(LIBDIR, $libdir)
AC_MSG_NOTICE(Storing library files in $LIBDIR)

AS_AC_EXPAND(DATADIR, $datadir)
AC_MSG_NOTICE(Storing data files in $DATADIR)

AS_AC_EXPAND(SYSCONFDIR, $sysconfdir)
AC_MSG_NOTICE(Storing configuration files in $SYSCONFDIR)

AS_AC_EXPAND(LOCALSTATEDIR, $localstatedir)
AC_MSG_NOTICE(Using localstatedir $LOCALSTATEDIR)

dnl check for python
AS_PATH_PYTHON(2.3)
dnl useful when we compile our own python modules
dnl AM_CHECK_PYTHON_HEADERS(,[AC_MSG_ERROR(could not find Python headers)])

export PYTHONPATH=$PYGTK_DIR:$PYTHONPATH

dnl check for epydoc
AC_CHECK_PROG(EPYDOC, epydoc, yes, no)
AM_CONDITIONAL(HAVE_EPYDOC, test "x$EPYDOC" = "xyes")

dnl check for pychecker
AC_CHECK_PROG(PYCHECKER, pychecker, yes, no)
AM_CONDITIONAL(HAVE_PYCHECKER, test "x$PYCHECKER" = "xyes")

dnl check for Twisted
AS_PYTHON_IMPORT(twisted,
  [
  AC_MSG_CHECKING(for Twisted >= 1.3.0)
  prog="
import sys
import twisted.copyright
minver = '1.3.0'
if twisted.copyright.version < minver:
    sys.exit(1)
sys.exit(0)
"
  if $PYTHON -c "$prog" 1>&AC_FD_CC 2>&AC_FD_CC
  then
    AC_MSG_RESULT(found)
  else
    AC_MSG_RESULT(too old)
    AC_MSG_ERROR([You need at least version 1.3.0 of Twisted])
  fi
  ]
  ,
  AC_MSG_ERROR([You need at least version 1.3.0 of Twisted])
)

dnl check for flumotion
PKG_CHECK_MODULES(FLUMOTION, flumotion >= $FLU_REQ)
FLUMOTION_DIR="`$PKG_CONFIG --variable=flumotiondir flumotion`"
AC_MSG_NOTICE([Flumotion code base directory is $FLUMOTION_DIR])
AC_SUBST(FLUMOTION_DIR)

PREAMBLE=`cat $srcdir/misc/preamble.py`


dnl output stuff
FLUMOTION_SETUP(flumotion/test/setup.py, $FLUMOTION_DIR, $PREAMBLE, fragmented-streaming)
FLUMOTION_SETUP(misc/setup.py, $FLUMOTION_DIR, $PREAMBLE, fragmented-streaming)

dnl output stuff
AC_OUTPUT(
Makefile
common/Makefile
misc/Makefile
flumotion/Makefile
flumotion/component/Makefile
flumotion/component/consumers/Makefile
flumotion/component/consumers/smoothstreamer/Makefile
flumotion/component/muxers/Makefile
flumotion/component/muxers/fmp4/Makefile
flumotion/component/muxers/mpegts/Makefile
flumotion/project/Makefile
flumotion/project/fragmentedstreaming.py
flumotion/test/Makefile
flumotion-fragmented-streaming.spec
)
