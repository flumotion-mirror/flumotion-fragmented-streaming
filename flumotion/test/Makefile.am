include $(top_srcdir)/common/python.mk
include $(top_srcdir)/common/trial.mk

BUILT_SOURCES = setup.py

TRIAL_ENV = $(top_srcdir)/env

setup.py: $(top_builddir)/config.status
	cd $(top_builddir) && $(SHELL) ./config.status $(subdir)/$@

EXTRA_DIST = __init__.py \
	test_dummy.py \
	test_hls_ring.py \
	test_mpegts.py \
	test_mpegts.xml \
	test_resource.py \
	test_ts_segmenter.py \
	test_ts_segmenter.xml

check-local: trial

clean-local:
	rm -f $(BUILT_SOURCES)
