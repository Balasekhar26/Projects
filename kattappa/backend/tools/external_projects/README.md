# External Project Tools

Kattappa can use these as optional standalone external tools:

- `wifi-csi` -> Wi-Fi CSI movement and activity sensing reference.
- `animal-meaning` -> Bioacoustic sound classification reference.
- `tiny-gpu` -> SystemVerilog GPU learning and HDL debugging reference.
- `kronos-finance` -> Kattappa Finance Brain OHLCV/K-line forecasting reference.

The upstream repositories are usually downloaded under:

```text
<Projects root>\external-projects
```

If the workspace has been cleaned, Kattappa also looks under:

```text
<Projects root>\bin\external-projects
```

These tools must not make sibling project folders required. Every project must
remain installable and runnable from its own folder.
