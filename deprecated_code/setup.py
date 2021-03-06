#!/usr/bin/env python

#from setuptools import setup
from setuptools import setup, Extension
from distutils.sysconfig import get_config_var, get_config_vars
from setuptools.command.build_ext import build_ext
from subprocess import call
import os
import sys
import glob

# Bail on Python < 3
assert sys.version_info[0] >= 3


# MF. This is a workaround to be able to build the library with MacOS
if sys.platform == 'darwin':
	vars = get_config_vars()
	vars['LDSHARED'] = vars['LDSHARED'].replace('-bundle','-dynamiclib')
	os.environ["CC"] = "clang"




# NB. These are not really Python extensions (i.e., they do not
# Py_Initialize() and they do define main() ), we are just cheating to
# re-use the setuptools build support.

libarlffi = Extension('libarlffi',
                   sources = ['ffiwrappers/src/arlwrap.c', 'ffiwrappers/src/wrap_support.c', 'ffiwrappers/src/wrappingcore.c'],
                   undef_macros = ['NDEBUG'],
                   extra_compile_args = ['-Wno-strict-prototypes'],
                   libraries= ['cfitsio'],
		   optional=True,
)

packages = ['data_models', 'processing_library', 'processing_components', 'workflows', 'wrappers']
package_data = [i for p in packages for i in glob.glob(p+'/*/') + glob.glob(p+'/*/*/')]
setup(name='algorithm-reference-library',
      version='0.9',
      python_requires='>=3',
      description='Algorithm Reference Library for Radio Interferometry',
      long_description=open('README.md').read(),
      author='Tim Cornwell, Peter Wortmann, Bojan Nikolic, Montse Farreras',
      author_email='realtimcornwell@gmail.com',
      url='https://github.com/SKA-ScienceDataProcessor/algorithm-reference-library',
      license='Apache License Version 2.0',
      packages=(packages + package_data),
      test_suite="tests",
      tests_require=['pytest'],
      ext_modules = [libarlffi]
      )


# noinspection PyCompatibility
class CFFIBuild(build_ext):
        def run(self):
            super().run()

            cmd = [
                    "make",
                    "BUILD_LIB={}".format(self.build_lib)
                ]

            call(cmd)

#setup(name='FFI_Demo',
#    version='0.1',
#    python_requires='>=3',
#    description = "Demo for compilation of FFI-wrapped Python callable from C",
#    ext_modules = [libarlffi])
#,
#    cmdclass = {'build_ext': CFFIBuild})
