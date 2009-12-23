include $(top_srcdir)/common/python.mk

component_PYTHON = \
	uuid.py

componentdir = $(libdir)/flumotion/python/flumotion/common

clean-local:
	rm -rf *.pyc *.pyo

# We do not install __init__.py since it would override flumotion's
EXTRA_DIST = __init__.py
