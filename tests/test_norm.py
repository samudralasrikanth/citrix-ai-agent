import sys
from pathlib import Path
ROOT = Path("/Users/srikanthsamudrala/Documents/legacia/citrix_ai_agent")
sys.path.append(str(ROOT))

from vision.text_normalizer import normalize

def test_normalization():
    cases = [
        ("0K", "ok"),
        ("1ogin", "login"),
        ("| Cancel", "cancel"),
        ("Ye5", "yes"),
        ("  SUBmlt  ", "submit"),
        ("CANCEl", "cancel"),
        ("0kay", "okay"),
        ("conhrm", "confirm"),
        ("rn", "m"), # cluster
    ]
    
    passed = 0
    for inp, expected in cases:
        out = normalize(inp)
        if out == expected:
            print(f"✅ '{inp}' -> '{out}'")
            passed += 1
        else:
            print(f"❌ '{inp}' -> expected '{expected}', got '{out}'")
            
    print(f"\nPassed {passed}/{len(cases)}")

if __name__ == "__main__":
    test_normalization()
