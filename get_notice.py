# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause-Clear
import subprocess
import re
import requests
import json
import os
os.environ["HOME"] = "/tmp"
def generate_notice_download_and_insert():
    # 1. Get git remote output
    remote_output = subprocess.check_output(["git", "-c", "safe.directory=*", "remote", "-v"], text=True)
    pattern = re.compile(
        r'^\s*\S+\s+(?:'
        r'(?:[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s]+/(?P<project>\S+?))|'
        r'(?:[^@\s]+@[^:\s]+[:/](?:\d+/)?(?P<project_ssh>\S+?))'
        r')\s+\((?:fetch|push)\)\s*$',
        re.MULTILINE
    )

    # 2. Extract project name from remote URL
    match = pattern.search(remote_output)
    if not match:
        raise ValueError("Could not extract project name from git remote.")
    project_name = match.group(1)
    if "@" in remote_output:
        project_name = match.group("project") or match.group("project_ssh")

    # 3. Get tip commit hash
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    # 4. Prepare payload
    payload = {
        "project_name": project_name,
        "revision": revision
    }

    # 5. Make POST request
    url = "https://notice-gen-api-ci.lvprd.oks.drekar.qualcomm.com/generate-notice"
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
    result = response.json()

    if result.get("status") == "success":
        download_link = result.get("download_link")
        if download_link:
            print(f"Downloading NOTICE file from: {download_link}")
            subprocess.run(["wget", "--no-check-certificate", download_link])

            # Detect actual downloaded file (handles _2 or renamed files)
            files = sorted([f for f in os.listdir('.') if os.path.isfile(f)], key=lambda x: os.path.getmtime(x), reverse=True)
            downloaded_file = files[0] if files else None

            if not downloaded_file:
                raise FileNotFoundError("Downloaded file not found.")

            # Read NOTICE content
            with open(downloaded_file, "r", encoding="utf-8", errors="ignore") as nf:
                notice_content = nf.read().strip()

            # Add header and indent each line with a space, replace blank lines with '.'
            header_lines = [
                "________________________________________",
                " NOTICES",
                "________________________________________"
            ]
            formatted_header = "\n".join(" " + line for line in header_lines)

            formatted_notice = "\n".join(
                " " + (line.strip() if line.strip() else ".")  # Replace blank or whitespace-only lines with '.'
                for line in notice_content.splitlines()
            )

            notice_block = f"{formatted_header}\n{formatted_notice}\n\n"

            # Locate debian/copyright
            repo_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
            copyright_path = os.path.join(os.getcwd(), "debian", "copyright")

            if not os.path.exists(copyright_path):
                raise FileNotFoundError(f"debian/copyright file not found at {copyright_path}")

            # Insert before Files: debian/* block
            with open(copyright_path, "r", encoding="utf-8", errors="ignore") as cf:
                original_lines = cf.readlines()

            new_content = []
            inserted = False
            i = 0
            while i < len(original_lines):
                if (not inserted and original_lines[i].strip().startswith("Files:") and
                    i + 1 < len(original_lines) and "debian/*" in original_lines[i + 1]):
                    while new_content and new_content[-1].strip() == "":
                        new_content.pop()  # Remove trailing blank lines
                    new_content.append(notice_block)
                    inserted = True
                new_content.append(original_lines[i])
                i += 1

            # Fallback: append at end if not inserted
            if not inserted:
                new_content.append(notice_block)

            # Write back updated content
            with open(copyright_path, "w", encoding="utf-8") as cf:
                cf.writelines(new_content)

            print("NOTICE inserted before 'Files: debian/*' block in {copyright_path}")
        else:
            print(f"curl -k -X POST '{url}' -H 'Content-Type: application/json' " + " ".join([f"-H '{k}: {v}'" for k,v in headers.items()]) + f" -d '{json.dumps(payload)}'")
            print("Download link not found in response.")
    else:
        return f"Notice generation failed: {result}"

# Example usage:
if __name__ == "__main__":
    print(generate_notice_download_and_insert())
