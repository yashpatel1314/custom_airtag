//go:build !tinygo

package main

import (
	"os"

	"github.com/hybridgroup/go-haystack/lib/findmy"
)

// AdvertisingKey is the public key of the device. Must be base64 encoded.
var AdvertisingKey = os.Args[1]

// readBatteryStatus is a stub for the host build (no battery hardware).
func readBatteryStatus() byte { return findmy.StatusBatteryFull }
