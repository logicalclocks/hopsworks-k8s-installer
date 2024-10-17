import shutil
import subprocess
import time

def print_colored(message, color, **kwargs):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}", **kwargs)


def periodic_status_update(stop_event, namespace):
    while not stop_event.is_set():
        cmd = f"kubectl get pods -n {namespace} --no-headers"
        success, output, _ = run_command(cmd, verbose=False)
        if success:
            pod_count = len(output.strip().split('\n'))
            print_colored(f"\rCurrent status: {pod_count} pods created", "cyan", end='')
        time.sleep(10)  # Update every 10 seconds


def run_command(command, verbose=False):
    if verbose:
        print_colored(f"Running: {command}", "cyan")
    try:
        result = subprocess.run(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if verbose and result.stdout:
            print(result.stdout)
        if result.stderr:
            print_colored(result.stderr, "yellow")
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def get_user_input(prompt, options=None):
    while True:
        response = input(prompt + " ").strip()
        if options is None or response.lower() in [option.lower() for option in options]:
            return response
        print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")


def get_deployment_environment():
    environments = list(ENV_CONFIGS.keys()) + ["On-Premise/VM"]
    print_colored("Select your deployment environment:", "blue")
    for i, env in enumerate(environments, 1):
        print(f"{i}. {env}")
    choice = get_user_input(
        "Enter the number of your environment:",
        [str(i) for i in range(1, len(environments) + 1)]
    )
    return environments[int(choice) - 1]

