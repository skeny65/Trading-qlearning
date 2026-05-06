import subprocess
import os

os.chdir(r'c:\Users\kenyb\Desktop\GEMINI\Trading-qlearning\Trading-qlearning')
result = subprocess.run([r'python', 'oneliner_setup.py'], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
print("Return code:", result.returncode)
