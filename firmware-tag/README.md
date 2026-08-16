# Tag firmware (Find My beacon + battery level)

FindMy-compatible BLE beacon for the Seeed XIAO nRF52840, based on
[go-haystack](https://github.com/hybridgroup/go-haystack) with one addition:
it reads the XIAO's battery voltage (P0.14 enable / P0.31 ADC) and reports a
real full/medium/low/critical level in the advertisement's status byte,
instead of the hardcoded "full".

## Build & flash

TinyGo builds this against the go-haystack module, so:

```bash
git clone https://github.com/hybridgroup/go-haystack
cp firmware-tag/*.go go-haystack/firmware/          # our versions
cd go-haystack/firmware
# key comes from findmy/keys/<tag>.keys ("Advertisement key")
tinygo build -target=xiao-ble -o tag.uf2 \
  -ldflags "-X main.AdvertisingKey=<ADV_KEY_BASE64>" .
```

Flash: double-tap the XIAO reset (or 1200-baud touch the USB serial port) to
mount the UF2 bootloader drive, then copy `tag.uf2` onto it.

## Battery calibration

`readBatteryStatus()` in [mcu.go](mcu.go) assumes TinyGo's SAADC full-scale of
3.6 V and the XIAO's 1M/510k divider (~2.961). It prints `batt raw / vbat_mV`
on USB serial. Verified: a charged cell reads "full". If a board reads off,
adjust the `3600` (ADC reference) or `2961` (divider) constants against a
multimeter reading. Thresholds: full ≥3.90 V, medium ≥3.70, low ≥3.50, else critical.
