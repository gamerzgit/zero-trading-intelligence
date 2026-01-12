#!/usr/bin/env python3
"""
Configure Grafana TimescaleDB datasource via API
Automatically sets the database password from environment variables
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

GRAFANA_URL = os.getenv('GRAFANA_URL', 'http://localhost:3000')
GRAFANA_USER = os.getenv('GRAFANA_ADMIN_USER', 'admin')
GRAFANA_PASSWORD = os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')

if not POSTGRES_PASSWORD:
    print("⚠️  POSTGRES_PASSWORD not set in .env file")
    print("   Skipping Grafana datasource configuration")
    sys.exit(0)

def wait_for_grafana(max_attempts=30):
    """Wait for Grafana to be ready"""
    print("⏳ Waiting for Grafana to be ready...")
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{GRAFANA_URL}/api/health", timeout=2)
            if response.status_code == 200:
                print("✅ Grafana is ready")
                return True
        except requests.exceptions.ConnectionError:
            # Grafana not started yet, continue waiting
            pass
        except requests.exceptions.RequestException as e:
            # Other errors, log but continue
            if attempt == 0:  # Only log on first attempt to avoid spam
                print(f"   Note: {type(e).__name__}")
        
        if attempt < max_attempts - 1:  # Don't print on last attempt
            print(f"   Attempt {attempt + 1}/{max_attempts}...")
        time.sleep(2)
    
    print("❌ Grafana did not become ready in time")
    print(f"   Check if Grafana is running: curl {GRAFANA_URL}/api/health")
    return False

def configure_datasource():
    """Configure TimescaleDB datasource in Grafana"""
    if not wait_for_grafana():
        return False
    
    print("📊 Configuring TimescaleDB datasource...")
    
    datasource_config = {
        "name": "TimescaleDB",
        "type": "postgres",
        "access": "proxy",
        "url": "timescaledb:5432",
        "database": "zero_trading",
        "user": "zero_user",
        "secureJsonData": {
            "password": POSTGRES_PASSWORD
        },
        "jsonData": {
            "sslmode": "disable",
            "postgresVersion": 1400,
            "timescaledb": True
        },
        "isDefault": True
    }
    
    # Use basic auth
    auth = (GRAFANA_USER, GRAFANA_PASSWORD)
    
    # Check if datasource already exists
    try:
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources/name/TimescaleDB",
            auth=auth,
            timeout=5
        )
        
        if response.status_code == 200:
            # Datasource exists, update it
            ds_data = response.json()
            ds_id = ds_data.get('id')
            print(f"   Updating existing datasource (ID: {ds_id})...")
            
            update_response = requests.put(
                f"{GRAFANA_URL}/api/datasources/{ds_id}",
                json=datasource_config,
                auth=auth,
                timeout=5
            )
            
            if update_response.status_code == 200:
                print("✅ Datasource updated successfully")
            else:
                print(f"⚠️  Failed to update datasource (HTTP {update_response.status_code})")
                try:
                    error_data = update_response.json()
                    print(f"   Error: {error_data.get('message', update_response.text)}")
                except:
                    print(f"   Response: {update_response.text}")
                return False
        elif response.status_code == 404:
            # Datasource doesn't exist, create it
            print("   Creating new datasource...")
            create_response = requests.post(
                f"{GRAFANA_URL}/api/datasources",
                json=datasource_config,
                auth=auth,
                timeout=5
            )
            
            if create_response.status_code in (200, 201):
                print("✅ Datasource created successfully")
            else:
                print(f"⚠️  Failed to create datasource (HTTP {create_response.status_code})")
                try:
                    error_data = create_response.json()
                    print(f"   Error: {error_data.get('message', create_response.text)}")
                except:
                    print(f"   Response: {create_response.text}")
                return False
        elif response.status_code == 401:
            print("❌ Authentication failed - check GRAFANA_ADMIN_USER and GRAFANA_ADMIN_PASSWORD")
            return False
        else:
            print(f"❌ Unexpected error checking datasource (HTTP {response.status_code})")
            print(f"   Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Error configuring datasource: {e}")
        return False
    
    # Test the datasource
    print("🧪 Testing datasource connection...")
    try:
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources/name/TimescaleDB",
            auth=auth,
            timeout=5
        )
        
        if response.status_code == 200:
            ds_data = response.json()
            ds_id = ds_data.get('id')
            
            test_response = requests.post(
                f"{GRAFANA_URL}/api/datasources/{ds_id}/health",
                auth=auth,
                timeout=10
            )
            
            if test_response.status_code == 200:
                test_data = test_response.json()
                if test_data.get('status') == 'OK':
                    print("✅ Datasource connection test passed")
                else:
                    print(f"⚠️  Datasource connection test failed: {test_data}")
            else:
                print(f"⚠️  Could not test datasource (HTTP {test_response.status_code})")
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error testing datasource: {e}")
    
    print("✅ Grafana datasource configuration complete")
    return True

if __name__ == '__main__':
    success = configure_datasource()
    sys.exit(0 if success else 1)
