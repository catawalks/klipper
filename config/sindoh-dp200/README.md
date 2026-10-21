# Sindoh 3DWOX DP200

Copy all three files to `printer_data/config/`:

- `printer.cfg` - the per-printer file: Z endstop, probe offsets, PID values
  and the SAVE_CONFIG block live here.
- `dp200_printer.cfg` - the hardware (UPC MCUs, steppers, heaters, sensors).
- `dp200_macros.cfg` - filament load/unload, nozzle cleaning, the levelling
  probe, bed mesh, lamp.

The MCU firmware and the host-side bridge (upctool) come from the DP200
port project; see https://github.com/catawalks/sindoh
