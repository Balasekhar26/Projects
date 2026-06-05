# External Project Tools

Universal AI should use these as optional project-aware tools:

- `wifi-csi` -> DEWS Wi-Fi sensing module.
- `animal-meaning` -> Universal Translator animal meaning module.
- `tiny-gpu` -> PCB Doctor HDL lab.
- `kronos-finance` -> Universal AI Finance Brain OHLCV/K-line forecasting reference.

The upstream repositories are usually downloaded under:

```text
<Projects root>\external-projects
```

If the workspace has been cleaned, Universal AI also looks under:

```text
<Projects root>\bin\external-projects
```

Universal AI should read reports and launch approved commands, but the related project must remain usable on its own.
