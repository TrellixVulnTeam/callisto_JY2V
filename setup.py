#!/usr/bin/env python
# Always prefer setuptools over distutils
from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / 'readme.md').read_text(encoding='utf-8')

setup(
    name='CallistoLinux',
    version='1.0.0',
    description='Callisto controller for linux systems.',
    url='https://github.com/lbarosi/callisto',
    author='Luciano Barosi',
    author_email='lbarosi@df.ufcg.edu.br',
    classifiers=[  # Optional
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Radioastronomy',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3 :: Only',
    ],
    keywords='radioastronomy, observation planning, callisto',
    packages=find_packages(where='./'),  # Required
    python_requires='>=3.9, <4',

    install_requires=['pandas', 'pyserial', 'watchdog'],
    project_urls={  # Optional
        'Bug Reports': 'https://github.com/lbarosi/callisto/issues',
        'Source': 'https://github.com/lbarosi/callisto/',
    },
)
