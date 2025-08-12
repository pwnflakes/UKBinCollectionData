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

            # Wait for the results page to load
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.listing_template_record")))

            # --- Start of corrected parsing logic ---
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Using a set to avoid duplicates from desktop/mobile views
            collections = set()

            # Find all bin records on the page
            bin_records = soup.select("div.listing_template_record")

            for record in bin_records:
                try:
                    # Extract bin type from the first row of the table
                    bin_type_element = record.select_one("table td p strong span")
                    if not bin_type_element:
                        continue
                    bin_type = bin_type_element.get_text(strip=True)

                    # Find the paragraph containing "Next collection"
                    date_p_tag = record.find("p", string=re.compile(r"Next collection"))
                    if not date_p_tag:
                        continue
                    
                    # The date is the text immediately following the <br> tag
                    br_tag = date_p_tag.find("br")
                    if not br_tag or not br_tag.next_sibling:
                        continue
                    
                    date_text = str(br_tag.next_sibling).strip()
                    
                    # Clean and parse the date
                    date_text = remove_ordinal_indicator_from_date_string(date_text)
                    collection_date = datetime.strptime(date_text, "%A %d %B %Y")
                    
                    # Add to our set of collections to handle duplicates
                    collections.add((bin_type, collection_date))

                except Exception:
                    # Ignore records that don't parse correctly and continue
                    continue
            
            # Convert the set of collections into the required dictionary format
            for bin_type, collection_date in collections:
                data["bins"].append({
                    "type": bin_type,
                    "collectionDate": collection_date.strftime(date_format),
                })
            
            if not data["bins"]:
                raise ValueError("No bin collection data could be extracted from the page")

            # Sort the bin collections by date
            data["bins"].sort(
                key=lambda x: datetime.strptime(x.get("collectionDate"), date_format)
            )

            return data
            # --- End of corrected parsing logic ---

        except Exception as e:
            # Add logging here if needed, then re-raise
            raise
        finally:
            if driver:
                driver.quit()
