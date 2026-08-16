//go:build !tinygo

package main

import "os"

// AdvertisingKey is the public key of the device. Must be base64 encoded.
var AdvertisingKey = os.Args[1]

// readBatteryPercent is a stub for the host build (no battery hardware).
func readBatteryPercent() int { return 100 }
