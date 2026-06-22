import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), "README.md")) as readme:
    README = readme.read()

setup(
    name="openimis-be-niyam",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    license="GNU AGPL v3",
    description="NIYAM deterministic pre-submission claim validation module for openIMIS.",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/shuv-amp/NIYAM",
    author="NIYAM",
    author_email="team@example.org",
    install_requires=[
        "django",
        "graphene-django",
        "openimis-be-core",
        "openimis-be-claim",
        "openimis-be-location",
        "openimis-be-medical",
        "openimis-be-product",
        "openimis-be-policy",
    ],
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Healthcare Industry",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3",
    ],
)
