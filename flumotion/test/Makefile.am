include $(top_srcdir)/common/python.mk
include $(top_srcdir)/common/trial.mk

BUILT_SOURCES = setup.py

TRIAL_ENV = $(top_srcdir)/env

setup.py: $(top_builddir)/config.status
	cd $(top_builddir) && $(SHELL) ./config.status $(subdir)/$@

EXTRA_DIST = __init__.py \
	test_dummy.py \
	test_fmp4.py \
	test_fmp4.xml \
	test_component_smoothstreamer.py

check-local: trial

clean-local:
	rm -f $(BUILT_SOURCES)
