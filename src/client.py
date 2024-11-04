import requests
import time
import os
import logging
import json
import random
import string

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_test_data():
    """Generate random key-value pair for testing"""
    # Generate a random key with timestamp to ensure uniqueness
    random_key = random.randint(1,100)
    random_value = random.randint(1,100)

    return {"key": random_key, "value": random_value}

def send_write_request():
    load_balancer_host = os.getenv('LOAD_BALANCER_HOST', 'load-balancer')
    load_balancer_port = os.getenv('LOAD_BALANCER_PORT', '80')
    write_url = f'http://{load_balancer_host}:{load_balancer_port}/write'

    # Generate test data
    data = generate_test_data()

    try:
        # Send POST request with JSON data
        response = requests.post(
            write_url,
            json=data,
            headers={'Content-Type': 'application/json'}
        )

        # Log the request and response
        logger.info(f"Sent write request to {write_url}")
        logger.info(f"Request data: {json.dumps(data, indent=2)}")
        logger.info(f"Response status: {response.status_code}")

        try:
            response_json = response.json()
            logger.info(f"Response data: {json.dumps(response_json, indent=2)}")
        except json.JSONDecodeError:
            logger.info(f"Response text: {response.text}")

        logger.info(f"Server: {response.headers.get('Server', 'Unknown')}")
        logger.info("-" * 50)  # Separator for better log readability

    except requests.exceptions.RequestException as e:
        logger.error(f"Error making request to {write_url}: {e}")
        logger.info("-" * 50)

def main():
    # Initial delay to allow the load balancer and servers to start
    initial_delay = int(os.getenv('INITIAL_DELAY_SECONDS', '3'))
    logger.info(f"Client starting up, waiting for {initial_delay} seconds initial delay...")
    time.sleep(initial_delay)

    # Continuous loop to send requests
    interval = int(os.getenv('REQUEST_INTERVAL_SECONDS', '30'))
    logger.info(f"Starting request loop with {interval} seconds interval")

    while True:
        send_write_request()
        time.sleep(interval)

if __name__ == "__main__":
    main()