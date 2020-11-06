#! /usr/bin/env python

from setuptools import setup

setup(
    name="my_reegis",
    version="0.0.1",
    author="Uwe Krien",
    author_email="uwe.krien@rl-institut.de",
    description="A reegis heat and power model of Berlin.",
    package_dir={"my_reegis": "my_reegis"},
    install_requires=[
        "oemof.solph >= 0.1.0",
        "pandas >= 0.17.0",
        "requests",
        "matplotlib",
        "numpy",
        "reegis",
        "deflex",
        "geopandas",
    ],
    extras_require={"dummy": ["oemof"]}
)
