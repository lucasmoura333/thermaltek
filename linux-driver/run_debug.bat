@echo off
echo ===================================================
echo Nuvoton Driver - Run WSL Debug
echo ===================================================
echo.

:: 1. Create directory
echo [1/4] Creating directory in WSL...
wsl -d Ubuntu -u root -- mkdir -p /tmp/nuvoton-driver

:: 2. Copy files from current directory to WSL
echo [2/4] Copying files to WSL...
:: The '.' in wsl refers to the current Windows directory mounted in /mnt/...
wsl -d Ubuntu -u root -- cp -r ./* /tmp/nuvoton-driver/

:: 3. Fix line endings (Windows CRLF -> Linux LF)
echo [3/4] Fixing line endings...
wsl -d Ubuntu -u root -- bash -c "cd /tmp/nuvoton-driver && sed -i 's/\r$//' setup_wsl.sh && sed -i 's/\r$//' debug_wsl.sh"

:: 4. Run the debug script
echo [4/4] Running debug script...
wsl -d Ubuntu -u root -- bash -c "cd /tmp/nuvoton-driver && chmod +x debug_wsl.sh && ./debug_wsl.sh"

echo.
echo ===================================================
echo DONE
echo ===================================================
pause
