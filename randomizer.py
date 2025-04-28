import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox, simpledialog, colorchooser
import pygame
import pygame.sndarray
import os
import time
import random
import json
from collections import deque
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess  
import platform     
import numpy as np      
import soundfile as sf  
import math    
import sounddevice as sd 
import librosa 
import shutil
import sys
import pathlib

# --- Constants ---
MAX_PLAYERS = 6
INITIAL_VOLUME = 0.7
EVENT_CHECK_MS = 100
MAX_HISTORY = 20
SUPPORTED_FORMATS = ('.mp3', '.wav', '.ogg', '.flac', '.aif', '.aiff')
DEFAULT_SWITCH_INTERVAL_S = 7
# PRESETS_FILENAME = "player_presets.json"
# CONFIG_FILENAME = "config.json" # <<< For saving settings
WAVEFORM_HEIGHT = 60  # Adjusted height for rows
WAVEFORM_WIDTH = 400 # Adjusted width estimate
PROGRESS_UPDATE_MS = 50 # How often to update progress visual
RECORDING_SAMPLE_RATE = 44100 # Or 48000, match your system/virtual device
RECORDING_CHANNELS = 2 # Usually stereo
INITIAL_PAN = 0 # Center pan (-100 to +100)
EXPORT_SAMPLE_RATE = 44100 # Target sample rate for export
EXPORT_CHANNELS = 2       # Target channels for export (stereo)
DEFAULT_WAVEFORM_COLOR = "#90EE90" # Light green - a default color if none is set
DEFAULT_FADE_MS = 0
APP_NAME = "Randomizer" # Or whatever you prefer

# --- Pygame Custom Events ---
PLAYER_END_EVENTS = [pygame.USEREVENT + 1 + i for i in range(MAX_PLAYERS)]

# --- Global State ---
players = []
for i in range(MAX_PLAYERS):
    players.append({
        "id": i,
        "channel": None,
        "sound": None,
        "filepath": None,
        "audio_files": [],
        "selected_folder": None,
        "is_playing": False,
        "is_paused": False, # Added state
        "is_looping": False, # Added state
        "playback_start_time": 0.0,
        "total_paused_duration": 0.0, # Added state
        "pause_start_time": 0.0, # Added state
        "play_history": deque(maxlen=MAX_HISTORY),
        "playback_timer_id": None,
        "waveform_data": None, # <<< Added for waveform
        "progress_update_timer_id": None, # <<< Added for progress
        "current_track_duration_s": 0.0, # <<< Added to store duration
        "current_waveform_color": DEFAULT_WAVEFORM_COLOR, # <<< initialize with default
        # GUI Elements
        "gui": {
             "folder_label": None,
             "status_label": None,
             "play_pause_button": None, # Renamed
             "stop_button": None,
             "volume_slider": None,
             "interval_entry": None,
             "select_folder_button": None,
             "loop_button": None, # Added
             "previous_button": None, # Added
             "next_button": None, # Added
             "drop_target_label": None, # <<< Added for DnD
             "preset_dropdown": None, # <<< Added for Presets
             "reveal_button": None, # <<< Added for Reveal File
             "waveform_canvas": None, # <<< Added for waveform
             "pan_slider": None, # <<< Added for Pan
               # Add placeholder for fade slider later
             "fade_slider": None, # <<< Added for Fade
              
             
        }
    })

# --- NEW: Platform-Specific Data Path Functions ---

def get_user_data_dir():
    """Gets the appropriate user data directory based on the OS."""
    home = pathlib.Path.home()
    if sys.platform == "win32":
        appdata = os.getenv('LOCALAPPDATA')
        if appdata:
            return pathlib.Path(appdata) / APP_NAME
        else:
             appdata = os.getenv('APPDATA')
             if appdata:
                 return pathlib.Path(appdata) / APP_NAME
             else:
                 return home / ".config" / APP_NAME
    elif sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    else:
        return home / ".config" / APP_NAME

def get_presets_path():
    """Gets the full path to the presets file, ensuring the directory exists."""
    data_dir = get_user_data_dir()
    os.makedirs(data_dir, exist_ok=True) # Ensure directory exists
    return data_dir / "player_presets.json" # Use the old filename here

def get_config_path():
    """Gets the full path to the config file, ensuring the directory exists."""
    data_dir = get_user_data_dir()
    os.makedirs(data_dir, exist_ok=True) # Ensure directory exists
    return data_dir / "config.json" # Use the old filename here

# --- End NEW Path Functions ---

# --- Preset Handling Functions ---

def load_presets():
    """Loads presets from the JSON file in the user data directory, handling both old and new formats."""
    global folder_presets
    loaded_presets = {} # Load into a temporary dict first
    presets_file_path = get_presets_path() # <<< Get the correct path

    try:
        if presets_file_path.exists(): # <<< Use the path variable
            with open(presets_file_path, 'r') as f: # <<< Use the path variable
                # --- Load the entire file content ONCE ---
                try:
                    loaded_data = json.load(f)
                except json.JSONDecodeError as decode_error:
                    # Handle case where the file exists but is invalid JSON
                    print(f"Error decoding JSON from {presets_file_path}: {decode_error}") # <<< Updated path in message
                    messagebox.showerror("Preset Load Error", f"Could not parse presets file:\n{presets_file_path}\nIt might be corrupted.\nError: {decode_error}\nStarting with empty presets.") # <<< Updated path in message
                    folder_presets = {}
                    return # Exit the function early on decode error

                # --- Process loaded data (including backward compatibility) ---
                for name, value in loaded_data.items():
                    if isinstance(value, str): # Old format (just path)
                        print(f"Converting old format preset: '{name}'")
                        loaded_presets[name] = {
                            "path": value,
                            "color": DEFAULT_WAVEFORM_COLOR # Assign default color
                        }
                    elif isinstance(value, dict) and "path" in value: # New format (or partially new)
                        # Ensure color exists, add default if missing
                        if "color" not in value or not value["color"]:
                             print(f"Preset '{name}' missing color, assigning default.")
                             value["color"] = DEFAULT_WAVEFORM_COLOR
                        # Basic validation for color format before adding
                        if not (isinstance(value.get("color"), str) and value["color"].startswith('#') and len(value["color"]) == 7):
                             print(f"Preset '{name}' has invalid color '{value.get('color')}', assigning default.")
                             value["color"] = DEFAULT_WAVEFORM_COLOR

                        loaded_presets[name] = value # Add the validated/corrected entry
                    else:
                        print(f"Skipping invalid preset entry during load: '{name}'")
                # --- End Processing ---

                # --- Assign the processed dictionary to the global variable ---
                folder_presets = loaded_presets

                print(f"Loaded {len(folder_presets)} presets from {presets_file_path}") # <<< Updated path in message
        else:
            folder_presets = {}
            print(f"Preset file '{presets_file_path}' not found. Starting with empty presets.") # <<< Updated path in message
    except IOError as e: # Catch file reading errors
        print(f"Error reading presets file {presets_file_path}: {e}") # <<< Updated path in message
        messagebox.showerror("Preset Load Error", f"Could not read presets file:\n{presets_file_path}.\nError: {e}\nStarting with empty presets.") # <<< Updated path in message
        folder_presets = {}
    except Exception as e: # Catch other unexpected errors during loading
        print(f"Unexpected error loading presets: {e}")
        messagebox.showerror("Preset Load Error", f"An unexpected error occurred while loading presets.\nError: {e}\nStarting with empty presets.")
        folder_presets = {}

def save_presets():
    """Saves the current presets (new format) to the JSON file in the user data directory."""
    global folder_presets
    presets_file_path = get_presets_path() # <<< Get the correct path
    try:
        with open(presets_file_path, 'w') as f: # <<< Use the path variable
            # Ensure all entries have path and color before saving (should be guaranteed by load/add)
            valid_presets = {}
            for name, data in folder_presets.items():
                if isinstance(data, dict) and "path" in data and "color" in data:
                    valid_presets[name] = data
                else:
                    print(f"Warning: Skipping invalid preset data for '{name}' during save.")
            json.dump(valid_presets, f, indent=4)
            print(f"Saved {len(valid_presets)} presets to {presets_file_path}") # <<< Updated path in message
    except IOError as e:
        print(f"Error saving presets: {e}")
        messagebox.showerror("Preset Save Error", f"Could not save presets to {presets_file_path}.\nError: {e}") # <<< Updated path in message
    except Exception as e: # Catch other potential errors during save
        print(f"Unexpected error saving presets: {e}")
        messagebox.showerror("Preset Save Error", f"An unexpected error occurred while saving presets.\nError: {e}")


def update_preset_dropdowns():
    """Updates the values in all player preset dropdowns."""
    global folder_presets
    preset_names = sorted(list(folder_presets.keys())) # Get sorted list of names
    for i in range(MAX_PLAYERS):
        dropdown = players[i]["gui"]["preset_dropdown"]
        if dropdown:
            dropdown['values'] = preset_names
            # Optionally clear current selection if folder doesn't match preset
            # current_folder = players[i]["selected_folder"]
            # current_preset_name = dropdown.get()
            # if current_preset_name and folder_presets.get(current_preset_name) != current_folder:
            #      dropdown.set('') # Clear selection

def add_preset(name, path, color): # <<< ADD color parameter
    """Adds or updates a preset with path and color, then saves."""
    global folder_presets
    if not name or not path or not color:
        messagebox.showwarning("Add Preset", "Preset name, path, and color cannot be empty.")
        return False
    if not os.path.isdir(path):
         messagebox.showwarning("Add Preset", f"The path is not a valid folder:\n{path}")
         return False
    # Validate color format (basic check)
    if not (isinstance(color, str) and color.startswith('#') and len(color) == 7):
         messagebox.showwarning("Add Preset", f"Invalid color format provided: {color}. Must be #RRGGBB.")
         return False

    folder_presets[name] = {"path": path, "color": color} # <<< Store as dict
    print(f"Added/Updated preset: '{name}' -> Path: '{path}', Color: '{color}'")
    save_presets()
    update_preset_dropdowns()
    return True

def add_current_folder_as_preset(player_index):
    """Prompts for a name, asks for a color, and adds the player's current folder as a preset."""
    player_state = players[player_index]
    current_folder = player_state["selected_folder"]

    if not current_folder or not os.path.isdir(current_folder):
        messagebox.showinfo("Add Preset", f"Player {player_index+1}: No valid folder currently selected.", parent=root) # Use player_index+1 for display
        return

    default_name = os.path.basename(current_folder)
    preset_name = simpledialog.askstring("Add Folder Preset",
                                         f"Enter a name for this preset:\n(Folder: {current_folder})",
                                         initialvalue=default_name,
                                         parent=root)

    if not preset_name: # If user cancelled name entry
        print("Add preset cancelled (name entry).")
        return # <<< ADDED: Stop processing if name was cancelled

    # --- Ask for Color ---
    # Suggest the current color if it's a preset, otherwise default
    current_preset_color = DEFAULT_WAVEFORM_COLOR # Start with default
    for name, data in folder_presets.items():
        if isinstance(data, dict) and data.get("path") == current_folder:
            current_preset_color = data.get("color", DEFAULT_WAVEFORM_COLOR)
            break

    color_info = colorchooser.askcolor(title=f"Choose Waveform Color for '{preset_name}'",
                                       initialcolor=current_preset_color, # Suggest current/default
                                       parent=root) # Use root as parent

    if color_info and color_info[1]: # Check if a color was chosen (color_info[1] is the hex string)
        chosen_color = color_info[1]
        print(f"Color chosen: {chosen_color}")
        # Call the modified add_preset (This is the correct place)
        add_preset(preset_name, current_folder, chosen_color)
    else:
        print("Add preset cancelled (color selection).")
        messagebox.showinfo("Add Preset", "Preset not saved because no color was selected.", parent=root)



def on_preset_selected(event, player_index):
    """Handles selection from the preset dropdown."""
    player_state = players[player_index]
    dropdown = player_state["gui"]["preset_dropdown"]
    selected_name = dropdown.get()

    if selected_name in folder_presets:
        preset_data = folder_presets[selected_name]
        # Ensure data is in the expected format (should be due to load_presets)
        if isinstance(preset_data, dict) and "path" in preset_data:
            folder_path = preset_data["path"]
            # Color will be picked up by process_folder
            print(f"Player {player_index+1}: Preset '{selected_name}' selected. Path: {folder_path}")
            process_folder(player_index, folder_path)
        else:
             print(f"Player {player_index+1}: Invalid data format for preset '{selected_name}'.")
             messagebox.showerror("Preset Error", f"Invalid data format found for preset '{selected_name}'.", parent=root)
             dropdown.set('') # Clear selection
    else:
        print(f"Player {player_index+1}: Selected item '{selected_name}' not found in presets?")
        dropdown.set('') # Clear selection

    # Shift focus back to the main window after processing the selection
    # This prevents the Combobox from retaining focus and interfering with global key bindings like spacebar.
    print(f"Player {player_index+1}: Setting focus back to root window after preset selection.")
    root.focus_set()

# --- Preset Management Dialog Functions ---

def populate_preset_listbox(listbox):
    """Clears and repopulates the listbox with current preset names and colors."""
    global folder_presets
    listbox.delete(0, tk.END) # Clear existing items
    sorted_names = sorted(folder_presets.keys())
    for name in sorted_names:
        preset_data = folder_presets.get(name, {})
        color = preset_data.get("color", DEFAULT_WAVEFORM_COLOR) if isinstance(preset_data, dict) else DEFAULT_WAVEFORM_COLOR
        # Add name to listbox
        listbox.insert(tk.END, name)
        # Set the item's background color to visualize the preset color
        # NOTE: This colors the whole line. A small colored square might be better UI but more complex.
        try:
            listbox.itemconfig(tk.END, {'bg': color})
            # Determine contrasting text color (simple black/white)
            try:
                rgb = listbox.winfo_rgb(color) # Get RGB tuple (0-65535 range)
                brightness = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 65535
                text_color = "black" if brightness > 0.5 else "white"
                listbox.itemconfig(tk.END, {'fg': text_color})
            except tk.TclError: # Handle invalid color names gracefully
                 listbox.itemconfig(tk.END, {'fg': 'black'}) # Default to black text on error
        except tk.TclError: # Handle invalid color names for background
             print(f"Warning: Invalid color '{color}' for preset '{name}', using default background.")
             listbox.itemconfig(tk.END, {'fg': 'black'}) # Default text color if bg fails

def delete_selected_preset(listbox):
    """Deletes the selected preset from the listbox and global state."""
    global folder_presets
    selection_indices = listbox.curselection()

    if not selection_indices:
        messagebox.showwarning("Delete Preset", "Please select a preset from the list to delete.", parent=listbox.winfo_toplevel())
        return

    # Assuming single selection mode for simplicity
    selected_index = selection_indices[0]
    preset_name_to_delete = listbox.get(selected_index)

    if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the preset:\n'{preset_name_to_delete}'?", parent=listbox.winfo_toplevel()):
        if preset_name_to_delete in folder_presets:
            del folder_presets[preset_name_to_delete]
            print(f"Deleted preset: '{preset_name_to_delete}'")
            save_presets() # Save changes to file
            populate_preset_listbox(listbox) # Refresh the dialog list
            update_preset_dropdowns() # Update dropdowns in main window
        else:
            messagebox.showerror("Error", "Selected preset not found (this shouldn't happen).", parent=listbox.winfo_toplevel())
            populate_preset_listbox(listbox) # Refresh list just in case

# multi_player.py

# --- Add this function definition ---
def toggle_loop_all():
    """Toggles the loop state for all currently playing (not paused) players."""
    print("Global Control: Toggling loop for all active players.")
    action_taken = False
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        # Only toggle loop for players that are actively playing (not stopped or paused)
        # Toggling loop on a paused player might be confusing.
        if player_state["is_playing"] and not player_state["is_paused"]:
            print(f"  Toggling loop for Player {i+1}...")
            toggle_loop(i) # Call the individual toggle function
            action_taken = True
        # Optional: Add print statements for skipped players if desired
        # elif player_state["is_playing"] and player_state["is_paused"]:
        #     print(f"  Skipping Player {i+1} (paused).")
        # elif not player_state["is_playing"]:
        #     print(f"  Skipping Player {i+1} (stopped).")

    if not action_taken:
        print("Global Control: No active (playing and not paused) players found to toggle loop.")
        update_global_loop_button_state()
# --- End function definition ---

# multi_player.py

# --- Add these functions BEFORE open_manage_presets_dialog ---

def rename_selected_preset(listbox):
    """Renames the selected preset."""
    global folder_presets
    selection_indices = listbox.curselection()

    if not selection_indices:
        messagebox.showwarning("Rename Preset", "Please select a preset from the list to rename.", parent=listbox.winfo_toplevel())
        return

    selected_index = selection_indices[0]
    old_preset_name = listbox.get(selected_index)

    if old_preset_name not in folder_presets:
        messagebox.showerror("Error", "Selected preset not found in data (this shouldn't happen).", parent=listbox.winfo_toplevel())
        populate_preset_listbox(listbox) # Refresh list just in case
        return

    # Prompt for new name, pre-fill with old name
    new_preset_name = simpledialog.askstring(
        "Rename Preset",
        f"Enter new name for preset '{old_preset_name}':",
        initialvalue=old_preset_name,
        parent=listbox.winfo_toplevel() # Ensure dialog is on top of manage window
    )

    # Validate the new name
    if not new_preset_name:
        print("Rename cancelled by user.")
        return # User cancelled or entered empty string

    new_preset_name = new_preset_name.strip() # Remove leading/trailing whitespace

    if not new_preset_name:
        messagebox.showwarning("Rename Preset", "Preset name cannot be empty.", parent=listbox.winfo_toplevel())
        return

    if new_preset_name == old_preset_name:
        print("New name is the same as the old name. No change made.")
        return # No change needed

    if new_preset_name in folder_presets:
        messagebox.showwarning("Rename Preset", f"A preset with the name '{new_preset_name}' already exists.", parent=listbox.winfo_toplevel())
        return

    # Perform the rename in the dictionary
    try:
        preset_data = folder_presets[old_preset_name] # Get data associated with old name
        folder_presets[new_preset_name] = preset_data # Create new entry
        del folder_presets[old_preset_name]           # Delete old entry

        print(f"Renamed preset '{old_preset_name}' to '{new_preset_name}'")

        # Save changes and update UI
        save_presets()
        populate_preset_listbox(listbox) # Refresh the dialog list
        update_preset_dropdowns() # Update dropdowns in main window

    except KeyError:
        messagebox.showerror("Error", "Failed to rename preset (KeyError).", parent=listbox.winfo_toplevel())
        populate_preset_listbox(listbox) # Refresh list just in case
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred during rename:\n{e}", parent=listbox.winfo_toplevel())
        populate_preset_listbox(listbox) # Refresh list just in case

def change_selected_preset_color(listbox):
    """Changes the color associated with the selected preset."""
    global folder_presets
    selection_indices = listbox.curselection()

    if not selection_indices:
        messagebox.showwarning("Change Color", "Please select a preset from the list to change its color.", parent=listbox.winfo_toplevel())
        return

    selected_index = selection_indices[0]
    preset_name = listbox.get(selected_index)

    if preset_name not in folder_presets or not isinstance(folder_presets[preset_name], dict):
        messagebox.showerror("Error", "Selected preset data not found or invalid.", parent=listbox.winfo_toplevel())
        populate_preset_listbox(listbox)
        return

    # Get current color to suggest it
    current_color = folder_presets[preset_name].get("color", DEFAULT_WAVEFORM_COLOR)

    # Ask for new color
    color_info = colorchooser.askcolor(
        title=f"Choose New Waveform Color for '{preset_name}'",
        initialcolor=current_color,
        parent=listbox.winfo_toplevel() # Ensure dialog is on top
    )

    if color_info and color_info[1]: # Check if a color was chosen (color_info[1] is the hex string)
        chosen_color = color_info[1]
        print(f"New color chosen for '{preset_name}': {chosen_color}")

        # Update the dictionary
        folder_presets[preset_name]["color"] = chosen_color

        # Save changes and update UI
        save_presets()
        populate_preset_listbox(listbox) # Refresh the dialog list to show new color bg
        # No need to update main window dropdowns as only color changed
    else:
        print(f"Color change cancelled for '{preset_name}'.")

# --- End new function definitions ---

# --- Modify open_manage_presets_dialog ---
def open_manage_presets_dialog():
    """Opens a dialog to view, delete, rename, and change color of saved presets.""" # <<< Updated docstring
    manage_win = tk.Toplevel(root)
    manage_win.title("Manage Presets")
    # <<< Increased width slightly more for extra button >>>
    manage_win.geometry("550x300") # Adjust if needed
    manage_win.transient(root)
    manage_win.grab_set()

    main_frame = ttk.Frame(manage_win, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Listbox Frame with Scrollbar
    list_frame = ttk.Frame(main_frame)
    list_frame.pack(pady=(0, 10), fill=tk.BOTH, expand=True)

    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
    preset_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, exportselection=False) # exportselection=False

    scrollbar.config(command=preset_listbox.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    preset_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    populate_preset_listbox(preset_listbox)

    # Buttons Frame
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(fill=tk.X)

    # --- ADD Rename Button ---
    rename_button = ttk.Button(button_frame, text="Rename",
                               command=lambda lb=preset_listbox: rename_selected_preset(lb))
    rename_button.pack(side=tk.LEFT, padx=5)
    # --- END ADD ---

    # --- ADD Change Color Button ---
    change_color_button = ttk.Button(button_frame, text="Change Color",
                                     command=lambda lb=preset_listbox: change_selected_preset_color(lb))
    change_color_button.pack(side=tk.LEFT, padx=5)
    # --- END ADD ---

    delete_button = ttk.Button(button_frame, text="Delete",
                               command=lambda lb=preset_listbox: delete_selected_preset(lb))
    delete_button.pack(side=tk.LEFT, padx=5) # Keep Delete button

    close_button = ttk.Button(button_frame, text="Close", command=manage_win.destroy)
    close_button.pack(side=tk.RIGHT, padx=5) # Keep Close on the right

    # Center the dialog
    manage_win.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() // 2) - (manage_win.winfo_width() // 2)
    y = root.winfo_y() + (root.winfo_height() // 2) - (manage_win.winfo_height() // 2)
    manage_win.geometry(f"+{x}+{y}")

    manage_win.wait_window()
# --- End open_manage_presets_dialog modification ---

# --- End Preset Management Dialog Functions ---

# --- NEW: Recording State ---
is_recording = False
recording_file = None
recording_stream = None
# recording_queue = queue.Queue() # Optional: For threaded writing later
# --- NEW: Configuration State ---
selected_recording_device = None # <<< Stores the user's chosen device name
shuffle_count_entry = None # <<< Added for shuffle count entry
global_loop_button = None # <<< ADDED: To hold reference to the global loop button

# --- Config Handling Functions ---

def load_config():
    """Loads configuration like the selected recording device from the user data directory."""
    global selected_recording_device
    config_file_path = get_config_path() # <<< Get the correct path
    try:
        if config_file_path.exists(): # <<< Use the path variable
            with open(config_file_path, 'r') as f: # <<< Use the path variable
                config_data = json.load(f)
                selected_recording_device = config_data.get("recording_device_name") # Get saved name
                print(f"Loaded config from {config_file_path}. Recording device: '{selected_recording_device}'") # <<< Updated path in message
        else:
            selected_recording_device = None
            print(f"Config file '{config_file_path}' not found.") # <<< Updated path in message
    except (json.JSONDecodeError, IOError, KeyError) as e:
        print(f"Error loading config from {config_file_path}: {e}") # <<< Updated path in message
        selected_recording_device = None
    except Exception as e: # Catch other potential errors
        print(f"Unexpected error loading config from {config_file_path}: {e}") # <<< Updated path in message
        selected_recording_device = None


def save_config():
    """Saves configuration to the user data directory."""
    global selected_recording_device
    config_file_path = get_config_path() # <<< Get the correct path
    config_data = {
        "recording_device_name": selected_recording_device
    }
    try:
        with open(config_file_path, 'w') as f: # <<< Use the path variable
            json.dump(config_data, f, indent=4)
            print(f"Saved config to {config_file_path}") # <<< Updated path in message
    except IOError as e:
        print(f"Error saving config to {config_file_path}: {e}") # <<< Updated path in message
        messagebox.showerror("Config Save Error", f"Could not save configuration to\n{config_file_path}.\nError: {e}") # <<< Updated path in message
    except Exception as e: # Catch other potential errors
        print(f"Unexpected error saving config to {config_file_path}: {e}") # <<< Updated path in message
        messagebox.showerror("Config Save Error", f"An unexpected error occurred while saving configuration.\nError: {e}")


# --- Helper Function for Fade Duration --- <<< ADDED FUNCTION
# --- Helper Function for Fade Duration ---
def update_fade_duration(player_index, value_sec):
    """Updates the stored fade duration (in ms) when the slider (in sec) changes."""
    # <<< ADD DEBUG PRINT >>>
    # print(f"--- DEBUG: update_fade_duration called for index {player_index} with value {value_sec} ---")
    try:
        fade_s = float(value_sec)
        fade_ms = int(fade_s * 1000)
        players[player_index]["fade_duration_ms"] = fade_ms
        # <<< ADD DEBUG PRINT >>>
        # print(f"  DEBUG: Stored fade_ms for index {player_index}: {fade_ms}")
    except ValueError:
        print(f"Player {player_index}: Invalid fade value '{value_sec}' received from slider.")
    except tk.TclError:
        print(f"Player {player_index}: Error accessing fade slider value (TclError).")

# --- GUI Setup ---
root = TkinterDnD.Tk() # <<< Use TkinterDnD.Tk() for drag & drop
root.title("Randomizer") # Updated title
root.geometry("1000x900") # <<< Increased width slightly for pan slider

# --- Bind Spacebar to Global Pause/Resume ---
def spacebar_toggle(event):
    # Check if focus is on an Entry widget, if so, do nothing
    # to allow typing spaces in the interval entry.
    focused_widget = root.focus_get()
    if isinstance(focused_widget, tk.Entry):
        print("Spacebar ignored (Entry focused)")
        return
    print("Spacebar pressed - Toggling Pause/Resume All")
    toggle_pause_all()

root.bind('<space>', spacebar_toggle)
# --- End Spacebar Binding ---

# --- Bind 'l' key to Global Loop Toggle ---  <<< NEW BLOCK
def l_key_toggle_loop(event):
    """Callback for the 'l' key to toggle loop for all active players."""
    focused_widget = root.focus_get()
    # Ignore if focus is on any Entry widget (Interval, Shuffle Count)
    if isinstance(focused_widget, tk.Entry):
        print("'l' key ignored (Entry focused)")
        return
    print("'l' key pressed - Toggling Loop All")
    toggle_loop_all() # Call the existing global loop toggle function

# Bind the lowercase 'l' key press event to the callback
root.bind('<l>', l_key_toggle_loop)
# --- End 'l' key Binding ---            <<< END NEW BLOCK


# --- Bind '[' key to Previous Group --- <<< NEW BLOCK
def left_bracket_prev_group(event):
    """Callback for the '[' key to trigger Previous Group."""
    focused_widget = root.focus_get()
    # Ignore if focus is on any Entry widget
    if isinstance(focused_widget, tk.Entry):
        print("'[' key ignored (Entry focused)")
        return
    print("'[' key pressed - Triggering Previous Group")
    play_previous_group() # Call the existing global previous function

# Bind the left bracket key press event
root.bind('<bracketleft>', left_bracket_prev_group)
# --- End '[' key Binding ---           <<< END NEW BLOCK

# --- Bind ']' key to Next Group ---    <<< NEW BLOCK
def right_bracket_next_group(event):
    """Callback for the ']' key to trigger Next Group."""
    focused_widget = root.focus_get()
    # Ignore if focus is on any Entry widget
    if isinstance(focused_widget, tk.Entry):
        print("']' key ignored (Entry focused)")
        return
    print("']' key pressed - Triggering Next Group")
    play_next_group() # Call the existing global next function

# Bind the right bracket key press event
root.bind('<bracketright>', right_bracket_next_group)
# --- End ']' key Binding ---           <<< END NEW BLOCK

# --- Load Presets ---
load_config()   # <<< Load config at startup
load_presets() # Load presets before creating GUI elements that use them

# --- Settings Dialog Function ---

def open_settings_dialog():
    """Opens a dialog to configure settings like the recording device."""
    global selected_recording_device

    settings_win = tk.Toplevel(root)
    settings_win.title("Settings")
    settings_win.geometry("450x150")
    settings_win.transient(root) # Keep on top of main window
    settings_win.grab_set()      # Modal behavior

    main_frame = ttk.Frame(settings_win, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # --- Recording Device Selection ---
    device_frame = ttk.LabelFrame(main_frame, text="Recording Input Device", padding="10")
    device_frame.pack(fill=tk.X)

    device_label = ttk.Label(device_frame, text="Device:")
    device_label.pack(side=tk.LEFT, padx=(0, 5))

    device_dropdown = ttk.Combobox(device_frame, width=40, state="readonly")
    device_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # Populate dropdown
    available_devices = ["Default"] # Start with Default option
    try:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            # List only input devices
            if device.get('max_input_channels', 0) > 0:
                available_devices.append(f"{device['name']}") # Store just the name
    except Exception as e:
        print(f"Error querying audio devices for settings: {e}")
        messagebox.showerror("Device Error", f"Could not list audio devices: {e}", parent=settings_win)

    device_dropdown['values'] = available_devices

    # Set current selection
    if selected_recording_device and selected_recording_device in available_devices:
        device_dropdown.set(selected_recording_device)
    elif "Default" in available_devices:
         device_dropdown.set("Default") # Fallback to Default if saved one isn't found
    elif available_devices:
         device_dropdown.current(0) # Select first available if Default isn't there

    # --- Save/Cancel Buttons ---
    button_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
    button_frame.pack(fill=tk.X, side=tk.BOTTOM)

    def save_settings_action():
        global selected_recording_device
        chosen_device = device_dropdown.get()
        # Store None if "Default" is chosen, sounddevice handles default automatically then
        selected_recording_device = None if chosen_device == "Default" else chosen_device
        print(f"Settings saved. Recording device set to: '{selected_recording_device}'")
        save_config()
        settings_win.destroy()

    def cancel_action():
        settings_win.destroy()

    save_button = ttk.Button(button_frame, text="Save", command=save_settings_action)
    save_button.pack(side=tk.RIGHT, padx=5)
    cancel_button = ttk.Button(button_frame, text="Cancel", command=cancel_action)
    cancel_button.pack(side=tk.RIGHT)

    # Center the dialog
    settings_win.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() // 2) - (settings_win.winfo_width() // 2)
    y = root.winfo_y() + (root.winfo_height() // 2) - (settings_win.winfo_height() // 2)
    settings_win.geometry(f"+{x}+{y}")

    settings_win.wait_window() # Wait until dialog is closed

# --- Closing Function ---
def on_closing():
    # ... (on_closing remains mostly the same, already calls stop_recording and save_presets) ...
    print("Closing application...")
    if is_recording: stop_recording()
    save_presets() # Save presets
    save_config()  # <<< Save config
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        if player_state["playback_timer_id"]:
            try: root.after_cancel(player_state["playback_timer_id"])
            except tk.TclError: pass
        if player_state["channel"]: player_state["channel"].stop()
    if mixer_initialized: print("Stopping Pygame mixer..."); pygame.mixer.stop()
    if pygame.get_init(): print("Quitting Pygame..."); pygame.quit(); print("Pygame quit.")
    if root and root.winfo_exists(): print("Destroying Tkinter root..."); root.destroy(); print("Tkinter root destroyed.")

# --- Menu Bar ---
menu_bar = tk.Menu(root)
root.config(menu=menu_bar)

# --- NEW: File Menu ---
file_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="Export Mix...", command=lambda: export_mix()) # <<< Add Export command
file_menu.add_command(label="Export Stems...", command=lambda: export_stems())
file_menu.add_separator()
file_menu.add_command(label="Exit", command=on_closing)
# --- End File Menu ---

# Preset Menu
preset_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Presets", menu=preset_menu)
preset_menu.delete(0, tk.END) # Clear all previous entries first
for i in range(MAX_PLAYERS):
    preset_menu.add_command(
        label=f"Save Player {i+1}'s Folder as Preset...",
        command=lambda idx=i: add_current_folder_as_preset(idx)
    )
preset_menu.add_separator()
preset_menu.add_command(label="Manage Presets...", command=lambda: open_manage_presets_dialog()) # <<< ADD THIS

# --- NEW: Settings Menu ---
settings_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Settings", menu=settings_menu)
settings_menu.add_command(label="Audio Settings...", command=open_settings_dialog)
# --- End Settings Menu ---

# TODO: Add "Manage Presets" option later if needed
# preset_menu.add_separator()
# preset_menu.add_command(label="Manage Presets...", command=manage_presets_dialog) # Placeholder

# --- Pygame Initialization ---
mixer_initialized = False
try:
    print("Initializing Pygame...")
    pygame.init()
    print("Initializing Pygame Mixer...")
    pygame.mixer.init()
    print(f"Setting number of channels to {MAX_PLAYERS}...")
    pygame.mixer.set_num_channels(MAX_PLAYERS)
    print("Assigning channels...")
    for i in range(MAX_PLAYERS):
        players[i]["channel"] = pygame.mixer.Channel(i)
    mixer_initialized = True

   # --- Set Initial Volume/Pan Directly --- <<< MODIFIED BLOCK
    print("Setting initial volume and pan for channels...")
    for i in range(MAX_PLAYERS):
         channel = players[i]["channel"]
         if channel:
             try:
                 # Calculate initial gain based on constants
                 overall_gain = float(INITIAL_VOLUME) # 0.0 to 1.0
                 pan_val = float(INITIAL_PAN)         # -100 to +100

                 # Calculate pan multipliers (same logic as in update_channel_audio_settings)
                 pan_normalized = (pan_val + 100.0) / 200.0
                 left_multiplier = math.sqrt(1.0 - pan_normalized)
                 right_multiplier = math.sqrt(pan_normalized)

                 # Apply multipliers to overall gain
                 initial_left_gain = max(0.0, min(1.0, overall_gain * left_multiplier))
                 initial_right_gain = max(0.0, min(1.0, overall_gain * right_multiplier))

                 # Set directly on the channel
                 channel.set_volume(initial_left_gain, initial_right_gain)
                 print(f"  Player {i}: Initial gain set to L={initial_left_gain:.2f}, R={initial_right_gain:.2f}")

             except pygame.error as e:
                 print(f"  Error setting initial volume/pan for Player {i}: {e}")
             except Exception as e:
                 print(f"  Unexpected error setting initial volume/pan for Player {i}: {e}")
    # --- End Initial Volume/Pan Setting ---


except pygame.error as e:
    messagebox.showerror("Pygame Initialization Error", f"Failed to initialize Pygame or its mixer: {e}\nAudio playback will not work.")
except Exception as e:
     messagebox.showerror("Unexpected Error", f"An unexpected error occurred during setup: {e}")
# --- End of Pygame Initialization ---

# --- Waveform and Progress Functions ---

def clear_waveform(player_index):
    """Clears the waveform display for a player."""
    player_state = players[player_index]
    canvas = player_state["gui"]["waveform_canvas"]
    if canvas:
        canvas.delete("waveform_bg")
        canvas.delete("waveform_played")
    player_state["waveform_data"] = None
    player_state["current_track_duration_s"] = 0.0

def load_and_draw_waveform(player_index, track_path):
    """Loads audio, processes, and draws the static waveform background."""
    player_state = players[player_index]
    canvas = player_state["gui"]["waveform_canvas"]
    clear_waveform(player_index) # Clear previous first

    if not canvas: return # No canvas to draw on

    try:
        data, samplerate = sf.read(track_path, dtype='float32')
        player_state["current_track_duration_s"] = len(data) / samplerate
        print(f"Player {player_index}: Duration: {player_state['current_track_duration_s']:.2f}s, Rate: {samplerate}Hz")

        if data.ndim > 1: data = data.mean(axis=1) # Make mono

        samples_per_pixel = math.ceil(len(data) / WAVEFORM_WIDTH)
        if samples_per_pixel <= 0: samples_per_pixel = 1

        num_segments = WAVEFORM_WIDTH
        processed_data = []
        for i in range(num_segments):
            start = i * samples_per_pixel
            end = min((i + 1) * samples_per_pixel, len(data))
            if start >= end:
                processed_data.append(processed_data[-1] if processed_data else 0)
                continue
            segment = data[start:end]
            processed_data.append(np.max(np.abs(segment))) # Peak amplitude

        max_amp = max(processed_data) if processed_data else 1.0
        if max_amp == 0: max_amp = 1.0

        # Store normalized data (0 to 1) for progress drawing
        player_state["waveform_data"] = [amp / max_amp for amp in processed_data]

        # --- Drawing Background Waveform ---
        center_y = WAVEFORM_HEIGHT / 2
        half_height = WAVEFORM_HEIGHT / 2
        for i, normalized_amp in enumerate(player_state["waveform_data"]):
            x = i
            line_height = max(1, normalized_amp * half_height) # Ensure minimum 1 pixel height
            y1 = center_y - line_height
            y2 = center_y + line_height
            # Draw background line (e.g., grey)
            canvas.create_line(x, y1, x, y2, fill="grey50", width=1, tags="waveform_bg")

    except Exception as e:
        print(f"Player {player_index}: Error processing waveform: {e}")
        player_state["waveform_data"] = None
        player_state["current_track_duration_s"] = 0.0
        canvas.create_text(WAVEFORM_WIDTH / 2, WAVEFORM_HEIGHT / 2,
                           text="Waveform unavailable", fill="grey", tags="waveform_bg")

def update_waveform_progress(player_index):
    """Updates the 'played' portion of the waveform using time and the player's stored color."""
    player_state = players[player_index]
    canvas = player_state["gui"]["waveform_canvas"]
    duration = player_state["current_track_duration_s"]
    waveform_data = player_state["waveform_data"]
    # <<< Get the stored color for this player >>>
    progress_color = player_state.get("current_waveform_color", DEFAULT_WAVEFORM_COLOR)

    player_state["progress_update_timer_id"] = None # Clear previous timer ID

    if not canvas or not player_state["is_playing"] or player_state["is_paused"] or duration <= 0 or not waveform_data:
        if canvas: canvas.delete("waveform_played")
        return

    try:
        elapsed_time = time.monotonic() - (player_state["playback_start_time"] + player_state["total_paused_duration"])

        effective_elapsed_time = elapsed_time
        if player_state["is_looping"]:
            if duration > 0:
                 effective_elapsed_time = elapsed_time % duration

        progress_ratio = max(0.0, min(1.0, effective_elapsed_time / duration)) if duration > 0 else 0.0

        played_pixels = int(progress_ratio * WAVEFORM_WIDTH)
        canvas.delete("waveform_played") # Clear only the played part

        center_y = WAVEFORM_HEIGHT / 2
        half_height = WAVEFORM_HEIGHT / 2
        for i in range(played_pixels):
            if i < len(waveform_data):
                normalized_amp = waveform_data[i]
                x = i
                line_height = max(1, normalized_amp * half_height)
                y1 = center_y - line_height
                y2 = center_y + line_height
                # <<< Use the progress_color variable >>>
                canvas.create_line(x, y1, x, y2, fill=progress_color, width=1, tags="waveform_played")

        # Reschedule
        player_state["progress_update_timer_id"] = root.after(PROGRESS_UPDATE_MS, lambda idx=player_index: update_waveform_progress(idx))

    except Exception as e:
        print(f"Player {player_index+1}: Error updating waveform progress: {e}")
        if player_state["progress_update_timer_id"]:
            try:
                root.after_cancel(player_state["progress_update_timer_id"])
            except tk.TclError: pass
            player_state["progress_update_timer_id"] = None

# --- Core Functions  ---

def find_audio_files(folder):
    """Scans a folder for supported audio files."""
    found_files = []
    try:
        for filename in os.listdir(folder):
            if not filename.startswith('.') and filename.lower().endswith(SUPPORTED_FORMATS):
                full_path = os.path.join(folder, filename)
                found_files.append(full_path)
    except Exception as e:
        messagebox.showerror("Folder Error", f"Could not read folder: {folder}\nError: {e}")
    return found_files

# multi_player.py

# --- Ensure these functions are defined *before* handle_play_pause ---
# update_button_states(player_index)
# play_next_random_track(player_index)
# get_interval_ms(player_index)
# initiate_fadeout_and_schedule_next(player_index)
# _play_next_after_fade(player_index)
# update_waveform_progress(player_index)
# --------------------------------------------------------------------

def handle_play_pause(player_index):
    """Handles Play/Pause/Resume button clicks for a specific player."""
    print(f"--- handle_play_pause({player_index}) ENTERED ---")
    player_state = players[player_index]
    channel = player_state["channel"]

    if not mixer_initialized:
        messagebox.showerror("Mixer Error", "Audio system not ready.")
        return

    # --- Case 1: Start Playback (Currently Stopped) ---
    if not player_state["is_playing"]:
        if not player_state["audio_files"]:
            messagebox.showwarning("No Files", f"Player {player_index+1}: Select a folder first.")
            return
        print(f"Player {player_index+1}: Starting playback...")
        player_state["is_playing"] = True
        player_state["is_paused"] = False
        player_state["total_paused_duration"] = 0.0
        # Don't call update_button_states here yet, call after track starts
        play_next_random_track(player_index) # Starts _play_track which handles timers and button updates

    # --- Case 2: Pause Playback (Currently Playing) ---
    elif player_state["is_playing"] and not player_state["is_paused"]:
        if channel and channel.get_busy():
            print(f"Player {player_index+1}: Pausing...")
            channel.pause()
            player_state["is_paused"] = True
            player_state["pause_start_time"] = time.monotonic()

            # Cancel the automatic transition/fade timer
            if player_state["playback_timer_id"]:
                try:
                    root.after_cancel(player_state["playback_timer_id"])
                    print(f"  Player {player_index+1}: Cancelled playback_timer_id on pause.")
                except tk.TclError: pass
                player_state["playback_timer_id"] = None

            # Cancel the progress visualization timer
            if player_state["progress_update_timer_id"]:
                try:
                    root.after_cancel(player_state["progress_update_timer_id"])
                    print(f"  Player {player_index+1}: Cancelled progress_update_timer_id on pause.")
                except tk.TclError: pass
                player_state["progress_update_timer_id"] = None

            update_button_states(player_index) # Update GUI now
        else:
            print(f"Player {player_index+1}: Tried to pause, but channel not busy or invalid?")
            # Force state update just in case
            update_button_states(player_index)

    # --- Case 3: Resume Playback (Currently Paused) ---
    elif player_state["is_playing"] and player_state["is_paused"]:
        if channel:
            print(f"Player {player_index+1}: Resuming...")
            # Note: Progress timer was already cancelled on pause

            channel.unpause()
            player_state["is_paused"] = False
            paused_duration = time.monotonic() - player_state["pause_start_time"]
            player_state["total_paused_duration"] += paused_duration
            print(f"  Player {player_index+1}: Resumed after {paused_duration:.2f}s pause. Total paused: {player_state['total_paused_duration']:.2f}s")

            # --- Reschedule Fade/End Timer based on remaining time ---
            # Cancel any potentially lingering timer ID first (shouldn't be needed, but safe)
            if player_state["playback_timer_id"]:
                 try: root.after_cancel(player_state["playback_timer_id"])
                 except tk.TclError: pass
                 player_state["playback_timer_id"] = None

            if not player_state["is_looping"]:
                fade_ms = player_state.get("fade_duration_ms", 0)
                track_duration_s = player_state["current_track_duration_s"]
                track_duration_ms = int(track_duration_s * 1000) if track_duration_s > 0 else 0
                user_interval_ms = get_interval_ms(player_index) # Can be None

                # Calculate time already elapsed *before* this pause started
                elapsed_time_before_pause = (player_state["pause_start_time"] - player_state["playback_start_time"]) - (player_state["total_paused_duration"] - paused_duration)
                # Calculate time remaining in the track *from now*
                remaining_track_time_ms = -1 # Default if duration unknown
                if track_duration_ms > 0:
                    remaining_track_time_ms = max(0, track_duration_ms - int(elapsed_time_before_pause * 1000))

                print(f"  Player {player_index+1}: Resuming - Track Duration={track_duration_ms}ms, Elapsed Before Pause={elapsed_time_before_pause*1000:.0f}ms, Remaining={remaining_track_time_ms}ms")

                if fade_ms > 0 and remaining_track_time_ms > fade_ms:
                    # --- Fade Enabled: Reschedule Timer to trigger fade-out ---
                    natural_end_fade_start_delay_ms = max(1, remaining_track_time_ms - fade_ms)

                    fade_trigger_delay_ms = natural_end_fade_start_delay_ms
                    if user_interval_ms is not None:
                        # Calculate remaining interval time *from now*
                        remaining_interval_ms = max(1, user_interval_ms - int(elapsed_time_before_pause * 1000))
                        if remaining_interval_ms < natural_end_fade_start_delay_ms:
                             fade_trigger_delay_ms = remaining_interval_ms
                             print(f"  Player {player_index+1}: Resuming - User interval ({remaining_interval_ms}ms remaining) is sooner than natural fade start.")

                    print(f"  Player {player_index+1}: Resuming - Rescheduling fade-out initiation in {fade_trigger_delay_ms / 1000:.2f}s.")
                    timer_id = root.after(fade_trigger_delay_ms, lambda idx=player_index: initiate_fadeout_and_schedule_next(idx))
                    player_state["playback_timer_id"] = timer_id
                    channel.set_endevent() # Ensure end event is NOT used

                elif fade_ms == 0:
                    # --- No Fade: Reschedule Original Timer/End Event Logic ---
                    if user_interval_ms is not None:
                        remaining_interval_ms = max(1, user_interval_ms - int(elapsed_time_before_pause * 1000))
                        print(f"  Player {player_index+1}: Resuming - Rescheduling next track (no fade) in {remaining_interval_ms / 1000:.2f}s.")
                        timer_id = root.after(remaining_interval_ms, lambda idx=player_index: _play_next_after_fade(idx))
                        player_state["playback_timer_id"] = timer_id
                        channel.set_endevent() # Ensure end event is NOT used
                    elif remaining_track_time_ms > 0: # Only set end event if duration known and > 0
                        print(f"  Player {player_index+1}: Resuming - Playing remaining track (no fade). Setting end event.")
                        channel.set_endevent(PLAYER_END_EVENTS[player_index])
                        player_state["playback_timer_id"] = None
                    else: # No duration, no interval, no fade
                         print(f"  Player {player_index+1}: Resuming - No duration/interval/fade. Playing until stopped.")
                         player_state["playback_timer_id"] = None
                         channel.set_endevent() # Clear end event
                else: # Fade > 0 but remaining time too short
                     print(f"  Player {player_index+1}: Resuming - Remaining time ({remaining_track_time_ms}ms) too short for fade-out ({fade_ms}ms). Using end event if possible.")
                     if remaining_track_time_ms > 0:
                         channel.set_endevent(PLAYER_END_EVENTS[player_index])
                     else:
                         channel.set_endevent() # Clear if no duration
                     player_state["playback_timer_id"] = None
            else: # Looping is ON
                 print(f"  Player {player_index+1}: Resuming loop - no transition timer needed.")
                 player_state["playback_timer_id"] = None # Ensure no timer
                 channel.set_endevent() # Ensure no end event
            # --- End Reschedule Block ---

            # Restart progress timer only if duration is known
            if track_duration_s > 0:
                 player_state["progress_update_timer_id"] = root.after(PROGRESS_UPDATE_MS, lambda idx=player_index: update_waveform_progress(idx))
                 print(f"  Player {player_index+1}: Restarted progress update timer.")

            update_button_states(player_index) # Update GUI now
        else:
            print(f"Player {player_index+1}: Tried to resume, but channel not available?")
            # Force state update just in case
            update_button_states(player_index)
            update_global_loop_button_state()

# --- End handle_play_pause ---
  

def process_folder(player_index, folder_path):
    """Scans folder, updates player state, determines waveform color, and starts playback."""
    player_state = players[player_index]
    if player_state["is_playing"]: stop_playback(player_index)

    # --- Determine Waveform Color ---
    waveform_color = DEFAULT_WAVEFORM_COLOR # Start with default
    found_preset_match = False
    for name, data in folder_presets.items():
        if isinstance(data, dict) and data.get("path") == folder_path:
            waveform_color = data.get("color", DEFAULT_WAVEFORM_COLOR)
            print(f"Player {player_index+1}: Matched preset '{name}', using color {waveform_color}")
            found_preset_match = True
            # Update dropdown selection if it doesn't match
            if dropdown := player_state["gui"].get("preset_dropdown"):
                if dropdown.get() != name:
                    if name in dropdown['values']:
                        dropdown.set(name)
                    else: # Should not happen if dropdowns are synced
                         dropdown.set('')
            break # Found the preset, stop searching

    if not found_preset_match:
        print(f"Player {player_index+1}: Folder '{os.path.basename(folder_path)}' not found in presets, using default color {waveform_color}.")
        # Clear preset dropdown if the loaded folder doesn't match any preset
        if dropdown := player_state["gui"].get("preset_dropdown"):
             dropdown.set('')

    player_state["current_waveform_color"] = waveform_color # <<< STORE THE COLOR
    # --- End Determine Waveform Color ---

    player_state["selected_folder"] = folder_path
    player_state["filepath"] = None
    player_state["sound"] = None
    player_state["play_history"].clear()
    player_state["gui"]["folder_label"].config(text=f"Folder: {os.path.basename(folder_path)}")
    player_state["gui"]["status_label"].config(text="Scanning...")
    clear_waveform(player_index) # Clear waveform *before* loading new one
    root.update_idletasks()
    print(f"Player {player_index+1}: Processing folder: {folder_path}")
    player_state["audio_files"] = find_audio_files(folder_path)
    print(f"Player {player_index+1}: Found {len(player_state['audio_files'])} files.")

    if not player_state["audio_files"]:
        messagebox.showwarning("No Audio Found", f"No supported audio files found in:\n{folder_path}")
        player_state["gui"]["status_label"].config(text="No files found.")
        update_button_states(player_index)
    else:
        player_state["gui"]["status_label"].config(text=f"{len(player_state['audio_files'])} tracks loaded.")
        update_button_states(player_index)
        print(f"Player {player_index+1}: Audio files found. Starting playback automatically...")
        root.after(10, lambda idx=player_index: handle_play_pause(idx))

def select_folder(player_index):
    """Opens dialog to select folder for a player."""
    folder = filedialog.askdirectory(title=f"Select Folder for Player {player_index}")
    if folder: process_folder(player_index, folder)
    else: print(f"Player {player_index}: Folder selection cancelled.")

def get_interval_ms(player_index):
    """Gets interval from player's Entry, validates, converts to ms."""
    player_state = players[player_index]
    interval_entry = player_state["gui"]["interval_entry"]
    if not interval_entry: return None
    seconds_str = interval_entry.get().strip()
    if not seconds_str: return None
    try:
        seconds = int(seconds_str)
        if seconds <= 0: return None
        print(f"Player {player_index}: Using interval: {seconds} seconds.")
        return seconds * 1000
    except ValueError:
        print(f"Player {player_index}: Invalid interval '{seconds_str}'. Will play full track.")
        return None

# --- Helper: Selects and plays next track after fade/end ---
def _play_next_after_fade(player_index):
     """Helper to select and play the next random track *after* a fadeout/end completes."""
     player_state = players[player_index]
     print(f"Player {player_index}: Selecting next track after fade/end.")

     # Double-check state in case stop was called during fade
     if not player_state["is_playing"]:
         print(f"Player {player_index}: Aborting play next (player stopped).")
         return
     if not player_state["audio_files"]:
         print(f"Player {player_index}: Aborting play next (no files).")
         stop_playback(player_index) # Stop cleanly
         return

     # Add the track that just finished/faded out to history
     current_file = player_state["filepath"]
     if current_file and (not player_state["play_history"] or player_state["play_history"][-1] != current_file):
          player_state["play_history"].append(current_file)

     # Select next random track (same logic as before)
     possible_tracks = list(player_state["audio_files"])
     next_track = None
     non_history_tracks = [t for t in possible_tracks if t not in player_state["play_history"]]
     if non_history_tracks: next_track = random.choice(non_history_tracks)
     elif possible_tracks: next_track = random.choice(possible_tracks)
     else:
         print(f"Player {player_index}: Error selecting next. Stopping.")
         stop_playback(player_index)
         return

     print(f"Player {player_index}: Playing next: {os.path.basename(next_track)}")
     _play_track(player_index, next_track) # Play directly, _play_track handles fade-in

# --- Callback: Initiates fade-out and schedules next track ---
def initiate_fadeout_and_schedule_next(player_index):
    """Callback triggered by timer to start fade-out and schedule the next track."""
    player_state = players[player_index]
    channel = player_state["channel"]
    fade_ms = player_state.get("fade_duration_ms", 0)

    print(f"Player {player_index}: Timer fired to initiate fade-out.")
    player_state["playback_timer_id"] = None # Clear the ID as timer has fired

    # Check if still playing and channel is valid/busy
    if player_state["is_playing"] and channel and channel.get_busy():
        if fade_ms > 0:
            print(f"Player {player_index}: Fading out ({fade_ms}ms)...")
            channel.fadeout(fade_ms)
            # Schedule the actual track selection *after* the fade completes
            root.after(fade_ms + 50, lambda idx=player_index: _play_next_after_fade(idx))
        else:
            # This case shouldn't happen if fade_ms was > 0 when timer was set,
            # but handle it defensively: stop and play next immediately.
            print(f"Player {player_index}: Fade is 0, stopping and playing next immediately.")
            channel.stop()
            _play_next_after_fade(player_index)
    elif player_state["is_playing"]:
         # Channel not busy or invalid, but we intended to play next
         print(f"Player {player_index}: Channel not busy, playing next immediately.")
         _play_next_after_fade(player_index)
    else:
        print(f"Player {player_index}: Timer fired but player stopped.")



# --- Inside _play_track function ---
# --- Inside _play_track function ---
# --- Inside _play_track function ---
def _play_track(player_index, track_path):
    """Internal: Loads, plays a specific track, handles fade-in, and schedules fade-out/next."""
    player_state = players[player_index]
    channel = player_state["channel"]
    if not channel:
        print(f"Player {player_index}: Error - Channel not available."); stop_playback(player_index); return

    # --- Stop previous state ---
    print(f"Player {player_index}: Stopping previous state before playing '{os.path.basename(track_path)}'")
    channel.stop(); channel.set_endevent()
    if player_state["playback_timer_id"]:
        try: root.after_cancel(player_state["playback_timer_id"])
        except tk.TclError: pass
        player_state["playback_timer_id"] = None
        print(f"  Cancelled previous playback_timer_id.")
    if player_state["progress_update_timer_id"]:
        try: root.after_cancel(player_state["progress_update_timer_id"])
        except tk.TclError: pass
        player_state["progress_update_timer_id"] = None
        print(f"  Cancelled previous progress_update_timer_id.")
    player_state["is_paused"] = False; player_state["total_paused_duration"] = 0.0
    clear_waveform(player_index)
    # --- End stop previous state ---

    print(f"Player {player_index}: Attempting to play: {track_path}")
    try:
        # --- Load sound using soundfile (convert to int16) and get accurate duration --- <<< MODIFIED BLOCK
        print(f"  Player {player_index}: Loading with soundfile (dtype='int16')...")
        try:
            # Read as int16, ensure 2D array for sndarray
            audio_data, samplerate = sf.read(track_path, dtype='int16', always_2d=True)
            track_duration_s = len(audio_data) / samplerate
            player_state["current_track_duration_s"] = track_duration_s # Store accurate duration now
            track_duration_ms = int(track_duration_s * 1000) if track_duration_s > 0 else 0
            print(f"  Player {player_index}: Loaded via soundfile. Rate={samplerate}Hz, Duration={track_duration_s:.2f}s, Shape={audio_data.shape}")

            # Check if mixer sample rate matches (Pygame often uses 44100 or 22050)
            mixer_freq, mixer_format, mixer_channels = pygame.mixer.get_init()
            if samplerate != mixer_freq:
                # This is a bigger issue - ideally, Pygame mixer should be initialized
                # at a common rate, or resampling would be needed here (complex).
                # For now, just warn. Playback might be speed-shifted.
                print(f"  Player {player_index}: WARNING - Track sample rate ({samplerate}Hz) differs from mixer ({mixer_freq}Hz). Playback speed may be incorrect.")
                # If this becomes a common problem, resampling audio_data here before make_sound
                # using librosa.resample would be the proper fix.

            # Create Pygame sound object from the NumPy array
            print(f"  Player {player_index}: Creating sound object using pygame.sndarray.make_sound...")
            new_sound = pygame.sndarray.make_sound(audio_data)
            print(f"  Player {player_index}: Sound object created successfully.")

        except Exception as sf_err:
            # Handle errors during soundfile read or make_sound
            print(f"  Player {player_index}: Error loading/converting audio with soundfile/sndarray: {sf_err}")
            raise sf_err # Re-raise to be caught by the outer try/except

        # --- End Sound Loading Block ---

        player_state["sound"] = new_sound
        player_state["filepath"] = track_path
        player_state["gui"]["status_label"].config(text=f"Playing: {os.path.basename(track_path)}")

        # Get current settings (fade, loop, interval)
        is_currently_looping = player_state["is_looping"]
        fade_ms = player_state.get("fade_duration_ms", 0)
        user_interval_ms = get_interval_ms(player_index)

        print(f"Player {player_index}: Settings: loop={is_currently_looping}, fade={fade_ms}ms, interval={user_interval_ms}ms, duration={track_duration_ms}ms")

        # --- Play the sound with Fade-In ---
        play_args = {}
        if is_currently_looping: play_args["loops"] = -1
        if fade_ms > 0: play_args["fade_ms"] = fade_ms; print(f"Player {player_index}: Playing with {fade_ms}ms fade-in.")

        channel.play(new_sound, **play_args) # <<< PLAY AUDIO NOW
        player_state["is_playing"] = True
        player_state["playback_start_time"] = time.monotonic()
        update_channel_audio_settings(player_index) # Apply volume/pan immediately

        # --- Schedule Waveform Generation AFTER starting playback ---
        # (Waveform function still reads the file itself to get float32 data)
        print(f"Player {player_index}: Scheduling waveform load/draw.")
        root.after(10, lambda p_idx=player_index, t_path=track_path: load_and_draw_waveform_async(p_idx, t_path))

        # --- Scheduling Logic for Next Track (Only if NOT looping) ---
        # (This logic remains the same, using the accurate duration obtained from soundfile)
        if not is_currently_looping:
             if fade_ms > 0 and track_duration_ms > fade_ms:
                natural_end_fade_start_time_ms = max(1, track_duration_ms - fade_ms)
                fade_trigger_time_ms = natural_end_fade_start_time_ms
                if user_interval_ms is not None and user_interval_ms < natural_end_fade_start_time_ms:
                    fade_trigger_time_ms = user_interval_ms
                    print(f"Player {player_index}: User interval ({user_interval_ms}ms) is earlier than natural fade start.")
                print(f"Player {player_index}: Scheduling fade-out initiation in {fade_trigger_time_ms / 1000:.2f}s.")
                timer_id = root.after(fade_trigger_time_ms, lambda idx=player_index: initiate_fadeout_and_schedule_next(idx))
                player_state["playback_timer_id"] = timer_id
                channel.set_endevent()
             elif fade_ms == 0:
                if user_interval_ms is not None:
                    print(f"Player {player_index}: Scheduling next track (no fade) in {user_interval_ms / 1000:.2f}s.")
                    timer_id = root.after(user_interval_ms, lambda idx=player_index: _play_next_after_fade(idx))
                    player_state["playback_timer_id"] = timer_id
                    channel.set_endevent()
                elif track_duration_ms > 0:
                    print(f"Player {player_index}: Playing full track (no fade). Setting end event.")
                    channel.set_endevent(PLAYER_END_EVENTS[player_index])
                    player_state["playback_timer_id"] = None
                else:
                     print(f"Player {player_index}: No duration, interval, or fade. Playing until stopped.")
                     player_state["playback_timer_id"] = None
                     channel.set_endevent()
             else: # Fade > 0 but duration too short
                 print(f"Player {player_index}: Track duration ({track_duration_ms}ms) too short for fade-out ({fade_ms}ms). Playing full track.")
                 if track_duration_ms > 0: channel.set_endevent(PLAYER_END_EVENTS[player_index])
                 else: channel.set_endevent()
                 player_state["playback_timer_id"] = None
        else: # Looping
            print(f"Player {player_index}: Looping enabled, no automatic transition scheduled.")
            player_state["playback_timer_id"] = None
            channel.set_endevent()

        # Progress timer is started by load_and_draw_waveform_async
        print(f"Player {player_index}: Playback started successfully.")

    # --- Outer Error Handling ---
    except pygame.error as e: # Catch Pygame errors (e.g., from channel.play)
        messagebox.showerror("Playback Error", f"Player {player_index}: Pygame error during playback setup:\n{os.path.basename(track_path)}\nError: {e}")
        player_state["sound"] = None; player_state["filepath"] = None; player_state["is_playing"] = False
        player_state["gui"]["status_label"].config(text="Playback Error.")
        clear_waveform(player_index)
    except Exception as e: # Catch other errors (e.g., from soundfile read)
         messagebox.showerror("File Error", f"Player {player_index}: Could not process file:\n{os.path.basename(track_path)}\nError: {e}")
         player_state["sound"] = None; player_state["filepath"] = None; player_state["is_playing"] = False
         player_state["gui"]["status_label"].config(text="File Error.")
         clear_waveform(player_index)

    update_button_states(player_index)


# --- NEW Helper function to load/draw waveform asynchronously ---
def load_and_draw_waveform_async(player_index, track_path):
    """Loads audio data, processes, draws waveform, and starts progress updates. Called via root.after."""
    player_state = players[player_index]
    canvas = player_state["gui"]["waveform_canvas"]

    # Check if the track currently playing is still the one we intended to draw
    if not player_state["is_playing"] or player_state["filepath"] != track_path:
        print(f"Player {player_index}: Skipping async waveform draw (track changed or stopped).")
        return

    if not canvas: return # No canvas

    print(f"Player {player_index}: Async waveform: Starting load/process for {os.path.basename(track_path)}")
    try:
        # --- Perform the potentially slow operations ---
        data, samplerate = sf.read(track_path, dtype='float32')
        # Use the more accurate duration from sf.read now
        accurate_duration_s = len(data) / samplerate
        player_state["current_track_duration_s"] = accurate_duration_s # Update duration
        print(f"Player {player_index}: Async waveform: Accurate Duration: {accurate_duration_s:.2f}s, Rate: {samplerate}Hz")

        if data.ndim > 1: data = data.mean(axis=1) # Make mono

        samples_per_pixel = math.ceil(len(data) / WAVEFORM_WIDTH)
        if samples_per_pixel <= 0: samples_per_pixel = 1

        num_segments = WAVEFORM_WIDTH
        processed_data = []
        for i in range(num_segments):
            start = i * samples_per_pixel
            end = min((i + 1) * samples_per_pixel, len(data))
            if start >= end:
                processed_data.append(processed_data[-1] if processed_data else 0)
                continue
            segment = data[start:end]
            processed_data.append(np.max(np.abs(segment))) # Peak amplitude

        max_amp = max(processed_data) if processed_data else 1.0
        if max_amp == 0: max_amp = 1.0

        # Store normalized data (0 to 1)
        player_state["waveform_data"] = [amp / max_amp for amp in processed_data]
        # --- End slow operations ---

        # --- Drawing Background Waveform (on the main thread via canvas) ---
        canvas.delete("waveform_bg") # Clear any previous "unavailable" message
        center_y = WAVEFORM_HEIGHT / 2
        half_height = WAVEFORM_HEIGHT / 2
        for i, normalized_amp in enumerate(player_state["waveform_data"]):
            x = i
            line_height = max(1, normalized_amp * half_height)
            y1 = center_y - line_height
            y2 = center_y + line_height
            canvas.create_line(x, y1, x, y2, fill="grey50", width=1, tags="waveform_bg")
        print(f"Player {player_index}: Async waveform: Drawing complete.")

        # --- Start Progress Visualization NOW that waveform data exists ---
        if accurate_duration_s > 0:
            # Cancel any lingering progress timer just in case
            if player_state["progress_update_timer_id"]:
                try: root.after_cancel(player_state["progress_update_timer_id"])
                except tk.TclError: pass
            player_state["progress_update_timer_id"] = root.after(PROGRESS_UPDATE_MS, lambda idx=player_index: update_waveform_progress(idx))
            print(f"Player {player_index}: Async waveform: Started progress updates.")
        # --- End Start Progress ---

    except Exception as e:
        print(f"Player {player_index}: Async waveform: Error processing: {e}")
        player_state["waveform_data"] = None
        # Don't reset duration here, keep the approximate one from get_length if possible
        # player_state["current_track_duration_s"] = 0.0
        if canvas:
             canvas.delete("waveform_bg") # Clear potential partial drawing
             canvas.create_text(WAVEFORM_WIDTH / 2, WAVEFORM_HEIGHT / 2,
                                text="Waveform unavailable", fill="grey", tags="waveform_bg")


def play_next_random_track(player_index):
    """Selects and plays the next random track (called by timer or end event)."""
    # NOTE: This should only be called when NOT looping, because _play_track
    # cancels the timer when is_looping is True.
    player_state = players[player_index]

    # --- Remove the loop check from the beginning ---
    # if player_state["is_looping"]: ... (DELETE THIS BLOCK)

    # --- Original logic for selecting next random track ---
    if not player_state["is_playing"]: print(f"Player {player_index}: Play next called but not playing."); stop_playback(player_index); return
    if not player_state["audio_files"]: print(f"Player {player_index}: No files."); stop_playback(player_index); messagebox.showwarning("No Files", f"Player {player_index}: No audio files."); return

    current_file = player_state["filepath"]
    if current_file and (not player_state["play_history"] or player_state["play_history"][-1] != current_file):
         player_state["play_history"].append(current_file)

    possible_tracks = list(player_state["audio_files"])
    next_track = None
    non_history_tracks = [t for t in possible_tracks if t not in player_state["play_history"]]
    if non_history_tracks: next_track = random.choice(non_history_tracks)
    elif possible_tracks: next_track = random.choice(possible_tracks)
    else: print(f"Player {player_index}: Error selecting next. Stopping."); stop_playback(player_index); return

    print(f"Player {player_index}: Selected next: {os.path.basename(next_track)}")
    _play_track(player_index, next_track)

# --- Drag and Drop Handler ---
def handle_folder_drop(player_index, event):
    """Handles a folder being dropped onto a player's target label."""
    player_state = players[player_index]
    path_string = event.data.strip()
    print(f"Player {player_index}: Drop event data: '{path_string}'")

    # Basic parsing (remove braces, quotes)
    if path_string.startswith('{') and path_string.endswith('}'):
        path_string = path_string[1:-1]
    path_string = path_string.strip('"')

    # Check if it's a directory
    if os.path.isdir(path_string):
        print(f"Player {player_index}: Valid folder dropped: {path_string}")
        process_folder(player_index, path_string)
        # Optional: Visual feedback on drop target
        player_state["gui"]["drop_target_label"].config(fg="black")
    else:
        print(f"Player {player_index}: Dropped item is not a valid folder: {path_string}")
        messagebox.showwarning("Invalid Drop", f"Player {player_index}: Please drop a single folder, not files.")
        # Optional: Visual feedback on drop target
        player_state["gui"]["drop_target_label"].config(fg="red") # Indicate error
        # Reset color after a delay?
        root.after(1000, lambda idx=player_index: players[idx]["gui"]["drop_target_label"].config(fg="grey"))


def toggle_loop(player_index):
    """Toggles looping for the specified player by restarting the track."""
    player_state = players[player_index]
    channel = player_state["channel"]

    
    # --- MODIFIED CHECK ---
    # Only prevent toggle if sound/channel is missing. Allow state change even if stopped.
    if not player_state["sound"] or not channel:
         print(f"Player {player_index}: Cannot toggle loop (no sound loaded or channel missing).")
         return
    # --- END MODIFIED CHECK ---

    # Toggle the state
    player_state["is_looping"] = not player_state["is_looping"]
    print(f"Player {player_index}: Looping toggled {'ON' if player_state['is_looping'] else 'OFF'}")
    update_button_states(player_index) # Update button text

    # --- Restart Logic ---
    # Restart only if the track is currently playing OR paused to apply the new loop setting.
    # If stopped, the new loop setting will apply the next time Play is pressed.
    if player_state["is_playing"]: # This check correctly includes the paused state (is_playing is True when paused)
        current_filepath = player_state["filepath"]
        if current_filepath:
            print(f"Player {player_index}: Restarting track to apply loop setting.")
            # Call _play_track which uses the updated is_looping flag
            _play_track(player_index, current_filepath)
        else:
            print(f"Player {player_index}: Error - Cannot apply loop, current filepath unknown.")
            stop_playback(player_index)
    else:
         print(f"Player {player_index}: Loop setting changed while stopped. Will apply on next play.")
    # --- End Restart Logic ---

# --- Previous Track ---
# --- Modify play_previous_track ---
def play_previous_track(player_index):
    """Plays the previous track from history (handles fadeout)."""
    player_state = players[player_index]
    channel = player_state["channel"]
    fade_ms = player_state.get("fade_duration_ms", 0)

    if not player_state["is_playing"]: print(f"Player {player_index}: Not playing."); return
    if len(player_state["play_history"]) < 1: print(f"Player {player_index}: No history."); return

    # Get previous track path *before* fading
    previous_track_path = player_state["play_history"].pop() # Pop it now

    # --- Cancel any scheduled automatic transition ---
    if player_state["playback_timer_id"]:
        try: root.after_cancel(player_state["playback_timer_id"])
        except tk.TclError: pass
        player_state["playback_timer_id"] = None
        print(f"  Cancelled scheduled transition timer.")

    # --- Fadeout Logic ---
    if channel and channel.get_busy() and fade_ms > 0:
        print(f"Player {player_index}: Fading out ({fade_ms}ms) for previous track.")
        channel.fadeout(fade_ms)
        # Schedule playing the previous track *after* the fade
        root.after(fade_ms + 50, lambda idx=player_index, path=previous_track_path: _play_track(idx, path))
    else:
        # No fade or channel not busy, play immediately
        print(f"Player {player_index}: No fade, playing previous track immediately.")
        if channel: channel.stop() # Ensure stopped if no fade
        _play_track(player_index, previous_track_path)

# --- Next Track (Manual) ---
# --- Modify play_next_manual ---
# --- Corrected play_next_manual for IMMEDIATE skip ---
def play_next_manual(player_index):
    """Manually skips IMMEDIATELY to the next random track, ignoring fade-out."""
    player_state = players[player_index]
    channel = player_state["channel"]
    # fade_ms = player_state.get("fade_duration_ms", 0) # No longer needed here

    if not player_state["is_playing"]:
        print(f"Player {player_index}: Not playing, cannot skip.")
        return

    print(f"Player {player_index}: Manual skip requested (Immediate)...")

    # --- Cancel any scheduled automatic transition ---
    if player_state["playback_timer_id"]:
        try: root.after_cancel(player_state["playback_timer_id"])
        except tk.TclError: pass
        player_state["playback_timer_id"] = None
        print(f"  Cancelled scheduled transition timer.")

    # --- Always Stop Immediately ---
    print(f"Player {player_index}: Stopping current track immediately for manual skip.")
    if channel:
        channel.stop() # Stop sound immediately
        channel.set_endevent() # Clear any end event just in case

    # --- Proceed to Next Track Immediately ---
    _play_next_after_fade(player_index) # Call helper to select and play next

# --- End Corrected play_next_manual ---

def stop_playback(player_index):
    """Stops playback completely for the specified player."""
    player_state = players[player_index]
    channel = player_state["channel"]
    fade_ms = player_state.get("fade_duration_ms", 0)
    # <<< ADD DEBUG PRINT >>>
    # print(f"--- DEBUG: stop_playback({player_index}) retrieved fade_ms: {fade_ms} ---")
    was_playing = player_state["is_playing"]
    player_state["is_playing"] = False; player_state["is_paused"] = False; player_state["is_looping"] = False

    if player_state["playback_timer_id"]: root.after_cancel(player_state["playback_timer_id"]); player_state["playback_timer_id"] = None
    # <<< Cancel progress timer on stop >>>
    if player_state["progress_update_timer_id"]: root.after_cancel(player_state["progress_update_timer_id"]); player_state["progress_update_timer_id"] = None

    if channel: print(f"Player {player_index}: Stopping channel."); channel.stop(); channel.set_endevent()
    if was_playing: player_state["gui"]["status_label"].config(text=f"Stopped: {os.path.basename(player_state['filepath'] or 'N/A')}")

    clear_waveform(player_index) # <<< Clear waveform on stop
    update_button_states(player_index)
    update_global_loop_button_state()


# --- NEW: Combined Volume and Pan Update Function ---
def update_channel_audio_settings(player_index, *args): # Use *args to accept potential extra args from Scale command
    """Reads Volume and Pan sliders and applies settings to the channel."""
    player_state = players[player_index]
    channel = player_state["channel"]
    gui = player_state["gui"]

    # Check if GUI elements exist before trying to get values
    if not mixer_initialized or not channel or not gui.get("volume_slider") or not gui.get("pan_slider"):
        # print(f"Debug Player {player_index}: Missing components for audio settings update.") # Optional debug
        return # Exit if components aren't ready

    try:
        # Read values from sliders
        volume_val = gui["volume_slider"].get() # 0-100
        pan_val = gui["pan_slider"].get()       # -100 to +100

        # Calculate overall gain (0.0 to 1.0)
        overall_gain = float(volume_val) / 100.0

        # Calculate pan multipliers (Linear Pan Law)
        # Normalize pan_val from -100..+100 to 0..1
        pan_normalized = (float(pan_val) + 100.0) / 200.0
        # Apply square root for a slightly more constant power feel (optional)
        left_multiplier = math.sqrt(1.0 - pan_normalized)
        right_multiplier = math.sqrt(pan_normalized)

        # Apply multipliers to overall gain
        final_left_gain = overall_gain * left_multiplier
        final_right_gain = overall_gain * right_multiplier

        # Clamp values just in case (0.0 to 1.0)
        final_left_gain = max(0.0, min(1.0, final_left_gain))
        final_right_gain = max(0.0, min(1.0, final_right_gain))

        # Set channel volume
        channel.set_volume(final_left_gain, final_right_gain)
        # print(f"Player {player_index}: Vol={volume_val}, Pan={pan_val} -> L={final_left_gain:.2f}, R={final_right_gain:.2f}") # Debug

    except pygame.error as e:
        print(f"Error setting volume/pan for Player {player_index}: {e}")
    except (ValueError, tk.TclError) as e: # Catch errors getting slider values
        print(f"Error reading slider value for Player {player_index}: {e}")
# --- End NEW Function ---

# --- Modify handle_player_end ---
def handle_player_end(player_index):
    """Handles the end event (only used when fade=0 and no interval)."""
    player_state = players[player_index]
    print(f"Player {player_index}: Sound finished naturally via end event (fade=0, no interval).")

    if player_state["is_playing"]:
        # Directly call the helper to select and play the next track
        _play_next_after_fade(player_index)
    else:
        # This case might happen if stop was called just before event processed
        print(f"Player {player_index}: End event received but not in playing state. Updating buttons.")
        update_button_states(player_index)

def check_pygame_events():
    """Periodically check for Pygame events."""
    if not root.winfo_exists(): return
    try:
        for event in pygame.event.get():
            for i in range(MAX_PLAYERS):
                if event.type == PLAYER_END_EVENTS[i]:
                    print(f"Player {i}: Received END event ({PLAYER_END_EVENTS[i]})")
                    player_state = players[i]; channel = player_state["channel"]
                    is_busy = False
                    try:
                        if channel: is_busy = channel.get_busy()
                        print(f"  Player {i}: Channel busy status on event: {is_busy}")
                    except pygame.error as busy_e: print(f"  Warning: Error checking busy status for Player {i}: {busy_e}"); continue
                    if player_state["is_playing"] and not is_busy: handle_player_end(i)
                    elif player_state["is_playing"] and is_busy: print(f"  Player {i}: Ignoring END event (channel busy - likely stale).")
                    elif not player_state["is_playing"]: print(f"  Player {i}: Ignoring END event (player not playing).")
                    break
    except pygame.error as e:
        if "mixer system not initialized" not in str(e): print(f"Pygame error during event check: {e}")
    except Exception as e: print(f"Unexpected error during event check: {e}")
    try:
        if root.winfo_exists(): root.after(EVENT_CHECK_MS, check_pygame_events)
    except tk.TclError: print("Event check scheduling stopped: Tkinter root destroyed.")

# --- Reveal File Function ---
def reveal_current_track(player_index):
    """Reveals the currently loaded file for the player in the system file explorer."""
    player_state = players[player_index]
    track_path = player_state["filepath"] # Get the path for this specific player

    if not track_path:
        print(f"Player {player_index}: No track is currently loaded.")
        messagebox.showinfo("Reveal File", f"Player {player_index}: No track is currently loaded.")
        return

    if not os.path.exists(track_path):
        print(f"Player {player_index}: Error - Current track path does not exist: {track_path}")
        messagebox.showerror("Reveal File Error", f"Player {player_index}: The file could not be found at:\n{track_path}")
        return

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(['explorer', f'/select,"{track_path}"'], check=True)
        elif system == "Darwin": # macOS
            subprocess.run(['open', '-R', track_path], check=True)
        elif system == "Linux":
            dir_path = os.path.dirname(track_path)
            subprocess.run(['xdg-open', dir_path], check=True)
        else:
            messagebox.showwarning("Unsupported OS", f"File revealing is not supported on this OS ({system}).")
            print(f"Unsupported OS for revealing file: {system}")

    except FileNotFoundError as e:
         messagebox.showerror("Command Error", f"Could not find the necessary command to reveal the file.\nError: {e}")
         print(f"Error running reveal command: {e}")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("Reveal Error", f"Failed to reveal the file.\nCommand exited with error: {e}")
        print(f"Error revealing file: {e}")
    except Exception as e:
        messagebox.showerror("Unexpected Error", f"An unexpected error occurred while trying to reveal the file.\n{e}")
        print(f"Unexpected error revealing file: {e}")


# --- NEW: Recording Functions ---

def audio_callback(indata, frames, time, status):
    """This function is called by sounddevice for each new audio chunk."""
    global recording_file # Use global file object
    # global recording_queue # Optional: Use queue for threading later

    if status:
        print(f"Recording status warning: {status}", flush=True) # Use flush for immediate output from callback

    # --- Direct Writing (Simpler, can block callback) ---
    if recording_file is not None:
        try:
            recording_file.write(indata)
        except Exception as e:
            print(f"Error writing to recording file: {e}", flush=True)
    # --- End Direct Writing ---

    # --- Queue-based Writing (More Robust, requires writer thread) ---
    # recording_queue.put(indata.copy()) # Put a copy into the queue
    # --- End Queue-based Writing ---

def start_recording():
    """Starts recording the audio output to a WAV file using the selected device."""
    global is_recording, recording_file, recording_stream, selected_recording_device # Use selected device

    if is_recording: print("Already recording."); return

    # --- Check if device is configured ---
    if selected_recording_device is None and "Default" not in sd.query_devices(kind='input')['name']:
         # Check if default exists if None is selected
         # A bit complex, maybe just check if selected_recording_device is None
         pass # Let sounddevice handle default if None

    if selected_recording_device is None:
         print("No specific recording device selected, using system default input.")
         # Allow proceeding, sounddevice will use default input if device=None
         # messagebox.showinfo("Recording Device", "No recording device selected in Settings.\nAttempting to use system default input.")
         # Alternatively, force user to select:
         # messagebox.showerror("Configuration Needed", "Please select a recording input device in Settings -> Audio Settings... first.")
         # return

    # 1. Prompt for save file
    filepath = filedialog.asksaveasfilename(
        title="Save Recording As...",
        defaultextension=".wav",
        filetypes=[("WAV files", "*.wav"), ("All Files", "*.*")]
    )
    if not filepath: print("Recording cancelled by user."); return

    # 2. Use Selected Device
    device_name_to_use = selected_recording_device # This can be None for default
    print(f"Attempting to record from device: '{device_name_to_use or 'Default Input'}'")

    try:
        # Verify device exists if a specific one is selected
        if device_name_to_use:
            sd.check_input_settings(device=device_name_to_use, channels=RECORDING_CHANNELS, samplerate=RECORDING_SAMPLE_RATE)
        else:
             # Check default settings if using default
             sd.check_input_settings(channels=RECORDING_CHANNELS, samplerate=RECORDING_SAMPLE_RATE)

        sample_rate = RECORDING_SAMPLE_RATE
        channels = RECORDING_CHANNELS

    except ValueError as e: # Catches device not found or invalid settings
         messagebox.showerror("Device Error", f"Recording input device '{device_name_to_use or 'Default'}' not found or settings invalid.\nPlease check Settings -> Audio Settings...\nError: {e}")
         print(f"Error: Recording device '{device_name_to_use or 'Default'}' invalid: {e}")
         return
    except Exception as e: # Catch other potential errors
         messagebox.showerror("Device Query Error", f"Error checking audio device settings: {e}")
         print(f"Error checking device settings: {e}")
         return

    # 3. Open SoundFile
    try:
        recording_file = sf.SoundFile(filepath, mode='w', samplerate=sample_rate,
                                      channels=channels, subtype='PCM_16')
        print(f"Opened recording file: {filepath}")
    except Exception as e:
        messagebox.showerror("File Error", f"Could not open file for recording:\n{filepath}\nError: {e}")
        print(f"Error opening recording file: {e}"); recording_file = None; return

    # 4. Start InputStream
    try:
        recording_stream = sd.InputStream(
            samplerate=sample_rate,
            device=device_name_to_use, # Use the selected name (or None for default)
            channels=channels,
            callback=audio_callback
        )
        recording_stream.start()
        is_recording = True
        print("Recording started...")
        record_button.config(text="Stop Recording")
        recording_status_label.config(text=f"Recording to: {os.path.basename(filepath)}", fg="red")

    except sd.PortAudioError as e:
        messagebox.showerror("Audio Stream Error", f"Could not start recording stream using '{device_name_to_use or 'Default'}'.\nIs it active and not in use?\nError: {e}")
        print(f"PortAudioError starting stream: {e}")
        if recording_file: recording_file.close(); recording_file = None
        is_recording = False
    except Exception as e:
        messagebox.showerror("Stream Error", f"An unexpected error occurred starting the recording stream.\nError: {e}")
        print(f"Unexpected error starting stream: {e}")
        if recording_file: recording_file.close(); recording_file = None
        is_recording = False

def stop_recording():
    """Stops the recording stream and closes the file."""
    global is_recording, recording_file, recording_stream

    if not is_recording:
        print("Not currently recording.")
        return

    print("Stopping recording...")
    try:
        if recording_stream:
            recording_stream.stop()
            recording_stream.close()
            print("Recording stream stopped and closed.")
        # Optional: Signal writer thread to stop and wait for queue to empty if using queue

        if recording_file:
            recording_file.close()
            print("Recording file closed.")

    except sd.PortAudioError as e:
        print(f"PortAudioError stopping stream: {e}") # Log error but continue cleanup
    except Exception as e:
        print(f"Error stopping recording: {e}") # Log error but continue cleanup
    finally:
        # Ensure state is reset regardless of errors during stop/close
        recording_stream = None
        recording_file = None
        is_recording = False
        # Update GUI
        record_button.config(text="Record Output")
        recording_status_label.config(text="Not Recording", fg="black")
        print("Recording stopped.")

def handle_record_button():
    """Toggles recording state when the button is pressed."""
    if is_recording:
        stop_recording()
    else:
        start_recording()

# --- NEW: Export Mix Function ---
def export_mix():
    """Exports a mix of the currently loaded tracks with user-defined panning and fades."""
    print("Starting Export Mix process...")

    # --- Get Fade Times from User ---
    try:
        fade_in_sec = simpledialog.askfloat("Export Mix Fades", "Enter Fade-in time (seconds):",
                                            initialvalue=0.5, minvalue=0.0, parent=root)
        if fade_in_sec is None: # User cancelled
            print("Export Mix cancelled by user (fade-in prompt).")
            return

        fade_out_sec = simpledialog.askfloat("Export Mix Fades", "Enter Fade-out time (seconds):",
                                             initialvalue=0.5, minvalue=0.0, parent=root)
        if fade_out_sec is None: # User cancelled
            print("Export Mix cancelled by user (fade-out prompt).")
            return
    except Exception as e:
        messagebox.showerror("Input Error", f"Invalid fade time input: {e}")
        return
    # --- End Get Fade Times ---

    # 1. Identify tracks, pan, and EQ settings
    tracks_to_process = []
    valid_track_found = False
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        if player_state["filepath"] and os.path.exists(player_state["filepath"]):
            pan_val = 0; eq_low = 0.0; eq_mid = 0.0; eq_high = 0.0 # Defaults
            if gui := player_state.get("gui"):
                 if pan_slider := gui.get("pan_slider"):
                     try: pan_val = pan_slider.get()
                     except tk.TclError: print(f"Warning: Could not get pan value for Player {i}")
                
            tracks_to_process.append({
                "index": i, "path": player_state["filepath"], "pan": pan_val,
                
            })
            valid_track_found = True
        else:
            tracks_to_process.append(None)

    if not valid_track_found: messagebox.showwarning("Export Mix", "No valid audio files loaded."); return


    # 2. Prompt for output file
    output_filepath = filedialog.asksaveasfilename(
        title="Export Mix As...",
        defaultextension=".wav",
        filetypes=[("WAV files", "*.wav"), ("FLAC files", "*.flac"), ("All Files", "*.*")]
    )
    if not output_filepath:
        print("Export Mix cancelled by user (file save prompt).")
        return

    # 3. Process and load audio data
    loaded_data = []
    max_length = 0
    target_sr = EXPORT_SAMPLE_RATE
    target_ch = EXPORT_CHANNELS

    print(f"Target export format: {target_sr} Hz, {target_ch} channels")

    root.config(cursor="watch") # Indicate processing
    root.update_idletasks()

    try:
        # --- Loop through tracks (loading, resampling, panning) ---
        # ... (This part remains the same as before) ...
        for track_info in tracks_to_process:
            if track_info is None:
                loaded_data.append(None)
                continue
            path = track_info["path"]; pan_val = track_info["pan"]; player_index = track_info["index"]
            print(f"  Processing Player {player_index}: {os.path.basename(path)}")
            try:
                data, sr = sf.read(path, dtype='float32', always_2d=True)
                # --- Resample ---
                if sr != target_sr:
                    print(f"    Resampling from {sr} Hz to {target_sr} Hz..."); data = librosa.resample(data.T, orig_sr=sr, target_sr=target_sr).T; print("    Resampling done.")
                # --- Adjust Channels ---
                current_ch = data.shape[1]
                if current_ch == 1 and target_ch == 2: print("    Converting mono to stereo..."); data = np.tile(data, (1, 2))
                elif current_ch != target_ch and not (current_ch == 2 and target_ch == 2): raise ValueError(f"Unsupported channel config: Source {current_ch}ch, Target {target_ch}ch")

                # --- Apply Panning ---
                if target_ch == 2:
                    print(f"    Applying Pan: {pan_val}")
                    pan_normalized = (float(pan_val) + 100.0) / 200.0; left_multiplier = math.sqrt(1.0 - pan_normalized); right_multiplier = math.sqrt(pan_normalized)
                    data[:, 0] *= left_multiplier; data[:, 1] *= right_multiplier

                loaded_data.append(data)
                max_length = max(max_length, data.shape[0])

            except Exception as e:
                print(f"    Error processing track {os.path.basename(path)}: {e}"); messagebox.showwarning("Track Error", f"Skipping track due to error:\n{os.path.basename(path)}\n{e}"); loaded_data.append(None)
        # --- End Loop ---
        # --- End Loop ---

        # 4. Pad and Mix
        if max_length == 0: raise ValueError("No valid audio data could be processed.")
        print(f"Mixing tracks (max length: {max_length} samples)...")
        mixed_data = np.zeros((max_length, target_ch), dtype='float32')
        for data in loaded_data:
            if data is not None:
                pad_width = max_length - data.shape[0]
                if pad_width > 0: data = np.pad(data, ((0, pad_width), (0, 0)), 'constant')
                mixed_data += data

        # 5. Normalize
        print("Normalizing mix...")
        max_abs_val = np.max(np.abs(mixed_data))
        if max_abs_val > 0:
            normalization_factor = (10**(-0.1/20)) / max_abs_val
            mixed_data *= normalization_factor
        else: print("Warning: Mix resulted in silence.")

        # --- 6. Apply Fades (Using User Input) ---
        # Calculate fade lengths in samples
        fade_in_samples = int(fade_in_sec * target_sr)
        fade_out_samples = int(fade_out_sec * target_sr)

        # Ensure fades aren't too long
        fade_in_samples = max(0, min(fade_in_samples, max_length // 2))
        fade_out_samples = max(0, min(fade_out_samples, max_length // 2))

        if fade_in_samples > 0:
            print(f"Applying {fade_in_sec:.2f}s fade in...")
            fade_in_curve = np.linspace(0.0, 1.0, fade_in_samples)**2
            for ch in range(target_ch):
                mixed_data[:fade_in_samples, ch] *= fade_in_curve

        if fade_out_samples > 0:
            print(f"Applying {fade_out_sec:.2f}s fade out...")
            fade_out_curve = np.linspace(1.0, 0.0, fade_out_samples)**2
            for ch in range(target_ch):
                mixed_data[-fade_out_samples:, ch] *= fade_out_curve
        # --- End Apply Fades ---

        # 7. Save
        print(f"Saving mixed file to: {output_filepath}")
        sf.write(output_filepath, mixed_data, target_sr, subtype='PCM_16')

        print("Export Mix completed successfully.")
        messagebox.showinfo("Export Mix", f"Mix saved successfully to:\n{output_filepath}")

    except Exception as e:
        print(f"Error during Export Mix process: {e}")
        messagebox.showerror("Export Mix Error", f"An error occurred during export:\n{e}")
    finally:
        root.config(cursor="") # Reset cursor
# --- End Export Mix Function ---

# --- NEW: Export Stems Function ---
def export_stems():
    """Copies the original files currently loaded in players to a NEW subfolder
       within a selected destination.""" # <<< Updated docstring
    print("Starting Export Stems process...")

    # 1. Identify currently loaded valid tracks
    tracks_to_copy = []
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        if player_state["filepath"] and os.path.exists(player_state["filepath"]):
            tracks_to_copy.append(player_state["filepath"])

    if not tracks_to_copy:
        messagebox.showwarning("Export Stems", "No valid audio files currently loaded in any player.")
        print("Export Stems cancelled: No tracks loaded.")
        return

    # 2. Prompt user for PARENT destination folder
    parent_destination_folder = filedialog.askdirectory(
        title="Select Parent Folder to Create Stems Folder In" # <<< Clarified title
    )
    if not parent_destination_folder:
        print("Export Stems cancelled by user (parent folder selection).")
        return

    # --- NEW: Prompt for Subfolder Name ---
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    default_subfolder_name = f"Stems_{timestamp}"
    subfolder_name = simpledialog.askstring(
        "Subfolder Name",
        "Enter a name for the new folder to contain the stems:",
        initialvalue=default_subfolder_name,
        parent=root
    )
    if not subfolder_name:
        print("Export Stems cancelled by user (subfolder name prompt).")
        return
    # --- End NEW ---

    # --- NEW: Create the Full Destination Path and Folder ---
    final_destination_folder = os.path.join(parent_destination_folder, subfolder_name)
    try:
        os.makedirs(final_destination_folder, exist_ok=True) # exist_ok=True prevents error if it already exists
        print(f"Ensured destination folder exists: {final_destination_folder}")
    except OSError as e:
        messagebox.showerror("Folder Creation Error", f"Could not create destination folder:\n{final_destination_folder}\nError: {e}")
        print(f"Error creating destination folder: {e}")
        return
    # --- End NEW ---

    print(f"Exporting {len(tracks_to_copy)} stems to: {final_destination_folder}") # <<< Updated path
    root.config(cursor="watch")
    root.update_idletasks()

    # 3. Copy files into the NEW subfolder
    errors_occurred = []
    success_count = 0
    try:
        for source_path in tracks_to_copy:
            try:
                print(f"  Copying: {os.path.basename(source_path)}")
                # <<< Use final_destination_folder as the target >>>
                shutil.copy2(source_path, final_destination_folder)
                success_count += 1
            except (IOError, OSError, shutil.Error) as e:
                error_msg = f"Could not copy file:\n{os.path.basename(source_path)}\nError: {e}"
                print(f"    Error: {error_msg}")
                errors_occurred.append(error_msg)
            except Exception as e:
                 error_msg = f"Unexpected error copying file:\n{os.path.basename(source_path)}\nError: {e}"
                 print(f"    Error: {error_msg}")
                 errors_occurred.append(error_msg)

        # 4. Report results
        if not errors_occurred:
             # <<< Updated path in message >>>
            messagebox.showinfo("Export Stems", f"Successfully exported {success_count} stem(s) to folder:\n{final_destination_folder}")
            print("Export Stems completed successfully.")
        else:
            first_error = errors_occurred[0]
            summary_msg = f"Export completed with {len(errors_occurred)} error(s).\n\nFirst error:\n{first_error}"
            if len(errors_occurred) > 1: summary_msg += f"\n\n(See console output for details on all errors)"
            messagebox.showerror("Export Stems Error", summary_msg)
            print(f"Export Stems completed with {len(errors_occurred)} errors.")

    except Exception as e:
        messagebox.showerror("Export Stems Error", f"An unexpected error occurred during the export process:\n{e}")
        print(f"Unexpected error during export_stems: {e}")
    finally:
        root.config(cursor="") # Reset cursor

# --- End Export Stems Function ---
# multi_player.py

# --- Add this function definition ---
# multi_player.py

# --- Add this function definition ---
def update_global_loop_button_state():
    """Checks all active players and updates the global loop button color."""
    global global_loop_button # Access the global button variable

    # <<< DEBUG PRINT >>>
    # print("--- update_global_loop_button_state CALLED ---")

    if not global_loop_button: # Button might not exist yet during setup
        # <<< DEBUG PRINT >>>
        # print("  DEBUG: global_loop_button is None, returning.")
        return
    else:
        # <<< DEBUG PRINT >>>
        print(f"  DEBUG: global_loop_button widget: {global_loop_button}")

    any_active_looping = False
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        # Check if playing, not paused, AND looping
        if player_state["is_playing"] and not player_state["is_paused"] and player_state["is_looping"]:
            any_active_looping = True
            # <<< DEBUG PRINT >>>
            # print(f"  DEBUG: Found active looping player: {i+1}")
            break # Found one, no need to check further

    # Define colors (consistent with individual buttons)
    loop_on_fg = "red"
    default_fg = "black"

    # <<< DEBUG PRINT >>>
    # print(f"  DEBUG: any_active_looping = {any_active_looping}")

    # Update the button's foreground color
    if any_active_looping:
        # <<< DEBUG PRINT >>>
        # print(f"  DEBUG: Setting foreground to: {loop_on_fg}")
        global_loop_button.config(foreground=loop_on_fg)
    else:
        # <<< DEBUG PRINT >>>
        # print(f"  DEBUG: Setting foreground to: {default_fg}")
        global_loop_button.config(foreground=default_fg)

    # Optional: Force Tkinter update (usually not needed, but can help diagnose)
    # root.update_idletasks()

# --- End function definition ---


# --- UI State Update Functions ---
# multi_player.py

# --- UI State Update Functions ---
def update_button_states(player_index):
    """Updates the GUI state for a single player."""
    player_state = players[player_index]
    gui = player_state["gui"]
    has_files = bool(player_state["audio_files"])
    can_play = has_files and mixer_initialized # Can only play if mixer ok AND files loaded
    track_loaded = player_state["filepath"] is not None
    is_looping = player_state["is_looping"]

    # --- Define Colors ---
    loop_on_fg = "red"
    default_fg = "black"
    # --- End Define Colors ---

    # --- Determine Widget States ---

    # Sliders (Vol, Pan, Fade) depend only on mixer initialization
    slider_state = tk.NORMAL if mixer_initialized else tk.DISABLED

    # Interval Entry: Enabled only if mixer ok, files loaded, AND stopped
    interval_state = tk.DISABLED
    if mixer_initialized and has_files and not player_state["is_playing"]:
        interval_state = tk.NORMAL

    # Select Folder Button: Enabled only if stopped
    select_folder_state = tk.DISABLED if player_state["is_playing"] else tk.NORMAL

    # Play/Pause/Stop/Next/Prev/Loop/Reveal states depend on playback status
    play_pause_text = "Play"
    play_pause_state = tk.DISABLED
    stop_state = tk.DISABLED
    prev_state = tk.DISABLED
    next_state = tk.DISABLED
    loop_button_state = tk.DISABLED # Tracks if the button itself should be enabled/disabled
    reveal_state = tk.DISABLED

    if player_state["is_playing"] and not player_state["is_paused"]: # Playing
        play_pause_text = "Pause"
        play_pause_state = tk.NORMAL
        stop_state = tk.NORMAL
        prev_state = tk.NORMAL if len(player_state["play_history"]) > 0 else tk.DISABLED
        next_state = tk.NORMAL
        loop_button_state = tk.NORMAL
        reveal_state = tk.NORMAL if track_loaded else tk.DISABLED
        if gui.get("drop_target_label"): gui["drop_target_label"].config(fg="grey")

    elif player_state["is_playing"] and player_state["is_paused"]: # Paused
        play_pause_text = "Resume"
        play_pause_state = tk.NORMAL
        stop_state = tk.NORMAL
        # Prev/Next disabled when paused
        reveal_state = tk.NORMAL if track_loaded else tk.DISABLED
        # Loop button disabled when paused
        if gui.get("drop_target_label"): gui["drop_target_label"].config(fg="grey")

    else: # Stopped
        play_pause_text = "Play"
        play_pause_state = tk.NORMAL if can_play else tk.DISABLED
        # Stop/Prev/Next/Loop disabled when stopped
        reveal_state = tk.NORMAL if track_loaded else tk.DISABLED # Reveal enabled if track loaded
        if gui.get("drop_target_label"): gui["drop_target_label"].config(fg="grey") # Default appearance

    # --- Apply States to Widgets ---

    # Sliders
    if gui.get("volume_slider"): gui["volume_slider"].config(state=slider_state)
    if gui.get("pan_slider"): gui["pan_slider"].config(state=slider_state)
    if gui.get("fade_slider"): gui["fade_slider"].config(state=slider_state) # Apply correct state

    # Entry / Folder Button
    if gui.get("interval_entry"): gui["interval_entry"].config(state=interval_state)
    if gui.get("select_folder_button"): gui["select_folder_button"].config(state=select_folder_state)

    # Playback Control Buttons
    if gui.get("play_pause_button"): gui["play_pause_button"].config(text=play_pause_text, state=play_pause_state)
    if gui.get("stop_button"): gui["stop_button"].config(state=stop_state)
    if gui.get("previous_button"): gui["previous_button"].config(state=prev_state)
    if gui.get("next_button"): gui["next_button"].config(state=next_state)
    if gui.get("reveal_button"): gui["reveal_button"].config(state=reveal_state)

    # Loop Button (Text, State, and Color)
    loop_button = gui.get("loop_button")
    if loop_button:
        loop_text = f"Loop [{'ON' if is_looping else 'OFF'}]"
        loop_fg = default_fg # Default text color

        if loop_button_state == tk.NORMAL:
            if is_looping:
                loop_fg = loop_on_fg # Red text if looping and button enabled
            loop_button.config(text=loop_text, state=tk.NORMAL, foreground=loop_fg)
        else: # Button is disabled
            loop_button.config(text=loop_text, state=tk.DISABLED, foreground=default_fg) # Reset color when disabled

# --- End update_button_states ---


def update_all_button_states():
    """Updates GUI state for all players."""
    for i in range(MAX_PLAYERS): update_button_states(i)
    update_global_loop_button_state()
# --- GUI Setup (Multiple Players) ---

# --- NEW: Main Area Frame for Player Grid ---
players_area_frame = tk.Frame(root)
# Pack this frame first, allowing it to expand, pushing controls down
players_area_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)


# <<< CHANGED Grid Configuration for 3 rows, 2 columns >>>
players_area_frame.grid_columnconfigure(0, weight=1) # Column 0
players_area_frame.grid_columnconfigure(1, weight=1) # Column 1
# players_area_frame.grid_columnconfigure(2, weight=1) # REMOVED Column 2
players_area_frame.grid_rowconfigure(0, weight=1)    # Row 0
players_area_frame.grid_rowconfigure(1, weight=1)    # Row 1
players_area_frame.grid_rowconfigure(2, weight=1)    # Row 2 (ADDED)
# --- End Grid Configuration Change ---
# # --- End Main Area Frame ---

for i in range(MAX_PLAYERS):
    player_state = players[i]
    player_frame = tk.Frame(players_area_frame, relief=tk.GROOVE, borderwidth=2)
    
    # --- Calculate Grid Position ---
    row = i // 2    # Rows 0, 1, 2
    column = i % 2  # Columns 0, 1
    # --- Place using grid ---
    # Use sticky="nsew" to make the frame fill the grid cell
    player_frame.grid(row=row, column=column, padx=5, pady=5, sticky="nsew")

    top_frame = tk.Frame(player_frame); top_frame.pack(fill=tk.X)
    tk.Label(top_frame, text=f"Player {i+1}", font=('Helvetica', 12, 'bold')).pack(side=tk.LEFT, padx=5)
    folder_label = tk.Label(top_frame, text="Folder: Not Selected", anchor='w')
    folder_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    player_state["gui"]["folder_label"] = folder_label

    # --- Folder Selection Row (Button + Drop Target + Preset Dropdown) --- # MODIFIED
    folder_select_frame = tk.Frame(player_frame)
    folder_select_frame.pack(fill=tk.X, pady=2)

    select_button = tk.Button(folder_select_frame, text="Select Folder", command=lambda idx=i: select_folder(idx))
    select_button.pack(side=tk.LEFT, padx=(5, 5)) # Adjusted padding
    player_state["gui"]["select_folder_button"] = select_button
    # --- Preset Dropdown ---    
    preset_label = tk.Label(folder_select_frame, text="Preset:")
    preset_label.pack(side=tk.LEFT, padx=(10, 2))
    preset_dropdown = ttk.Combobox(folder_select_frame, width=15, state="readonly") # Readonly prevents typing
    preset_dropdown.pack(side=tk.LEFT, padx=(0, 10))
    # Bind selection event
    preset_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: on_preset_selected(event, idx))
    player_state["gui"]["preset_dropdown"] = preset_dropdown # Store reference
    # --- End Preset Dropdown ---

    # --- Drop Target Widget ---
    drop_target = tk.Label(folder_select_frame, text="Drop Folder", relief="sunken", borderwidth=1, fg="grey", padx=5, width=10)
    drop_target.pack(side=tk.LEFT, ipady=10, padx=(0,5)) # Fill remaining space
    drop_target.drop_target_register(DND_FILES)
    # Bind with lambda to pass player_index
    drop_target.dnd_bind('<<Drop>>', lambda event, idx=i: handle_folder_drop(idx, event))
    player_state["gui"]["drop_target_label"] = drop_target # Store reference
    # --- End Drop Target ---
    
    # --- Waveform Canvas ---
    waveform_canvas = tk.Canvas(player_frame, width=WAVEFORM_WIDTH, height=WAVEFORM_HEIGHT, bg="black", highlightthickness=0)
    waveform_canvas.pack(pady=5, fill=tk.X, padx=5)
    player_state["gui"]["waveform_canvas"] = waveform_canvas # Store reference
    # --- End Waveform Canvas ---

    # --- Inside the player GUI loop ---
    controls_frame = tk.Frame(player_frame); controls_frame.pack(fill=tk.X, pady=3)

    # --- Add Prev/Next/Play/Stop/Loop ---
    # <<< ADD internal padx/pady during button creation >>>
    previous_button = tk.Button(controls_frame, text="Prev", width=2, command=lambda idx=i: play_previous_track(idx), state=tk.DISABLED, padx=0, pady=0)
    previous_button.pack(side=tk.LEFT, padx=0) # Keep external padx=0
    player_state["gui"]["previous_button"] = previous_button

    play_pause_button = tk.Button(controls_frame, text="Play", width=3, command=lambda idx=i: handle_play_pause(idx), state=tk.DISABLED, padx=0, pady=1)
    play_pause_button.pack(side=tk.LEFT, padx=0) # Keep external padx=0
    player_state["gui"]["play_pause_button"] = play_pause_button

    stop_button = tk.Button(controls_frame, text="Stop", width=3, command=lambda idx=i: stop_playback(idx), state=tk.DISABLED, padx=0, pady=1)
    stop_button.pack(side=tk.LEFT, padx=0) # Keep external padx=0
    player_state["gui"]["stop_button"] = stop_button

    next_button = tk.Button(controls_frame, text="Next", width=3, command=lambda idx=i: play_next_manual(idx), state=tk.DISABLED, padx=0, pady=1)
    next_button.pack(side=tk.LEFT, padx=0) # Keep external padx=0
    player_state["gui"]["next_button"] = next_button

    loop_button = tk.Button(controls_frame, text="Loop [OFF]", width=6, command=lambda idx=i: toggle_loop(idx), state=tk.DISABLED, padx=0, pady=0)
    loop_button.pack(side=tk.LEFT, padx=0) # Keep external padx=0
    player_state["gui"]["loop_button"] = loop_button
    # --- End Prev/Next/Play/Stop/Loop ---

    # --- Add Reveal Button ---
    reveal_button = tk.Button(controls_frame, text="Reveal", width=3, command=lambda idx=i: reveal_current_track(idx), state=tk.DISABLED, padx=0, pady=1)
    reveal_button.pack(side=tk.LEFT, padx=0) # Keep external padx=0
    player_state["gui"]["reveal_button"] = reveal_button # Store reference
    # --- End Reveal Button ---

    # --- Interval Entry (Keep as is or adjust its external padding if needed) ---
    interval_label = tk.Label(controls_frame, text="Int(s):")
    interval_label.pack(side=tk.LEFT, padx=(5, 2)) # External padding for label
    interval_entry = tk.Entry(controls_frame, width=4, state=tk.DISABLED)
    interval_entry.pack(side=tk.LEFT, padx=(0, 1)) # External padding for entry
    player_state["gui"]["interval_entry"] = interval_entry

 # --- Bottom Row: Status, Volume, and Pan --- # MODIFIED
    bottom_frame = tk.Frame(player_frame)
    bottom_frame.pack(fill=tk.X, pady=3)
    # --- EQ and Audio Settings Frame ---
    audio_settings_frame = tk.Frame(player_frame)
    audio_settings_frame.pack(fill=tk.X, pady=3)

    # Status Label (Moved here for better grouping)
    status_label = tk.Label(audio_settings_frame, text="No files loaded.", width=25, anchor='w')
    status_label.pack(side=tk.LEFT, padx=5)
    player_state["gui"]["status_label"] = status_label

    # Volume Slider
    volume_slider = tk.Scale(audio_settings_frame, from_=0, to=100, orient=tk.HORIZONTAL, label="Vol:", length=80, command=lambda value, idx=i: update_channel_audio_settings(idx))
    if mixer_initialized: volume_slider.set(int(INITIAL_VOLUME * 100))
    else: volume_slider.config(state=tk.DISABLED)
    volume_slider.pack(side=tk.LEFT, padx=(5, 2))
    player_state["gui"]["volume_slider"] = volume_slider

    # Pan Slider
    pan_slider = tk.Scale(audio_settings_frame, from_=-100, to=100, orient=tk.HORIZONTAL, label="Pan:", length=80, command=lambda value, idx=i: update_channel_audio_settings(idx))
    pan_slider.set(INITIAL_PAN)
    if not mixer_initialized: pan_slider.config(state=tk.DISABLED)
    pan_slider.pack(side=tk.LEFT, padx=(2, 5))
    player_state["gui"]["pan_slider"] = pan_slider

    # --- Fade Slider (Seconds) --- <<< ADDED BLOCK
    fade_slider = tk.Scale(audio_settings_frame, from_=0.0, to=10.0, resolution=0.5, # 0 to 10 seconds, step 0.5s
                           orient=tk.HORIZONTAL, label="Fade(s):", length=80,
                           command=lambda value, idx=i: update_fade_duration(idx, value))
    fade_slider.set(DEFAULT_FADE_MS / 1000.0) # Set initial value (converted to seconds)
    if not mixer_initialized: fade_slider.config(state=tk.DISABLED)
    fade_slider.pack(side=tk.LEFT, padx=(2, 5))
    player_state["gui"]["fade_slider"] = fade_slider # Store reference
    # --- End Fade Slider ---


# --- Phase 4.5: Global Controls ---
# --- Helper: Stop and Clear Single Player --- <<< NEW FUNCTION
def stop_and_clear_player(player_index):
    """Stops playback and clears all data for a single player."""
    print(f"  Clearing Player {player_index+1}...")
    player_state = players[player_index]

    # 1. Stop playback (handles audio, timers, state flags like is_playing, calls clear_waveform)
    stop_playback(player_index)

    # 2. Clear core state variables not handled by stop_playback
    player_state["selected_folder"] = None
    player_state["audio_files"] = []
    player_state["filepath"] = None
    player_state["sound"] = None
    player_state["play_history"].clear()
    # waveform_data and current_track_duration_s are cleared by clear_waveform

    # 3. Reset GUI elements not fully handled by update_button_states/clear_waveform
    gui = player_state.get("gui", {}) # Use .get for safety
    if folder_label := gui.get("folder_label"):
        folder_label.config(text="Folder: Not Selected")
    if status_label := gui.get("status_label"):
        # Set status label *after* stop_playback might have set it to "Stopped: ..."
        status_label.config(text="No files loaded.")
    if preset_dropdown := gui.get("preset_dropdown"):
        preset_dropdown.set('') # Clear selection
    if interval_entry := gui.get("interval_entry"):
        # Clear interval entry and disable it
        interval_entry.delete(0, tk.END)
        interval_entry.config(state=tk.DISABLED) # Ensure disabled
    if fade_slider := gui.get("fade_slider"):
        # Reset fade slider to default and disable it
        fade_slider.set(DEFAULT_FADE_MS / 1000.0)
        fade_slider.config(state=tk.DISABLED) # Ensure disabled

    # 4. Ensure button states are fully updated after clearing everything
    update_button_states(player_index)
# --- End Helper Function ---

# --- Add this function definition ---
def stop_and_clear_all():
    """Stops playback and clears all data for all players by calling helper."""
    print("Global Control: Stopping and clearing all players...")
    for i in range(MAX_PLAYERS):
        print(f"  Clearing Player {i+1}...")
        player_state = players[i]

        # 1. Stop playback (handles audio, timers, state flags like is_playing, calls clear_waveform)
        stop_playback(i)

        # 2. Clear core state variables not handled by stop_playback
        player_state["selected_folder"] = None
        player_state["audio_files"] = []
        player_state["filepath"] = None
        player_state["sound"] = None
        player_state["play_history"].clear()
        # waveform_data and current_track_duration_s are cleared by clear_waveform called within stop_playback

        # 3. Reset GUI elements not fully handled by update_button_states/clear_waveform
        gui = player_state.get("gui", {}) # Use .get for safety
        if folder_label := gui.get("folder_label"):
            folder_label.config(text="Folder: Not Selected")
        if status_label := gui.get("status_label"):
            # Set status label *after* stop_playback might have set it to "Stopped: ..."
            status_label.config(text="No files loaded.")
        if preset_dropdown := gui.get("preset_dropdown"):
            preset_dropdown.set('') # Clear selection
        # Interval entry state is handled by update_button_states, but clear value? Optional.
        # if interval_entry := gui.get("interval_entry"):
        #     interval_entry.delete(0, tk.END)
        #     # interval_entry.insert(0, str(DEFAULT_SWITCH_INTERVAL_S)) # Or leave blank

        # 4. Ensure button states are fully updated after clearing everything
        # (stop_playback already called it, but call again for safety after clearing folder/files)
        update_button_states(i)

    print("All players stopped and cleared.")
# --- End function definition ---

# ... (Rest of the code, including other global functions) ...


def toggle_pause_all():
    """Pauses all currently playing players, or resumes all currently paused players."""
    print("--- toggle_pause_all ENTERED ---") # <<< ADDED
    action_taken = False
    should_pause = False
    should_resume = False

    for i in range(MAX_PLAYERS):
        if players[i]["is_playing"] and not players[i]["is_paused"]:
            should_pause = True
            break

    if not should_pause:
        for i in range(MAX_PLAYERS):
             if players[i]["is_playing"] and players[i]["is_paused"]:
                  should_resume = True
                  break

    # Now perform the determined action
    if should_pause:
        print("Global Control: Determined action = PAUSE.") # <<< ADDED
        for i in range(MAX_PLAYERS):
            # <<< ADDED print inside loop >>>
            print(f"  Checking Player {i} for PAUSE: is_playing={players[i]['is_playing']}, is_paused={players[i]['is_paused']}")
            if players[i]["is_playing"] and not players[i]["is_paused"]:
                print(f"    >>> Calling handle_play_pause({i}) to PAUSE") # <<< ADDED
                handle_play_pause(i) # Call individual handler to pause
                action_taken = True
    elif should_resume:
        print("Global Control: Determined action = RESUME.") # <<< ADDED
        for i in range(MAX_PLAYERS):
             # <<< ADDED print inside loop >>>
            print(f"  Checking Player {i} for RESUME: is_playing={players[i]['is_playing']}, is_paused={players[i]['is_paused']}")
            if players[i]["is_playing"] and players[i]["is_paused"]:
                print(f"    >>> Calling handle_play_pause({i}) to RESUME") # <<< ADDED
                handle_play_pause(i) # Call individual handler to resume
                action_taken = True

    if not action_taken:
        print("Global Control: No players met criteria for pause/resume.") # <<< MODIFIED


# --- Modify toggle_loop ---

def toggle_loop(player_index):
    """Toggles looping for the specified player by restarting the track."""
    player_state = players[player_index]
    channel = player_state["channel"]

    if not player_state["sound"] or not channel:
         print(f"Player {player_index}: Cannot toggle loop (no sound loaded or channel missing).")
         return

    # --- Cancel any scheduled automatic transition --- <<< ADDED
    if player_state["playback_timer_id"]:
        try: root.after_cancel(player_state["playback_timer_id"])
        except tk.TclError: pass
        player_state["playback_timer_id"] = None
        print(f"  Cancelled scheduled transition timer before toggling loop.")

    # Toggle the state
    player_state["is_looping"] = not player_state["is_looping"]
    print(f"Player {player_index}: Looping toggled {'ON' if player_state['is_looping'] else 'OFF'}")
    update_button_states(player_index) # Update button text

    # Restart Logic
    if player_state["is_playing"]:
        current_filepath = player_state["filepath"]
        if current_filepath:
            print(f"Player {player_index}: Restarting track to apply loop setting.")
            # Call _play_track which uses the updated is_looping flag and handles scheduling
            _play_track(player_index, current_filepath)
        else:
            print(f"Player {player_index}: Error - Cannot apply loop, current filepath unknown.")
            stop_playback(player_index)
    else:
         print(f"Player {player_index}: Loop setting changed while stopped. Will apply on next play.")
    update_global_loop_button_state()     

def play_previous_group():
    """Triggers 'Previous' for all playing players."""
    print("Global Control: Playing previous track for all active players.")
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        # Only trigger if playing and not paused
        if player_state["is_playing"] and not player_state["is_paused"]:
            play_previous_track(i)
        elif player_state["is_playing"] and player_state["is_paused"]:
             print(f"  Player {i}: Skipping previous track (paused).")

def play_next_group():
    """Triggers 'Next' for all playing players."""
    print("--- play_next_group ENTERED ---")
    print("Global Control: Playing next track for all active players.")
    action_taken = False # Track if action attempted
    for i in range(MAX_PLAYERS):
        player_state = players[i]
        print(f"  Checking Player {i} for NEXT: is_playing={player_state['is_playing']}, is_paused={player_state['is_paused']}")
        # Only trigger if playing and not paused
        if player_state["is_playing"] and not player_state["is_paused"]:
            print(f"    >>> Calling play_next_manual({i})")
            play_next_manual(i)
            action_taken = True
        # Optional: Add back the print for skipped paused players if desired
        # elif player_state["is_playing"] and player_state["is_paused"]:
        #      print(f"  Player {i}: Skipping next track (paused).")

    if not action_taken: # Check if any action was taken
         print("  Global Control: No active (playing and not paused) players found for next group.")

    # <<< THE ENTIRE BLOCK BELOW THIS COMMENT WAS INCORRECTLY PLACED HERE AND HAS BEEN REMOVED >>>
    # global folder_presets # Need access to the loaded presets
    # if not folder_presets: ...
    # ... (all the code related to choosing random presets, calling process_folder, etc.) ...
    # print("Finished loading random presets.")
    # <<< END OF REMOVED BLOCK >>>

# --- End replacement for play_next_group ---

# --- End Global Random Preset Loader ---

# --- NEW: Global Random Preset Loader ---
# --- Modify load_random_presets_all ---
# multi_player.py

# --- Modify load_random_presets_all ---
# multi_player.py

# --- Modify load_random_presets_all ---
def load_random_presets_all():
    """Loads a randomly selected preset folder into the specified number of players (1-6), defaulting to all if input is invalid/empty.""" # <<< Updated docstring
    global folder_presets, shuffle_count_entry # Need access to the entry widget

    print("--- load_random_presets_all ENTERED ---")

    if not folder_presets:
        messagebox.showwarning("Random Presets", "No presets have been saved yet.") # Keep this warning
        print("Cannot load random presets: No presets available.")
        return

    # --- Get and Validate Shuffle Count --- <<< MODIFIED BLOCK
    num_players_to_shuffle = MAX_PLAYERS # Default to all
    if shuffle_count_entry:
        count_str = shuffle_count_entry.get().strip()
        # print(f"DEBUG: Read count_str from entry: '{count_str}'")
        if count_str: # Only try to parse if the string is not empty
            try:
                requested_count = int(count_str)
                # print(f"DEBUG: Parsed requested_count: {requested_count}")
                if 1 <= requested_count <= MAX_PLAYERS:
                    # Only update if the count is valid and within range
                    num_players_to_shuffle = requested_count
                    print(f"Shuffle Count: User requested {num_players_to_shuffle} players.")
                else:
                    # Input is numeric but out of range - Log and default
                    # --- REMOVED messagebox.showwarning(...) ---
                    print(f"Invalid shuffle count '{count_str}' (out of range 1-{MAX_PLAYERS}). Defaulting to {MAX_PLAYERS}.")
                    # num_players_to_shuffle remains MAX_PLAYERS (default)
            except ValueError:
                # Input is non-numeric - Log and default
                # --- REMOVED messagebox.showwarning(...) ---
                print(f"Invalid shuffle count input '{count_str}' (not a number). Defaulting to {MAX_PLAYERS}.")
                # num_players_to_shuffle remains MAX_PLAYERS (default)
        else:
            # Input string was empty - Log and default
            print(f"Shuffle count entry is empty. Defaulting to {MAX_PLAYERS}.")
            # num_players_to_shuffle remains MAX_PLAYERS (default)
    else:
        # Fallback if the GUI widget wasn't found for some reason
        print("Warning: Shuffle count entry widget not found. Defaulting to all players.")
        # num_players_to_shuffle remains MAX_PLAYERS (default)
    # --- End Get and Validate ---

    # print(f"DEBUG: Final num_players_to_shuffle = {num_players_to_shuffle}") # Log the final count being used

    print(f"Global Control: Loading random presets for {num_players_to_shuffle} player(s)...")
    preset_names = list(folder_presets.keys())

    if not preset_names:
        messagebox.showwarning("Random Presets", "Preset list is empty.") # Keep this warning
        print("Error: Preset names list is empty.")
        return

    # --- Loop 1: Load presets for the specified number of players ---
    loaded_count = 0
    # print(f"DEBUG: Starting Loop 1: range({num_players_to_shuffle})")
    for i in range(num_players_to_shuffle): # Use validated/defaulted count
        try:
            # ... (rest of the preset loading logic for player i remains the same) ...
             if not preset_names: break
             chosen_preset_name = random.choice(preset_names)
             preset_data = folder_presets.get(chosen_preset_name)
             if not preset_data or not isinstance(preset_data, dict):
                 print(f"  Error: Invalid data for preset '{chosen_preset_name}'. Skipping Player {i+1}.")
                 continue
             actual_folder_path = preset_data.get("path")
             if not actual_folder_path or not isinstance(actual_folder_path, str):
                 print(f"  Error: Missing path in preset '{chosen_preset_name}'. Skipping Player {i+1}.")
                 continue
             print(f"  Player {i+1}: Loading preset '{chosen_preset_name}' -> Path: '{actual_folder_path}'")
             process_folder(i, actual_folder_path)
             if dropdown := players[i].get("gui", {}).get("preset_dropdown"):
                 if chosen_preset_name in dropdown['values']: dropdown.set(chosen_preset_name)
                 else: dropdown.set("")
             loaded_count += 1
        except Exception as e:
            print(f"Error loading random preset for Player {i+1}: {e}")
            messagebox.showerror("Error", f"Could not load random preset for Player {i+1}.\nPreset: {chosen_preset_name}\nError: {e}") # Keep error popups for actual loading failures
            stop_and_clear_player(i)
            continue
    # --- End Loop 1 ---

    # --- Loop 2: Clear remaining players ---
    # print(f"DEBUG: Starting Loop 2: range({num_players_to_shuffle}, {MAX_PLAYERS})")
    print(f"Clearing players from {num_players_to_shuffle + 1} to {MAX_PLAYERS}...")
    for i in range(num_players_to_shuffle, MAX_PLAYERS):
        stop_and_clear_player(i)
    # --- End Loop 2 ---

    print(f"Finished loading random presets for {loaded_count} player(s).")

    # --- Keep the focus fix for the spacebar issue ---
    print("Setting focus back to root window after shuffling.")
    root.focus_set()
    # --- End focus fix ---

# --- End Modification ---

# --- End Modification ---



# --- Global Controls ---

# --- Global Controls GUI Frame ---
global_controls_frame = tk.Frame(root, relief=tk.RAISED, borderwidth=1)
global_controls_frame.pack(pady=(5, 5), padx=10, fill=tk.X, side=tk.BOTTOM)

tk.Label(global_controls_frame, text="Global Controls", font=('Helvetica', 10, 'bold')).pack()

global_button_subframe = tk.Frame(global_controls_frame)
global_button_subframe.pack(pady=5)

# --- NEW: Recording Controls ---
# <<< Pack below the players_area_frame, above global controls using side=tk.BOTTOM >>>
recording_frame = tk.Frame(root, relief=tk.RAISED, borderwidth=1)
recording_frame.pack(pady=(5, 5), padx=10, fill=tk.X, side=tk.BOTTOM)

record_button = tk.Button(recording_frame, text="Record Output", width=15, command=handle_record_button)
record_button.pack(side=tk.LEFT, padx=10, pady=5)

recording_status_label = tk.Label(recording_frame, text="Not Recording", anchor='w')
recording_status_label.pack(side=tk.LEFT, padx=10, pady=5, fill=tk.X, expand=True)
# --- End Recording Controls ---

# TODO: Add logic to update this button's text based on state?
global_pause_button = tk.Button(global_button_subframe, text="Pause/Resume All", command=toggle_pause_all)
global_pause_button.pack(side=tk.LEFT, padx=10)

global_loop_button = tk.Button(global_button_subframe, text="Loop All", command=toggle_loop_all)
global_loop_button.pack(side=tk.LEFT, padx=10)

global_prev_button = tk.Button(global_button_subframe, text="Previous Group", command=play_previous_group)
global_prev_button.pack(side=tk.LEFT, padx=10)

global_next_button = tk.Button(global_button_subframe, text="Next Group", command=play_next_group)
global_next_button.pack(side=tk.LEFT, padx=10)


# --- Add Shuffle Count Entry --- <<< NEW BLOCK
shuffle_count_label = tk.Label(global_button_subframe, text="#")
shuffle_count_label.pack(side=tk.LEFT, padx=(10, 0)) # Add some left padding

shuffle_count_entry = tk.Entry(global_button_subframe, width=3)
shuffle_count_entry.pack(side=tk.LEFT, padx=(0, 0))
shuffle_count_entry.insert(0, str(MAX_PLAYERS)) # Default to max players
# --- End Shuffle Count Entry ---
# <<< ADD THIS BINDING >>>
# Bind the Enter key (<Return>) press event on this specific Entry widget
# to call the load_random_presets_all function.
# The lambda accepts the event object passed by bind, but doesn't need to use it.
shuffle_count_entry.bind('<Return>', lambda event: load_random_presets_all())
# --- END ADDED BINDING ---


global_random_preset_button = tk.Button(global_button_subframe, text="Shuffle Presets", command=load_random_presets_all)
global_random_preset_button.pack(side=tk.LEFT, padx=5)



global_stop_clear_button = tk.Button(global_button_subframe, text="Clear All", command=stop_and_clear_all)
global_stop_clear_button.pack(side=tk.LEFT, padx=10)

# --- Populate Preset Dropdowns ---
update_preset_dropdowns() # <<< Populate dropdowns after GUI is built

# --- Initialize Button States ---
update_all_button_states() # Update all after GUI is built

# --- Center Window on Screen ---
def center_window(win_width=1000, win_height=900): # Pass known dimensions
    """Calculates and sets the window position to center it on the screen."""
    try:
        # No need for update_idletasks if using known dimensions
        # root.update_idletasks()

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # Calculate position
        x_coord = (screen_width // 2) - (win_width // 2)
        y_coord = (screen_height // 2) - (win_height // 2)

        # Set the position using geometry string "+x+y"
        # This only sets the position, preserving the size set earlier
        root.geometry(f"+{x_coord}+{y_coord}")
        print(f"Attempting to center window at +{x_coord}+{y_coord}")

    except tk.TclError as e:
        # Catch potential errors if window info isn't available yet (less likely with after_idle)
        print(f"Warning: Could not center window (TclError): {e}")
    except Exception as e:
        print(f"Warning: Unexpected error centering window: {e}")

# Schedule the centering function to run once Tkinter is idle
root.after_idle(center_window)
# --- End Center Window ---

# --- Start Event Checking ---

# --- Initialize Button States ---
update_all_button_states()

# --- Start Event Checking ---
if mixer_initialized: print("Starting Pygame event checking loop..."); root.after(EVENT_CHECK_MS, check_pygame_events)
else: messagebox.showwarning("Mixer Not Ready", "Audio mixer failed to initialize. Event checking disabled.")

# --- Window Closing Protocol ---
root.protocol("WM_DELETE_WINDOW", on_closing)

# --- Start Tkinter Main Loop ---
print("Starting Tkinter main loop..."); root.mainloop(); print("Application finished.")

