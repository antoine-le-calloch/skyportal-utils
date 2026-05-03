import os
import sys
import time
import requests

from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

INSTANCE_NAME = os.environ.get("INSTANCE_NAME")
INSTANCE_URL = os.environ.get("INSTANCE_URL", "").rstrip("/")
INSTANCE_TOKEN = os.environ.get("INSTANCE_TOKEN")

INPUT_FILE = "missing_thumbnails.txt"
NOT_ON_INSTANCE_LOG = f"sources_not_on_{INSTANCE_NAME}.txt"
ON_INSTANCE_LOG = f"sources_on_{INSTANCE_NAME}.txt"
WORKERS = 4
TIMEOUT = 30
THROTTLE = 0.1  # seconds between requests, per worker
MAX_RETRIES = 5


def check(obj_id: str) -> tuple[str, str]:
    """Returns (obj_id, result) where result is "yes", "no", or "error:<reason>"."""
    headers = {"Authorization": f"token {INSTANCE_TOKEN}"}
    backoff = 1.0
    last_err = ""
    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(
                f"{INSTANCE_URL}/api/source_exists/{obj_id}",
                headers=headers,
                timeout=TIMEOUT,
                allow_redirects=False,
            )
        except requests.exceptions.RequestException as e:
            time.sleep(backoff)
            backoff *= 2
            last_err = f"network:{type(e).__name__}"
            continue

        if r.status_code == 429:
            retry_after = float(r.headers.get("Retry-After", backoff))
            time.sleep(retry_after)
            backoff *= 2
            last_err = "429"
            continue
        time.sleep(THROTTLE)
        if r.status_code != 200:
            return obj_id, f"error:http{r.status_code}"
        try:
            payload = r.json()
        except ValueError:
            return obj_id, "error:bad_json"
        exists = payload.get("data", {}).get("source_exists")
        if exists is True:
            return obj_id, "yes"
        if exists is False:
            return obj_id, "no"
        return obj_id, f"error:unexpected_payload"
    return obj_id, f"error:retries_exhausted({last_err})"


def main():
    if not INSTANCE_URL or not INSTANCE_NAME:
        print("ERROR: set INSTANCE_URL/INSTANCE_NAME env vars", file=sys.stderr)
        return 1
    if not INSTANCE_TOKEN:
        print("ERROR: set INSTANCE_TOKEN env var (/profile page)", file=sys.stderr)
        return 1
    print(f"Checking sources on instance {INSTANCE_NAME} at {INSTANCE_URL}\n")

    obj_ids = set()
    with open(INPUT_FILE) as f:
        next(f)  # skip header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if parts and parts[0]:
                obj_ids.add(parts[0])

    total = len(obj_ids)
    print(f"Unique obj_ids to check: {total}")

    on_instance_ids: list[str] = []
    not_on_instance_ids: list[str] = []
    other: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(check, oid) for oid in obj_ids]
        for i, fut in enumerate(as_completed(futures), 1):
            obj_id, status = fut.result()
            if status == "yes":
                on_instance_ids.append(obj_id)
            elif status == "no":
                not_on_instance_ids.append(obj_id)
            else:
                other.append((obj_id, status))
            if i % 50 == 0 or i == total:
                print(
                    f"  {i}/{total} Available={len(on_instance_ids)} "
                    f"Not available={len(not_on_instance_ids)} other={len(other)}",
                    flush=True,
                )

    with open(NOT_ON_INSTANCE_LOG, "w") as f:
        for oid in sorted(not_on_instance_ids):
            f.write(oid + "\n")
    with open(ON_INSTANCE_LOG, "w") as f:
        for oid in sorted(on_instance_ids):
            f.write(oid + "\n")

    print("\n=== SUMMARY ===")
    print(f"Checked       : {total}")
    print(f"Available     : {len(on_instance_ids)}")
    print(f"Not available : {len(not_on_instance_ids)}")
    print(f"Other/errors  : {len(other)}")
    if other:
        print("  examples:")
        for obj_id, status in other[:10]:
            print(f"    {obj_id} -> {status}")
    print(f"\nWritten: {NOT_ON_INSTANCE_LOG}, {ON_INSTANCE_LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
