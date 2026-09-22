# GlintScraping

A command-line scraper that collects job listings from [Glints](https://glints.com) (Vietnam) using Selenium and BeautifulSoup.

## Overview

Glints is an online talent recruitment and career discovery platform headquartered in Singapore. It helps young talent build career readiness through internships and graduate jobs, developing the skill sets required in different careers.

This project searches the Glints Vietnam explore page for a keyword, loads every matching listing, and extracts the details of each job (name, company, location, salary, experience, type, field, posting/update dates, and required skills) into a CSV file. It can optionally send progress notifications by email.

The scraper drives a real Chrome browser, so it depends on the live Glints website and its current page markup.

## Requirements

- Python 3.12 (developed and tested against 3.12.13)
- Google Chrome installed locally (the scraper launches a real Chrome browser; the matching driver is downloaded automatically by `webdriver-manager`)
- Network access to `glints.com`
- Python packages listed in `requirements.txt`

## Installation

Install the runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

For development and running the test suite, install the dev dependencies as well (this also pulls in the runtime requirements and `pytest`):

```bash
python -m pip install -r requirements-dev.txt
```

## Configuration

Configuration values can be provided through CLI flags (see [Usage](#usage)), environment variables, or an interactive prompt. Environment variables can be placed in a `.env` file in the project root, which is loaded automatically via `python-dotenv`.

Copy the provided template and fill in your values:

```bash
cp .env.example .env
```

The `.env` file is git-ignored and must never be committed.

| Environment variable    | Purpose                                                         |
| ----------------------- | --------------------------------------------------------------- |
| `GLINTS_KEYWORD`        | Search keyword used on Glints (e.g. `data analyst`).            |
| `GLINTS_SENDER_EMAIL`   | Sender Gmail address used to send notification emails. When set, email notifications are enabled. |
| `GLINTS_APP_PASSWORD`   | Gmail app password (see below). Read from this environment variable only; it is never accepted as a CLI flag and is never logged. |
| `GLINTS_RECEIVER_EMAIL` | Receiver Gmail address for notifications.                       |
| `GLINTS_SLEEP`          | Per-page delay in seconds (default `5`).                        |

### Gmail app password

To send notification emails, the sender Gmail account must use an app password rather than your normal account password. Generate one at [Google App Passwords](https://myaccount.google.com/apppasswords) (a 16-character value such as `mmodryzaeyqeseoe`). For security, this value is read only from the `GLINTS_APP_PASSWORD` environment variable (or an interactive prompt) and can never be passed as a CLI flag.

## Usage

Run the scraper:

```bash
python scrape_glints.py --keyword "data analyst" --sleep 5
```

### CLI flags

| Flag                    | Description                                                     |
| ----------------------- | --------------------------------------------------------------- |
| `--keyword`             | Search keyword (falls back to `GLINTS_KEYWORD`).               |
| `--email` / `--no-email`| Enable or disable email notifications (mutually exclusive).    |
| `--sender`              | Sender Gmail address (falls back to `GLINTS_SENDER_EMAIL`).    |
| `--receiver`            | Receiver Gmail address (falls back to `GLINTS_RECEIVER_EMAIL`).|
| `--sleep`               | Per-page delay in seconds (falls back to `GLINTS_SLEEP`, default `5`). |

There is no flag for the Gmail app password; it is read only from the `GLINTS_APP_PASSWORD` environment variable.

Example enabling email notifications:

```bash
python scrape_glints.py \
  --keyword "data analyst" \
  --email \
  --sender you@gmail.com \
  --receiver recipient@gmail.com
```

### Interactive fallback

When a required value is missing and the program is run in an interactive terminal (stdin is a TTY), it prompts for the value:

1. Prompts for the search keyword if none was supplied.
2. Asks whether you want to receive progress notifications by email. If yes, it prompts for the sender email, the Gmail app password, and the receiver email.
3. After searching, it reports the number of jobs found and asks you to confirm whether to begin scraping (`y/n`). If no jobs are found, it lets you choose another keyword.
4. On successful setup it sends a confirmation email, and it sends further messages when the run finishes or hits an error (when email is enabled).

When stdin is **not** a TTY (for example in CI or a non-interactive shell) and a required value such as the keyword is missing, the program exits with a clear error message instead of hanging on a prompt.

## Output

The scraper writes two CSV files to the project root:

- `detail_urls.csv` — the list of job detail-page URLs discovered for the keyword.
- `ScrapedData.csv` — the scraped job records, with the columns: `Name`, `Company`, `Location`, `Salary`, `Experience`, `Type`, `Field`, `Posted`, `Updated`, `Skill Required`, and `Link`.

Both files are generated output and are listed in `.gitignore`, so they are not tracked in version control.

## Testing

The test suite covers the pure, browser-free extraction helpers using saved HTML fixtures (no Chrome or network access required). Run it with:

```bash
python -m pytest tests/ -v
```

## Limitations

- The scraper requires a live Google Chrome browser and network access to `glints.com`; it cannot run without them.
- It relies on the current Glints page markup, including hashed CSS class names and absolute XPaths. When the site changes its layout, these selectors may break and require updating.
- Only the Glints Vietnam explore page is supported.

## Author

Vi Pham
