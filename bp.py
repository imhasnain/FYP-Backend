import asyncio
from bleak import BleakClient

ADDRESS = "18:7A:93:12:26:AE"

async def main():
    print(f"Connecting to {ADDRESS}...")
    print("Cuff ABHI mat pehno.\n")

    for attempt in range(1, 6):
        try:
            print(f"Attempt {attempt}...")
            client = BleakClient(
                ADDRESS,
                timeout=60.0,
                winrt=dict(use_cached_services=False)
            )
            await client.connect()
            print("CONNECTED!\n")

            # Saare services aur characteristics print karo
            for service in client.services:
                print(f"Service: {service.uuid}")
                for char in service.characteristics:
                    print(f"  Char: {char.uuid}")
                    print(f"    Properties: {char.properties}")

                    # Notify support karne wale characteristics note karo
                    if "notify" in char.properties or "indicate" in char.properties:
                        print(f"    *** YEH DATA BHEJ SAKTA HAI ***")
                print()

            await client.disconnect()
            return

        except Exception as e:
            print(f"  Failed: {type(e).__name__}: {e}")
            if attempt < 5:
                await asyncio.sleep(2)

    print("\nSab attempts fail. Device ko OFF/ON karo aur phir try karo.")

asyncio.run(main())