# Sindoh 3DWOX DP200

This fork carries the Klipper **code** for the DP200:

- `src/upc/`: the MCU port for the Marvell 88PA6170's two UPC cores, and
  the build configs `config/dp200_fm.config` / `config/dp200_io.config`;
- `klippy/extras/upc_stats.py`, `upc_clockcheck.py`, `dp200_cartridge.py`:
  host modules;
- a few changes to shared files (`src/stepper.c`, `src/sched.c`,
  `src/Kconfig`).

The printer **configuration** (`printer.cfg`, `dp200_printer.cfg`,
`dp200_macros.cfg`) is not kept here. Its one home is the port project:
https://github.com/catawalks/sindoh, folder `klipper_port/klipper/config/`.
That project also holds the installer, the host-side bridge (upctool) and
the documentation.

## Branches

| Branch | What it is |
|---|---|
| `master` | Upstream Klipper, unchanged. Synced from Klipper3d/klipper. |
| `sindoh-dp200` | The product branch: what the printers build and run. |
| anything else | A short-lived working branch. It is merged into `sindoh-dp200` and deleted when its work is tested. |

Rules:
- One topic per commit. Start the summary with the module it touches
  (`upc:`, `stepper:`, `config:`, `dp200_cartridge:`), as upstream does.
- No merge commits on `sindoh-dp200`: rebase a working branch onto it.
- Don't copy files between this fork and the port project. If a file has
  to exist in both (`src/upc/upc_hw.h` and `upc_ipc.h` are the port's
  `common/` headers), the port project's check script compares them.
