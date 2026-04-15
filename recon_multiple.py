#!/usr/bin/env python3
import os
import subprocess
import argparse
import time
from pathlib import Path

# ── ANSI Colors ───────────────────────────────────────────────────────────────
G, C, Y, R, B, RST = "\033[32m", "\033[36m", "\033[33m", "\033[31m", "\033[34m", "\033[0m"


def print_step(msg):  print(f"\n{C}[*]{RST} {msg}")
def print_ok(msg):    print(f"    {G}[+]{RST} {msg}")
def print_warn(msg):  print(f"    {Y}[!]{RST} {msg}")

def run_command(cmd: str) -> bool:
    result = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def count_lines(filepath: Path) -> int:
    if not filepath.exists():
        return 0
    with open(filepath, 'r', errors='ignore') as f:
        return sum(1 for _ in f)


def send_notification(msg: str):
    subprocess.run(f'echo "{msg}" | notify -silent', shell=True)


def main():
    parser = argparse.ArgumentParser(description="Multi-Target Recon (Wildcard Scope)")
    parser.add_argument("-l", "--list", required=True, help="File containing list of domains")
    parser.add_argument("-n", "--name", required=True, help="Project/Company name for the output folder")
    args = parser.parse_args()

    input_list = Path(args.list).resolve()
    project_name = args.name

    start_time = time.time()

    if not input_list.exists():
        print(f"{R}[-]{RST} Error: Input list file '{input_list}' not found!")
        exit(1)

    with open(input_list, 'r', errors='ignore') as f:
        valid_scopes = tuple(line.strip().lower() for line in f if line.strip())

    base_dir = Path(os.path.expanduser("~/bounty/targets")) / project_name
    base_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{G}[+]{RST} Starting multi-target enumeration for project: {project_name}")
    print(f"{G}[+]{RST} Input list: {input_list} ({len(valid_scopes)} domains)")
    print(f"{G}[+]{RST} Output directory: {base_dir}")

    subfinder_out = base_dir / "temp_subfinder.txt"
    assetfinder_out = base_dir / "temp_assetfinder.txt"
    findomain_out = base_dir / "temp_findomain.txt"
    amass_out = base_dir / "temp_amass.txt"

    final_merged = base_dir / "01_all_subs_merged.txt"
    final_httpx = base_dir / "02_alive_httpx.txt"

    stats = {}

    # Subfinder
    print_step("Running Subfinder...")
    run_command(f"subfinder -dL {input_list} -silent -o {subfinder_out}")
    stats['subfinder'] = count_lines(subfinder_out)
    send_notification(f"🎯 Subfinder finished for {project_name}. Found: {stats['subfinder']} subdomains.")
    print_ok(f"Subfinder: {stats['subfinder']} found.")

    # Assetfinder
    print_step("Running Assetfinder...")
    run_command(f"cat {input_list} | xargs -I % assetfinder -subs-only % > {assetfinder_out}")
    stats['assetfinder'] = count_lines(assetfinder_out)
    send_notification(f"🎯 Assetfinder finished for {project_name}. Found: {stats['assetfinder']} subdomains.")
    print_ok(f"Assetfinder: {stats['assetfinder']} found.")

    # Findomain
    print_step("Running Findomain...")
    run_command(f"findomain -f {input_list} -q -u {findomain_out}")
    stats['findomain'] = count_lines(findomain_out)
    send_notification(f"🎯 Findomain finished for {project_name}. Found: {stats['findomain']} subdomains.")
    print_ok(f"Findomain: {stats['findomain']} found.")

    # Amass
    print_step("Running Amass (Passive)... this may take a while..")
    run_command(f"amass enum -passive -df {input_list} -o {amass_out}")
    stats['amass'] = count_lines(amass_out)
    send_notification(f"🎯 Amass finished for {project_name}. Found: {stats['amass']} subdomains.")
    print_ok(f"Amass: {stats['amass']} found.")

    # Cleaning & Deduplication
    print_step("Merging results and removing duplicates.")
    all_subs = set()
    for temp_file in [subfinder_out, assetfinder_out, findomain_out, amass_out]:
        if temp_file.exists():
            with open(temp_file, 'r', errors='ignore') as f:
                for line in f:
                    sub = line.strip().lower()
                    # Verifica se o subdomínio pertence a algum dos escopos válidos
                    if sub.endswith(valid_scopes):
                        all_subs.add(sub)

    # Saving clean file
    with open(final_merged, 'w') as f:
        for sub in sorted(all_subs):
            f.write(sub + '\n')

    stats['merged'] = len(all_subs)
    print_ok(f"Total number of unique subdomains: {stats['merged']}")
    send_notification(f"🧹 Blending in {project_name} completed. Total unique: {stats['merged']}.")

    # Httpx
    print_step("Validating active subdomains with Httpx...")
    if stats['merged'] > 0:
        run_command(f"cat {final_merged} | httpx -silent -o {final_httpx}")
        stats['alive'] = count_lines(final_httpx)
    else:
        stats['alive'] = 0

    print_ok(f"Subdomains assets (HTTP/HTTPS): {stats['alive']}")

    end_time = time.time()
    elapsed_seconds = int(end_time - start_time)
    minutes, seconds = divmod(elapsed_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    time_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

    send_notification(
        f"🚀 Recon completed for {project_name}!\nAssets (httpx): {stats['alive']}/{stats['merged']}\n⏱️ Total time: {time_str}")


    # Clean up
    print_step("Clearing temporary files.")
    for temp_file in [subfinder_out, assetfinder_out, findomain_out, amass_out]:
        if temp_file.exists():
            temp_file.unlink()
    print_ok("Temporary files removed. Keeping only the clean RAW file and the live HTTPX.")

    # Resume
    print(f"\n{G}{'─' * 46}{RST}")
    print(f"{G}  Summary of the Enumeration › {project_name}{RST}")
    print(f"{G}{'─' * 46}{RST}")
    print(f"  Subfinder:    {stats['subfinder']}")
    print(f"  Assetfinder:  {stats['assetfinder']}")
    print(f"  Findomain:    {stats['findomain']}")
    print(f"  Amass:        {stats['amass']}")
    print(f"{Y}{'─' * 46}{RST}")
    print(f" Total Unique: {C}{stats['merged']}{RST}")
    print(f" Total Assets: {G}{stats['alive']}{RST} (httpx)")
    print(f" Total Time:   {B}{time_str}{RST} ⏱️")
    print(f"{G}{'─' * 46}{RST}\n")

if __name__ == "__main__":
    main()