from setuptools import setup

setup(name='gingham',
      version='0.1.0',
      description='ReST API testing language',
      url='http://github.com/tjb1982/gingham',
      author='Tom Brennan',
      author_email='tjb1982@gmail.com',
      license='MIT',
      packages=['gingham'],
      install_requires=[
          "requests",
          "pyyaml"
      ],
      zip_safe=False)
