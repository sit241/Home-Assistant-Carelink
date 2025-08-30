# Medtronic 720G Support (Fork)

⚠️ The main installation and setup instructions are located in the **main branch of the project**.
Please refer to it for how to install and add the integration.

## What this fork provides

* Works specifically with the **Medtronic 720G** pump
* Sends delivered insulin data to Nightscout
* Displays the amount of insulin delivered via the pump
* ❓ Carbohydrate transfer has not been tested yet and may not work (cannot be verified since my wife does not log carbs)

## How to use

1. Clone this fork.
2. Copy the `custom_components/carelink` folder into your Home Assistant under the `custom_components` directory.
3. All other setup steps are identical to the main branch.

## Why this was made

My wife has type 1 diabetes, and I needed a working fork for the Medtronic 720G since the main branch does not support this pump.
The code contains some hacks, but it works. Use it at your own risk.

# Note:
I am aware that in the post-Soviet region and CIS countries the Medtronic 720G pump is still very common and widely issued, while in the US and Western Europe it is considered outdated. I decided to publish this fork because it may be useful for someone, especially for diabetics who are tech-savvy enough to use GitHub and Home Assistant. If you don’t want to deal with Home Assistant setup, I suggest buying a cheap Android phone (30–40 USD), installing xDrip+ and pointing it to Carelink. This works much more reliably, and xDrip+ definitely supports the Medtronic 720G.
