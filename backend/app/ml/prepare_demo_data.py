import argparse
import csv
import random
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = PROJECT_ROOT / "ml_model" / "data" / "demo_urls.csv"


def generate_demo_rows(samples_per_class=300, seed=42):
    randomizer = random.Random(seed)
    benign_hosts = ("portal", "docs", "support", "status", "calendar", "projects")
    benign_paths = ("home", "help/article", "teams/overview", "news", "products", "contact")
    suspicious_terms = ("verify-account", "secure-login", "password-update", "confirm-payment", "wallet-recover")
    rows = []

    for index in range(samples_per_class):
        host = randomizer.choice(benign_hosts)
        path = randomizer.choice(benign_paths)
        query = f"?page={index % 12}" if index % 4 == 0 else ""
        rows.append({"url": f"https://{host}.trusted.example/{path}{query}", "label": 0})

    for index in range(samples_per_class):
        term = randomizer.choice(suspicious_terms)
        if index % 4 == 0:
            url = f"http://192.0.2.{(index % 250) + 1}:8080/{term}?session={index}938472"
        elif index % 4 == 1:
            url = f"http://{term}.customer-check.example/login/account?id={index}884201&confirm=true"
        elif index % 4 == 2:
            url = f"http://xn--secure-{index % 30}.example/{term}/signin?token={index}991827364"
        else:
            url = f"http://account.example@verify-{index}.customer-check.example/{term}?auth={index}"
        rows.append({"url": url, "label": 1})

    randomizer.shuffle(rows)
    return rows


def write_demo_dataset(output_path=DEFAULT_OUTPUT, samples_per_class=300):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_demo_rows(samples_per_class=samples_per_class)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("url", "label"))
        writer.writeheader()
        writer.writerows(rows)
    return output_path, len(rows)


def main():
    parser = argparse.ArgumentParser(description="Generate a non-production synthetic URL dataset.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples-per-class", type=int, default=300)
    args = parser.parse_args()
    path, count = write_demo_dataset(args.output, args.samples_per_class)
    print(f"Wrote {count} synthetic rows to {path}")


if __name__ == "__main__":
    main()
