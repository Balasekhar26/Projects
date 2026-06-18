from __future__ import annotations


MODEL_TIMEOUT_PREFIX = "Local model timed out."


def built_in_answer(user_input: str) -> str | None:
    text = user_input.lower()
    if "embedded" in text or "embeded" in text:
        if any(word in text for word in ("more", "deep", "detail", "advanced", "next layer")):
            return _embedded_systems_deeper_answer()
        return _embedded_systems_answer()
    return None


def is_model_timeout(answer: str | None) -> bool:
    return bool(
        answer
        and (
            answer.startswith(MODEL_TIMEOUT_PREFIX)
            or answer.startswith("The local AI model did not answer quickly enough.")
        )
    )


def _embedded_systems_answer() -> str:
    return (
        "Embedded systems are small computers built inside a product to control one specific job.\n\n"
        "In a normal computer, you open many apps: browser, games, editor, video player. "
        "In an embedded system, the computer is usually hidden inside the device and keeps doing one focused task. "
        "Examples are a washing machine controller, TV remote, bike ECU, smart meter, router, printer, drone flight controller, "
        "medical device, or a sensor node in an IoT system.\n\n"
        "The main parts are:\n"
        "1. Microcontroller or processor: the brain that runs the program.\n"
        "2. Firmware: the code stored inside the chip, usually written in C, C++, Rust, MicroPython, or assembly.\n"
        "3. Inputs: sensors, buttons, switches, camera, microphone, temperature sensor, voltage reading, etc.\n"
        "4. Outputs: motor, relay, display, LED, speaker, heater, valve, or communication signal.\n"
        "5. Communication: UART, I2C, SPI, CAN, USB, Bluetooth, Wi-Fi, Ethernet, or RF.\n"
        "6. Power system: battery, regulator, charger, protection circuit, and power-saving modes.\n\n"
        "A simple example: in a temperature controller, the sensor reads temperature, the microcontroller compares it with the target, "
        "and then turns a fan or heater on/off. That loop repeats again and again.\n\n"
        "The deep idea is this: embedded systems connect software to the physical world. "
        "Code is not just showing text on a screen; it is reading real voltages, timing signals, controlling current, protecting hardware, "
        "and reacting within strict time limits. That is why embedded work needs both programming knowledge and electronics knowledge.\n\n"
        "Important concepts:\n"
        "- Real-time behavior: some actions must happen within microseconds or milliseconds.\n"
        "- Interrupts: the chip can pause normal code to handle urgent events, like a button press or incoming data.\n"
        "- Memory limits: many chips have tiny RAM/Flash compared with PCs.\n"
        "- Reliability: a bug can stop a motor, damage hardware, or create unsafe behavior.\n"
        "- Debugging: you use multimeters, oscilloscopes, logic analyzers, serial logs, JTAG/SWD, and careful measurement.\n\n"
        "So in one sentence: an embedded system is a dedicated computer inside a device that senses, decides, and controls hardware."
    )


def _embedded_systems_deeper_answer() -> str:
    return (
        "Here is the next layer of embedded systems.\n\n"
        "An embedded product is usually designed around a control loop: read inputs, decide, act on outputs, then repeat. "
        "The hard part is making that loop reliable when hardware is noisy, power is limited, and timing matters.\n\n"
        "Important deeper ideas:\n"
        "1. Timing and real time: some work must happen before a deadline. A motor-control signal, UART byte, or sensor sample "
        "can fail if the firmware reacts too late.\n"
        "2. Peripherals: microcontrollers have built-in hardware blocks like ADC, PWM, timers, UART, SPI, I2C, CAN, DMA, watchdogs, "
        "and GPIO interrupts. Good firmware uses these blocks instead of doing everything in a slow main loop.\n"
        "3. Interrupts and concurrency: urgent events interrupt normal code. The firmware must keep interrupt handlers short, share "
        "data safely, and avoid race conditions.\n"
        "4. Memory layout: Flash stores the program, RAM stores live data, EEPROM/FRAM/Flash pages may store settings, and stack/heap "
        "mistakes can crash the device.\n"
        "5. Power behavior: embedded devices often sleep, wake on interrupt, measure battery voltage, reduce clock speed, or shut down "
        "sensors to save energy.\n"
        "6. Hardware protection: firmware must consider brownouts, overcurrent, overheating, wrong polarity, sensor faults, stuck buttons, "
        "and communication loss.\n"
        "7. Debugging method: engineers inspect serial logs, measure pins with a scope or logic analyzer, test edge cases, and reproduce "
        "faults with controlled inputs.\n\n"
        "A simple embedded design process is: define the job, choose the MCU and sensors, design power and interfaces, write a small "
        "firmware loop, test each peripheral, add safety checks, then validate the whole product under real conditions."
    )
