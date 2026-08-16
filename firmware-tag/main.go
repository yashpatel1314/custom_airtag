// Firmware to advertise a FindMy compatible device aka AirTag
// see https://github.com/biemster/FindMy for more information.
//
// To build:
// tinygo flash -target nano-rp2040 -ldflags="-X main.AdvertisingKey='SGVsbG8sIFdvcmxkIQ=='" .
//
// For Linux:
// go run . SGVsbG8sIFdvcmxkIQ==
package main

import (
	"encoding/base64"
	"errors"
	"time"

	"github.com/hybridgroup/go-haystack/lib/findmy"
	"tinygo.org/x/bluetooth"
)

var adapter = bluetooth.DefaultAdapter

func main() {
	// wait for USB serial to be available
	time.Sleep(2 * time.Second)

	key, err := getKeyData()
	if err != nil {
		fail("failed to get key data: " + err.Error())
	}
	println("key is", AdvertisingKey, "(", len(key), "bytes)")

	pct := readBatteryPercent()

	must("enable BLE stack", adapter.Enable())

	// Set the address to the first 6 bytes of the public key.
	adapter.SetRandomAddress(bluetooth.MAC{key[5], key[4], key[3], key[2], key[1], key[0] | 0xC0})

	println("configure advertising...")
	adv := adapter.DefaultAdvertisement()
	must("config adv", adv.Configure(advOptions(key, pct)))

	println("start advertising...")
	must("start adv", adv.Start())
	println("advertising, battery", pct, "%")

	// Brief calibration burst (visible on USB serial) then settle into a slow
	// maintenance loop that only reconfigures when the battery % changes.
	for i := 0; i < 8; i++ {
		time.Sleep(2 * time.Second)
		readBatteryPercent()
	}
	last := pct
	for {
		time.Sleep(2 * time.Minute)
		p := readBatteryPercent()
		if p != last {
			last = p
			adv.Stop()
			adv.Configure(advOptions(key, p))
			adv.Start()
			println("battery updated:", p, "%")
		}
	}
}

// advOptions builds advertisement options for a given battery percentage.
func advOptions(key []byte, pct int) bluetooth.AdvertisementOptions {
	return bluetooth.AdvertisementOptions{
		AdvertisementType: bluetooth.AdvertisingTypeNonConnInd,
		Interval:          bluetooth.NewDuration(1285000 * time.Microsecond), // 1285ms
		ManufacturerData:  []bluetooth.ManufacturerDataElement{newData(key, pct)},
	}
}

// newData builds the FindMy manufacturer data. The status byte carries the
// standard 4-level battery status (Apple-compatible); the trailing hint byte,
// which stock FindMy leaves 0x00, we repurpose to carry a precise 0-100%
// reading for our own listener. (This makes the advert diverge slightly from
// stock OpenHaystack — only relevant if reviving the Apple Find My backend.)
func newData(key []byte, pct int) bluetooth.ManufacturerDataElement {
	data := make([]byte, 0, 27)
	data = append(data, findmy.PayloadTypeRegistered, findmy.PayloadLength)
	data = append(data, statusFromPercent(pct))
	data = append(data, key[6:]...) // last 22 bytes of advertising key
	data = append(data, key[0]>>6)  // first two bits of advertising key
	data = append(data, byte(pct))  // battery percent (stock FindMy: 0x00 hint)
	return bluetooth.ManufacturerDataElement{
		CompanyID: findmy.AppleCompanyID,
		Data:      data,
	}
}

// statusFromPercent maps a battery percentage to a FindMy 4-level status byte.
func statusFromPercent(pct int) byte {
	switch {
	case pct >= 60:
		return findmy.StatusBatteryFull
	case pct >= 35:
		return findmy.StatusBatteryMedium
	case pct >= 15:
		return findmy.StatusBatteryLow
	default:
		return findmy.StatusBatteryCritical
	}
}

// getKeyData returns the public key data from the base64 encoded string.
func getKeyData() ([]byte, error) {
	val, err := base64.StdEncoding.DecodeString(AdvertisingKey)
	if err != nil {
		return nil, err
	}
	if len(val) != 28 {
		return nil, errors.New("public key must be 28 bytes long")
	}

	return val, nil
}

// must calls a function and fails if an error occurs.
func must(action string, err error) {
	if err != nil {
		fail("failed to " + action + ": " + err.Error())
	}
}

// fail prints a message over and over forever.
func fail(msg string) {
	for {
		println(msg)
		time.Sleep(time.Second)
	}
}
