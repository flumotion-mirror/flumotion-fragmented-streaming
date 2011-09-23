include $(top_srcdir)/common/python.mk

component_PYTHON = \
	__init__.py \
	packetizer.py \
	fmp4.py

componentdir = $(libdir)/flumotion/python/flumotion/component/muxers/fmp4
component_DATA = fmp4.xml

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)
