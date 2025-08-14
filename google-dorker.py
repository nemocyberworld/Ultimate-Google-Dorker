#!/usr/bin/env python3
"""
Google Dorker — interactive, beginner-friendly upgrade
(Modified to prompt for updating dorks before running)
"""

import argparse
import time
import datetime
import json
import logging
import os
import random
import re
import sys
import time
import subprocess
from typing import List


def print_usage_banner():
    banner = """
𝔾𝕠𝕠𝕘𝕝𝕖 𝔻𝕠𝕣𝕜𝕖𝕣
──────────────────────────────────────────────
   Powered by HackToLive Academy
──────────────────────────────────────────────
A passive Google dork search tool.

How to use:
1. Place your .dorks or .txt files with Google dorks in the ./dorks folder.
2. Run the program:
       python3 google-dorker.py
3. Enter the target domain when prompted (e.g., example.com).
4. Choose a dorks file from the list.
5. Wait while Google Dorker runs searches and saves results.

Default settings:
  - Limit per dork: 100 URLs
  - Save TXT results: ON
  - Delay between dorks: 35s ±10%
  - JSON and TXT output saved in current folder

Respect Google’s Terms of Service and local laws.
For educational and authorized testing only!
──────────────────────────────────────────────
"""
    print(banner)



try:
    import yagooglesearch
except ImportError:
    print("[!] Missing dependency: yagooglesearch. Install with: pip install yagooglesearch")
    sys.exit(1)

try:
    from tqdm import tqdm
except Exception:
    def tqdm(x, *args, **kwargs):
        return x


__version__ = "4.0.1"


def discover_dork_files(search_dir: str = "dorks") -> List[str]:
    files = []
    if os.path.isdir(search_dir):
        for name in sorted(os.listdir(search_dir)):
            path = os.path.join(search_dir, name)
            if os.path.isfile(path) and (name.lower().endswith(".dorks") or name.lower().endswith(".txt")):
                files.append(path)
    return files


def prompt_domain() -> str:
    while True:
        domain = input("Enter target domain (e.g., example.com): ").strip()
        if domain and "." in domain and not domain.startswith("http") and "/" not in domain:
            return domain
        print("Please enter a valid domain like: example.com")


def prompt_dorks_file(candidates: List[str]) -> str:
    if not candidates:
        print("No dorks files found under ./dorks. You can enter a custom path.")
        while True:
            path = input("Path to dorks file: ").strip()
            if os.path.isfile(path):
                return path
            print("File not found. Try again.")

    print("\nAvailable dorks files:")
    for idx, path in enumerate(candidates, start=1):
        print(f"  [{idx}] {path}")
    print("  [0] Enter a custom path")

    while True:
        choice = input("Choose a dorks file number (or 0): ").strip()
        if choice.isdigit():
            n = int(choice)
            if n == 0:
                path = input("Path to dorks file: ").strip()
                if os.path.isfile(path):
                    return path
                print("File not found. Try again.")
            elif 1 <= n <= len(candidates):
                return candidates[n - 1]
        print("Invalid choice. Try again.")


class GoogleDorker:
    # Keep your original GoogleDorker class implementation here
    pass


class SmartFormatter(argparse.HelpFormatter):
    def _split_lines(self, text, width):
        if text.startswith("R|"):
            return text[2:].splitlines()
        return argparse.HelpFormatter._split_lines(self, text, width)


def ask_update_dorks():
    choice = input("Do you want to update the dorks before running? (y/n): ").strip().lower()
    if choice == "y":
        script_path = os.path.join(os.path.dirname(__file__), "update-dorks.py")
        if os.path.isfile(script_path):
            print("[*] Running update-dorks.py...")
            try:
                subprocess.run([sys.executable, script_path], check=True)
                print("[+] Dorks update completed.")
            except subprocess.CalledProcessError as e:
                print(f"[!] Error running update-dorks.py: {e}")
                sys.exit(1)
        else:
            print(f"[!] update-dorks.py not found in {os.path.dirname(__file__)}")
            sys.exit(1)


def main():
    print_usage_banner()
    time.sleep(3)
    ask_update_dorks()

    parser = argparse.ArgumentParser(
        description=f"google-dorker (interactive) v{__version__}",
        formatter_class=SmartFormatter,
    )

    parser.add_argument("-d", "--domain", help="Target domain (e.g., example.com).")
    parser.add_argument("-g", "--google-dorks-file", help="File with Google dorks, one per line.")
    parser.add_argument("-l", "--limit", type=int, default=100, help="Max URLs to return per dork. Default: 100")
    parser.add_argument("-s", "--save-text", dest="save_text", action="store_true", default=True,
                        help="Save plain text results to an auto-named file (default: ON)")
    parser.add_argument("-e", "--exact-delay", type=float, default=35.0,
                        help="Exact base delay between dorks in seconds. Default: 35.0")
    parser.add_argument("-j", "--jitter", type=float, default=1.1,
                        help="Delay jitter factor (>=1.0). Default: 1.1")
    parser.add_argument("-p", "--proxies", type=str, default="",
                        help="Comma-separated proxies")
    parser.add_argument("-k", "--insecure", action="store_true", help="Disable SSL/TLS verification (proxy only)")
    parser.add_argument("--include", nargs="*", default=[], help="Regex patterns to include")
    parser.add_argument("--exclude", nargs="*", default=[], help="Regex patterns to exclude")
    parser.add_argument("-v", "--verbosity", type=int, default=4, help="Verbosity level")
    parser.add_argument("-z", "--log", dest="log_file", default="google_dorker.log", help="Log filename")

    args = parser.parse_args()

    domain = args.domain or prompt_domain()
    dorks_file = args.google_dorks_file or prompt_dorks_file(discover_dork_files("dorks"))

    gd = GoogleDorker(
        google_dorks_file=dorks_file,
        domain=domain,
        limit_per_dork=args.limit,
        save_urls_to_file=args.save_text,
        exact_delay=args.exact_delay,
        jitter=args.jitter,
        proxies=args.proxies,
        insecure=args.insecure,
        verbosity=args.verbosity,
        log_file=args.log_file,
        include_regex=args.include,
        exclude_regex=args.exclude,
    )

    gd.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Interrupted.")
        sys.exit(130)
