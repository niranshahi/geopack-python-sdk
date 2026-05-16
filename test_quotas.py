"""
Live integration test: GET /api/quotas/me/summary

Usage:
  Set GEOPACK_API_URL, GEOPACK_USERNAME, GEOPACK_PASSWORD in .env
  python test_quotas.py
"""
import os
import sys

from dotenv import load_dotenv

from geopack_sdk import GeopackClient

load_dotenv()


def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")

    print("--- Geopack SDK Quota Summary Test ---")
    print(f"Target API: {api_url}")

    try:
        client = GeopackClient(base_url=api_url)

        print("\n[1/2] Logging in...")
        client.auth.login(username=username, password=password)
        print("[OK] Login successful!")

        print("\n[2/2] Fetching quota summary (GET /quotas/me/summary)...")
        summary = client.quotas.my_summary()

        print(f"[OK] Quotas enabled: {summary.enabled}")
        if summary.reason:
            print(f"     reason: {summary.reason}")

        if summary.plan:
            print(
                f"[OK] Plan: {summary.plan.displayName} "
                f"(code={summary.plan.code}, id={summary.plan.id})"
            )
        else:
            print("[!] No plan assigned.")

        if not summary.limits:
            print("[!] No limit rows returned.")
        else:
            print(f"[OK] {len(summary.limits)} limit(s):")
            for row in summary.limits:
                name = (
                    row.dimension.get("displayName")
                    if row.dimension
                    else row.dimensionKey
                )
                remaining = row.remaining
                used = row.percentageUsed
                print(
                    f"  - {row.dimensionKey} ({name}): "
                    f"{row.currentValue}/{row.limitValue} "
                    f"(remaining={remaining}, used={used:.1f}% "
                    if used is not None
                    else f"(remaining={remaining}) "
                )

        wf_key = os.getenv("TEST_QUOTA_DIMENSION", "workflow.count.runs.daily")
        if client.quotas.is_over_limit(wf_key, summary=summary):
            print(f"[WARN] Over limit for dimension: {wf_key}")
        else:
            rem = client.quotas.remaining_for(wf_key, summary=summary)
            print(f"[OK] {wf_key}: remaining={rem}")

        warned = client.quotas.warn_limits(summary=summary)
        if warned:
            print(f"[WARN] {len(warned)} dimension(s) at/above warn threshold:")
            for row in warned:
                print(f"  - {row.dimensionKey}: {row.percentageUsed}%")

        print("\n--- Quota Test Completed Successfully ---")

    except Exception as e:
        print(f"\n[ERROR] Test Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
