from fastapi import FastAPI, HTTPException
import requests
from bs4 import BeautifulSoup
import uvicorn
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import re
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time


app = FastAPI()

CHROME_DRIVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver")

def extract_property_details(url):
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")

    address_element = soup.find(itemprop="streetAddress")
    if address_element is None:
        raise ValueError("Failed to extract the property address. The website structure might have changed.")

    address = address_element.get_text(strip=True)

    # Regular expression to match UK postcodes
    postcode_regex = r"[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}"
    postcode_match = re.search(postcode_regex, address)

    if postcode_match:
        postcode = postcode_match.group()
    else:
        raise ValueError("Failed to extract the postcode from the address. The postcode might not be included in the address.")

    # Find the price using a different approach
    price_tag = soup.find("span", text=re.compile("£"))
    if price_tag is None:
        raise ValueError("Failed to extract the price. The website structure might have changed.")

    price = float(price_tag.get_text(strip=True).replace("£", "").replace(",", ""))
    
    # Extract the property's street address
    street_address = " ".join(address.split()[:-1])
   
    # Find the price qualifier, if available
    qualifier_tag = soup.find(attrs={"data-testid": "priceQualifier"})
    if qualifier_tag is not None:
        price_qualifier = qualifier_tag.get_text(strip=True)
    else:
        price_qualifier = None

    return {
        "address": address,
        "street_address": street_address,
        "postcode": postcode,
        "price": price,
        "price_qualifier": price_qualifier
    }


def get_simd_data(postcode):
    url = "https://simd.scot/"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)

    driver.get(url)

    postcode_input = driver.find_element(By.ID, "postcode")
    postcode_input.send_keys(postcode)

    submit_button = driver.find_element(By.ID, "postcodeButton")

    # Wait for the submit button to be clickable and click it
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "postcodeButton"))) # noqa
    
    # Move to the element before clicking it
    actions = ActionChains(driver)
    actions.move_to_element(submit_button).click().perform()

    # Wait for the data to load
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "componenttable"))) # noqa

    # Extract data from the table
    table = driver.find_element(By.ID, "componenttable")
    rows = table.find_elements(By.TAG_NAME, "tr")

    simd_data = []
    row_count = len(driver.find_elements(By.XPATH, '//*[@id="componenttable"]/tbody/tr'))
    for i in range(2, row_count + 1):
        domain_name = driver.find_element(By.XPATH, f'//*[@id="componenttable"]/tbody/tr[{i}]/td[1]').text.strip()
        rank_text = driver.find_element(By.XPATH, f'//*[@id="componenttable"]/tbody/tr[{i}]/td[2]').text.strip()
        if rank_text:
            rank = int(re.sub(r"[^\d]", "", rank_text))
            simd_data.append({"domain": domain_name, "rank": rank})
            print(f"Extracted: {{'domain': '{domain_name}', 'rank': {rank}}}")

    print(f"simd_data: {simd_data}")
    return simd_data


def extract_section_data(soup, section_id):
    section_data = {}
    section = soup.find("a", {"href": f"#{section_id}"})
    
    if section:
        parent = section.find_parent("div", {"class": "tab-content"})
        section = parent.find("div", {"id": section_id})

        if section_id == "housing":
            info_pieces = section.find_all("div", {"class": "info-piece"})
            for info_piece in info_pieces:
                header = info_piece.find("h3").get_text(strip=True)
                description = info_piece.find("p").get_text(strip=True)
                pie_chart_data = {}
                for pie_segment in info_piece.find_all("div", {"class": "chartable"}):
                    label = pie_segment["data-label"]
                    value = float(pie_segment["data-value"])
                    pie_chart_data[label] = value
                section_data[header] = {
                    "description": description,
                    "pie_chart_data": pie_chart_data
                }
        else:
            for row in section.find_all("div", {"class": "row"}):
                for key, value in zip(row.find_all("div", {"class": "col-md-6"}),
                                      row.find_all("div", {"class": "col-md-6", "style": "font-weight: bold;"})):
                    key_text = key.get_text(strip=True).replace(":", "")
                    value_text = value.get_text(strip=True)
                    section_data[key_text] = value_text

    return section_data


def get_geographical_data(postcode):
    street_check_url = f"https://www.streetcheck.co.uk/postcode/{postcode.lower().replace(' ', '')}"
    response = requests.get(street_check_url)
    soup = BeautifulSoup(response.content, "html.parser")

    geographical_data = {
        "housing": extract_section_data(soup, "housing"),
        "summary": extract_section_data(soup, "summary"),
        "culture": extract_section_data(soup, "culture"),
        "employment": extract_section_data(soup, "employment"),
        "nearby": extract_section_data(soup, "nearby"),
        "broadband": extract_section_data(soup, "services"),
    }
    return geographical_data


def get_recent_sale_prices(url, street_address):
    # Use the street address to construct a URL for the "Recently sold & under offer" tab on Rightmove
    search_url = f"https://www.rightmove.co.uk/house-prices/detail.html?country=england&locationIdentifier=REGION%5E{street_address}&searchLocation={street_address}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.content, "html.parser")

    # Extract the recent sale prices
    sold_prices = []
    sold_price_tags = soup.find_all("td", {"class": "soldPrice"})
    for price_tag in sold_price_tags:
        price = float(price_tag.get_text(strip=True).replace("£", "").replace(",", ""))
        sold_prices.append(price)

    return sold_prices


@app.get("/property_analysis")
async def property_analysis(url: str):
    property_details = extract_property_details(url)
    postcode = property_details["postcode"]
    street_address = property_details["street_address"]

    simd_data = get_simd_data(postcode)
    geographical_data = get_geographical_data(postcode)
    recent_sale_prices = get_recent_sale_prices(postcode, street_address)

    return {
        "property_details": property_details,
        "simd_data": simd_data,
        "geographical_data": geographical_data,
        "recent_sale_prices": recent_sale_prices,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
