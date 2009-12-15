include $(top_srcdir)/common/python.mk

component_PYTHON = \
	__init__.py \
	mpegts.py \
	keyframescounter.py

componentdir = $(libdir)/flumotion/python/flumotion/component/muxers/mpegts
component_DATA = mpegts.xml

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)
