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

	status := readBatteryStatus()

	must("enable BLE stack", adapter.Enable())

	// Set the address to the first 6 bytes of the public key.
	adapter.SetRandomAddress(bluetooth.MAC{key[5], key[4], key[3], key[2], key[1], key[0] | 0xC0})

	println("configure advertising...")
	adv := adapter.DefaultAdvertisement()
	must("config adv", adv.Configure(advOptions(key, status)))

	println("start advertising...")
	must("start adv", adv.Start())

	// Re-check the battery periodically. Reconfigure the advertisement only
	// when the level actually changes (rare), so steady-state is just
	// "advertise forever" — no repeated stop/start to destabilize.
	for {
		time.Sleep(2 * time.Minute)
		ns := readBatteryStatus()
		if ns != status {
			status = ns
			adv.Stop()
			adv.Configure(advOptions(key, status))
			adv.Start()
			println("battery status updated:", int(status))
		}
	}
}

// advOptions builds the advertisement options for a given battery status byte.
func advOptions(key []byte, status byte) bluetooth.AdvertisementOptions {
	return bluetooth.AdvertisementOptions{
		AdvertisementType: bluetooth.AdvertisingTypeNonConnInd,
		Interval:          bluetooth.NewDuration(1285000 * time.Microsecond), // 1285ms
		ManufacturerData:  []bluetooth.ManufacturerDataElement{newData(key, status)},
	}
}

// newData builds the FindMy manufacturer data with a live battery-status byte
// (findmy.NewData hardcodes "full"; this lets us report the real level).
func newData(key []byte, status byte) bluetooth.ManufacturerDataElement {
	data := make([]byte, 0, 27)
	data = append(data, findmy.PayloadTypeRegistered, findmy.PayloadLength)
	data = append(data, status)
	data = append(data, key[6:]...) // last 22 bytes of advertising key
	data = append(data, key[0]>>6)  // first two bits of advertising key
	data = append(data, findmy.Hint)
	return bluetooth.ManufacturerDataElement{
		CompanyID: findmy.AppleCompanyID,
		Data:      data,
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
