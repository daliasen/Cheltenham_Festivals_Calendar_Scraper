from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
import selenium

import time
import urllib.parse
import csv
from datetime import datetime, timedelta
import re
import os
import warnings

from config import sleep_duration_seconds, timeout_duration_seconds


def validate_config(festival_name: str,
                    selected_titles: list,
                    export_csv_flag: bool):
    """Validates configuration parameters.

    Args:
        festival_name (str): "Jazz", "Music", or "Science".
        selected_titles (list): A list of strings, or an empty list.
        export_csv_flag (bool): True of false.

    Raises:
        TypeError: If festival name does not match any of the predefined name.
        TypeError: If the selected titles are not in a list or the list contains
            types other than strings.
        TypeError: If the export flag is not a boolean.
    """
    festivals = ['Jazz', 'Music', 'Science']
    if festival_name not in festivals:
        raise ValueError('festival_name should be "Jazz", "Music", '
                         'or "Science" (case-sensitive).')

    if type(export_csv_flag) is not bool:
        raise TypeError('export_csv_flag should be either "True" or "False".')

    if type(selected_titles) is list:
        for i, title in enumerate(selected_titles):
            if type(title) is str:
                selected_titles[i] = title.strip().lower()
            else:
                raise TypeError('Event titles in selected_titles should be '
                                'strings.')
        return festival_name, selected_titles, export_csv_flag
    else:
        raise TypeError('selected_titles should be a list.')


def get_all_event_titles_and_urls(driver: selenium.webdriver):
    """Scrapes event titles and links from the festival page.

    Args:
        driver (selenium.webdriver): An object pointing to the required festival
            page.

    Returns:
        A dictionary where each key is an event title (str)
      and the corresponding value (str) is a link to that event's page.
    """
    wait = WebDriverWait(driver, timeout=timeout_duration_seconds)
    li_element_class = 'li.ais-Hits-item.c-event-search__results-item'
    more_info_links_by_title = {}
    while True:
        # Find all the list items with this class.
        wait.until(ec.presence_of_element_located((By.CSS_SELECTOR,
                                                   li_element_class)))
        event_elements = driver.find_elements(By.CSS_SELECTOR,
                                              li_element_class)

        # Scrape events on the current page.
        for event in event_elements:
            wait.until(ec.presence_of_element_located((By.TAG_NAME, 'h3')))
            title = event.find_element(By.TAG_NAME, 'h3').text

            # Find all hyperlink elements within the event.
            wait.until(ec.presence_of_all_elements_located((By.TAG_NAME, 'a')))
            links = event.find_elements(By.TAG_NAME, 'a')

            # Loop through all hyperlink elements and filter based on the text.
            more_info_links_by_title[title] = None
            for link in links:
                link_text = None
                try:
                    wait.until(ec.visibility_of(link))
                    # Get the text inside the hyperlink element.
                    link_text = link.text.strip()
                except TimeoutException:
                    # Skip this link, most likely not "More info".
                    warnings.warn('Skipping a link...')

                # If the text is "More info", assume it's the event page URL.
                if link_text == 'More info':
                    href = link.get_attribute('href')
                    more_info_links_by_title[title] = href
                    print(f'Found URL for "{title}": {href}')
                    break

        # Click the "Next" button.
        try:
            wait.until(ec.presence_of_element_located((By.CSS_SELECTOR,
                                                       'a[aria-label="Next"]')))
            next_button = driver.find_element(By.CSS_SELECTOR,
                                              'a[aria-label="Next"]')

            # Scroll the button into view to make sure it's clickable.
            ActionChains(driver).move_to_element(next_button).perform()

            # Check if the button is disabled (last page).
            if 'is-disabled' in next_button.get_attribute('class'):
                print('Last page scraped.')
                break
            print('Next page...')

            # Use JavaScript to click the button.
            driver.execute_script('arguments[0].click();', next_button)

            # Wait for new page elements to replace the old ones
            # to avoid StaleElementReferenceException.
            time.sleep(sleep_duration_seconds)

        except NoSuchElementException:
            print('Next button is not found.')
            break
        except ElementNotInteractableException:
            print('Next button is not interactable.')
            break

    return more_info_links_by_title


def get_event_details(driver: selenium.webdriver,
                      all_more_info_links_by_title: dict,
                      selected_titles: list[str]) -> dict:
    """
    Scrape details about each event from its corresponding web page.

    Args:
        driver: A Selenium webdriver.
        all_more_info_links_by_title: A dictionary where each key is an event
            title (str) and the corresponding value (str) is a link to that
            event's page.
        selected_titles: A list of strings where each string is an event title
            whose details should be scraped. If an empty list is supplied,
            all events are scraped.

    Returns:
        A dictionary with event titles as keys where each value is a dictionary
        containing the details about a particular event, it should have the
        following key/value pairs:
            'location': (str) Location, can be None or empty string
                if not know.
            'start_time': (datetime.datetime) Event start time.
            'end_time': (datetime.datetime) Event end time, set to 00:00 if not
                known.
            'description': (str) Event description, can be None or empty string
                if not know.
            'more_info_link': (str) A URL to the event page, will be appended to
                the description.
            'google_calendar_link': (str) A Google Calendar URL with event
                details encoded.
    """
    wait = WebDriverWait(driver, timeout=timeout_duration_seconds)
    details_by_title = {}
    # Go to each event web page.
    for title, more_info_link in all_more_info_links_by_title.items():
        if (not selected_titles) or (title.lower() in selected_titles):
            driver.get(more_info_link)

            print(title)
            details_by_title[title] = {}

            # Get the start time.
            start_time_object = None
            try:
                wait.until(ec.visibility_of_element_located((By.TAG_NAME,
                                                             'time')))
                time_string = driver.find_element(By.TAG_NAME, 'time').text
                if is_valid_time_format(time_string, '%a %d %b, %I.%M%p'):
                    start_time_object = datetime.strptime(time_string,
                                                          '%a %d %b, %I.%M%p')
                elif is_valid_time_format(time_string, '%a %d %b, %I%p'):
                    start_time_object = datetime.strptime(time_string,
                                                          '%a %d %b, %I%p')
                else:
                    warnings.warn(f'Could not find the start time'
                                  f'for {title} ({more_info_link})')
                if start_time_object:
                    start_time_object = start_time_object.replace(
                        year=datetime.now().year)
            except TimeoutException:
                warnings.warn('No date found.')
            details_by_title[title]['start_time'] = start_time_object

            # Get duration and location.
            location = None
            duration = None
            end_time_object = None
            try:
                wait.until(ec.presence_of_element_located(
                    (By.CLASS_NAME, 'c-meta__value.o-text')))
                all_elements_with_class = driver.find_elements(
                    By.CLASS_NAME, 'c-meta__value.o-text')
                for element in all_elements_with_class:
                    text = element.text
                    if 'United Kingdom' in text:
                        wait.until(ec.visibility_of(element.find_element(
                            By.TAG_NAME, 'a')))
                        link_text = element.find_element(By.TAG_NAME, 'a').text
                        location = text.replace(link_text, '').strip()

                    if 'minutes' in text:
                        match = re.search(r'(\d+)', text)
                        if match:
                            minutes = int(match.group(1))
                            duration = timedelta(minutes=minutes)

                    if duration and start_time_object:
                        end_time_object = start_time_object + duration

            except TimeoutException:
                print('Duration and location were not found.')

            # Set the end time to midnight if duration is not known.
            if start_time_object and not end_time_object:
                end_time_object = start_time_object + timedelta(days=1)
                end_time_object = end_time_object.replace(hour=0, minute=0)
                print('No duration found - set end of event to midnight.')

            details_by_title[title]['location'] = location
            details_by_title[title]['end_time'] = end_time_object

            # Get the description,
            # some event description class names differ therefor check several.
            description_class_names = ['o-block.o-text.o-text-block.o-grid__item.h-colstart--1.h-colend--9.h-phone-colstart--1.h-phone-colend--13.has-h-col.o-block--row-1',
                                       'o-block.o-text.o-text-block.o-grid__item.h-colstart--1.h-colend--8.h-phone-colstart--1.h-phone-colend--13.has-h-col.o-block--row-1',
                                       'o-block.o-text.o-text-block.o-grid__item.h-colstart--1.h-colend--7.h-phone-colstart--1.h-phone-colend--13.has-h-col.o-block--row-1',
                                       'o-block.o-text.o-text-block.o-grid__item.h-colstart--5.h-colend--13.h-phone-colstart--1.h-phone-colend--13.has-h-col.o-block--row-1']
            description_class_idx = 0
            description = None
            while not description:
                try:
                    description = driver.find_element(
                        By.CLASS_NAME,
                        description_class_names[description_class_idx]).text
                except NoSuchElementException:
                    ...  # Ignore this class name.
                description_class_idx += 1

            if description is None:
                warnings.warn(f'Could not find the description '
                              f'for "{title}" ({more_info_link})')

            details_by_title[title]['description'] = description
            details_by_title[title]['more_info_link'] = more_info_link

            event_details = details_by_title[title].copy()
            event_details['title'] = title
            calendar_link = generate_calendar_link(event_details)
            details_by_title[title]['google_calendar_link'] = calendar_link
            print(f'  {start_time_object.strftime('%A')}')
            print(f'  Google Calendar link: {calendar_link}')

    return details_by_title


def is_valid_time_format(time_str, time_format):
    try:
        datetime.strptime(time_str, time_format)
        return True
    except ValueError:
        return False


def generate_calendar_link(event_details: dict) -> str:
    """Encode event details into a Google Calendar link.

    Args:
        event_details: A dictionary with the following key/value pairs:
            'title': (str) Event title.
            'location': (str) Location, can be None or empty string
                if not know.
            'start_time': (datetime.datetime) Event start time.
            'end_time': (datetime.datetime) Event end time, set to 00:00 if not
                known.
            'description': (str) Event description, can be None or empty string
                if not know.
            'more_info_link': (str) A URL to the event page, will be appended to
                the description.

    Returns:
        A string containing a Google Calendar URL with event details encoded
        such that, when opened with a browser, it goes to a new event page with
        event details prefilled.
    """
    title = event_details['title']
    location = event_details['location']
    start_time = event_details['start_time']
    end_time = event_details['end_time']
    description = event_details['description']
    more_info_link = event_details['more_info_link']

    # Format date and time as "YYYYMMDDTHHMMSS".
    start_time_utc_str = start_time.strftime('%Y%m%dT%H%M%S')
    end_time_utc_str = end_time.strftime('%Y%m%dT%H%M%S')

    if not description:
        description = ''
    else:
        description = description + 2 * os.linesep
    description += more_info_link

    if not location:
        location = ''

    params = {'action': 'TEMPLATE',
              'text': title,
              'dates': f'{start_time_utc_str}/{end_time_utc_str}',
              'ctz': 'Europe/London',
              'details': description,
              'location': location}

    base_url = 'https://www.google.com/calendar/render'
    return f'{base_url}?{urllib.parse.urlencode(params)}'


def export_csv(event_details_by_title):
    """Exports a CSV file with even details.

    A CSV file called "events.csv" with a header row and each row below the
        header contains event details and a Google Calendar link.

    Args:
        event_details_by_title (dict): A dictionary with event titles as keys
            where each value is a dictionary containing the details about a
            particular event, it should have the following key/value pairs:
            'location': (str) Location, can be None or empty string
                if not know.
            'start_time': (datetime.datetime) Event start time.
            'end_time': (datetime.datetime) Event end time, set to 00:00 if not
                known.
            'description': (str) Event description, can be None or empty string
                if not know.
            'more_info_link': (str) A URL to the event page, will be appended to
                the description.
            'google_calendar_link': (str) A Google Calendar URL with event
                details encoded.
    """
    with open('events.csv', 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile,
                                delimiter='|',
                                quotechar='"',
                                quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(['date',
                             'weekday',
                             'start_time',
                             'end_time',
                             'title',
                             'description',
                             'location',
                             'google_calendar_link',
                             'more_info_link'])
        for title, details in event_details_by_title.items():
            csv_writer.writerow([details['start_time'].strftime('%b %d, %Y'),
                                 details['start_time'].strftime('%a'),
                                 details['start_time'].strftime('%H:%M'),
                                 details['end_time'].strftime('%H:%M'),
                                 title,
                                 details['description'],
                                 details['location'],
                                 details['google_calendar_link'],
                                 details['more_info_link']])
