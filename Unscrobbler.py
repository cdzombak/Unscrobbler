import argparse
import json
import logging
import os
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Final, Optional, Dict, IO, Set

import dateutil.parser
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

load_dotenv()


EXIT_SUCCESS: Final = 0
EXIT_ERROR: Final = 1


# noinspection PyShadowingNames
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


@dataclass(frozen=True)
class UnscrobblerConfig:
    lastfm_username: str
    lastfm_password: str
    dry_run: bool
    delete_artists: Set[str]
    delete_titles: Set[str]
    max_removals: int
    log_file: Optional[IO[str]]
    year: Optional[int]
    first_hr: Optional[int]
    last_hr: Optional[int]
    start_page: Optional[int]
    geckodriver_log_file: Optional[IO[str]]
    max_page: Optional[int]


def _unscrobbler_log_deleted_item(logfile: Optional[IO[str]], d: Dict):
    if not logfile or logfile.closed:
        return
    json.dump(d, logfile, allow_nan=False, sort_keys=True)


def unscrobbler(cfg: UnscrobblerConfig) -> int:
    if cfg.dry_run:
        logging.info('This is a dry run. No destructive actions will be performed.')
    else:
        logging.info('--no-dry-run is given. **Destructive actions may be performed.**')

    login_page_url: Final = "https://www.last.fm/login"
    user_library_page_url: Final = f"https://www.last.fm/user/{cfg.lastfm_username}/library"

    library_page_num: int = 1
    if cfg.start_page and cfg.start_page > 0:
        library_page_num = cfg.start_page

    # should_delete() support: extract some config & logic to aliases here, so
    # I don't have to rename a ton of variables/constants from upstream,
    # possibly introducing bugs.
    use_hours: Final = cfg.first_hr is not None and cfg.last_hr is not None
    use_year: Final = cfg.year is not None
    start_hour: Final = cfg.first_hr
    stop_hour: Final = cfg.last_hr
    year_to_use: Final = cfg.year

    def should_delete(track_name, artist_name, parsed_timestamp):
        delete = False

        # Delete if track matches artist/track name list (exactly):
        if artist_name in cfg.delete_artists:
            delete = True
        if track_name in cfg.delete_titles:
            delete = True

        if delete:
            # Don't delete if track is outside of specified time
            if use_hours:
                if start_hour > stop_hour:
                    # spans midnight
                    delete = parsed_timestamp.hour >= start_hour or parsed_timestamp.hour <= stop_hour
                elif stop_hour > start_hour:
                    delete = start_hour <= parsed_timestamp.hour <= stop_hour
                else:
                    delete = parsed_timestamp.hour == start_hour
            if use_year:
                delete = parsed_timestamp.year == year_to_use

        return delete

    # Check if there are scrobbles to delete on the page
    def to_delete_exists(driver):
        sections: List[WebElement] = driver.find_elements(by=By.CSS_SELECTOR,
                                                          value="section.tracklist-section")
        section: WebElement
        for section in sections:
            table: WebElement = section.find_element(by=By.TAG_NAME, value="table")
            table_body: WebElement = table.find_element(by=By.TAG_NAME, value="tbody")

            row_num = 0
            for row in table_body.find_elements(by=By.TAG_NAME, value="tr"):
                row_num += 1
                track_name = row.find_element(by=By.CLASS_NAME,
                                              value="chartlist-name").find_element(by=By.TAG_NAME,
                                                                                   value="a").text
                artist_name = row.find_element(by=By.CLASS_NAME,
                                               value="chartlist-artist").find_element(
                    by=By.TAG_NAME, value="a").text
                timestamp = row.find_element(by=By.CLASS_NAME,
                                             value="chartlist-timestamp").find_element(
                    by=By.TAG_NAME, value="span")
                timestamp_string = timestamp.get_attribute("title")
                parsed_timestamp = dateutil.parser.parse(timestamp_string)

                delete = should_delete(track_name=track_name, artist_name=artist_name,
                                       parsed_timestamp=parsed_timestamp)
                if delete:
                    return True

        return False

    deletions = 0
    logging.debug("Launching Firefox")
    with webdriver.Firefox(service=webdriver.FirefoxService(log_output=cfg.geckodriver_log_file)) as driver:
        driver.get(login_page_url)
        WebDriverWait(driver, 10).until(lambda d: "Login" in d.title)
        driver.find_element(by=By.ID, value="id_username_or_email").send_keys(cfg.lastfm_username)
        driver.find_element(by=By.ID, value="id_password").send_keys(cfg.lastfm_password)
        WebDriverWait(driver, 10).until(expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, "button[name='submit']")))
        submit_attempts = 0
        while True:
            submit_attempts += 1
            try:
                driver.find_element(by=By.CSS_SELECTOR, value="button[name='submit']").click()
                break
            except Exception as e:
                logging.error(e)
                print("[Error] Can't access the webpage. You need to accept the cookies popup.")
                if submit_attempts >= 12:
                    return EXIT_ERROR
                print("        Will retry in 10 seconds.")
                print("        Press Ctrl+C to stop the program and exit.")
                time.sleep(10)

        while True and deletions < cfg.max_removals:
            library_page_url = f"{user_library_page_url}?page={library_page_num}"
            logging.info(f"on page #{library_page_num}; url {library_page_url}")
            driver.get(library_page_url)
            WebDriverWait(driver, 10).until(lambda d: "Library" in d.title)
            attempt = 0
            while to_delete_exists(driver) and deletions < cfg.max_removals:
                attempt += 1
                logging.info(f"attempt #{attempt}")
                sections: List[WebElement] = driver.find_elements(by=By.CSS_SELECTOR,
                                                                  value="section.tracklist-section")
                section: WebElement
                for section in sections:
                    if deletions >= cfg.max_removals:
                        break

                    table: WebElement = section.find_element(by=By.TAG_NAME, value="table")
                    table_body: WebElement = table.find_element(by=By.TAG_NAME, value="tbody")

                    row_num = 0
                    for row in table_body.find_elements(by=By.TAG_NAME, value="tr"):
                        if deletions >= cfg.max_removals:
                            break

                        row_num += 1
                        track_name = row.find_element(by=By.CLASS_NAME,
                                                      value="chartlist-name").find_element(
                            by=By.TAG_NAME, value="a").text
                        artist_name = row.find_element(by=By.CLASS_NAME,
                                                       value="chartlist-artist").find_element(
                            by=By.TAG_NAME, value="a").text
                        timestamp = row.find_element(by=By.CLASS_NAME,
                                                     value="chartlist-timestamp").find_element(
                            by=By.TAG_NAME, value="span")
                        timestamp_string = timestamp.get_attribute("title")
                        parsed_timestamp = dateutil.parser.parse(timestamp_string)

                        if should_delete(track_name=track_name, artist_name=artist_name,
                                         parsed_timestamp=parsed_timestamp):
                            chartlist_more = row.find_element(by=By.CLASS_NAME,
                                                              value="chartlist-more")
                            driver.execute_script(
                                f"window.scrollTo(0, {timestamp.location['y'] - 100})")
                            ActionChains(driver).move_to_element_with_offset(timestamp, 0,
                                                                             100).perform()
                            timestamp.click()
                            while True:
                                try:
                                    if not cfg.dry_run:
                                        chartlist_more.find_element(by=By.CLASS_NAME,
                                                                    value="chartlist-more-button").click()
                                        time.sleep(0.1)
                                        chartlist_more.find_element(by=By.CLASS_NAME,
                                                                    value="more-item--delete").click()
                                        time.sleep(0.1)
                                    break
                                except Exception as e:
                                    logging.error(
                                        f"Problem deleting {track_name} ({artist_name}) ({timestamp_string}). This should be fixed automatically.", e)

                            _unscrobbler_log_deleted_item(cfg.log_file, {
                                "track_title": track_name,
                                "artist_name": artist_name,
                                "timestamp": timestamp_string,
                                "timestamp_parsed": str(parsed_timestamp),
                            })
                            deletions += 1

                driver.get(library_page_url)

            try:
                next_button = driver.find_element(by=By.CSS_SELECTOR,
                                                  value=".pagination-next > a:nth-child(1)")
            except NoSuchElementException:
                logging.info("Finished last page! Exiting.")
            if cfg.max_page and library_page_num >= cfg.max_page:
                logging.debug(f"Reached max page ({cfg.max_page}). Exiting.")
                break

            library_page_num += 1
            driver.get(next_button.get_attribute("href"))

        logging.info(f"{'[dry run]' if is_dry_run else '' }Removed {deletions} Scrobbles "
                     f"(configured max: {cfg.max_removals}).")
        return EXIT_SUCCESS


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='Unscrobbler',
        description="Remove Last.fm Scrobbles by artist or track titles and optionally by "
                    "the Scrobble's year and/or time of day.",
    )
    parser.add_argument('-a', '--artists-file', type=str,
                        help='Path of a list of artists to remove. If given with --titles-file, '
                             'Scrobbles that match artist _or_ title will be deleted. '
                             '(File must be plain text, newline-delimited.)')
    parser.add_argument('-t', '--titles-file', type=str,
                        help='Path of a list of track titles to remove. If given with '
                             '--artists-file, Scrobbles that match artist _or_ title will be '
                             'deleted. (File must be plain text, newline-delimited.)')
    parser.add_argument('--no-dry-run', action='store_true', default=False,
                        help='Run the Unscrobbler for real. (Dry run - ie. no destructive action '
                             'is taken - is the default.)')
    parser.add_argument('--year', type=int, default=None,
                        help='Only remove Scrobbles from the given year.')
    parser.add_argument('--start-page', type=int, default=1,
                        help='Last.fm library page to start at.')
    parser.add_argument('--max-page', type=int, default=20,
                        help='Last.fm library page to end at.')
    parser.add_argument('--first-hr', type=int, default=None,
                        help='First hour of the day in which to remove Scrobbles (0-23). (If used, '
                             '--last-hr must also be given.)')
    parser.add_argument('--last-hr', type=int, default=None,
                        help='Last hour of the day in which to remove Scrobbles (0-23). (If used, '
                             '--first-hr must also be given.)')
    parser.add_argument('--log-dir', type=str, default=None,
                        help='If given, data about deleted Scrobbles will be logged in this '
                             'directory.')
    parser.add_argument('-m', '--max-removals', type=int, default=100,
                        help='Maximum number of Scrobbles to remove.')
    args = parser.parse_args()

    is_dry_run = not args.no_dry_run

    if not args.artists_file and not args.titles_file:
        eprint('At least one of --artists-file or --titles-file must be given.')
        sys.exit(EXIT_ERROR)
    if args.year is not None:
        if args.year < 1970 or args.year > 2999:
            eprint(f"Given --year '{args.year}' seems incorrect.")
            sys.exit(EXIT_ERROR)
    if (args.first_hr and not args.last_hr) or (args.last_hr and not args.first_hr):
        eprint('--first-hr and --last-hr must be used together.')
        sys.exit(EXIT_ERROR)
    if (args.first_hr and (args.first_hr < 0 or args.first_hr > 23)) \
            or (args.last_hr and (args.last_hr < 0 or args.last_hr > 23)):
        eprint('--first-hr and --last-hr must be between 0-23 (inclusive).')
        sys.exit(EXIT_ERROR)
    if args.max_removals <= 0:
        eprint('--max-removals must be a positive number.')
        sys.exit(EXIT_ERROR)

    delete_artists = set()
    delete_titles = set()

    if args.artists_file:
        with open(args.artists_file, 'rt') as f:
            delete_artists = {line.rstrip('\n') for line in f}
    if args.titles_file:
        with open(args.titles_file, 'rt') as f:
            delete_titles = {line.rstrip('\n') for line in f}

    log_file_path = None
    geckodriver_log_path = None
    now_str = datetime.now().strftime('%Y%m%d-%H%M%S')
    if args.log_dir:
        log_file_path = Path(args.log_dir) / f"unscrobbler_{now_str}{'_dryrun' if is_dry_run else ''}.log.jsonl"
        geckodriver_log_path = Path(args.log_dir) / f"geckodriver_{now_str}.log"

    lastfm_user = os.getenv('LASTFM_USERNAME')
    lastfm_pass = os.getenv('LASTFM_PASSWORD')
    if not lastfm_user or not lastfm_pass:
        eprint('Last.fm username & password must be set using environment variables.')
        eprint('Copy .env.sample to .env and fill it out to provide credentials.')
        sys.exit(EXIT_ERROR)

    result = EXIT_SUCCESS
    try:
        with open(geckodriver_log_path, mode='xt', encoding='utf8') if geckodriver_log_path \
                else nullcontext() as geckodriver_log_file:
            with open(log_file_path, mode='xt', encoding='utf8') if log_file_path \
                    else nullcontext() as log_file:
                result = unscrobbler(UnscrobblerConfig(
                    lastfm_username=lastfm_user,
                    lastfm_password=lastfm_pass,
                    dry_run=is_dry_run,
                    delete_artists=delete_artists,
                    delete_titles=delete_titles,
                    year=args.year,
                    log_file=log_file,
                    first_hr=args.first_hr,
                    last_hr=args.last_hr,
                    max_removals=args.max_removals,
                    start_page=args.start_page,
                    geckodriver_log_file=geckodriver_log_file,
                    max_page=args.max_page,
                ))
    except FileExistsError as e:
        logging.exception(e)
        result = EXIT_ERROR
    sys.exit(result)
