# ============================================================
# hardware/bp_reader.py — BLE Blood Pressure Machine reader
#
# Uses the standard BLE GATT Blood Pressure Measurement
# characteristic (UUID 0x2A35) — no proprietary SDK needed.
#
# Protocol reference:
#   https://www.bluetooth.com/specifications/gatt/
#   Characteristic: Blood Pressure Measurement (0x2A35)
#
# Byte layout of notification payload:
#   Byte 0:   Flags
#             Bit 0 = 0 → mmHg units, 1 → kPa
#             Bit 2 = 1 → pulse rate field present
#   Bytes 1–2: Systolic  (IEEE-11073 SFLOAT, little-endian)
#   Bytes 3–4: Diastolic (IEEE-11073 SFLOAT, little-endian)
#   Bytes 5–6: MAP       (IEEE-11073 SFLOAT, little-endian)
#   Bytes 7–8: Pulse     (IEEE-11073 SFLOAT, little-endian) — if bit2 set
# ============================================================

import asyncio
import logging
import struct
from typing import Optional, Callable, Dict

from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)

# Standard GATT Blood Pressure Measurement characteristic UUID
BP_MEASUREMENT_UUID = "00002a35-0000-1000-8000-00805f9b34fb"

# Scan timeout in seconds (overridden by config.BLE_SCAN_TIMEOUT at call site)
DEFAULT_SCAN_TIMEOUT = 10


def _sfloat_to_float(raw: int) -> float:
    """
    Convert a 16-bit IEEE-11073 SFLOAT value to a Python float.

    SFLOAT layout:
      Bits 15–12 : signed 4-bit exponent
      Bits  11–0 : signed 12-bit mantissa

    Special values (0x07FF = NaN, 0x0800 = NRes, etc.) return 0.0.
    """
    exponent = raw >> 12
    mantissa = raw & 0x0FFF

    # Sign-extend the 4-bit exponent
    if exponent >= 0x8:
        exponent -= 0x10

    # Sign-extend the 12-bit mantissa
    if mantissa >= 0x800:
        mantissa -= 0x1000

    # Reserved special values
    if mantissa in (0x07FF, 0x0800, 0x07FE, 0x0801, 0x07FD):
        return 0.0

    return mantissa * (10 ** exponent)


def parse_bp_reading(data: bytearray) -> Dict[str, Optional[int]]:
    """
    Parse a raw BLE notification payload from a Blood Pressure cuff
    into human-readable BP values.

    Args:
        data: Raw bytearray received from the GATT notification.

    Returns:
        dict with keys: systolic, diastolic, pulse_rate (all int or None).

    The parser follows the Bluetooth GATT 0x2A35 specification.
    """
    if len(data) < 7:
        logger.warning("BP payload too short (%d bytes); expected at least 7", len(data))
        return {"systolic": None, "diastolic": None, "pulse_rate": None}

    flags = data[0]

    # Bytes 1-2: systolic (little-endian SFLOAT)
    systolic_raw = struct.unpack_from("<H", data, 1)[0]
    # Bytes 3-4: diastolic
    diastolic_raw = struct.unpack_from("<H", data, 3)[0]
    # Bytes 5-6: MAP (mean arterial pressure — not stored but parsed for completeness)
    # map_raw = struct.unpack_from("<H", data, 5)[0]

    systolic = int(_sfloat_to_float(systolic_raw))
    diastolic = int(_sfloat_to_float(diastolic_raw))

    pulse_rate = None
    # Bit 2 of flags indicates whether pulse rate field is present
    if flags & 0x04:
        if len(data) >= 9:
            pulse_raw = struct.unpack_from("<H", data, 7)[0]
            pulse_rate = int(_sfloat_to_float(pulse_raw))

    logger.debug(
        "Parsed BP: systolic=%s mmHg, diastolic=%s mmHg, pulse=%s bpm",
        systolic, diastolic, pulse_rate,
    )
    return {"systolic": systolic, "diastolic": diastolic, "pulse_rate": pulse_rate}


async def find_bp_device(scan_timeout: int = DEFAULT_SCAN_TIMEOUT) -> Optional[str]:
    """
    Scan for nearby BLE devices and return the address of the first
    device whose advertised name contains 'BP', 'Blood', or 'Pressure'
    (case-insensitive).

    Args:
        scan_timeout: How long to scan in seconds.

    Returns:
        BLE address string (e.g. 'AA:BB:CC:DD:EE:FF') or None if not found.
    """
    logger.info("Scanning for BLE BP machine (timeout=%ds)...", scan_timeout)
    devices = await BleakScanner.discover(timeout=scan_timeout)

    keywords = ("bp", "blood", "pressure", "sphygmo")
    for device in devices:
        name = (device.name or "").lower()
        if any(kw in name for kw in keywords):
            logger.info("Found BP device: name=%s, address=%s", device.name, device.address)
            return device.address

    logger.warning("No BP machine found. Available devices:")
    for d in devices:
        logger.warning("  %s — %s", d.address, d.name)
    return None


async def read_bp_once(
    address: str,
    callback: Callable[[Dict[str, Optional[int]]], None],
) -> None:
    """
    Connect to a BLE BP cuff at *address*, subscribe to notifications
    on the Blood Pressure Measurement characteristic, wait for exactly
    one reading, invoke *callback* with the parsed result, then disconnect.

    Args:
        address:  BLE device address returned by find_bp_device().
        callback: Function called with the parsed BP dict.

    Usage:
        result = {}
        def on_reading(data): result.update(data)
        await read_bp_once("AA:BB:CC:DD:EE:FF", on_reading)
        print(result)
    """
    # Event used to signal that we received a complete reading
    reading_received = asyncio.Event()

    def notification_handler(sender: int, data: bytearray) -> None:
        """Called by bleak each time the device sends a notification."""
        parsed = parse_bp_reading(data)
        # Only accept a reading that has valid systolic > 0
        if parsed.get("systolic") and parsed["systolic"] > 0:
            callback(parsed)
            reading_received.set()

    async with BleakClient(address) as client:
        logger.info("Connected to BP device at %s", address)

        await client.start_notify(BP_MEASUREMENT_UUID, notification_handler)
        logger.info("Subscribed to BP notifications. Waiting for measurement...")

        # Wait up to 60 seconds for the user to squeeze the cuff
        try:
            await asyncio.wait_for(reading_received.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.error("Timed out waiting for BP reading after 60 seconds.")
        finally:
            await client.stop_notify(BP_MEASUREMENT_UUID)

    logger.info("Disconnected from BP device.")


async def discover_device_uuids(address: str) -> None:
    """
    Debugging helper — connect to a BLE device and print all
    services and characteristic UUIDs.

    Useful when testing with an unknown BP machine to find the
    correct measurement characteristic UUID.

    Usage:
        import asyncio
        asyncio.run(discover_device_uuids("AA:BB:CC:DD:EE:FF"))
    """
    async with BleakClient(address) as client:
        print(f"\n=== Services on {address} ===")
        for service in client.services:
            print(f"\nService: {service.uuid}  —  {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  Char: {char.uuid}  [{props}]  —  {char.description}")


# ── Quick test ────────────────────────────────────────────
if __name__ == "__main__":
    async def _test():
        addr = await find_bp_device()
        if addr:
            print(f"Found device: {addr}")
            await discover_device_uuids(addr)
        else:
            print("No BP device found. Make sure it is powered on and in pairing/measurement mode.")

    asyncio.run(_test())
