//go:build tinygo

package main

import "machine"

// AdvertisingKey is the public key of the device. Must be base64 encoded.
var AdvertisingKey string

var (
	battADC   machine.ADC
	battReady bool
)

// initBattery wires up the XIAO nRF52840 battery-sense path:
//   P0.14 (VBAT_ENABLE) driven LOW connects the on-board divider,
//   P0.31 (AIN7) reads the divided battery voltage.
func initBattery() {
	en := machine.P0_14
	en.Configure(machine.PinConfig{Mode: machine.PinOutput})
	en.Low()
	machine.InitADC()
	battADC = machine.ADC{Pin: machine.P0_31}
	battADC.Configure(machine.ADCConfig{})
	battReady = true
}

// readBatteryMV returns the battery voltage in millivolts.
func readBatteryMV() int {
	if !battReady {
		initBattery()
	}
	var sum uint32
	const n = 16
	for i := 0; i < n; i++ {
		sum += uint32(battADC.Get())
	}
	raw := sum / n
	// raw is 16-bit full-scale. 3086 = empirically-calibrated full-scale in mV
	// (a fully-charged 4.2 V cell read raw~30125; TinyGo's SAADC default ref is
	// ~3.0 V, not 3.6 V). 2961 = on-board divider ratio (1M/510k, x2.961).
	return int(raw) * 3086 / 65535 * 2961 / 1000
}

// readBatteryPercent maps voltage to an approximate 0-100% charge.
// LiPo curve approximated as linear 3.30 V (empty) -> 4.20 V (full).
// Prints raw values on USB serial for calibration.
func readBatteryPercent() int {
	mv := readBatteryMV()
	pct := (mv - 3300) * 100 / (4200 - 3300)
	if pct < 0 {
		pct = 0
	}
	if pct > 100 {
		pct = 100
	}
	println("batt mv", mv, "pct", pct)
	return pct
}
