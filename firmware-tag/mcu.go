//go:build tinygo

package main

import (
	"machine"

	"github.com/hybridgroup/go-haystack/lib/findmy"
)

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

// readBatteryStatus reads the battery voltage and maps it to a FindMy
// battery-status byte. Serial prints let us calibrate on USB.
func readBatteryStatus() byte {
	if !battReady {
		initBattery()
	}
	var sum uint32
	const n = 16
	for i := 0; i < n; i++ {
		sum += uint32(battADC.Get())
	}
	raw := sum / n
	// TinyGo nRF52 SAADC: Get() is 16-bit, full-scale 3.6 V (internal 0.6 V
	// ref, gain 1/6). On-board divider ratio ~2.961 (1M / 510k).
	mv := int(raw) * 3600 / 65535 * 2961 / 1000
	println("batt raw", int(raw), "vbat_mV", mv)
	switch {
	case mv >= 3900:
		return findmy.StatusBatteryFull
	case mv >= 3700:
		return findmy.StatusBatteryMedium
	case mv >= 3500:
		return findmy.StatusBatteryLow
	default:
		return findmy.StatusBatteryCritical
	}
}
