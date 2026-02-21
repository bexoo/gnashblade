import requests
import json
import sqlite3
import time
import datetime
from typing import Optional


def get_item_vendor_value(item_id: int) -> Optional[int]:
    try:
        res = requests.get(f"https://api.guildwars2.com/v2/items/{item_id}", timeout=10)
        res.raise_for_status()  # Raise an exception for bad status codes
        response = json.loads(res.text)
        return response.get("vendor_value", None)
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        print(f"Error fetching vendor value for item {item_id}: {str(e)}")
        return None


def updateMinPrices():
    conn = sqlite3.connect("gw2.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM tp")
        items = cursor.fetchall()
        updates = 0
        
        for item in items:
            item_id = item[0]
            current_min_price = item[10]
            
            if current_min_price is not None:
                print(f"Item {item_id} already has min price: {current_min_price}")
                continue
                
            print(f"Fetching min price for item {item_id}")
            min_price = get_item_vendor_value(item_id)
            
            if min_price is not None:
                cursor.execute(
                    "UPDATE tp SET MinPrice = ? WHERE ItemID = ?",
                    (min_price, item_id)
                )
                updates += 1
                print(f"Updated min price for item {item_id}: {min_price}")
                
                # Commit every 10 updates to avoid losing all progress if something fails
                if updates % 10 == 0:
                    conn.commit()
                    print(f"Committed {updates} updates to database")
                    
                # Add a small delay to avoid hitting API rate limits
                time.sleep(0.1)
        
        # Final commit for any remaining updates
        conn.commit()
        print(f"Finished updating min prices. Total updates: {updates}")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    updateMinPrices()
