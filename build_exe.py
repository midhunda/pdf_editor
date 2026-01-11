import subprocess
import sys
import os

def main():
    script_name = "pdf_editor.py"
    icon_name = "appicon.ico"

    # Ensure files exist
    if not os.path.exists(script_name):
        print(f"Error: {script_name} not found.")
        sys.exit(1)

    if not os.path.exists(icon_name):
        print(f"Error: {icon_name} not found.")
        sys.exit(1)

    command = [
        "pyinstaller",
        "--noconsole",
        "--onefile",
        f"--icon={icon_name}",
        script_name
    ]

    print("Running:", " ".join(command))

    try:
        subprocess.run(command, check=True)
        print("\nBuild completed successfully!")
        print("Check the 'dist' folder for your EXE.")
    except subprocess.CalledProcessError:
        print("\nBuild failed. Please check PyInstaller output.")

if __name__ == "__main__":
    main()
