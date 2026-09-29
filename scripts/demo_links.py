"""Print scoped synthetic portal links for local operator walkthroughs."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from apps.api.database import SessionLocal
from apps.api.models import Onboarding
from apps.api.services import detail


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", default="")
    args = parser.parse_args()
    with SessionLocal() as db:
        for onboarding in db.scalars(select(Onboarding).order_by(Onboarding.created_at)).all():
            if args.client.casefold() not in onboarding.client.name.casefold():
                continue
            link = detail(db, onboarding)["onboarding"].get("portal_link")
            if link:
                print(f"{onboarding.client.name}\t{onboarding.status}\t{onboarding.id}\t{link}")


if __name__ == "__main__":
    main()
