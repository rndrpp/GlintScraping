"""Shared pytest helpers for the scrape_glints test suite.

Importing scrape_glints must NOT launch a browser or hit the network (the module
is side-effect-free on import). Tests build BeautifulSoup objects from saved HTML
fixtures and pass them to the pure helper functions.
"""

import os

from bs4 import BeautifulSoup

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


def load_soup(fixture_name):
    """Load a fixture HTML file and return it parsed as a BeautifulSoup object."""
    path = os.path.join(FIXTURES_DIR, fixture_name)
    with open(path, encoding='utf-8') as fh:
        return BeautifulSoup(fh.read(), 'lxml')
