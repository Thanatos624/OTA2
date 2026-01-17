# tcu_client.py
import requests
import time
import os
import shutil
import configparser
import sys
from shared_utils import version_to_tuple, calculate_sha256

def log_to_gui(message_type, message, color=None):
    """Prints a formatted string for the GUI to capture."""
    if color:
        print(f"{message_type.upper()}:{message}:{color}", flush=True)
    else:
        print(f"{message_type.upper()}:{message}", flush=True)

def check_single_server(server_url):
    """Checks one server for an update (Anonymous logic)."""
    if not server_url: return None
    try:
        # Reverted: No VIN headers included
        response = requests.get(f"{server_url}/check-update", timeout=3)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def download_and_process(config, firmware_info, checksum_verification_enabled):
    log_to_gui('status', 'Downloading', '#ffc107')
    log_to_gui('progress', '0')
    time.sleep(0.75)

    # Reverted: URL lookup is based on the 'source' key from the server response
    source = firmware_info.get("source", "unknown")
    server_url = config.get('Server', f'{source}_url', fallback=None)
    
    if not server_url:
        log_to_gui('log', f" Error: No URL configured for source '{source}'")
        return False
    
    try:
        filename = firmware_info['filename']
        download_url = f"{server_url}/download/{filename}"
        
        dl_response = requests.get(download_url, stream=True, timeout=10)
        dl_response.raise_for_status()
        
        total_size = int(dl_response.headers.get('content-length', 0))
        temp_dir = config['Folders']['tcu_download_folder']
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, filename)
        
        bytes_downloaded = 0
        with open(temp_filepath, 'wb') as f:
            for chunk in dl_response.iter_content(chunk_size=8192):
                f.write(chunk)
                bytes_downloaded += len(chunk)
                if total_size > 0:
                    log_to_gui('progress', f"{(bytes_downloaded / total_size) * 100}")
        
        log_to_gui('log', " Download complete.")
        log_to_gui('progress', '100')
        time.sleep(0.75)

        log_to_gui('status', 'Verifying', '#9c27b0')
        log_to_gui('log', " Verifying file integrity...")
        time.sleep(0.75)
        local_checksum = calculate_sha256(temp_filepath)
        
        # Security Toggle: Restored from reference
        if checksum_verification_enabled and local_checksum != firmware_info['checksum']:
            log_to_gui('log', " CHECKSUM MISMATCH! Deleting file.")
            os.remove(temp_filepath)
            return False
        
        log_to_gui('log', " Checksum match! File is valid.")
        time.sleep(0.75)
        
        ecu_folder = config['Folders']['ecu_shared_folder']
        os.makedirs(ecu_folder, exist_ok=True)
        shutil.move(temp_filepath, os.path.join(ecu_folder, filename))
        log_to_gui('log', f" Transferred '{filename}' to ECU folder.")
        
        return wait_for_ecu_ack(config, filename)

    except Exception as e:
        log_to_gui('log', f" Download/Processing Error: {e}")
        return False

def wait_for_ecu_ack(config, filename):
    log_to_gui('status', 'Awaiting ACK', '#673ab7')
    log_to_gui('log', f"   Waiting for ECU acknowledgment for {filename}...")
    ack_folder = config['Folders']['tcu_ack_folder']
    os.makedirs(ack_folder, exist_ok=True)
    ack_path = os.path.join(ack_folder, f"{filename}.ack")
    
    for _ in range(30): 
        if os.path.exists(ack_path):
            # Reverted: Does not check file content
            os.remove(ack_path) 
            log_to_gui('log', f" ACK received from ECU.")
            return True
        time.sleep(1)
        
    log_to_gui('log', " Timed out waiting for ECU.")
    return False

def perform_single_update_check():
    """Main update logic: Finds highest version between servers."""
    try:
        config = configparser.ConfigParser()
        config.read('config.ini')
        current_version_str = config.get('TCU', 'current_version', fallback='1.0')
        oem_url = config.get('Server', 'oem_url')
        malicious_url = config.get('Server', 'malicious_url')
        checksum_enabled = config.getboolean('Security', 'checksum_verification_enabled', fallback=True)
        current_version_tuple = version_to_tuple(current_version_str)

        log_to_gui('status', 'Checking', '#2196F3')
        log_to_gui('log', f" TCU (v{current_version_str}) checking for updates...")
        
        oem_info = check_single_server(oem_url)
        malicious_info = check_single_server(malicious_url)
        
        best_update = None
        best_version_tuple = current_version_tuple

        # Logic to select the highest version available
        if oem_info and version_to_tuple(oem_info.get("version")) > best_version_tuple:
            best_update = oem_info
            best_version_tuple = version_to_tuple(oem_info.get("version"))
        
        if malicious_info and version_to_tuple(malicious_info.get("version")) > best_version_tuple:
            best_update = malicious_info
            best_version_tuple = version_to_tuple(malicious_info.get("version"))

        if best_update:
            log_to_gui('log', f" New version found: {best_update['version']}")
            if download_and_process(config, best_update, checksum_enabled):
                # Update local config only on successful transfer and ACK
                config.set('TCU', 'current_version', best_update['version'])
                with open('config.ini', 'w') as configfile: config.write(configfile)
                log_to_gui('log', f" Update successful.")
                log_to_gui('status', 'Success', '#4CAF50')
            else:
                log_to_gui('status', 'Idle', 'gray')
        else:
            log_to_gui('log', " No updates available.")
            log_to_gui('status', 'Idle', 'gray')
    
    except Exception as e:
        log_to_gui('log', f"TCU ERROR: {e}")
        log_to_gui('status', 'Crashed', '#f44336')

def main_loop():
    log_to_gui('status', 'Idle', 'gray')
    for command in sys.stdin:
        if command.strip() == "CHECK":
            perform_single_update_check()

if __name__ == '__main__':
    main_loop()