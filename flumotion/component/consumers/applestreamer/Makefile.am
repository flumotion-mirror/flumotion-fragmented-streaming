include $(top_srcdir)/common/python.mk

component_PYTHON = __init__.py \
		   common.py \
		   resources.py \
		   applestreamer.py \
		   hlsring.py \
		   mpegtssegmenter.py \
		   admin_gtk.py

componentdir = $(libdir)/flumotion/python/flumotion/component/consumers/applestreamer
component_DATA = \
	applestreamer.xml \
	applestreamer.glade

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)
