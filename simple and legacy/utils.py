# utils.py

import subprocess

HOPSWORKS_LOGO = """
 _   _                                      _        
| | | |                                    | |       
| |_| | ___  _ __  _____      _____  _ __  | | _____ 
|  _  |/ _ \| '_ \/ __\ \ /\ / / _ \| '__| | |/ / __|
| | | | (_) | |_) \__ \\ V  V / (_) | |    |   <\__ \\
\_| |_/\___/| .__/|___/ \_/\_/ \___/|_|    |_|\_\___/
            | |                                      
            |_|                                      
"""

def print_colored(text, color):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[96m',
        'reset': '\033[0m'
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")

def run_command(command, verbose=True):
    if verbose:
        print_colored(f"Running command: {command}", "blue")
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if verbose:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print_colored(f"Error executing command: {e}", "red")
        print_colored(f"Error output: {e.stderr}", "red")
        return False

def get_user_input(prompt, options=None):
    while True:
        user_input = input(prompt).strip()
        if options and user_input.lower() not in [opt.lower() for opt in options]:
            print_colored(f"Invalid input. Please choose from: {', '.join(options)}", "yellow")
        else:
            return user_input