include $(top_srcdir)/common/python.mk

component_PYTHON = __init__.py \
		   common.py \
		   resources.py \
		   smoothstreamer.py \
		   admin_gtk.py \
		   avcc.py

componentdir = $(libdir)/flumotion/python/flumotion/component/consumers/smoothstreamer
component_DATA = \
	smoothstreamer.xml \
	smoothstreamer.glade

clean-local:
	rm -rf *.pyc *.pyo

EXTRA_DIST = $(component_DATA)
