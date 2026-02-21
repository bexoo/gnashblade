from math import floor
import requests
import json
import sqlite3
import time
import datetime


# Not using this function anymore
def getPrices():
    page_count = 1
    prices = {}
    page_counter = 0

    for page_counter in range(page_count):
        count_string = str(page_counter)
        res = requests.get(
            "https://api.guildwars2.com/v2/commerce/prices?page="
            + count_string
            + "&page_size=200"
        )
        response = json.loads(res.text)

        if page_counter == 0:
            page_count = res.headers["X-Page-Total"]

        for j in range(200):
            id = response[j]["id"]
            buy_price = response[j]["buys"]["unit_price"]
            buy_quantity = response[j]["buys"][
                "quantity"
            ]  # This is the quantity for the top offer
            sell_price = response[j]["sells"]["unit_price"]
            sell_quantity = response[j]["sells"][
                "quantity"
            ]  # This is the quantity for the top offer

            prices[id] = {
                "buy_price": buy_price,
                "sell_price": sell_price,
                "buy_quantity": buy_quantity,
                "sell_quantity": sell_quantity,
            }

    return prices


def getSummaryData():
    try:
        res = requests.get("https://api.gw2tp.com/1/bulk/items.json")
        response = json.loads(res.text)
    except Exception as e:
        print(e)
        return

    conn = sqlite3.connect("gw2.db")
    cursor = conn.cursor()

    time_updated = int(response["updated"])
    columns = response["columns"]
    for line in response["items"]:
        id = line[columns.index("id")]
        cursor.execute(
            "select Supply,Demand,LastUpdatedTime,MinPrice from tp where ItemID=?",
            (id,),
        )
        supply = line[columns.index("supply")]
        demand = line[columns.index("demand")]
        buy_price = line[columns.index("buy")]
        sell_price = line[columns.index("sell")]
        percent_profit = (
            (floor((sell_price - 1) * 0.8) - (buy_price + 1)) / (buy_price + 1) * 100
        )
        timestamp = datetime.datetime.fromtimestamp(time_updated / 1000.0)

        row = cursor.fetchone()
        # Decrease in supply/demand offers means a positive velocity
        time_format = "%Y-%m-%d %H:%M:%S"
        buy_velocity = sell_velocity = flip_index = 0
        if row is not None:
            time_diff = (
                timestamp - datetime.datetime.strptime(row[2], time_format)
            ).total_seconds()
            vendor_price = row[3]
            if vendor_price is not None:
                buy_price = max(buy_price, vendor_price)
                percent_profit = (
                    ((sell_price - 1) * 0.85 - (buy_price + 1)) / (buy_price + 1) * 100
                )

            if time_diff > 0:
                buy_velocity = (row[0] - supply) / (
                    (
                        timestamp - datetime.datetime.strptime(row[2], time_format)
                    ).total_seconds()
                )
                sell_velocity = (row[1] - demand) / (
                    (
                        timestamp - datetime.datetime.strptime(row[2], time_format)
                    ).total_seconds()
                )
                if buy_velocity > 0 and percent_profit > 0:
                    flip_index = buy_velocity * percent_profit
                else:
                    flip_index = -abs(buy_velocity * percent_profit)

                # If row is in the database and time has passed, update the values
                # print("Updating item " + str(id) + " at time " + str(timestamp))
                cursor.execute(
                    "update tp set TopBuyPrice=?, TopSellPrice=?, Supply=?, Demand=?, LastUpdatedTime=?, BuyVelocity=?, SellVelocity=?, PercentProfit=?, FlipIndex=? where ItemID=?",
                    (
                        buy_price,
                        sell_price,
                        supply,
                        demand,
                        timestamp,
                        buy_velocity,
                        sell_velocity,
                        percent_profit,
                        flip_index,
                        id,
                    ),
                )
            # If time difference is 0, no need to update the values
            else:
                conn.commit()
                cursor.close()
                conn.close()
                print(
                    "No update needed for item "
                    + str(id)
                    + " at time "
                    + str(timestamp)
                )
                return

        # If the item is not in the database, we create a row for it
        else:
            cursor.execute(
                "insert into tp(ItemID, TopBuyPrice, TopSellPrice, Supply, Demand, LastUpdatedTime, BuyVelocity, SellVelocity, PercentProfit, FlipIndex) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id,
                    buy_price,
                    sell_price,
                    supply,
                    demand,
                    timestamp,
                    buy_velocity,
                    sell_velocity,
                    percent_profit,
                    flip_index,
                ),
            )
            print(f"Added item {id} to database")

    conn.commit()
    cursor.close()
    conn.close()
    # cursor.execute("delete from tp where ItemID=?", (id,))
    # cursor.execute("insert into tp(ItemID, TopBuyPrice, TopSellPrice, Supply, Demand, LastUpdatedTime) values (?, ?, ?, ?, ?, ?)", (id, top_buy_price, top_sell_price, supply, demand, current_datetime))


def getListings():
    page_count = 1
    listings = {}
    page_counter = 0

    while page_counter < page_count:
        print("New page " + str(page_counter))
        count_string = str(page_counter)
        try:
            res = requests.get(
                "https://api.guildwars2.com/v2/commerce/listings?page="
                + count_string
                + "&page_size=200"
            )
            response = json.loads(res.text)
            print(res.headers["X-Result-Count"])
        except:
            print(count_string)
            print(res.status_code)
            print(res.text)
            page_counter += 1
            continue

        if page_counter == 0:
            page_count = int(res.headers["X-Page-Total"])
            print(page_count)

        for j in range(int(res.headers["X-Result-Count"])):
            id = response[j]["id"]
            buy_listings = {}
            sell_listings = {}
            for item in response[j]["buys"]:
                buy_listings[item["unit_price"]] = item["quantity"]
            for item in response[j]["sells"]:
                sell_listings[item["unit_price"]] = item["quantity"]
            listings[id] = {
                "buy_listings": buy_listings,
                "sell_listings": sell_listings,
            }

        page_counter += 1

    return listings


def get_total_listings(ids):
    listing_count = {}
    id_string = ",".join(ids)
    res = requests.get("https://api.guildwars2.com/v2/commerce/listings/" + id_string)
    response = json.loads(res.text)
    for item in response:
        curr_buy_listings = 0
        curr_sell_listings = 0
        for line in item["buys"]:
            curr_buy_listings += line["quantity"]
        for line in item["sells"]:
            curr_sell_listings += line["quantity"]
        listing_count[item["id"]] = {
            "buys": curr_buy_listings,
            "sells": curr_sell_listings,
        }

    return listing_count


def calculate_supply(id, listings):
    sell_listings = listings[id]["sell_listings"]
    supply = sum(sell_listings.values())
    return supply


def calculate_demand(id, listings):
    buy_listings = listings[id]["buy_listings"]
    demand = sum(buy_listings.values())
    return demand


if __name__ == "__main__":
    # TODO: Calculate buy/sell velocity based on net direction of supply/demand movement
    # TODO: Try to optimize code
    # 1: We can calculate our target item with just the summary data, and get the listings once we find the item
    #    Then use the listing to supply/demand ratio to calculate how much to buy

    getSummaryData()
