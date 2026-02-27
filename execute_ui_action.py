import json
import time
import pyautogui
from pathlib import Path

def interact_by_index(element_id, action="click", value=None):
    """
    Performs an action on a UI element stored in memory/ui_map.json.
    """
    json_path = Path("memory/ui_map.json")
    if not json_path.exists():
        print("Error: memory/ui_map.json not found. Run observe_ui.py first.")
        return False
        
    with open(json_path, "r") as f:
        data = json.load(f)
        elements = data.get("elements", [])
        
    # Find the element by ID
    target = next((e for e in elements if e["id"] == element_id), None)
    
    if not target:
        print(f"Error: Element ID {element_id} not found in current UI map.")
        return False
        
    sx, sy = target["center_screen"]
    print(f"Action: {action} on Element {element_id} at screen coords ({sx}, {sy})")
    
    pyautogui.moveTo(sx, sy, duration=0.5)
    
    if action == "click":
        pyautogui.click()
    elif action == "type":
        pyautogui.click()
        time.sleep(0.3)
        # Triple click to clear
        pyautogui.click(clicks=3, interval=0.1)
        pyautogui.press('backspace')
        pyautogui.write(value, interval=0.05)
        
    return True

if __name__ == "__main__":
    # EXAMPLE USAGE:
    # Based on your image:
    # Index 3 = Operator ID field
    # Index 5 = Password field
    # Index 22 = OK button
    
    print("--- Executing Script based on UI Map ---")
    
    # 1. Type Operator ID (Change Index 3 to the actual green number you see in the map)
    interact_by_index(3, action="type", value="ADMIN_TEST")
    time.sleep(1)
    
    # 2. Type Password (Change Index 5 to the actual green number you see in the map)
    interact_by_index(5, action="type", value="PASSWORD123")
    time.sleep(1)
    
    # 3. Click OK (Change Index 22 to the actual green number you see in the map)
    # interact_by_index(22, action="click") # Uncomment to click
