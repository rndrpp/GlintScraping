"""Tests for scrape_glints.extract_job_details (browser-free)."""

from conftest import load_soup

from scrape_glints import extract_job_details

EXPECTED_KEYS = [
    'Name', 'Company', 'Location', 'Salary', 'Experience', 'Type', 'Field',
    'Posted', 'Updated', 'Skill Required', 'Link',
]


def test_returns_all_expected_keys():
    soup = load_soup('job_detail_full.html')
    result = extract_job_details(soup, 'https://glints.com/vn/opportunities/jobs/x')
    assert list(result.keys()) == EXPECTED_KEYS


def test_happy_path_parses_populated_fields():
    link = 'https://glints.com/vn/opportunities/jobs/senior-python'
    result = extract_job_details(load_soup('job_detail_full.html'), link)

    assert result['Name'] == 'Senior Python Developer'
    assert result['Company'] == 'Acme Corp'
    assert result['Location'] == 'Ho Chi Minh City'
    assert result['Salary'] == '20.000.000 - 30.000.000 VND'
    assert result['Link'] == link


def test_experience_type_field_vietnamese_classification():
    result = extract_job_details(load_soup('job_detail_full.html'), 'link')

    # Experience is the info block containing 'kinh nghiệm'.
    assert result['Experience'] == '3 - 5 năm kinh nghiệm'
    # Type is the info block containing 'Việc' (or 'Thực Tập').
    assert result['Type'] == 'Việc toàn thời gian'
    # Field is the remaining info block after Experience and Type are removed.
    assert result['Field'] == 'Công nghệ thông tin'


def test_posted_and_updated_strip_leading_token():
    result = extract_job_details(load_soup('job_detail_full.html'), 'link')

    # Source splits on the first space only: 'Đăng 2 ngày trước' -> '2 ngày trước'.
    assert result['Posted'] == '2 ngày trước'
    # 'Cập nhật 1 ngày trước' -> 'nhật 1 ngày trước' (split(' ', 1)[1]).
    assert result['Updated'] == 'nhật 1 ngày trước'


def test_skills_joined_with_comma_space():
    result = extract_job_details(load_soup('job_detail_full.html'), 'link')
    assert result['Skill Required'] == 'Python, Django, PostgreSQL'


def test_missing_fields_yield_none():
    # The 'missing' fixture only has Name plus two info blocks (Type + Field).
    result = extract_job_details(load_soup('job_detail_missing.html'), 'link')

    assert result['Name'] == 'Intern Data Analyst'
    assert result['Company'] is None
    assert result['Location'] is None
    assert result['Salary'] is None
    assert result['Posted'] is None
    assert result['Updated'] is None
    # No 'kinh nghiệm' info block present -> Experience stays None.
    assert result['Experience'] is None
    # 'Thực Tập' info block is classified as Type.
    assert result['Type'] == 'Thực Tập'
    # Remaining info block becomes Field.
    assert result['Field'] == 'Phân tích dữ liệu'


def test_skill_required_empty_string_when_no_skill_tags():
    # No skill tags -> the loop produces an empty string (not None).
    result = extract_job_details(load_soup('job_detail_missing.html'), 'link')
    assert result['Skill Required'] == ''
