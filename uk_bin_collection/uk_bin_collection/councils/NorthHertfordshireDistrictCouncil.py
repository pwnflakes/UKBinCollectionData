# File: NHDC.py (Revised with Enhanced Wait Condition)

import re
import time
from datetime import datetime

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from uk_bin_collection.uk_bin_collection.common import (
    create_webdriver,
    date_format,
    remove_ordinal_indicator_from_date_string,
)
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
            
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

            driver = create_webdriver(web_driver=web_driver, headless=headless, user_agent=user_agent)
            driver.get(url)

            wait = WebDriverWait(driver, 30) # Increased wait time slightly for safety
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

            # --- Selenium navigation ---
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

            # --- NEW ROBUST WAIT CONDITION ---
            # Instead of just waiting for the container, we now wait for the container
            # AND for it to contain the text "Next collection". This ensures the JS has finished rendering.
            wait.until(EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, "div.listing_template_record"), "Next collection"
            ))

            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            collections = set()
            bin_records = soup.select("div.listing_template_record")
            
            # Diagnostic print to show in logs how many records were found
            print(f"Found {len(bin_records)} bin records to process.")

            for record in bin_records:
                try:
                    bin_type_element = record.select_one("td:first-child p span strong span")
                    if not bin_type_element:
                        continue
                    bin_type = bin_type_element.get_text(strip=True)

                    date_text = None
                    p_tags = record.select("p")
                    for p_tag in p_tags:
                        if "Next collection" in p_tag.get_text():
                            br_tag = p_tag.find("br")
                            if br_tag and br_tag.next_sibling:
                                date_text = str(br_tag.next_sibling).strip()
                                break
                    
                    if not date_text:
                        continue
                    
                    date_text_cleaned = remove_ordinal_indicator_from_date_string(date_text)
                    collection_date = datetime.strptime(date_text_cleaned, "%A %d %B %Y")
                    
                    collections.add((bin_type, collection_date))
                except Exception:
                    continue
            
            if not collections:
                raise ValueError("No bin collection data could be extracted from the page")

            for bin_type, collection_date in collections:
                 data["bins"].append({
                    "type": bin_type,
                    "collectionDate": collection_date.strftime(date_format),
                })

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
