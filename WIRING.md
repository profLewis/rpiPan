# rpiPan Wiring Diagram

Wiring for the `mux_touch` input mode: digital GPIO pins for touch detection,
analog multiplexer (CD74HC4067) for velocity-sensitive strike intensity.

## Pico Connections

```
                        Raspberry Pi Pico
                    ┌─────────────────────┐
                    │                     │
              3.3V ─┤VBUS            GP18 ├──── 1K ───┬─── Speaker/Amp (+)
                    │                     │            │
               GND ─┤GND             GND ├────────┐  100nF
                    │                     │        │   │
                    │  DIGITAL TRIGGERS   │        │  GND
                    │  (touch detect)     │        │
         Pad 0 ──> ┤GP0              GP26 ├─── SIG │  (ADC from mux)
         Pad 1 ──> ┤GP1                  │        │
         Pad 2 ──> ┤GP2                  │        │
                    │                     │        │
                    │  MUX SELECT         │        │
                    │  (channel address)  │        │
            S0 <── ┤GP10                 │        │
            S1 <── ┤GP11                 │        │
            S2 <── ┤GP12                 │        │
            S3 <── ┤GP13                 │        │
                    │                     │        │
                    │              3.3V   ├──┐     │
                    │               GND   ├──┼─┐   │
                    └─────────────────────┘  │ │   │
                                             │ │   │
                  ┌──────────────────────────┘ │   │
                  │  ┌─────────────────────────┘   │
                  │  │                             │
                  │  │   CD74HC4067 (16-ch mux)    │
                  │  │  ┌───────────────────┐      │
                  │  ├──┤ GND          VCC  ├──┐   │
                  │  │  │                   │  │   │
                  │  ├──┤ EN (low=on)  SIG  ├──┼───┘
                  │  │  │                   │  │
                  │  │  │  S0  S1  S2  S3   │  │
                  │  │  └──┬───┬───┬───┬────┘  │
                  │  │     │   │   │   │       │
                  │  │     │   │   │   │    3.3V
                  │  │   GP10 GP11 GP12 GP13
                  │  │
                  │ GND
                  │
                3.3V
```

## Per-Pad Wiring

Each pad has a conductive touch surface (digital trigger) and an FSR
underneath (analog velocity). Repeat for each note.

```
              3.3V                 GND
               │                   │
              [FSR]          ┌─────┴─────┐
               │             │ Conductive │
               ├─── [10K] ──┤  Surface   │
               │         GND│ (top layer)│
               │             └─────┬─────┘
               │                   │
          MUX Ch N              Pico GPn
       (analog velocity)    (digital trigger)
```

**Digital trigger**: The conductive pad surface is tied to GND. When you
touch it, the GPIO (with internal pull-up) gets pulled LOW, triggering
`note_on`. This gives instant detection.

**Analog velocity**: The FSR sits in a voltage divider
(3.3V → FSR → junction → 10K → GND). Harder strikes compress the FSR,
lowering its resistance, producing higher voltage at the junction. The mux
routes this to GP26 (ADC) for the velocity reading.

### Pad Assignments

| Pad | GPIO (digital) | MUX Channel | Note |
|-----|---------------|-------------|------|
| 0   | GP0           | C0          | C4   |
| 1   | GP1           | C1          | D4   |
| 2   | GP2           | C2          | E4   |
| ... | ...           | ...         | ...  |
| 15  | GP15          | C15         | ...  |

## Multiplexer

The CD74HC4067 is a 16-channel analog multiplexer. GP10-GP13 set the binary
channel address (4 pins = 16 channels). When a touch is detected on a GPIO
pin, the code sets the mux select pins to that pad's channel, reads GP26,
and maps the voltage to MIDI velocity 1-127.

- **EN** (enable): tie to GND (always on)
- **VCC**: 3.3V
- **GND**: GND
- **SIG**: → GP26 (Pico ADC input)
- **S0-S3**: → GP10-GP13 (Pico digital outputs)
- **C0-C15**: ← one per pad's FSR voltage divider output

## Audio Output

```
GP18 ─── [1K] ───┬─── Speaker + (or amplifier input)
                  │
               [100nF]   ← RC low-pass filter smooths PWM
                  │
                 GND ─── Speaker - (or amplifier ground)
```

The RC filter (1K + 100nF) smooths the PWM audio output. For better quality,
use a class-D amplifier module (e.g. PAM8403) instead of driving a speaker
directly.

## Tuning

- **10K resistor**: Adjust to match your FSR's resistance range. Larger
  values increase sensitivity to light touches. Start with 10K and tune.
- **Settle time**: The code waits 1ms after switching the mux channel before
  reading. Increase if readings are noisy.
- **Velocity range**: ADC maps 0-3.3V linearly to velocity 1-127. The
  `(vel/127)^0.7` curve in the player gives natural-feeling dynamics.
