"""Tests for scrape_glints.extract_detail_urls (browser-free)."""

from conftest import load_soup

from scrape_glints import extract_detail_urls


def test_extract_detail_urls_returns_absolute_urls_in_order():
    soup = load_soup('listing.html')
    urls = extract_detail_urls(soup)

    assert urls == [
        'https://glints.com/vn/opportunities/jobs/job-1',
        'https://glints.com/vn/opportunities/jobs/job-2',
        'https://glints.com/vn/opportunities/jobs/job-3',
    ]


def test_extract_detail_urls_ignores_non_jobcard_anchors():
    soup = load_soup('listing.html')
    urls = extract_detail_urls(soup)

    # The "Not a job card" anchor lives in a different wrapper class and must be skipped.
    assert 'https://glints.com/vn/ignore-me' not in urls
    assert len(urls) == 3


def test_extract_detail_urls_empty_input_returns_empty_list():
    soup = load_soup('listing_empty.html')
    assert extract_detail_urls(soup) == []
