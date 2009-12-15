include $(top_srcdir)/common/python.mk

component_PYTHON = __init__.py \
		   common.py \
		   resources.py \
		   httpfragstreamer.py \
		   hlsring.py \
		   mpegtssegmenter.py \
		   admin_gtk.py

componentdir = $(libdir)/flumotion/python/flumotion/component/consumers/httpfragstreamer
component_DATA = \
	httpfragstreamer.xml \
	httpfragstreamer.glade 

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)
