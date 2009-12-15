AUTOMAKE_OPTIONS = dist-bzip2 no-dist-gzip 1.8

SUBDIRS = flumotion common  misc

EXTRA_DIST = \
	env.in \
	LICENSE.Flumotion \
	flumotion-fragmentssplitter.spec

PYCHECKER_WHITELIST = flumotion/component/*/*/*.py
PYCHECKER_BLACKLIST =

COVERAGE_MODULES = \
	flumotion.component.consumers.fragmentssplitter
