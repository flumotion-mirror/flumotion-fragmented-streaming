AUTOMAKE_OPTIONS = dist-bzip2 no-dist-gzip 1.8

ACLOCAL_AMFLAGS = -I common

include $(srcdir)/common/common.mk
include $(srcdir)/common/pychecker.mk

SUBDIRS = flumotion common misc

EXTRA_DIST = \
	env\
	LICENSE.Flumotion \
	flumotion-fragmented-streaming.spec

PYCHECKER_WHITELIST = flumotion/component/*/*/*.py
PYCHECKER_BLACKLIST =

COVERAGE_MODULES = \
	flumotion.component.consumers.applestreamer
