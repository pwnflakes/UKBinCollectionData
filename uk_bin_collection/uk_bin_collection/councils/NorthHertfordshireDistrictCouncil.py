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

            driver = create_webdriver(web_driver, headless) # Removed unused args for clarity
            driver.get(url)

            wait = WebDriverWait(driver, 20)
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

            # --- Selenium navigation (remains the same) ---
            postcode_input = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "input.relation_path_type_ahead_search.form-control")
                )
            )
            postcode_input.clear()
            postcode_input.send_keys(postcode)

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".relation_path_type_ahead_results_holder li")))
            
            address_xpath = f"//li[@aria-label and contains(@aria-label, '{user_paon}')]"
            matching_address = wait.until(EC.element_to_be_clickable((By.XPATH, address_xpath)))
            matching_address.click()
            time.sleep(2)

            continue_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.bg-green[value='Select address and continue']"))
            )
            continue_button.click()

            # --- Start of Robust Parsing Logic ---

            # Wait for any of the bin records to appear on the page.
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.listing_template_record")))
            time.sleep(3) # Extra buffer for any JS rendering

            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Use a set to automatically handle duplicate entries from mobile/desktop views
            collections = set()

            # Find ALL bin records on the page. The class "listing_template_record" is
            # a much more stable selector than a data-widget_identifier with a random ID.
            bin_records = soup.select("div.listing_template_record")

            for record in bin_records:
                try:
                    # The internal selectors are already quite robust as they rely on table structure
                    bin_type_element = record.select_one("td:first-child p span strong span")
                    if not bin_type_element:
                        continue
                    bin_type = bin_type_element.get_text(strip=True)

                    date_text = None
                    # Find the paragraph containing the "Next collection" text
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
                    
                    # Add the parsed data tuple to the set. Duplicates will be ignored.
                    collections.add((bin_type, collection_date))

                except Exception:
                    # If one record fails to parse, skip it and continue with the others
                    continue
            
            if not collections:
                raise ValueError("No bin collection data could be extracted from the page")

            # Convert the set of unique collections into the required dictionary format
            for bin_type, collection_date in collections:
                 data["bins"].append({
                    "type": bin_type,
                    "collectionDate": collection_date.strftime(date_format),
                })

            # Sort the final list by date
            data["bins"].sort(
                key=lambda x: datetime.strptime(x.get("collectionDate"), date_format)
            )

            return data

        except Exception as e:
            raise
        finally:
            if driver:
                print("Closing webdriver.")
                driver.quit()
