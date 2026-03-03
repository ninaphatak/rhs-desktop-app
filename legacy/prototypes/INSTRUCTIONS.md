# RHS Serial Reader — Setup & Run Guide

Follow these steps to record sensor data from the Right Heart Simulator on your laptop.

---

## What You Need

- Your laptop (Windows or macOS)
- The Arduino plugged into your laptop via USB
- The files from the zip: `serial_reader.py`, `requirements_serial.txt`

> **You do not need Arduino IDE.** The firmware is already loaded onto the Arduino — it runs automatically as soon as you plug it in. Arduino IDE is only needed if the firmware ever needs to be re-flashed, which you don't need to worry about.

---

## Step 1: Install Miniconda

Miniconda gives you Python and the `conda` tool for managing environments.

**Windows**
1. Go to https://docs.conda.io/en/latest/miniconda.html
2. Download the **Windows 64-bit** installer (`.exe`)
3. Run the installer — accept the defaults
4. After install, open **Anaconda Prompt** from the Start menu (search "Anaconda Prompt")

**macOS — Apple Silicon (M1/M2/M3)**
1. Go to https://docs.conda.io/en/latest/miniconda.html
2. Download **Miniconda3 macOS Apple Silicon 64-bit pkg**
3. Open the `.pkg` and follow the installer
4. After install, open **Terminal** (Cmd + Space, type "Terminal")

**macOS — Intel**
1. Go to https://docs.conda.io/en/latest/miniconda.html
2. Download **Miniconda3 macOS Intel x86 64-bit pkg**
3. Open the `.pkg` and follow the installer
4. After install, open **Terminal** (Cmd + Space, type "Terminal")

> You only need to install Miniconda once. Skip this step on future runs.

---

## Step 2: Unzip and Locate the Files

1. Unzip the folder you received somewhere easy to find (e.g. your Desktop)
2. You should see:
   ```
   serial_reader.py
   requirements_serial.txt
   ```

**Open a terminal in that folder:**

- **Windows:** In the Anaconda Prompt, type `cd ` (with a space), then drag the folder into the window and press Enter
- **macOS:** In Terminal, type `cd ` (with a space), then drag the folder into the window and press Enter

Confirm you're in the right place by running:
```bash
ls
```
You should see `serial_reader.py` and `requirements_serial.txt` listed.

---

## Step 3: Create the Conda Environment

ADD MORE INSTRUCTIONS FOR INSTALLING CONDA ON WINDOWS OR MAC

Run these commands one at a time, pressing Enter after each:

```bash
conda create -n rhs python=3.11
```
When prompted `Proceed ([y]/n)?`, press Enter (or type `y`).

```bash
conda activate rhs
```

```bash
pip install -r requirements_serial.txt
```

This installs all required packages. It may take a minute or two.

> You only need to do this once. On future runs, just activate the environment with `conda activate rhs`.

---

## Step 4: Connect the Arduino

Plug the Arduino into your laptop via USB **before** running the script. The script auto-detects the port.

---

## Step 5: Run the Script

Make sure the `rhs` environment is active (you'll see `(rhs)` at the start of your prompt), then run:

```bash
python serial_reader.py
```

The script will ask:
```
Valve type? Enter 'silicone' or 'tpu':
```
Type `silicone` or `tpu` and press Enter.

A live plot window will open showing pressure, flow rate, and heart rate in real time. Data is saved automatically to CSV as the session runs.

**To stop:** Close the plot window. The CSV is saved automatically.

---

## Step 6: Find Your Data

After closing the window, look for an `outputs/` folder in the same directory as `serial_reader.py`.

Your CSV file will be named like:
```
silicone_18022026_1.csv
silicone_18022026_2.csv   ← if you ran it again the same day
tpu_18022026_1.csv
```

Format: `{valve type}_{date as DDMMYYYY}_{run number}.csv`

The CSV contains columns: `Time (s)`, `Pressure 1 (mmHg)`, `Pressure 2 (mmHg)`, `Flow Rate (mL/s)`, `Heart Rate (BPM)`.

---

## Troubleshooting

**"No compatible serial port found" / Arduino not detected**
- Make sure the Arduino is plugged in via USB before running the script
- Try unplugging and replugging the USB cable
- On Windows: open Device Manager and look under "Ports (COM & LPT)" to confirm it appears
- On macOS: run `ls /dev/cu.*` in Terminal — you should see something like `/dev/cu.usbmodem*`

**"conda: command not found" or "conda is not recognized"**
- Close and reopen your terminal after installing Miniconda
- On Windows, make sure you're using **Anaconda Prompt**, not plain Command Prompt or PowerShell

**"ModuleNotFoundError" when running the script**
- Make sure you've activated the environment: `conda activate rhs`
- If it still fails, re-run `pip install -r requirements_serial.txt`

**Plot window is blank / no data appearing**
- Check that the Arduino is sending data (its TX LED should be blinking)
- Try closing and restarting the script

**Permission error on macOS when accessing the serial port**
- Open System Settings → Privacy & Security → Serial (or USB Accessories) and allow Terminal access
