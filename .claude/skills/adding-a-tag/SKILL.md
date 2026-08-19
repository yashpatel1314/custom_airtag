---
name: adding-a-tag
description: Use when flashing a new tag board, generating tag keys, building the tag firmware, deriving a tag MAC address, or registering a tag in tags.json.
---

# Adding a new tag

**Canonical walkthrough: `docs/adding-a-tag.md`** — follow it. Command
skeleton for orientation:

```bash
haystack keys tag-NN                       # keypair -> move to findmy/keys/ (NEVER commit)
cp firmware-tag/*.go go-haystack/firmware/ # battery-reporting overlay
cd go-haystack/firmware && tinygo build -target=xiao-ble -o tag.uf2 \
  -ldflags "-X main.AdvertisingKey=<ADV_KEY_BASE64>" .
# double-tap XIAO reset -> copy tag.uf2 to the UF2 drive
python tools/mac_from_key.py findmy/keys/tag-NN.keys   # -> MAC
# add MAC -> name in server/tags.json, restart server
python tools/scan_tags.py                  # confirm REGISTERED + battery
```

## Non-obvious constraints

- The MAC comes deterministically from the advertisement key (first 6
  bytes, top two bits set) — never scan-and-guess it; use the tool.
- Skipping the `cp` overlay silently gives stock firmware: tag works but
  battery always reads "full" with no % (shows as `n/a` in scan_tags.py).
- `server/tags.json` is read only at server startup.
- `.keys` files are irreplaceable secrets: gitignored, must be backed up
  off-repo, and needed again to ever reflash or decrypt Find My reports.
