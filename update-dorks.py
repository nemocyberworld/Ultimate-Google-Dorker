#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib3
from collections import OrderedDict
from typing import Dict, Any, List, Optional, Tuple

from bs4 import BeautifulSoup
import requests

__version__ = "1.4.0"  # upgraded

# ------------------------------ UI / Banner ------------------------------

def print_banner(sleep_seconds: float = 2.0) -> None:
    banner = """
𝔾𝕠𝕠𝕘𝕝𝕖 𝔻𝕠𝕣𝕜𝕖𝕣 — Dorks Updater
──────────────────────────────────────────────
   Powered by HackToLive Academy
──────────────────────────────────────────────
"""
    print(banner)
    # Pause so users can read the banner
    time.sleep(max(0.0, sleep_seconds))


# ------------------------------ Helpers ------------------------------

def _safe_filename(name: str) -> str:
    name = (name or "").strip()
    # Replace path separators just in case
    name = name.replace(os.sep, "_").replace("/", "_")
    # Normalize spaces/accents and keep common filename chars
    name = name.lower().replace(" ", "_")
    name = re.sub(r"[^a-z0-9._-]+", "_", name)
    return (name[:120] or "category")

def _ordered_dedupe(items: List[str]) -> List[str]:
    """Preserve order while removing duplicates (case-sensitive)."""
    return list(OrderedDict.fromkeys(items))


# ------------------------------ Core Scraper ------------------------------

def retrieve_google_dorks(
    save_json_response_to_file: bool = False,
    save_all_dorks_to_file: bool = False,
    save_individual_categories_to_files: bool = False,
    outdir: str = "dorks",
    timeout: int = 15,
    insecure: bool = False,
    page_size: int = 1000,
    max_pages: Optional[int] = None,
    user_agent: str = None,
    csv_export: Optional[str] = None,
    quiet: bool = False,
    retry_attempts: int = 3,
    retry_backoff: float = 1.5,
) -> Optional[Dict[str, Any]]:
    """
    Retrieves ALL Google dorks from Exploit-DB GHDB using pagination.
    Returns dict with keys: total_dorks, extracted_dorks, category_dict.

    Improvements:
      - Robust retries with exponential backoff
      - Ordered dedupe for 'extracted_dorks'
      - Optional CSV export (one row per dork with category)
      - Safer, clearer logging; --quiet mode
    """
    os.makedirs(outdir, exist_ok=True)

    base_url = "https://www.exploit-db.com/google-hacking-database"
    if not user_agent:
        user_agent = f"GHDB-Scraper/{__version__} (+https://security-research)"

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "User-Agent": user_agent,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": base_url,
    }

    session = requests.Session()
    session.headers.update(headers)

    extracted_dorks: List[str] = []
    category_dict: Dict[int, Dict[str, Any]] = {}
    total_dorks: Optional[int] = None

    def log(msg: str) -> None:
        if not quiet:
            print(msg)

    def fetch_page(start: int) -> Dict[str, Any]:
        params = {"draw": 1, "start": start, "length": page_size}
        last_err: Optional[BaseException] = None
        for attempt in range(1, retry_attempts + 1):
            try:
                resp = session.get(base_url, params=params, timeout=timeout, verify=not insecure)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.SSLError as e:
                last_err = e
                if not insecure:
                    # If not explicitly allowed insecure, don't retry with verify=False.
                    raise
                requests.packages.urllib3.disable_warnings()
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                try:
                    resp = session.get(base_url, params=params, timeout=timeout, verify=False)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e2:
                    last_err = e2
            except (requests.RequestException, ValueError) as e:
                last_err = e

            # Backoff before next try
            sleep_s = retry_backoff ** (attempt - 1)
            log(f"[!] Fetch attempt {attempt}/{retry_attempts} failed: {last_err}. Backing off {sleep_s:.1f}s...")
            time.sleep(sleep_s)

        # Exhausted retries
        raise RuntimeError(f"Failed to fetch page starting at {start}: {last_err}")

    start = 0
    pages = 0
    while True:
        log(f"[+] Requesting: {base_url}?start={start}&length={page_size}")
        data = fetch_page(start)

        if total_dorks is None:
            # Some endpoints use 'recordsTotal', others 'recordsFiltered'
            total_dorks = int(data.get("recordsTotal") or data.get("recordsFiltered") or 0)
            if total_dorks == 0:
                log("[-] No records reported by server; stopping.")
                break

        rows = data.get("data", [])
        if not rows:
            log("[*] No more rows returned; stopping.")
            break

        for dork in rows:
            title_html = (dork.get("url_title", "") or "").replace("\t", "")
            soup = BeautifulSoup(title_html, "html.parser")
            a = soup.find("a")
            if not a or not a.contents:
                continue

            # Clean text for the actual dork string
            text = str(a.contents[0]).strip()
            if text:
                extracted_dorks.append(text)

            # Category parsing
            cat = dork.get("category", {}) or {}
            try:
                cid = int(cat.get("cat_id", -1))
            except (ValueError, TypeError):
                cid = -1
            cname = cat.get("cat_title", f"category_{cid}") or f"category_{cid}"

            if cid not in category_dict:
                category_dict[cid] = {"category_name": cname, "dorks": []}

            # Save normalized title_html back for later writes
            dork["url_title"] = title_html
            category_dict[cid]["dorks"].append(dork)

        start += len(rows)
        pages += 1
        log(f"[*] Progress: {start}/{total_dorks} (pages fetched: {pages})")

        if max_pages and pages >= max_pages:
            log(f"[*] Reached max_pages={max_pages}; stopping early.")
            break
        if start >= total_dorks:
            break

        time.sleep(0.4)  # small politeness delay

    # Dedupe while preserving order
    extracted_dorks = _ordered_dedupe(extracted_dorks)

    # --- Writes ---
    if save_individual_categories_to_files:
        for cid in sorted(category_dict):
            cname = category_dict[cid]["category_name"]
            fname = _safe_filename(cname) + ".dorks"
            path = os.path.join(outdir, fname)
            log(f"[*] Writing category '{cname}' to {path}")
            with open(path, "w", encoding="utf-8") as fh:
                for d in category_dict[cid]["dorks"]:
                    soup = BeautifulSoup(d["url_title"], "html.parser")
                    a = soup.find("a")
                    if a and a.contents:
                        fh.write(f"{str(a.contents[0]).strip()}\n")

    if save_json_response_to_file:
        # Flatten all rows back into a single list for JSON convenience
        all_rows = []
        for v in category_dict.values():
            all_rows.extend(v["dorks"])
        path = os.path.join(outdir, "all_google_dorks.json")
        log(f"[*] Writing JSON to {path}")
        with open(path, "w", encoding="utf-8") as jf:
            json.dump(all_rows, jf, ensure_ascii=False)

    if save_all_dorks_to_file:
        path = os.path.join(outdir, "all_google_dorks.txt")
        log(f"[*] Writing TXT to {path}")
        with open(path, "w", encoding="utf-8") as fh:
            for d in extracted_dorks:
                fh.write(d + "\n")

    if csv_export:
        # CSV with: dork, category_id, category_name
        csv_path = os.path.join(outdir, csv_export if csv_export.endswith(".csv") else f"{csv_export}.csv")
        log(f"[*] Writing CSV to {csv_path}")
        with open(csv_path, "w", encoding="utf-8", newline="") as cf:
            writer = csv.writer(cf)
            writer.writerow(["dork", "category_id", "category_name"])
            # Build a quick lookup from dork -> (cid, cname) using first occurrence
            dork_to_cat: Dict[str, Tuple[int, str]] = {}
            for cid, cinfo in category_dict.items():
                cname = cinfo["category_name"]
                for d in cinfo["dorks"]:
                    soup = BeautifulSoup(d["url_title"], "html.parser")
                    a = soup.find("a")
                    if a and a.contents:
                        s = str(a.contents[0]).strip()
                        if s and s not in dork_to_cat:
                            dork_to_cat[s] = (cid, cname)
            for d in extracted_dorks:
                cid, cname = dork_to_cat.get(d, (-1, "unknown"))
                writer.writerow([d, cid, cname])

    log(f"[*] Total dorks reported by server: {total_dorks or 0}")
    log(f"[*] Total dorks extracted locally: {len(extracted_dorks)}")

    return {
        "total_dorks": total_dorks or 0,
        "extracted_dorks": extracted_dorks,
        "category_dict": category_dict,
    }


# ------------------------------ CLI ------------------------------

if __name__ == "__main__":
    print_banner(sleep_seconds=3.0)

    categories = {
        1: "Footholds",
        2: "File Containing Usernames",
        3: "Sensitive Directories",
        4: "Web Server Detection",
        5: "Vulnerable Files",
        6: "Vulnerable Servers",
        7: "Error Messages",
        8: "File Containing Juicy Info",
        9: "File Containing Passwords",
        10: "Sensitive Online Shopping Info",
        11: "Network or Vulnerability Data",
        12: "Pages Containing Login Portals",
        13: "Various Online Devices",
        14: "Advisories and Vulnerabilities",
    }

    epilog = f"Dork categories:\n\n{json.dumps(categories, indent=4, ensure_ascii=False)}"

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            f"GHDB Scraper v{__version__} - Retrieve ALL Google Hacking Database dorks "
            "from https://www.exploit-db.com/google-hacking-database."
        ),
        epilog=epilog,
    )

    parser.add_argument("-i", dest="save_individual_categories_to_files",
                        action="store_true", default=False,
                        help="Write the individual dork categories to separate files (*.dorks).")
    parser.add_argument("-j", dest="save_json_response_to_file",
                        action="store_true", default=False,
                        help="Save flattened GHDB JSON to all_google_dorks.json.")
    parser.add_argument("-s", dest="save_all_dorks_to_file",
                        action="store_true", default=False,
                        help="Save all dorks (deduped, ordered) to all_google_dorks.txt.")

    # New knobs / upgrades
    parser.add_argument("--csv", dest="csv_export", default=None,
                        help="Also export dorks to a CSV file (name or path, .csv optional).")
    parser.add_argument("--quiet", action="store_true", default=False,
                        help="Reduce console output.")
    parser.add_argument("--outdir", default="dorks", help="Output directory (default: dorks).")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds (default: 15).")
    parser.add_argument("--page-size", type=int, default=1000, help="Rows per page request (default: 1000).")
    parser.add_argument("--max-pages", type=int, default=None, help="Stop early after N pages (optional).")
    parser.add_argument("--user-agent", default=None, help="Custom User-Agent string.")
    parser.add_argument("--insecure", action="store_true", default=False,
                        help="Disable TLS verification (NOT recommended).")
    parser.add_argument("--retries", type=int, default=3, dest="retry_attempts",
                        help="Max HTTP retry attempts (default: 3).")
    parser.add_argument("--backoff", type=float, default=1.5, dest="retry_backoff",
                        help="Exponential backoff base between retries (default: 1.5).")

    args = parser.parse_args()

    try:
        retrieve_google_dorks(**vars(args))
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)
