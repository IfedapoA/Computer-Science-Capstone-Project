"""OPTIONAL demo data for trying the program (fictional people). Safe to run twice; never touches existing students.
    python seed_demo.py          (same as starting the program with  python main.py --demo)
Real use: skip this, start the program and press 'Create advisor account...'.

The demo data itself lives in main.seed_demo(), so there is only one copy to keep up to date."""
import migrate
from main import DEMO_ADVISOR, seed_demo


def seed() -> dict:
    migrate.run()
    return seed_demo()


if __name__ == "__main__":
    print("demo data created for:", list(seed()) or "nothing (already present)")
    print("sign in as", DEMO_ADVISOR[2])
