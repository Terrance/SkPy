from setuptools import setup
from os import path

setup(name="SkPy",
      description="An unofficial Python library for interacting with the Skype HTTP API.",
      long_description=open(path.join(path.abspath(path.dirname(__file__)), "README.rst"), "r").read(),
      packages=["skpy"],
      install_requires=["beautifulsoup4", "requests"],
      tests_require=["beautifulsoup4", "requests", "responses"],
      classifiers=["Development Status :: 4 - Beta",
                   "Intended Audience :: Developers",
                   "Topic :: Communications :: Chat",
                   "Topic :: Software Development :: Libraries"])
