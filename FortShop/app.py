import requests
import json
import os
import schedule
import smtplib
from datetime import datetime
import pytz
from flask import Flask, render_template, request, redirect, url_for
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure Flask
app = Flask(__name__)

# Fortnite API URL
FORTNITE_API_URL = "https://fortnite-api.com/v2/shop"

# Email Configuration (Replace with real credentials)
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USER = 'your-email@gmail.com'
EMAIL_PASSWORD = 'your-email-password'
TO_EMAIL = 'recipient-email@gmail.com'

# Function to send email notification

# Function to fetch and categorize item shop data
def remove_duplicates(items):
    """Removes duplicate items, keeping the one with the lowest price."""
    unique_items = {}
    
    for item in items:
        name = item["name"]
        price = item["price"]
        
        if name not in unique_items or price < unique_items[name]["price"]:
            unique_items[name] = item
    
    return list(unique_items.values())

# Modify fetch_item_shop_data to use remove_duplicates
def fetch_item_shop_data():
    """Fetches Fortnite item shop data, categorizes items, removes duplicates, checks requests, and sends emails."""
    print("\U0001F50E Fetching Fortnite Item Shop data...")

    try:
        response = requests.get(FORTNITE_API_URL)
        response.raise_for_status()
        shop_data = response.json()

        if shop_data.get('status') != 200:
            print(f"⚠️ API Error: {shop_data.get('error', 'Unknown error')}")
            return

        items = shop_data.get('data', {}).get('entries', [])
        categorized_items = {
            "Skins": [],
            "Emotes": [],
            "Shoes": [],
            "Music": [],
            "Instruments": [],
        }

        for item in items:
            for br_item in item.get('brItems', []):
                item_name = br_item.get('name', 'Unknown Item')
                item_price = item.get('finalPrice', float('inf'))  # Ensure price is numeric
                item_type = br_item.get('type', {}).get('displayValue', 'Unknown Type')
                item_image = br_item.get('images', {}).get('featured') or br_item.get('images', {}).get('icon')

                item_data = {"name": item_name, "price": item_price, "image": item_image}

                # Categorize items
                if "Outfit" in item_type:
                    categorized_items["Skins"].append(item_data)
                elif "Emote" in item_type:
                    categorized_items["Emotes"].append(item_data)
                elif "Shoes" in item_type:
                    categorized_items["Shoes"].append(item_data)
                elif "Track" in item_type or "Music" in item_type:
                    categorized_items["Music"].append(item_data)
                elif "Instrument" in item_type:
                    categorized_items["Instruments"].append(item_data)

        # Remove duplicates while keeping the lowest price
        for category in categorized_items:
            categorized_items[category] = remove_duplicates(categorized_items[category])

        # Check for item requests and send email if necessary
        check_requests_and_notify(categorized_items)

        # Save the shop data for today
        today = datetime.now(pytz.timezone("America/Puerto_Rico")).strftime("%Y-%m-%d")
        save_shop_data(today, categorized_items)

        print(f"✅ Successfully saved data for {today}.")

    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error fetching data from the Fortnite Tracker API: {e}")


def check_requests_and_notify(shop_data):
    """Check the requests and notify users if their requested item is in the shop."""
    # Load the current item requests
    with open(REQUESTS_FILE, 'r') as file:
        data = json.load(file)

    requests = data.get("requests", [])

    # Check each request
    for request_item in requests:
        if request_item.get("notified", False):
            continue  # Skip already notified requests

        # Check if the item is available in the shop
        for category, items in shop_data.items():
            for item in items:
                if item["name"].lower() == request_item["item_name"].lower():
                    # Item found, send email
                    send_email(request_item["email"], item["name"])
                    # Mark the request as notified
                    request_item["notified"] = True
                    break  # No need to check other items for this request

    # Save updated requests back to the JSON file
    with open(REQUESTS_FILE, 'w') as file:
        json.dump(data, file, indent=4)


# Function to save the data into JSON
def save_shop_data(date, item_list):
    """Saves categorized Fortnite shop data to a JSON file."""
    if not os.path.exists("item_shop_data.json"):
        with open("item_shop_data.json", "w") as f:
            json.dump({}, f)

    try:
        with open("item_shop_data.json", "r+") as f:
            data = json.load(f)
            data[date] = item_list  # Append data for the given date
            f.seek(0)
            json.dump(data, f, indent=4)
            print(f"✅ Data saved for {date}.")
    except json.JSONDecodeError:
        print("⚠️ Failed to decode JSON file.")

# Function to retrieve data from JSON
def get_shop_data_from_json(date):
    try:
        with open("item_shop_data.json", "r") as f:
            data = json.load(f)
            return data.get(date, {})
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

# Flask Routes
@app.route('/')
def index():
    try:
        with open("item_shop_data.json", "r") as f:
            data = json.load(f)
            dates = sorted(data.keys(), reverse=True)

            latest_date = dates[0] if dates else None
            shop_data = data.get(latest_date, {})

            return render_template('index.html', dates=dates, shop_data=shop_data)
    except (json.JSONDecodeError, FileNotFoundError):
        return render_template('index.html', dates=[], shop_data={})

@app.route('/shop/<date>')
def show_shop(date):
    shop_data = get_shop_data_from_json(date)
    return render_template('shop.html', date=date, shop_data=shop_data)

@app.route('/changes', methods=['GET'])
def shop_changes():
    """Compares two selected dates and highlights differences in the Fortnite shop."""
    try:
        with open("item_shop_data.json", "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"⚠️ Error reading JSON file: {e}")
        return render_template("changes.html", dates=[], added_items=[], removed_items=[], date1=None, date2=None)

    dates = sorted(data.keys(), reverse=True)
    print("📅 Available Dates:", dates)

    date1 = request.args.get('date1')
    date2 = request.args.get('date2')

    if not date1 or not date2 or date1 not in data or date2 not in data:
        return render_template("changes.html", dates=dates, added_items=[], removed_items=[], date1=date1, date2=date2)

    def extract_items(shop):
        """Extracts all items from the shop data across categories."""
        return {item["name"]: item for category in shop.values() for item in category}

    items1 = extract_items(data[date1])
    items2 = extract_items(data[date2])

    added_items = [items2[item] for item in items2 if item not in items1]
    removed_items = [items1[item] for item in items1 if item not in items2]

    return render_template("changes.html", dates=dates, added_items=added_items, removed_items=removed_items, date1=date1, date2=date2)



# Path to store the requests data
REQUESTS_FILE = 'requests.json'

# Load existing requests from JSON file
# Load existing requests from JSON file
def load_requests():
    try:
        with open(REQUESTS_FILE, 'r') as file:
            data = json.load(file)
            if "requests" not in data:
                data["requests"] = []  # Ensure requests is a list
            return data  # Return the entire dictionary
    except (FileNotFoundError, json.JSONDecodeError):
        return {"requests": []}  # Ensure requests is always a dictionary with a list

# Save requests to JSON file
def save_requests(data):
    with open(REQUESTS_FILE, 'w') as file:
        json.dump(data, file, indent=4)


# Save requests to JSON file
def save_requests(requests):
    with open(REQUESTS_FILE, 'w') as file:
        json.dump(requests, file, indent=4)

# Send email notification
def send_email(recipient, item_name):
    sender_email = "dece.ai.tt.noreply@gmail.com"  
    sender_password = "hhzc umgl wfoi ksww"
    subject = f"Item Back in Stock: {item_name}"
    body = f"Good news! The item '{item_name}' is now back in stock!"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient, msg.as_string())

@app.route('/request_item', methods=['GET', 'POST'])
def request_item():
    if request.method == 'POST':
        email = request.form['email']
        item_name = request.form['item_name']

        # Load the current requests
        data = load_requests()  # Now returns a dictionary
        requests = data["requests"]  # Extract the list

        # Store the new request
        requests.append({'email': email, 'item_name': item_name, 'notified': False})

        # Save back to the JSON file
        save_requests(data)

        return redirect(url_for('request_item', message="Request submitted successfully!"))

    return render_template('request_item.html', message=request.args.get('message', ''))

if __name__ == '__main__':
    print("🚀 Starting Fortnite Item Shop Tracker...")
    fetch_item_shop_data()

    # Start background thread for daily updates
    schedule.every(57).minutes.do(fetch_item_shop_data)
    scheduler_thread = threading.Thread(target=fetch_item_shop_data, daemon=True)
    scheduler_thread.start()

    app.run(debug=True, port=5000)
