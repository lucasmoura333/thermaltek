@echo off
echo ===================================================
echo Nuvoton Driver - WSL Setup & USB Attach
echo ===================================================
echo.

:: 1. Check for Admin Privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running as Administrator
) else (
    echo [ERROR] Please run this script as Administrator!
    echo Right-click -> Run as Administrator
    pause
    exit
)

:: 2. Copy files to WSL
echo.
echo [1/4] Copying files to WSL...
wsl mkdir -p /tmp/nuvoton-driver
wsl cp -r /mnt/f/helpmeplease/linux-driver/* /tmp/nuvoton-driver/
echo Files copied to /tmp/nuvoton-driver inside WSL

:: 3. Bind USB Device (Force)
echo.
echo [2/4] Binding USB Device (4-17)...
usbipd bind --force -b 4-17
if %errorLevel% neq 0 (
    echo [WARNING] Bind failed or already bound. Continuing...
)

:: 4. Attach USB Device
echo.
echo [3/4] Attaching USB Device to WSL...
usbipd attach --wsl --busid 4-17
if %errorLevel% neq 0 (
    echo [ERROR] Failed to attach device. Make sure WSL is running.
    echo Try running 'wsl' in another window first.
    pause
    exit
)

:: 5. Run Setup Script inside WSL
echo.
echo [4/4] Running Setup Script inside WSL...
wsl -d Ubuntu -u root -- cd /tmp/nuvoton-driver && chmod +x setup_wsl.sh && ./setup_wsl.sh

echo.
echo ===================================================
echo SETUP COMPLETE!
echo ===================================================
echo.
echo To start testing:
echo 1. Open a new terminal
echo 2. Type: wsl
echo 3. Go to folder: cd /tmp/nuvoton-driver
echo 4. Activate venv: source venv/bin/activate
echo 5. Run scripts: python python-lib/test_magic.py
echo.
pause
