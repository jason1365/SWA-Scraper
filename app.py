import argparse
import configparser
import sys
import time
from datetime import datetime
from selenium import webdriver #using Firefox rather than 
#from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from twilio.rest import Client

CONFIG = configparser.ConfigParser()
CONFIG.read('config.ini')
ACCOUNT_SID = CONFIG['twilio']['account_sid']
AUTH_TOKEN = CONFIG['twilio']['auth_token']
FROM_NUMBER = CONFIG['twilio']['from_number']
TO_NUMBER = CONFIG['twilio']['to_number']

def main():
    """
    Perform a search on southwest.com for the given flight parameters.
    """
    args = parse_args()
    scrape(args)

def parse_args():
    """
    Parse the command line for search parameters.
    """
    parser = argparse.ArgumentParser(description='Process command line arguments')

    parser.add_argument(
        "--one-way",
        action="store_true",
        help="If present, the search will be limited to one-way tickets.")

    parser.add_argument(
        "--depart",
        "-d",
        type=str,
        help="Origin airport code.")

    parser.add_argument(
        "--arrive",
        "-a",
        type=str,
        help="Destination airport code.")

    parser.add_argument(
        "--departure-date",
        "-dd",
        type=str,
        help="Date of departure flight.")

    parser.add_argument(
        "--return-date",
        "-rd",
        type=str,
        help="Date of return flight.")

    parser.add_argument(
        "--passengers",
        "-p",
        action="store",
        type=int,
        help="Number of passengers.")

    parser.add_argument(
        "--max-price",
        "-mp",
        type=float,
        help="Ceiling on the total cost of flights.")

    parser.add_argument(
        "--interval",
        "-i",
        type=str,
        default=180,
        help="Refresh time period.")

    parser.add_argument(
        "--departure-time",
        "-dt",
        type=str,
        help="Time of departure flight.")

    parser.add_argument(
        "--return-time",
        "-rt",
        type=str,
        help="Time of return flight.")
    
    args = parser.parse_args()

    return args

def scrape(args):
    """
    Run scraper on Southwest.com.
    If we find a flight that meets our search parameters, send an SMS message.
    """
    while True:
        # PhantomJS is headless, so it doesn't open up a browser. PhantomJS is now depricated.
        #https://github.com/mozilla/geckodriver/releases
        options = Options()
        options.add_argument('-headless')
        browser = webdriver.Firefox(executable_path='./geckodriver', firefox_options=options) 
        browser.implicitly_wait(10)
        wait30 = WebDriverWait(browser, 30)
        wait10 = WebDriverWait(browser, 10)
               
        browser.get("https://www.southwest.com/")
        
        #Check to see if page is fully loaded
        try:
            testelement = wait30.until(EC.visibility_of_element_located((By.ID, "jb-booking-form-submit-button")))
        except:
            browser.quit()
            #retry the loop
            break

        if args.one_way:
            # Set one way trip with click event.
            one_way_elem = browser.find_element_by_id("trip-type-one-way")
            one_way_elem.click()

        # Set the departing airport.
        depart_airport = browser.find_element_by_id("air-city-departure")
        depart_airport.send_keys(args.depart)

        # Set the arrival airport.
        arrive_airport = browser.find_element_by_id("air-city-arrival")
        arrive_airport.send_keys(args.arrive)

        # Set departure date.
        depart_date = browser.find_element_by_id("air-date-departure")
        depart_date.clear()
        depart_date.send_keys(args.departure_date)

        # Set pay with points
        depart_date = browser.find_element_by_id("price-type-points")
        depart_date.click()

        if not args.one_way:
            # Set return date.
            return_date = browser.find_element_by_id("air-date-return")
            return_date.clear()
            return_date.send_keys(args.return_date)

        # Clear the readonly attribute from the element.
        passengers = browser.find_element_by_id("air-pax-count-adults")
        browser.execute_script("arguments[0].removeAttribute('readonly', 0);", passengers)
        passengers.click()
        passengers.clear()

        # Set passenger count.
        passengers.send_keys(args.passengers)
        passengers.click()
        search = browser.find_element_by_id("jb-booking-form-submit-button")
        search.click()

        outbound_array = []
        return_array = []

        # Webdriver might be too fast. Tell it to slow down.
        try:
            wait10.until(EC.element_to_be_clickable((By.ID, "faresOutbound")))
            faresOutboundTableID = "faresOutbound"
            faresReturnTableID = "faresReturn"
            outboundTimeXPath = "td/div/span[contains(@class, 'bugText')]"
            priceXPath = "td//label[contains(@class, 'product_price')]"
        except:
            #Needed to support flights to non-US airports            
            wait10.until(EC.element_to_be_clickable((By.ID, "b0Table")))
            faresOutboundTableID = "b0Table"
            faresReturnTableID = "b1Table"
            outboundTimeXPath = "(td[contains(@class, 'h6 h8')])[1]"
            priceXPath = "td[contains(@class, 'price')]/div/label/span"
            
        outbound_fares = browser.find_element_by_id(faresOutboundTableID)
        #outbound_rows = outbound_fares.find_elements_by_class_name("bugTableRow")
        outbound_tbody = outbound_fares.find_element_by_xpath("tbody")
        outbound_rows = outbound_tbody.find_elements_by_xpath("tr")
        for outbound_row in outbound_rows:
            outbound_time = outbound_row.find_elements_by_xpath(outboundTimeXPath)[0].text
            if(outbound_time == args.departure_time):
                outbound_prices = outbound_row.find_elements_by_xpath(priceXPath)

                for price in outbound_prices:
                    realprice = price.text.replace("$", "").replace(",", "").split()[0]
                    outbound_array.append(int(realprice))
        
                lowest_outbound_fare = min(outbound_array)
                break
            else:
                lowest_outbound_fare = 999999

        if not args.one_way:
            return_fares = browser.find_element_by_id(faresReturnTableID)
            return_tbody = return_fares.find_element_by_xpath("tbody")
            return_rows = return_tbody.find_elements_by_xpath("tr")
            for return_row in return_rows:
                return_time = return_row.find_elements_by_xpath(outboundTimeXPath)[0].text
                if(return_time == args.return_time):
                    return_prices = return_row.find_elements_by_xpath(priceXPath)
            
                    for price in return_prices:
                        realprice = price.text.replace("$", "").replace(",", "")
                        return_array.append(int(realprice))
        
                    lowest_return_fare = min(return_array)
                    break
                else:
                    lowest_return_fare = 99999999

            real_total = lowest_outbound_fare + lowest_return_fare

            print("[{:%Y-%m-%d %H:%M:%S}] Current Lowest Outbound Fare: {:,.2f}.".format(
                datetime.now(), lowest_outbound_fare))

            print("[{:%Y-%m-%d %H:%M:%S}] Current Lowest Return Fare: {:,.2f}.".format(
                datetime.now(), lowest_return_fare))

        else:
            real_total = lowest_outbound_fare
            print("[{:%Y-%m-%d %H:%M:%S}] Current Lowest Outbound Fare: {:,.2f}.".format(
                datetime.now(), lowest_outbound_fare))

        print("[{:%Y-%m-%d %H:%M:%S}] Current Lowest TOTAL Fare: {:,.2f}.".format(
            datetime.now(), real_total))

        # Found a good deal. Send a text via Twilio and then stop running.
        if real_total < int(args.max_price):
            print("[{:%Y-%m-%d %H:%M:%S}] Found a deal. Desired total: {:,.2f}. Current Total: {:,.2f}.".format(
                datetime.now(), args.max_price, real_total))

            client = Client(ACCOUNT_SID, AUTH_TOKEN)
            client.api.account.messages.create(
                to=TO_NUMBER,
                from_=FROM_NUMBER,
                body="[{:%Y-%m-%d %H:%M:%S}] Found a deal. Desired total: {:,.2f}. Current Total: {:,.2f}".format(
                    datetime.now(), args.max_price, real_total))

            print(
                "[{:%Y-%m-%d %H:%M:%S}] Text message sent!".format(datetime.now())
            )

            sys.exit()

        print(
            '''
            [{:%Y-%m-%d %H:%M:%S}] Couldn\'t find a deal under the amount you specified, {:,.2f}.
            Trying again to find cheaper prices...
            '''.format(datetime.now(), args.max_price)
        )

        browser.quit()        

        # Keep scraping according to the interval the user specified.
        time.sleep(int(args.interval) * 60)

if __name__ == "__main__":
    main()
