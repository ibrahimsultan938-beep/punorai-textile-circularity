import subprocess
import sys

test_files = [
    "test_punorai_rebrand.py",
    "test_multiobjective_optimizer.py",
    "test_final_demo_fixes.py",
    "test_aggregation_eligibility.py",
    "test_planner_exclusion_audit.py",
    "test_passport_regression.py",
    "test_impact_analytics.py",
]

print("================================================================================")
print("              PUNORAI COMPLETE REGRESSION & VERIFICATION SUITE                  ")
print("================================================================================\n")

all_passed = True
results = {}

for tf in test_files:
    print(f"\n>>> Running {tf}...")
    proc = subprocess.run([sys.executable, tf], capture_output=True, text=True)
    if proc.returncode == 0:
        results[tf] = "PASS"
        print(f"[OK] {tf} PASSED")
    else:
        results[tf] = "FAIL"
        all_passed = False
        print(f"[ERROR] {tf} FAILED:\n{proc.stdout}\n{proc.stderr}")

print("\n================================================================================")
print("                                SUITE SUMMARY                                   ")
print("================================================================================")
for tf, status in results.items():
    print(f"  {tf:<35} : {status}")

if all_passed:
    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")
else:
    print("\n>>> ONE OR MORE TESTS FAILED <<<")
    sys.exit(1)
