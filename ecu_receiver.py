# ecu_receiver.py
import os
import time
import configparser
import re

# --- STATE MANAGEMENT ---
# Real ECUs store this in non-volatile memory (NVRAM).
# We simulate it with global variables.
system_state = {
    "active_slot": "A",
    "slot_a_version": "1.0",
    "slot_b_version": "0.0" # Empty initially
}

def log_to_gui(message_type, message, color=None):
    if color:
        print(f"{message_type.upper()}:{message}:{color}", flush=True)
    else:
        print(f"{message_type.upper()}:{message}", flush=True)

def extract_version(filename):
    """Extracts version number '1.2' from 'firmware_v1.2.bin'"""
    match = re.search(r'v([\d.]+)', filename)
    return match.group(1) if match else "?.?"

def run_receiver():
    config = configparser.ConfigParser()
    time.sleep(1) 
    
    log_to_gui('status', 'Listening', '#4CAF50')
    log_to_gui('log', f"[o] ECU Online. Booted from Slot {system_state['active_slot']} (v{system_state['slot_a_version']}).")

    while True:
        try:
            config.read('config.ini')
            watch_folder = config.get('Folders', 'ecu_shared_folder')
            ack_folder = config.get('Folders', 'tcu_ack_folder')
            resilience_enabled = config.getboolean('Security', 'ecu_resilience_enabled', fallback=True)
            
            os.makedirs(watch_folder, exist_ok=True)
            os.makedirs(ack_folder, exist_ok=True)

            files = os.listdir(watch_folder)
            if files:
                filename = files[0]
                filepath = os.path.join(watch_folder, filename)
                is_malicious = "malicious" in filename.lower()
                new_version = extract_version(filename)

                # --- A/B PARTITION LOGIC ---
                # Determine which slot is the "Update Target" (The inactive one)
                target_slot = "B" if system_state["active_slot"] == "A" else "A"
                current_slot = system_state["active_slot"]

                log_to_gui('status', 'Updating...', '#ffc107')
                log_to_gui('log', f"----------------------------------------")
                log_to_gui('log', f" New firmware detected: {filename}")
                log_to_gui('log', f" Active Slot: {current_slot} | Target Slot: {target_slot}")
                time.sleep(1)
                
                # Simulate Writing to the Inactive Partition
                log_to_gui('status', f'Flashing Slot {target_slot}', '#ff9800')
                log_to_gui('log', f" Writing image to Partition {target_slot}...")
                
                for i in range(1, 4): 
                    log_to_gui('log', f"   [Slot {target_slot}] Writing block {i}/3...")
                    time.sleep(0.6) 
                
                log_to_gui('log', f" [Slot {target_slot}] Checksum verification passed.")
                time.sleep(0.5)

                # Simulate the "Swap and Boot" attempt
                log_to_gui('log', f" Swapping active partition to Slot {target_slot}...")
                time.sleep(1)
                log_to_gui('log', f" Rebooting into Slot {target_slot}...")
                time.sleep(1.5)

                # --- OUTCOME LOGIC ---
                if is_malicious:
                    log_to_gui('status', 'COMPROMISED', '#f44336')
                    log_to_gui('log', " [!!!] BOOT ERROR: MALICIOUS CODE DETECTED IN STARTUP.")
                    
                    if resilience_enabled:
                        # CASE A: A/B Rollback (The Safety Net)
                        time.sleep(2) 
                        log_to_gui('status', 'Rolling Back', '#FF9800')
                        log_to_gui('log', " [!] WATCHDOG: Boot failure detected.")
                        log_to_gui('log', f" [!] SWITCHING BACK to known good Slot {current_slot}...")
                        time.sleep(1.5)
                        
                        # We do NOT update system_state['active_slot'] (Stay on old slot)
                        # We update the version of the failed slot to show we tried
                        if target_slot == "A": system_state["slot_a_version"] = new_version + " (BAD)"
                        else: system_state["slot_b_version"] = new_version + " (BAD)"

                        log_to_gui('log', f" [o] Recovered. Running on Slot {current_slot} (v{system_state['slot_a_version' if current_slot=='A' else 'slot_b_version']}).")
                        
                        with open(os.path.join(ack_folder, f"{filename}.ack"), 'w') as f:
                            f.write("FAILURE") 
                    else:
                        # CASE B: Bricked (No Rollback)
                        # We commit the switch to the bad slot
                        system_state["active_slot"] = target_slot
                        if target_slot == "A": system_state["slot_a_version"] = new_version
                        else: system_state["slot_b_version"] = new_version

                        log_to_gui('log', " [!!!] WATCHDOG DISABLED. SYSTEM HANG.")
                        log_to_gui('log', f" [X] STUCK ON CORRUPT SLOT {target_slot}.")
                        
                        with open(os.path.join(ack_folder, f"{filename}.ack"), 'w') as f:
                            f.write("SUCCESS") # Setup thinks it worked, but ECU is dead
                else:
                    # CASE C: Success
                    # Commit the switch
                    system_state["active_slot"] = target_slot
                    if target_slot == "A": system_state["slot_a_version"] = new_version
                    else: system_state["slot_b_version"] = new_version

                    log_to_gui('log', f" Boot successful. System running on Slot {target_slot} (v{new_version}).")
                    log_to_gui('status', 'Success', '#4CAF50')
                    with open(os.path.join(ack_folder, f"{filename}.ack"), 'w') as f:
                        f.write("SUCCESS")
                
                log_to_gui('log', f"----------------------------------------")
                # -------------------------------------

                if os.path.exists(filepath): os.remove(filepath)
                time.sleep(1)
                
                # If compromised and no resilience, stay red longer
                if is_malicious and not resilience_enabled:
                    time.sleep(10)
                else:
                    time.sleep(3)
                    log_to_gui('status', f'Slot {system_state["active_slot"]} Active', '#4CAF50')
                
        except Exception as e:
            log_to_gui('log', f"ECU CRITICAL ERROR: {e}")
            log_to_gui('status', 'Crashed', '#f44336')
            time.sleep(5)
        
        time.sleep(1)

if __name__ == '__main__':
    log_to_gui('log', "ECU Receiver process started.")
    run_receiver()