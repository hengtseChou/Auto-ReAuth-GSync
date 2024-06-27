from setuptools import setup

with open("README.md") as f:
    long_description = f.read()

with open("requirements.txt") as f:
    requirements = f.readlines()

setup(
    name="Auto-ReAuth-GSync",
    version="0.1.0",
    install_requires=requirements,
    description="",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Heng-Tse Chou",
    author_email="hankthedev@gmail.com",
    url="https://github.com/hengtseChou/Auto_ReAuth-GSync",
    license="MIT",
    keywords="sync",
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        "Development Status :: 3 - Alpha",
        # Indicate who your project is intended for
        "Intended Audience :: End Users/Desktop",
        "Operating System :: Unix",
        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        "Programming Language :: Python :: 3",
    ],
    entry_points={
        "console_scripts": [
            "argsync = src.main:cli",
        ],
    },
)