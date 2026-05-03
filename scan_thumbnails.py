import os
import sys
from collections import Counter

import sqlalchemy as sa

from baselayer.app.env import load_env
from baselayer.app.models import init_db
from skyportal.models import DBSession, Thumbnail

env, cfg = load_env()
init_db(**cfg["database"])

PAGE_SIZE = 5000
MISSING_LOG = "missing_thumbnails.txt"


def main():
    page = 0
    total = 0
    missing = 0
    null_uri = 0
    by_type = Counter()
    missing_by_type = Counter()

    with open(MISSING_LOG, "w") as f:
        f.write("obj_id\ttype\tfile_uri\n")

    while True:
        with DBSession() as session:
            rows = session.execute(
                sa.select(
                    Thumbnail.id, Thumbnail.obj_id, Thumbnail.type, Thumbnail.file_uri
                )
                .order_by(Thumbnail.id)
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            ).all()

        if not rows:
            break

        for _id, obj_id, ttype, file_uri in rows:
            total += 1
            by_type[ttype] += 1

            if file_uri is None:
                null_uri += 1
                continue

            if not os.path.isfile(file_uri):
                missing += 1
                missing_by_type[ttype] += 1
                with open(MISSING_LOG, "a") as f:
                    f.write(f"{obj_id}\t{ttype}\t{file_uri}\n")

        page += 1
        print(
            f"page={page} scanned={total} missing={missing} null_uri={null_uri}",
            flush=True,
        )

    print("\n=== SUMMARY ===")
    print(f"Total thumbnails scanned : {total}")
    print(f"With file_uri = NULL     : {null_uri} (skipped, public_url only)")
    print(f"With file_uri set        : {total - null_uri}")
    print(f"Missing on disk          : {missing}")
    print("\nBy type (total / missing):")
    for ttype in sorted(by_type):
        print(f"  {ttype:<10} {by_type[ttype]:>8} / {missing_by_type.get(ttype, 0):>6}")
    print(f"\nMissing entries written to: {MISSING_LOG}")


if __name__ == "__main__":
    sys.exit(main())
