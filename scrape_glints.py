"""Scrape job listings from glints.com (Vietnam) using Selenium + BeautifulSoup.

This module is safe to import: nothing runs at import time. The scraping flow is
orchestrated by main(), which is only invoked under the __main__ guard.

Configuration is read from environment variables (optionally via a .env file) and
argparse CLI flags. The Gmail app password is read ONLY from the GLINTS_APP_PASSWORD
environment variable (or an interactive prompt) and is never logged or accepted as a
CLI flag.
"""

import argparse
import getpass
import logging
import os
import smtplib
import sys
from time import sleep

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# Default per-page delay in seconds (matches the original sleep_time).
DEFAULT_SLEEP_TIME = 5
EMAIL_SUBJECT = '-- Glints Data Scrape'
BASE_URL = 'https://glints.com'
EXPLORE_URL = 'https://glints.com/vn/opportunities/jobs/explore'


# ---------------------------------------------------------------------------
# Pure, browser-free helpers (unit-testable)
# ---------------------------------------------------------------------------
def extract_detail_urls(soup):
    """Return the list of absolute detail-view URLs found in a listings page soup.

    Mirrors the original selection: 'div.JobCardsc__JobCardWrapper... > a',
    prefixing each href with 'https://glints.com'.
    """
    posts = soup.select('div[class="JobCardsc__JobCardWrapper-sc-1f9hdu8-1 dPPDau"]>a')
    detail_urls = []
    for post in posts:
        detail_urls.append(BASE_URL + post['href'])
    return detail_urls


def extract_job_details(soup, link):
    """Extract job details from a detail-view page soup.

    Returns a dict with keys exactly:
    ['Name','Company','Location','Salary','Experience','Type','Field',
     'Posted','Updated','Skill Required','Link'].

    Uses the same CSS selectors as the original scraper; missing fields are set to
    None instead of raising.
    """
    item_dict = {}

    # Name
    try:
        item_dict['Name'] = soup.select(
            'div[class="TopFoldsc__JobOverviewHeader-sc-kklg8i-24 gfOGEj"]')[0].text
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Name field: %s', exc)
        item_dict['Name'] = None

    # Company Name
    try:
        item_dict['Company'] = soup.select(
            'div[class="TopFoldsc__JobOverViewCompanyName-sc-kklg8i-5 eLQvRY"]>a')[0].text
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Company field: %s', exc)
        item_dict['Company'] = None

    # Location
    try:
        item_dict['Location'] = soup.select(
            'div[class="TopFoldsc__JobOverViewCompanyLocation-sc-kklg8i-6 gLATOW"]>span>a')[0].text
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Location field: %s', exc)
        item_dict['Location'] = None

    # Salary range
    try:
        salary_ele = soup.select(
            'div[class="TopFoldsc__JobOverViewInfoContainer-sc-kklg8i-8 fgSCsF"]>div>span')[0]
        item_dict['Salary'] = salary_ele.text
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Salary field: %s', exc)
        item_dict['Salary'] = None

    # Experience, Type, Field
    info = soup.select('div[class="TopFoldsc__JobOverViewInfo-sc-kklg8i-9 EWOdY"]')
    info_list = []
    for ite in info:
        info_list.append(ite.text)

    item_dict['Experience'] = None
    item_dict['Type'] = None

    for ele in info_list:
        if 'kinh nghiệm' in ele:
            item_dict['Experience'] = ele
            info_list.remove(ele)
    for ele in info_list:
        if ('Việc' in ele) or ('Thực Tập' in ele):
            item_dict['Type'] = ele
            info_list.remove(ele)
    try:
        item_dict['Field'] = info_list[0]
    except IndexError as exc:
        logger.debug('Missing Field field: %s', exc)
        item_dict['Field'] = None

    # Posted and Updated time
    try:
        posted = soup.select('span[class="TopFoldsc__PostedAt-sc-kklg8i-13 vnaHT"]')
        posted = posted[0].text.split(' ', 1)[1]
        item_dict['Posted'] = posted
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Posted field: %s', exc)
        item_dict['Posted'] = None

    try:
        updated = soup.select('span[class="TopFoldsc__UpdatedAt-sc-kklg8i-14 kjxTBC"]')
        updated = updated[0].text.split(' ', 1)[1]
        item_dict['Updated'] = updated
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Updated field: %s', exc)
        item_dict['Updated'] = None

    # Skill required
    try:
        skills = soup.select(
            'div[class="TagStyle__TagContainer-sc-66xi2f-1 gtZZMG aries-tag '
            'Skillssc__TagOverride-sc-11imayw-3 fyJqX"]')
        skills_str = ''
        for i in range(len(skills)):
            if i == (len(skills) - 1):
                sub = skills[i].text
            else:
                sub = skills[i].text + ', '
            skills_str = skills_str + sub
        item_dict['Skill Required'] = skills_str
    except (IndexError, AttributeError) as exc:
        logger.debug('Missing Skill Required field: %s', exc)
        item_dict['Skill Required'] = None

    # Link
    item_dict['Link'] = link

    return item_dict


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def send_email(sender_gmail, sender_apppass, receiver, subject, message):
    """Send a notification email via Gmail SMTP (starttls). Never logs the password."""
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(sender_gmail, sender_apppass)
    server.sendmail(sender_gmail, receiver, f'Subject: {subject}\n{message}')
    server.quit()
    logger.info('-- Email setup successfully')


# ---------------------------------------------------------------------------
# Browser / driver
# ---------------------------------------------------------------------------
def build_driver():
    """Construct a Chrome webdriver with the original options."""
    options = webdriver.ChromeOptions()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument("--start-maximized")
    options.add_argument("--disable-popup-blocking")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options)
    driver.implicitly_wait(0)
    logger.info("-- Driver setup and browser opened")
    return driver


def search_keyword(driver, keyword):
    """Type the keyword into the search box and click search."""
    search_box = driver.find_element(
        By.XPATH,
        '//*[@id="__next"]/div/div[3]/div[2]/div[2]/div[2]/div[2]/div/div/div[1]/div/input')
    sleep(1)
    search_box.send_keys(Keys.CONTROL + "a")
    search_box.send_keys(Keys.DELETE)
    search_box.send_keys(keyword)
    sleep(1.5)
    search_button = driver.find_element(
        By.XPATH,
        '//*[@id="__next"]/div/div[3]/div[2]/div[2]/div[2]/div[2]/div/div/div[3]/button')
    search_button.click()


# ---------------------------------------------------------------------------
# Configuration / CLI
# ---------------------------------------------------------------------------
class Config:
    """Runtime configuration resolved from CLI flags, env vars and prompts."""

    def __init__(self):
        self.keyword = None
        self.email_enabled = None
        self.sender_gmail = None
        self.sender_apppass = None
        self.receiver = None
        self.sleep_time = DEFAULT_SLEEP_TIME


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Scrape job listings from glints.com (Vietnam).')
    parser.add_argument('--keyword', help='Search keyword (or set GLINTS_KEYWORD).')
    email_group = parser.add_mutually_exclusive_group()
    email_group.add_argument(
        '--email', dest='email', action='store_true', default=None,
        help='Enable email notifications.')
    email_group.add_argument(
        '--no-email', dest='email', action='store_false', default=None,
        help='Disable email notifications.')
    parser.add_argument('--sender', help='Sender Gmail address (or GLINTS_SENDER_EMAIL).')
    parser.add_argument('--receiver', help='Receiver Gmail address (or GLINTS_RECEIVER_EMAIL).')
    parser.add_argument(
        '--sleep', type=float, default=None,
        help=f'Per-page delay in seconds (default {DEFAULT_SLEEP_TIME}).')
    return parser.parse_args(argv)


def _prompt_if_tty(prompt):
    """Return input() from the prompt if stdin is a TTY, else None."""
    if sys.stdin.isatty():
        return input(prompt)
    return None


def resolve_config(args):
    """Resolve configuration from CLI args, env vars and interactive prompts.

    Raises SystemExit with a clear message when a required value is missing and
    stdin is not a TTY.
    """
    cfg = Config()

    # Sleep time
    if args.sleep is not None:
        cfg.sleep_time = args.sleep
    elif os.getenv('GLINTS_SLEEP'):
        cfg.sleep_time = float(os.getenv('GLINTS_SLEEP'))

    # Keyword
    cfg.keyword = args.keyword or os.getenv('GLINTS_KEYWORD')
    if not cfg.keyword:
        cfg.keyword = _prompt_if_tty('-- Search keyword: ')
    if not cfg.keyword:
        raise SystemExit(
            'Error: search keyword is required. Provide --keyword or set GLINTS_KEYWORD.')

    # Email enabled?
    if args.email is not None:
        cfg.email_enabled = args.email
    else:
        env_email = os.getenv('GLINTS_SENDER_EMAIL')
        if env_email:
            cfg.email_enabled = True
        else:
            answer = _prompt_if_tty(
                '-- Do you want to recieve notifications by email? (y/n)  ')
            if answer is None:
                cfg.email_enabled = False
            else:
                cfg.email_enabled = answer.lower().startswith('y')

    if cfg.email_enabled:
        cfg.sender_gmail = args.sender or os.getenv('GLINTS_SENDER_EMAIL')
        if not cfg.sender_gmail:
            cfg.sender_gmail = _prompt_if_tty('-- Sender gmail: ')
        if not cfg.sender_gmail:
            raise SystemExit(
                'Error: sender email is required for notifications. '
                'Provide --sender or set GLINTS_SENDER_EMAIL.')

        # App password: environment variable ONLY (never a CLI flag).
        cfg.sender_apppass = os.getenv('GLINTS_APP_PASSWORD')
        if not cfg.sender_apppass and sys.stdin.isatty():
            cfg.sender_apppass = getpass.getpass('-- Sender gmail app password: ')
        if not cfg.sender_apppass:
            raise SystemExit(
                'Error: Gmail app password is required for notifications. '
                'Set the GLINTS_APP_PASSWORD environment variable.')

        cfg.receiver = args.receiver or os.getenv('GLINTS_RECEIVER_EMAIL')
        if not cfg.receiver:
            cfg.receiver = _prompt_if_tty('-- Reciever gmail: ')
        if not cfg.receiver:
            raise SystemExit(
                'Error: receiver email is required for notifications. '
                'Provide --receiver or set GLINTS_RECEIVER_EMAIL.')

    return cfg


# ---------------------------------------------------------------------------
# Runtime flow
# ---------------------------------------------------------------------------
def open_explore_page(driver):
    """Open the explore page and dismiss the intro notification."""
    sleep(1)
    driver.get(EXPLORE_URL)
    logger.info('-- Glints accessed')

    # Scroll page to pop up the message
    sleep(7)
    html = driver.find_element(By.TAG_NAME, 'html')
    html.send_keys(Keys.DOWN)

    # Escape
    sleep(5)
    html.send_keys(Keys.ESCAPE)


def confirm_keyword(driver, cfg):
    """Run the search for the configured keyword and confirm results are present.

    Preserves the original interactive confirmation loop when stdin is a TTY.
    Returns True when scraping should proceed, False otherwise.
    """
    while True:
        keyword = cfg.keyword

        search_keyword(driver, keyword)
        sleep(4)
        element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                'div[class="MainContainersc__MainBody-sc-iy5ixg-2 dyvvBG"]')))
        html_of_interest = driver.execute_script('return arguments[0].innerHTML', element)
        soup = BeautifulSoup(html_of_interest, 'lxml')

        jobcnt = soup.select('h1[class="ExploreTabsc__JobCount-sc-gs9c0s-4 iAPXyD"]')
        try:
            jobcnt = int(jobcnt[0].text.split(' ', 1)[0])
        except (IndexError, AttributeError, ValueError) as exc:
            logger.warning('-- No job found, choose another keyword (%s)', exc)
            new_keyword = _prompt_if_tty('-- Search keyword: ')
            if new_keyword:
                cfg.keyword = new_keyword
                continue
            return False

        if jobcnt != 0:
            answer = _prompt_if_tty(
                f'-- {jobcnt} jobs found in Vietnam, do you want to begin the scraper? (y/n)  ')
            if answer is None or answer.lower().startswith("y"):
                logger.info('-- Keyword confirmed: %s', keyword)
                return True
            logger.info('-- Please choose another keyword')
            new_keyword = _prompt_if_tty('-- Search keyword: ')
            if new_keyword:
                cfg.keyword = new_keyword
                continue
            return False

        logger.info('-- No job found, please choose another keyword')
        new_keyword = _prompt_if_tty('-- Search keyword: ')
        if new_keyword:
            cfg.keyword = new_keyword
            continue
        return False


def notify(cfg, message):
    """Send an email notification if enabled, logging (not raising) on failure."""
    if not cfg.email_enabled:
        return
    try:
        send_email(cfg.sender_gmail, cfg.sender_apppass, cfg.receiver,
                   EMAIL_SUBJECT, message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning('-- Failed to send email notification: %s', exc)


def send_startup_email(cfg):
    """Verify email credentials by sending the startup notification.

    Preserves the original retry loop when stdin is a TTY.
    """
    if not cfg.email_enabled:
        return
    message = 'Glints data scraping program initialized successfully'
    while True:
        try:
            send_email(cfg.sender_gmail, cfg.sender_apppass, cfg.receiver,
                       EMAIL_SUBJECT, message)
            return
        except (smtplib.SMTPException, OSError) as exc:
            logger.error('-- Fail to send email, please check inputs (%s)', exc)
            if not sys.stdin.isatty():
                raise SystemExit(
                    'Error: failed to send startup email; check sender/receiver/app password.')
            cfg.sender_gmail = input('-- Sender gmail: ')
            cfg.sender_apppass = os.getenv('GLINTS_APP_PASSWORD') or \
                getpass.getpass('-- Sender gmail app password: ')
            cfg.receiver = input('-- Reciever gmail: ')


def load_all_listings(driver, cfg):
    """Scroll the explore page until all listings are loaded."""
    driver.refresh()
    sleep(7)
    html = driver.find_element(By.TAG_NAME, 'html')
    html.send_keys(Keys.DOWN)

    sleep(5)
    html.send_keys(Keys.ESCAPE)

    logger.info('-- Loading pages to get detail urls')
    while True:
        page_height = driver.execute_script("return document.body.scrollHeight")
        target_height = page_height - 1220
        driver.execute_script("window.scrollTo(0, %s);" % target_height)
        sleep(2)
        try:
            state = driver.find_element(
                By.XPATH,
                '//*[@id="__next"]/div/div[3]/div[2]/div[2]/div[2]/div[4]/div[2]/div[2]/span')
        except NoSuchElementException:
            continue
        if state.text == 'Đã tải lên tất cả cơ hội việc làm':
            logger.info('-- All page loaded')
            notify(cfg, 'All page loaded, ready to extract urls')
            break


def collect_detail_urls(driver):
    """Extract detail-view URLs from the loaded explore page and save to CSV."""
    element = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            'div[class="MainContainersc__MainBody-sc-iy5ixg-2 dyvvBG"]')))
    html_of_interest = driver.execute_script('return arguments[0].innerHTML', element)
    soup = BeautifulSoup(html_of_interest, 'lxml')

    detail_urls = extract_detail_urls(soup)
    logger.info('-- Total urls extracted: %s', len(detail_urls))

    df = pd.DataFrame({'Detail Urls': detail_urls})
    df.to_csv('detail_urls.csv')
    logger.info('-- Detail urls saved to file detail_urls.csv')
    sleep(5)
    return detail_urls


def scrape_detail_page(driver, link):
    """Load a detail page in the driver and return the extracted details dict."""
    element = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            'div[class="GlintsContainer-sc-ap1z3q-0 iUnyrV"]')))
    html_of_interest = driver.execute_script('return arguments[0].innerHTML', element)
    soup = BeautifulSoup(html_of_interest, 'lxml')
    return extract_job_details(soup, link)


def scrape_all_details(driver, cfg):
    """Visit each saved detail URL, scrape it, and write ScrapedData.csv."""
    urls = pd.read_csv('detail_urls.csv')
    urls = urls['Detail Urls']

    logger.info('-- URL count: %s, estimated time: %ss', len(urls), len(urls) * 5)
    logger.info('-- Progress:')
    cnt = 0
    df_list = []
    total_urls = len(urls)

    try:
        for link in urls.iloc:
            driver.get(link)
            sleep(cfg.sleep_time)
            try:
                df_list.append(scrape_detail_page(driver, link))
            except (TimeoutException, WebDriverException) as exc:
                logger.warning(
                    '-- Error raised: %s ,at url number %s. Passed to the next url',
                    exc.__class__, cnt)
                continue

            cnt += 1
            if cnt % 10 == 0:
                logger.info('%s%%', round((cnt / total_urls) * 100, 3))

        logger.info('-- Successfully scraped all data!!')
        notify(
            cfg,
            f'Successfully scraped all data!!\nTotal data records: {len(df_list)}\n'
            f'Total urls: {len(urls)}')
    except (TimeoutException, WebDriverException, OSError) as err:
        logger.error('-- Program shut down at url number %s. Error: %s', cnt, err.__class__)
        notify(
            cfg,
            f'Error raised at url number {cnt}, program stopped\nData saved\n'
            f'Total urls: {len(urls)}')
    finally:
        df = pd.DataFrame(df_list)
        df.to_csv('ScrapedData.csv')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv=None):
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s')

    args = parse_args(argv)
    cfg = resolve_config(args)

    driver = build_driver()
    try:
        open_explore_page(driver)
        if not confirm_keyword(driver, cfg):
            logger.info('-- No keyword confirmed, exiting.')
            return
        send_startup_email(cfg)
        load_all_listings(driver, cfg)
        collect_detail_urls(driver)
        scrape_all_details(driver, cfg)
    finally:
        try:
            driver.quit()
        except WebDriverException as exc:
            logger.debug('-- Error while quitting driver: %s', exc)


if __name__ == "__main__":
    main()
