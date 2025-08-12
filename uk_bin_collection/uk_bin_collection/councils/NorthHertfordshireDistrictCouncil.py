# direct URL works, but includes a token, so I'm using Selenium
# https://waste.nc.north-herts.gov.uk/w/webpage/find-bin-collection-day-show-details?webpage_token=c7c7c3cbc2f0478735fc746ca985b8f4221dea31c24dde99e39fb1c556b07788&auth=YTc5YTAwZmUyMGQ3&id=1421457

import re
import time
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil.parser import parse
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.wait import WebDriverWait

from uk_bin_collection.uk_bin_collection.common import *
from uk_bin_collection.uk_bin_collection.get_bin_data import AbstractGetBinDataClass


class CouncilClass(AbstractGetBinDataClass):

    def parse_data(self, page: str, **kwargs) -> dict:
        driver = None
        try:
            data = {"bins": []}

            user_paon = kwargs.get("paon")
            postcode = kwargs.get("postcode")
            web_driver = kwargs.get("web_driver")
            headless = kwargs.get("headless")
            url = "https://waste.nc.north-herts.gov.uk/w/webpage/find-bin-collection-day-input-address"

            driver = create_webdriver(web_driver, headless, None, __name__)
            driver.get(url)

            # Wait for page to load
            wait = WebDriverWait(driver, 20)
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

            # Enter postcode
            postcode_input = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "input.relation_path_type_ahead_search.form-control")
                )
            )
            postcode_input.clear()
            postcode_input.send_keys(postcode)

            # Wait for address dropdown and select address
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".relation_path_type_ahead_results_holder li")))
            address_xpath = f"//li[@aria-label and contains(@aria-label, '{user_paon}')]"
            matching_address = wait.until(EC.element_to_be_clickable((By.XPATH, address_xpath)))
            matching_address.click()
            time.sleep(2)  # Allow selection to register

            # Click the 'continue' button
            continue_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.bg-green[value='Select address and continue']"))
            )
            continue_button.click()

            # Wait for the results page to load. Wait for at least one record to be present.
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.listing_template_record")))
            # Add a small buffer for any final JS rendering
            time.sleep(3)

            # Create BeautifulSoup object
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # The page has two sections with identical data (for desktop and mobile views).
            # We only need to parse one. We target the desktop listing widget first.
            listing_widget = soup.find("div", {"data-widget_identifier": "listing_template_689307fd89e25"})
            if not listing_widget:
                # Fallback to the mobile view if the desktop one isn't found
                listing_widget = soup.find("div", {"data-widget_identifier": "listing_template_6893125e31f59"})

            if not listing_widget:
                # If neither widget is found, something is wrong with the page load.
                raise ValueError("Could not find the bin collection listing widget on the page.")

            # Find all bin records within the selected widget
            bin_records = listing_widget.select("div.listing_template_record")

            for record in bin_records:
                try:
                    # Extract bin type.
                    bin_type_element = record.select_one("td:first-child p span strong span")
                    if not bin_type_element:
                        continue
                    bin_type = bin_type_element.get_text(strip=True)

                    # Find the paragraph containing "Next collection" and extract the date
                    date_text = None
                    p_tags = record.select("p")
                    for p_tag in p_tags:
                        if "Next collection" in p_tag.get_text():
                            # The date text is the sibling immediately following the <br> tag
                            br_tag = p_tag.find("br")
                            if br_tag and br_tag.next_sibling:
                                date_text = str(br_tag.next_sibling).strip()
                                break
                    
                    if not date_text:
                        continue
                    
                    # Clean and parse the date
                    date_text_cleaned = remove_ordinal_indicator_from_date_string(date_text)
                    collection_date = datetime.strptime(date_text_cleaned, "%A %d %B %Y")
                    
                    # Add to the list of bins
                    data["bins"].append({
                        "type": bin_type,
                        "collectionDate": collection_date.strftime(date_format),
                    })

                except Exception:
                    # Ignore records that don't parse correctly, but allow the loop to continue.
                    continue
            
            if not data["bins"]:
                raise ValueError("No bin collection data could be extracted from the page")

            # Sort the bin collections by date
            data["bins"].sort(
                key=lambda x: datetime.strptime(x.get("collectionDate"), date_format)
            )

            return data

        except Exception as e:
            # Re-raise any exception caught during the process
            raise
        finally:
            if driver:
                driver.quit()
