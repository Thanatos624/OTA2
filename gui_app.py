# gui_app.py
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import threading
import queue
import os
import shutil
import configparser
import subprocess
import sys
import csv
import datetime
from shared_utils import find_latest_version

# --- THEME INITIALIZATION ---
ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("blue")

class OTASimulatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window Configuration
        self.title("OTA Update Simulator: Cyber-Resilience Testbed")
        self.geometry("1600x900")
        
        # Grid Layout (2x2 Matrix for Logs, 1 Row for Controls)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.log_queue = queue.Queue()
        self.simulation_running = False
        self.processes = {} 
        self.current_theme = "Dark" # Track state

        # --- CONTROL HEADER ---
        self.control_frame = ctk.CTkFrame(self, corner_radius=10)
        self.control_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        
        # Left Side Controls
        self.start_stop_button = ctk.CTkButton(self.control_frame, text="START SIMULATION", command=self.toggle_simulation, fg_color="#4CAF50", font=("Roboto", 12, "bold"), width=150)
        self.start_stop_button.pack(side="left", padx=15, pady=15)
        
        self.deploy_oem_button = ctk.CTkButton(self.control_frame, text="Deploy OEM Update", command=self.deploy_oem_update, fg_color="#2196F3", width=140)
        self.deploy_oem_button.pack(side="left", padx=5)

        self.deploy_malicious_button = ctk.CTkButton(self.control_frame, text="Deploy Malicious Payload", command=self.deploy_malicious_update, fg_color="#BF092F", hover_color="#900623", width=160)
        self.deploy_malicious_button.pack(side="left", padx=5)
        
        self.toggle_checksum_button = ctk.CTkButton(self.control_frame, text="Checksum: ON", command=self.toggle_checksum_verification, fg_color="transparent", border_width=2, border_color="#4CAF50", text_color="#4CAF50")
        self.toggle_checksum_button.pack(side="left", padx=15)

        # Right Side Controls (Theme & Clear)
        self.theme_button = ctk.CTkButton(self.control_frame, text="☀ Light Mode", command=self.toggle_theme, fg_color="#607d8b", width=100)
        self.theme_button.pack(side="right", padx=15)
        
        self.clear_button = ctk.CTkButton(self.control_frame, text="Clear Logs", command=self.clear_logs, fg_color="#546E7A", width=100)
        self.clear_button.pack(side="right", padx=5)

        # --- LOGGING INFRASTRUCTURE (THE CARDS) ---
        # Top Row: Servers
        self.server_frame, self.server_status = self.create_log_card(0, 1, "OEM Cloud Server")
        self.malicious_server_frame, self.malicious_server_status = self.create_log_card(1, 1, "Adversary / Malicious Server")
        
        # Bottom Row: Vehicle
        self.tcu_frame, self.tcu_status = self.create_log_card(0, 2, "TCU Client (Telematics)")
        self.ecu_frame, self.ecu_status = self.create_log_card(1, 2, "ECU Receiver (Engine Control)")

        # Log Textboxes
        self.server_log = self.create_log_box(self.server_frame)
        self.malicious_server_log = self.create_log_box(self.malicious_server_frame)
        self.tcu_log = self.create_log_box(self.tcu_frame)
        self.ecu_log = self.create_log_box(self.ecu_frame)
        
        # Progress Bar (TCU)
        self.progress_bar = ctk.CTkProgressBar(self.tcu_frame, orientation="horizontal", height=10)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=15, pady=(5, 15))

        # --- INITIALIZATION ---
        self.after(100, self.process_queue)
        self.ensure_config_exists()
        self.update_button_visuals() 
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_log_card(self, col, row, title):
        card = ctk.CTkFrame(self, corner_radius=15, fg_color=("#CCE5CF", "#2b2b2b"))
        card.grid(row=row, column=col, padx=15, pady=10, sticky="nsew")
        
        header = ctk.CTkFrame(card, corner_radius=10, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=8)
        
        label = ctk.CTkLabel(header, text=title, font=("Roboto", 16, "bold"))
        label.pack(side="left", padx=5)
        
        status_indicator = ctk.CTkLabel(header, text="OFFLINE", font=("Roboto Mono", 12), text_color="gray")
        status_indicator.pack(side="right", padx=5)
        
        if "TCU" in title:
            self.trigger_check_button = ctk.CTkButton(header, text="↻ Request Update", width=120, height=28, command=self.trigger_tcu_check, fg_color="#FF9800", font=("Arial", 11, "bold"))
            self.trigger_check_button.pack(side="right", padx=15)
            
        if "ECU" in title:
            self.toggle_resilience_button = ctk.CTkButton(header, text="Resilience: ON", width=120, height=28, command=self.toggle_resilience, fg_color="transparent", border_width=2, border_color="#4CAF50", text_color="#4CAF50", font=("Arial", 11, "bold"))
            self.toggle_resilience_button.pack(side="right", padx=15)

        return card, status_indicator

    def create_log_box(self, parent_frame):
        log_box = ctk.CTkTextbox(
            parent_frame, 
            font=("Consolas", 12), 
            activate_scrollbars=True,
            corner_radius=8
        )
        if self.current_theme == "Dark":
            log_box.configure(fg_color="#1e1e1e", text_color="#00e676") 
        else:
            log_box.configure(fg_color="#ffffff", text_color="#000000") 
            
        log_box.pack(expand=True, fill="both", padx=15, pady=(0, 15))
        
        # --- NEW: Configure a RED tag for critical alerts ---
        # We access the internal Tkinter widget using ._textbox
        log_box._textbox.tag_config("critical", foreground="#ff4444") 
        # ----------------------------------------------------
        
        log_box.configure(state="disabled")
        return log_box

    # --- THEME TOGGLE LOGIC ---
    def toggle_theme(self):
        if self.current_theme == "Dark":
            self.current_theme = "Light"
            ctk.set_appearance_mode("Light")
            self.theme_button.configure(text="🌙 Dark Mode")
            for box in [self.server_log, self.malicious_server_log, self.tcu_log, self.ecu_log]:
                box.configure(fg_color="#ffffff", text_color="#000000", border_width=1, border_color="#cccccc")
        else:
            self.current_theme = "Dark"
            ctk.set_appearance_mode("Dark")
            self.theme_button.configure(text="☀ Light Mode")
            for box in [self.server_log, self.malicious_server_log, self.tcu_log, self.ecu_log]:
                box.configure(fg_color="#1e1e1e", text_color="#00e676", border_width=0)

    # --- CORE LOGIC ---
    def process_queue(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            log_path = os.path.join(script_dir, "simulation_logs.csv")
            
            with open(log_path, "a", newline='', encoding='utf-8') as log_file:
                writer = csv.writer(log_file)
                while True:
                    msg_type, target, message, color = self.log_queue.get_nowait()
                    
                    timestamp = datetime.datetime.now().isoformat()
                    writer.writerow([timestamp, target, msg_type, message])
                    
                    box_map = {'server': self.server_log, 'malicious_server': self.malicious_server_log, 'tcu': self.tcu_log, 'ecu': self.ecu_log}
                    status_map = {'server': self.server_status, 'malicious_server': self.malicious_server_status, 'tcu': self.tcu_status, 'ecu': self.ecu_status}
                    
                    if msg_type == 'log':
                        box = box_map.get(target)
                        if box:
                            box.configure(state='normal')
                            
                            # --- UPDATED: Apply Red Color to Critical Alerts ---
                            if "[!!!]" in message:
                                box.insert("end", message + '\n', "critical")
                            else:
                                box.insert("end", message + '\n')
                            # ---------------------------------------------------
                            
                            box.configure(state='disabled')
                            box.see("end")
                    elif msg_type == 'status':
                        indicator = status_map.get(target)
                        if indicator: 
                            indicator.configure(text=message, text_color=color)
                    elif msg_type == 'progress' and target == 'tcu':
                        self.progress_bar.set(float(message) / 100)
        except queue.Empty: pass
        except Exception as e: print(f"Logging Error: {e}")
        finally: self.after(100, self.process_queue)

    def parse_and_log(self, line, target_component):
        line = line.strip()
        if not line: return
        parts = line.split(':', 1)
        if len(parts) != 2:
            self.log_queue.put(('log', target_component, line, None))
            return
        msg_type, content = parts[0].lower().strip(), parts[1].strip()
        if msg_type == 'status':
            status_parts = content.split(':', 1)
            color = status_parts[1].strip() if len(status_parts) == 2 else "#FFFFFF"
            self.log_queue.put(('status', target_component, status_parts[0].strip(), color))
        elif msg_type in ['log', 'progress']:
            self.log_queue.put((msg_type, target_component, content, None))
        else:
            self.log_queue.put(('log', target_component, line, None))

    def stream_reader(self, process_stdout, target_component):
        try:
            for line in iter(process_stdout.readline, ''):
                self.parse_and_log(line, target_component)
        finally:
            process_stdout.close()
            
    def ensure_config_exists(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        if not config.has_section('TCU'): config.add_section('TCU')
        if not config.has_option('TCU', 'current_version'): config.set('TCU', 'current_version', '1.0')
        if not config.has_section('Server'): config.add_section('Server')
        if not config.has_option('Server', 'oem_url'): config.set('Server', 'oem_url', 'http://127.0.0.1:5000')
        if not config.has_option('Server', 'malicious_url'): config.set('Server', 'malicious_url', 'http://127.0.0.1:5001')
        if not config.has_section('Security'): config.add_section('Security')
        if not config.has_option('Security', 'checksum_verification_enabled'): config.set('Security', 'checksum_verification_enabled', 'true')
        if not config.has_option('Security', 'ecu_resilience_enabled'): config.set('Security', 'ecu_resilience_enabled', 'true')
        if not config.has_section('Folders'): config.add_section('Folders')
        if not config.has_option('Folders', 'ecu_shared_folder'): config.set('Folders', 'ecu_shared_folder', 'shared_for_ecu')
        if not config.has_option('Folders', 'tcu_download_folder'): config.set('Folders', 'tcu_download_folder', 'tcu_downloads')
        if not config.has_option('Folders', 'tcu_ack_folder'): config.set('Folders', 'tcu_ack_folder', 'tcu_acks')
        
        with open('config.ini', 'w') as configfile: config.write(configfile)
        self.checksum_enabled = config.getboolean('Security', 'checksum_verification_enabled')
        self.resilience_enabled = config.getboolean('Security', 'ecu_resilience_enabled')

    def toggle_simulation(self):
        if self.simulation_running: self.stop_simulation()
        else: self.start_simulation()

    def start_simulation(self):
        self.simulation_running = True
        self.clear_logs()
        folders = ['updates', 'malicious_updates', 'shared_for_ecu', 'tcu_acks', 'tcu_downloads']
        for folder in folders:
            if os.path.exists(folder): shutil.rmtree(folder)
            os.makedirs(folder)
        with open("updates/firmware_v1.1.bin", "w") as f: f.write("Initial legitimate firmware v1.1.")
        self.log_queue.put(('log', 'server', " SERVER READY: Deployed 'firmware_v1.1.bin'.", None))
        self.ensure_config_exists()
        config = configparser.ConfigParser()
        config.read('config.ini')
        config.set('TCU', 'current_version', '1.0')
        with open('config.ini', 'w') as configfile: config.write(configfile)
        
        self.start_stop_button.configure(text="STOP SIMULATION", fg_color="#f44336")
        
        scripts = {'server': 'oem_server.py', 'malicious_server': 'malicious_server.py', 'tcu': 'tcu_client.py', 'ecu': 'ecu_receiver.py'}
        for name, script_file in scripts.items():
            try:
                process = subprocess.Popen([sys.executable, script_file],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                    text=True, encoding='utf-8', errors='replace', bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.processes[name] = process
                thread = threading.Thread(target=self.stream_reader, args=(process.stdout, name), daemon=True)
                thread.start()
            except FileNotFoundError:
                self.log_queue.put(('log', name, f"ERROR: Could not find '{script_file}'.", None))
                self.stop_simulation()
                return

    def stop_simulation(self):
        self.simulation_running = False
        for p in self.processes.values():
            if p.poll() is None: p.terminate()
        self.processes.clear()
        self.start_stop_button.configure(text="START SIMULATION", fg_color="#4CAF50")
        for status in [self.server_status, self.malicious_server_status, self.tcu_status, self.ecu_status]:
            status.configure(text="OFFLINE", text_color="gray")
    
    def trigger_tcu_check(self):
        if self.simulation_running and 'tcu' in self.processes:
            tcu_process = self.processes['tcu']
            try:
                tcu_process.stdin.write("CHECK\n"); tcu_process.stdin.flush()
                self.log_queue.put(('log', 'tcu', "[~] Manual update check triggered.", None))
            except: pass

    def deploy_oem_update(self): self.deploy_update("oem")
    def deploy_malicious_update(self): self.deploy_malicious_update_logic()

    def deploy_malicious_update_logic(self):
        if not self.simulation_running: return
        filepath = filedialog.askopenfilename(title="Select Payload", filetypes=(("Text files", "*.txt"), ("All", "*.*")))
        if not filepath: return
        try:
            latest_version_tuple = find_latest_version(['updates', 'malicious_updates'])
            major, minor = latest_version_tuple
            filename = f"malicious_firmware_v{major}.{minor + 1}.bin"
            shutil.copy(filepath, os.path.join("malicious_updates", filename))
            self.log_queue.put(('log', 'malicious_server', f" MALICIOUS DEPLOY: Deployed '{filename}'.", None))
        except Exception as e:
            self.log_queue.put(('log', 'malicious_server', f" ERROR: {e}", None))

    def deploy_update(self, source):
        if not self.simulation_running: return
        latest_version_tuple = find_latest_version(['updates', 'malicious_updates'])
        major, minor = latest_version_tuple
        new_version = f"{major}.{minor + 1}"
        folder, prefix = ("updates", "firmware_v") if source == "oem" else ("malicious_updates", "malicious_firmware_v")
        filename = f"{prefix}{new_version}.bin"
        with open(os.path.join(folder, filename), "w") as f: f.write(f"Content v{new_version}")
        self.log_queue.put(('log', 'server' if source == 'oem' else 'malicious_server', f" DEPLOYED: '{filename}'.", None))

    def update_button_visuals(self): 
        if self.checksum_enabled:
            self.toggle_checksum_button.configure(text="Checksum: ON", border_color="#4CAF50", text_color="#4CAF50")
        else:
            self.toggle_checksum_button.configure(text="Checksum: OFF", border_color="#f44336", text_color="#f44336")
            
        if hasattr(self, 'toggle_resilience_button'):
            if self.resilience_enabled:
                self.toggle_resilience_button.configure(text="Resilience: ON", border_color="#4CAF50", text_color="#4CAF50")
            else:
                self.toggle_resilience_button.configure(text="Resilience: OFF", border_color="#f44336", text_color="#f44336")

    def toggle_checksum_verification(self):
        self.checksum_enabled = not self.checksum_enabled
        self.save_config_value('Security', 'checksum_verification_enabled', str(self.checksum_enabled))
        self.update_button_visuals()
        self.log_queue.put(('log', 'tcu', f"Checksum Verification is now {'ON' if self.checksum_enabled else 'OFF'}.", None))

    def toggle_resilience(self):
        self.resilience_enabled = not self.resilience_enabled
        self.save_config_value('Security', 'ecu_resilience_enabled', str(self.resilience_enabled))
        self.update_button_visuals()
        self.log_queue.put(('log', 'ecu', f"ECU Watchdog/Resilience is now {'ON' if self.resilience_enabled else 'OFF'}.", None))

    def save_config_value(self, section, key, value):
        config = configparser.ConfigParser()
        config.read('config.ini')
        if not config.has_section(section): config.add_section(section)
        config.set(section, key, value)
        with open('config.ini', 'w') as configfile: config.write(configfile)

    def clear_logs(self):
        for log_box in [self.server_log, self.malicious_server_log, self.tcu_log, self.ecu_log]:
            log_box.configure(state='normal')
            log_box.delete('1.0', "end")
            log_box.configure(state='disabled')
    
    def on_closing(self):
        if self.simulation_running: self.stop_simulation()
        self.destroy()

if __name__ == '__main__':
    app = OTASimulatorApp()
    app.mainloop()