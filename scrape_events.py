from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

import helpers
from config import festival_name, selected_titles, export_csv_flag


(festival_name,
 selected_titles,
 export_csv_flag) = helpers.validate_config(festival_name,
                                            selected_titles,
                                            export_csv_flag)

# Set up Chrome options.
chrome_options = Options()
chrome_options.add_argument('--headless')  # No browser window
chrome_options.add_argument('--disable-dev-shm-usage')

# Set up the ChromeDriver service.
service = Service('/usr/local/bin/chromedriver')

# Start the browser.
driver = webdriver.Chrome(service=service, options=chrome_options)

# Open the Cheltenham Festivals page.
url = f'https://www.cheltenhamfestivals.com/whats-on?menu%5BrelatedFestival%5D={festival_name}%20Festival'
driver.get(url)
# Title was loaded as HTML therefor waiting is handled by the driver.
print(f'Loaded "{driver.title}"')

# Find links to all events at the specified festival.
all_event_urls_by_title = helpers.get_all_event_titles_and_urls(driver)
print(f'Found {len(all_event_urls_by_title)} events.')

# Go to each link and get the description, time, location, and duration,
# and create Google calendar links.
if selected_titles:
    print('Going to the selected event pages...')
else:
    print('Going to each event page...')
event_details_by_title = helpers.get_event_details(driver,
                                                   all_event_urls_by_title,
                                                   selected_titles)

if export_csv_flag:
    helpers.export_csv(event_details_by_title)

# Close the browser.
driver.quit()
